"""Reusable end-to-end pipeline.

run_pipeline() takes interviews + functions + an LLM and returns a structured
result dict (raw pain points, ranked and gated canonical use cases with
provenance, totals, stats). Both the CLI (run_demo.py) and the dashboard server
(app.py) call this, so they always show the same numbers.
"""

from __future__ import annotations

from .models import Function, Interview, Organization
from .llm import LLM
from .extract import extract_all, extract_interview
from .dedup import deduplicate
from .savings import aggregate_and_size
from .score import score_portfolio

DEFAULT_PER_SEAT = 8000  # illustrative annual SaaS/vendor spend per employee


def default_org(functions: dict[str, Function]) -> Organization:
    headcount = sum(f.headcount for f in functions.values())
    return Organization(
        company_name="",
        total_headcount=headcount,
        annual_saas_spend=headcount * DEFAULT_PER_SEAT,
        source="manual",
        confidence=1.0,
    )


def _use_case_view(uc, pp_by_id, fn_name) -> dict:
    d = uc.to_dict()
    d["affected_function_names"] = [fn_name.get(f, f) for f in uc.affected_functions]
    d["provenance"] = [
        {
            "pain_id": p.pain_id,
            "interview_id": p.interview_id,
            "function": fn_name.get(p.function_id, p.function_id),
            "title": p.title,
            "description": p.description,
            "minutes": p.time_cost_per_occurrence_min,
            "volume": p.est_annual_volume,
            "match_confidence": p.match_confidence,
        }
        for p in (pp_by_id[pid] for pid in uc.member_pain_ids)
    ]
    return d


def run_pipeline(
    interviews: list[Interview],
    functions: dict[str, Function],
    llm: LLM,
    pp_cache: dict | None = None,
    org: Organization | None = None,
) -> dict:
    """pp_cache: optional {interview_id: [PainPoint]} so already-extracted
    interviews are not re-extracted (extraction is the costly LLM step)."""
    fn_name = {fid: f.name for fid, f in functions.items()}
    if org is None:
        org = default_org(functions)

    if pp_cache is None:
        pain_points = extract_all(interviews, llm)
    else:
        pain_points = []
        for iv in interviews:
            if iv.interview_id not in pp_cache:
                pp_cache[iv.interview_id] = extract_interview(iv, llm)
            pain_points.extend(pp_cache[iv.interview_id])

    use_cases = deduplicate(pain_points, functions, llm)
    aggregate_and_size(use_cases, pain_points, functions, org)
    ranked, gated = score_portfolio(use_cases, pain_points, functions)

    pp_by_id = {p.pain_id: p for p in pain_points}
    merged_away = sum(len(uc.member_pain_ids) for uc in use_cases) - len(use_cases)

    ranked_view = [_use_case_view(uc, pp_by_id, fn_name) for uc in ranked]
    gated_view = [_use_case_view(uc, pp_by_id, fn_name) for uc in gated]

    return {
        "mode": llm.mode,
        "org": org.to_dict(),
        "functions": fn_name,
        "pain_points": [
            {**p.to_dict(), "function_name": fn_name.get(p.function_id, p.function_id)}
            for p in pain_points
        ],
        "ranked": ranked_view,
        "gated": gated_view,
        "totals": {
            "base": sum(uc.est_savings_base for uc in ranked),
            "low": sum(uc.est_savings_low for uc in ranked),
            "high": sum(uc.est_savings_high for uc in ranked),
            "quick_wins": [uc.title for uc in ranked if uc.quadrant == "quick win"],
        },
        "stats": {
            "interviews": len(interviews),
            "functions": len(functions),
            "pain_points": len(pain_points),
            "canonical": len(use_cases),
            "merged_away": merged_away,
            "cross_functional": sum(1 for uc in use_cases if uc.cross_functional),
            "needs_review": sum(1 for uc in use_cases if uc.needs_review),
        },
    }
