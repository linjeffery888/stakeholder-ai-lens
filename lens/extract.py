"""Stage 2 + 3: extract raw pain points from interviews and tag onto taxonomy.

Extraction asks the LLM for one structured record per distinct problem.
Tagging is done in the same call (the taxonomy is supplied in the prompt), so
the model picks from fixed lists rather than inventing labels. We validate the
tags against the taxonomy here and flag anything off-list for review.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import Interview, PainPoint
from .taxonomy import CATEGORIES, LEVERS
from .llm import LLM

# Extraction is independent per interview, so run several Claude calls at once.
# Bounded so we stay well under API rate limits. Override with LENS_MAX_WORKERS.
MAX_WORKERS = int(os.environ.get("LENS_MAX_WORKERS", "8"))


def _coerce_enum(value: str, allowed: list, default: str) -> str:
    return value if value in allowed else default


# A single human task type rarely recurs more than ~5,000x/yr (~20/workday),
# and one extracted pain should not imply more than a few FTE of effort.
MAX_VOLUME = 5000.0
MAX_HOURS_YEAR = 6000.0   # ~3 FTE on one task; above this is an extraction error


def _clamp_volume(minutes: float, volume: float) -> float:
    """Cap implausible annual volumes so an LLM mis-read (e.g. 7,200 month-end
    reconciliations/yr) cannot inflate savings."""
    volume = min(max(volume, 0.0), MAX_VOLUME)
    if minutes > 0:
        max_by_hours = MAX_HOURS_YEAR / (minutes / 60.0)
        volume = min(volume, max_by_hours)
    return round(volume)


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
            est_annual_volume=_clamp_volume(
                float(rec.get("time_cost_per_occurrence_min", 0) or 0),
                float(rec.get("est_annual_volume", 0) or 0)),
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


def extract_all(interviews: list[Interview], llm: LLM, progress=None) -> list[PainPoint]:
    """Extract every interview concurrently. progress(stage, done, total) is
    called as each interview finishes so callers can show a real progress bar.
    Results are returned in interview order so pain ids stay stable."""
    total = len(interviews)
    if progress:
        progress("extract", 0, total)
    if total == 0:
        return []

    workers = max(1, min(MAX_WORKERS, total))
    # mock mode is local/instant; no need to spin up threads
    if llm.mode == "mock" or workers == 1:
        out: list[PainPoint] = []
        for i, iv in enumerate(interviews, 1):
            out.extend(extract_interview(iv, llm))
            if progress:
                progress("extract", i, total)
        return out

    results: list = [None] * total
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(extract_interview, iv, llm): i for i, iv in enumerate(interviews)}
        for fut in as_completed(futs):
            i = futs[fut]
            results[i] = fut.result()
            done += 1
            if progress:
                progress("extract", done, total)

    out = []
    for r in results:
        out.extend(r or [])
    return out
