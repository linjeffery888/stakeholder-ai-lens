"""Stage 2 + 3: extract raw pain points from interviews and tag onto taxonomy.

Extraction asks the LLM for one structured record per distinct problem.
Tagging is done in the same call (the taxonomy is supplied in the prompt), so
the model picks from fixed lists rather than inventing labels. We validate the
tags against the taxonomy here and flag anything off-list for review.
"""

from __future__ import annotations

from .models import Interview, PainPoint
from .taxonomy import CATEGORIES, LEVERS
from .llm import LLM


def _coerce_enum(value: str, allowed: list, default: str) -> str:
    return value if value in allowed else default


def extract_interview(interview: Interview, llm: LLM) -> list[PainPoint]:
    taxonomy = {"categories": CATEGORIES, "levers": LEVERS}
    raw = llm.extract_pain_points(
        {
            "interview_id": interview.interview_id,
            "function_id": interview.function_id,
            "raw_notes": interview.raw_notes,
        },
        taxonomy,
    )
    points: list[PainPoint] = []
    for i, rec in enumerate(raw, start=1):
        pain_id = f"{interview.interview_id}-P{i}"
        tags = [t for t in rec.get("category_tags", []) if t in CATEGORIES]
        needs_review = not tags or rec.get("ai_lever") not in LEVERS
        pp = PainPoint(
            pain_id=pain_id,
            interview_id=interview.interview_id,
            function_id=interview.function_id,
            description=rec.get("description", "").strip(),
            title=rec.get("title", "").strip(),
            workflow=rec.get("workflow", "").strip(),
            time_cost_per_occurrence_min=float(rec.get("time_cost_per_occurrence_min", 0) or 0),
            est_annual_volume=float(rec.get("est_annual_volume", 0) or 0),
            severity=_coerce_enum(rec.get("severity", "med"), ["low", "med", "high"], "med"),
            ai_addressability=_coerce_enum(
                rec.get("ai_addressability", "med"), ["low", "med", "high"], "med"
            ),
            category_tags=tags or ["manual data entry"],
            ai_lever=_coerce_enum(rec.get("ai_lever", ""), LEVERS, "extraction and structuring"),
            status="needs_review" if needs_review else "tagged",
        )
        points.append(pp)
    return points


def extract_all(interviews: list[Interview], llm: LLM) -> list[PainPoint]:
    out: list[PainPoint] = []
    for iv in interviews:
        out.extend(extract_interview(iv, llm))
    return out
