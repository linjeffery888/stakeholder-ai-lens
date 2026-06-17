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

import re
from difflib import SequenceMatcher

from .models import PainPoint, UseCase
from .llm import LLM
from .savings import SPEND_LEVERS

AUTO_MERGE = 0.90       # at/above this lexical sim, merge without adjudication
ACCEPT_MERGE = 0.55     # below this adjudication confidence, do not merge
REVIEW_BELOW = 0.75     # merges accepted under this confidence go to review

# The spend lever is sized off ONE organization spend pool, so every
# spend-levered pain belongs to a SINGLE pooled use case. Fragmenting it into
# several use cases produces identical, double-counted dollar figures. We route
# all spend pains into one canonical here (also skips an LLM call).
SPEND_POOL_TITLE = "Vendor & SaaS spend rationalization (pooled)"
SPEND_POOL_DESC = (
    "Pooled opportunity: review and rationalize organization spend (vendors, "
    "SaaS, licenses, contracts) to recover waste and consolidate. Sized once "
    "off the org spend pool, not per pain point, so it is never double counted. "
    "Contributing pains are listed as provenance."
)


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


def deduplicate(pain_points: list[PainPoint], functions: dict, llm: LLM,
                progress=None, cache: dict | None = None) -> list[UseCase]:
    """Cluster pain points into canonical use cases.

    Incremental: if `cache` carries prior state (use_cases, members, counter,
    assigned pain ids), only pain points not already assigned are adjudicated
    against the existing clusters. This is the expensive (LLM) step, so an
    upload of a few interviews costs a few calls instead of re-running all of
    them. Pass cache=None (or empty) for a full from-scratch run.
    """
    if cache is None:
        cache = {}
    use_cases: list[UseCase] = cache.get("use_cases") or []
    members: dict[str, list[PainPoint]] = cache.get("members") or {}
    uc_counter = cache.get("uc_counter", 0)
    assigned = cache.get("assigned")
    if assigned is None:
        assigned = set()
    spend_uc_id = cache.get("spend_uc_id")

    # only adjudicate pain points we have not clustered before
    todo = [pp for pp in pain_points if pp.pain_id not in assigned]
    total = len(todo)
    if progress:
        progress("dedup", 0, total)
    for idx, pp in enumerate(todo, 1):
        # Spend lever -> the single pooled spend use case (no adjudication).
        if pp.ai_lever in SPEND_LEVERS:
            if spend_uc_id is None:
                uc_counter += 1
                spend_uc = UseCase(
                    use_case_id=f"UC-{uc_counter:03d}",
                    title=SPEND_POOL_TITLE,
                    canonical_description=SPEND_POOL_DESC,
                    category=_primary_category(pp),
                    ai_lever=pp.ai_lever,
                    member_pain_ids=[pp.pain_id],
                    affected_functions=[pp.function_id],
                    cross_functional=False,
                )
                use_cases.append(spend_uc)
                members[spend_uc.use_case_id] = [pp]
                spend_uc_id = spend_uc.use_case_id
            else:
                spend_uc = next(u for u in use_cases if u.use_case_id == spend_uc_id)
                members[spend_uc_id].append(pp)
                spend_uc.member_pain_ids.append(pp.pain_id)
                if pp.function_id not in spend_uc.affected_functions:
                    spend_uc.affected_functions.append(pp.function_id)
                spend_uc.cross_functional = len(spend_uc.affected_functions) > 1
            pp.use_case_id = spend_uc_id
            pp.match_confidence = 1.0
            pp.status = "matched"
            assigned.add(pp.pain_id)
            if progress and (idx % 5 == 0 or idx == total):
                progress("dedup", idx, total)
            continue

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

        assigned.add(pp.pain_id)
        if progress and (idx % 5 == 0 or idx == total):
            progress("dedup", idx, total)

    # Second pass: deterministically merge true duplicate use cases the live
    # adjudicator split on wording/function (e.g. four "batch record review"
    # clusters, three "prior auth status" clusters). No LLM calls.
    _consolidate(use_cases, members)

    # prevalence = number of distinct interviews that raised the use case
    for uc in use_cases:
        interviews = {members_pp.interview_id for members_pp in members[uc.use_case_id]}
        uc.prevalence_count = len(interviews)
        uc.reach = len(uc.affected_functions)

    # persist incremental state for the next call
    cache["use_cases"] = use_cases
    cache["members"] = members
    cache["uc_counter"] = uc_counter
    cache["assigned"] = assigned
    cache["spend_uc_id"] = spend_uc_id

    return use_cases


_STOP = {"and", "the", "for", "manual", "manually", "across", "from", "into",
         "with", "of", "to", "a", "in", "per", "each", "review", "tracking"}


def _toks(s: str) -> set:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return {t for t in s.split() if len(t) > 2 and t not in _STOP}


def _overlap(a: set, b: set) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def _is_duplicate(a: UseCase, b: UseCase, rep_a: PainPoint, rep_b: PainPoint) -> bool:
    """True if a and b are the same problem stated differently. Tuned to merge
    genuine duplicates while avoiding the over-merge of distinct work."""
    ta, tb = _toks(a.title), _toks(b.title)
    oc = _overlap(ta, tb)
    ds = SequenceMatcher(None, (rep_a.description or "").lower(),
                         (rep_b.description or "").lower()).ratio()
    ts = SequenceMatcher(None, (a.title or "").lower(), (b.title or "").lower()).ratio()
    if oc >= 0.6:
        return True
    if oc >= 0.45 and ds >= 0.45:
        return True
    if max(ds, ts) >= 0.62:
        return True
    return False


def _consolidate(use_cases: list, members: dict) -> None:
    """Merge duplicate use cases in place. Skips the pooled spend use case."""
    changed = True
    while changed:
        changed = False
        for i in range(len(use_cases)):
            a = use_cases[i]
            if a.ai_lever in SPEND_LEVERS:
                continue
            for j in range(i + 1, len(use_cases)):
                b = use_cases[j]
                if b.ai_lever in SPEND_LEVERS:
                    continue
                if _is_duplicate(a, b, members[a.use_case_id][0], members[b.use_case_id][0]):
                    members[a.use_case_id].extend(members[b.use_case_id])
                    a.member_pain_ids.extend(b.member_pain_ids)
                    for f in b.affected_functions:
                        if f not in a.affected_functions:
                            a.affected_functions.append(f)
                    a.cross_functional = len(a.affected_functions) > 1
                    a.needs_review = a.needs_review or b.needs_review
                    for pp in members[b.use_case_id]:
                        pp.use_case_id = a.use_case_id
                    del members[b.use_case_id]
                    use_cases.pop(j)
                    changed = True
                    break
            if changed:
                break
