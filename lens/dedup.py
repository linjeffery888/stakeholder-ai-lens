"""Stage 4: deduplicate and resolve overlap.

Collapse raw pain points into canonical use cases. Cascade:

  1. Taxonomy pre-filter  -> only compare points sharing a (category, lever).
  2. Lexical similarity    -> cheap stand-in for embeddings + cosine.
                              sim >= AUTO_MERGE: merge without asking.
  3. LLM adjudication      -> for everything below the auto threshold, ask the
                              model (or mock heuristic): same underlying problem?
  4. Human review queue    -> low-confidence merges are flagged, never silently
                              merged.

Cross-function pain points that merge set cross_functional = True and list
every function. Savings later aggregate on this de-duplicated scope, so the
same problem raised twice is counted once.

Production note: step 2 uses difflib (lexical) as a portable stand-in. The real
system embeds descriptions and uses cosine similarity, which catches semantic
matches across different wording. The 0.75-0.90 adjudication band in the design
doc is tuned for embeddings; here everything below AUTO_MERGE goes to step 3.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from .models import PainPoint, UseCase
from .llm import LLM

AUTO_MERGE = 0.90       # at/above this lexical sim, merge without adjudication
ACCEPT_MERGE = 0.55     # below this adjudication confidence, do not merge
REVIEW_BELOW = 0.75     # merges accepted under this confidence go to review


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _primary_category(pp: PainPoint) -> str:
    return pp.category_tags[0] if pp.category_tags else "manual data entry"


def _candidate_rank(pp: PainPoint, uc: UseCase, rep: PainPoint) -> float:
    """Soft pre-rank score: taxonomy overlap plus lexical similarity. Used only
    to order/shortlist candidates for adjudication, never to exclude them."""
    score = _sim(pp.description, rep.description)
    if _primary_category(pp) == uc.category:
        score += 0.5
    if pp.ai_lever == uc.ai_lever:
        score += 0.5
    return score


def deduplicate(pain_points: list[PainPoint], functions: dict, llm: LLM) -> list[UseCase]:
    use_cases: list[UseCase] = []
    members: dict[str, list[PainPoint]] = {}
    uc_counter = 0

    for pp in pain_points:
        best_uc, best_conf, best_reason = None, 0.0, ""

        # Step 2: cheap lexical auto-merge for near-identical wording.
        for uc in use_cases:
            rep = members[uc.use_case_id][0]
            if _sim(pp.description, rep.description) >= AUTO_MERGE:
                best_uc, best_conf, best_reason = uc, 0.95, "auto-merge (high similarity)"
                break

        # Step 1 + 3: pre-rank candidates by taxonomy overlap (a soft signal,
        # NOT a hard gate, so inconsistent tagging cannot hide a true overlap),
        # then let the model pick the same underlying problem. At scale this
        # pre-rank is an embeddings + cosine shortlist.
        if best_uc is None and use_cases:
            # Step 1 pre-filter: shortlist canonicals that share a category OR a
            # lever (looser than exact match, so minor tagging drift cannot hide
            # a true overlap, but tight enough that unrelated work is never
            # compared). Step 3: the model adjudicates within the shortlist. At
            # scale the shortlist is an embeddings + cosine top-K.
            pool = [uc for uc in use_cases
                    if uc.category == _primary_category(pp) or uc.ai_lever == pp.ai_lever]
            ranked = sorted(
                pool,
                key=lambda uc: _candidate_rank(pp, uc, members[uc.use_case_id][0]),
                reverse=True,
            )
            cands = [{"id": uc.use_case_id, "desc": members[uc.use_case_id][0].description}
                     for uc in ranked[:8]]
            verdict = llm.best_match(pp.description, cands)
            conf = verdict.get("confidence", 0.0)
            if verdict.get("match_id") and conf >= ACCEPT_MERGE:
                best_uc = next((u for u in use_cases if u.use_case_id == verdict["match_id"]), None)
                best_conf = conf
                best_reason = verdict.get("reason", "adjudicated match")

        if best_uc is not None:
            # merge
            pp.use_case_id = best_uc.use_case_id
            pp.match_confidence = round(best_conf, 2)
            pp.status = "matched"
            members[best_uc.use_case_id].append(pp)
            best_uc.member_pain_ids.append(pp.pain_id)
            if pp.function_id not in best_uc.affected_functions:
                best_uc.affected_functions.append(pp.function_id)
            best_uc.cross_functional = len(best_uc.affected_functions) > 1
            # Step 4: low-confidence merges go to review
            if best_conf < REVIEW_BELOW:
                best_uc.needs_review = True
                best_uc.review_reasons.append(
                    f"merged {pp.pain_id} at confidence {best_conf:.2f}"
                )
        else:
            # spawn a new canonical use case
            uc_counter += 1
            uc = UseCase(
                use_case_id=f"UC-{uc_counter:03d}",
                title=pp.title or pp.workflow or pp.description[:48],
                canonical_description=pp.description,
                category=_primary_category(pp),
                ai_lever=pp.ai_lever,
                member_pain_ids=[pp.pain_id],
                affected_functions=[pp.function_id],
                cross_functional=False,
            )
            pp.use_case_id = uc.use_case_id
            pp.match_confidence = 1.0
            pp.status = "matched"
            use_cases.append(uc)
            members[uc.use_case_id] = [pp]

    # prevalence = number of distinct interviews that raised the use case
    for uc in use_cases:
        interviews = {members_pp.interview_id for members_pp in members[uc.use_case_id]}
        uc.prevalence_count = len(interviews)
        uc.reach = len(uc.affected_functions)

    return use_cases
