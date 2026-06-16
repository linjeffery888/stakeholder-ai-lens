"""Stages 5 + 6: aggregate scope and hypothesize savings (the gate).

Savings aggregate on the canonical use case over its de-duplicated member pain
points, never summed naively from raw points. Each member carries its own
hours and its function's fully loaded hourly rate, so a cross-function use case
sums real, distinct hours from each function.

    annual_savings = sum over members of
        time_saved_fraction
        x hours_per_task
        x tasks_per_year
        x fully_loaded_hourly_cost
        x adoption_rate

Three scenarios flex time_saved_fraction and adoption_rate. The gate: a use
case with no savings hypothesis (base savings == 0) cannot proceed to scoring.
"""

from __future__ import annotations

from .models import PainPoint, UseCase, Function

# (time_saved_fraction, adoption_rate) per scenario
SCENARIOS = {
    "low": (0.30, 0.50),
    "base": (0.50, 0.70),
    "high": (0.70, 0.85),
}

# which P&L line each lever hits
PNL_BY_LEVER = {
    "spend analysis": "vendor spend",
    "reconciliation": "rework",
}


def _pnl_line(uc: UseCase) -> str:
    return PNL_BY_LEVER.get(uc.ai_lever, "labor")


def aggregate_and_size(
    use_cases: list[UseCase],
    pain_points: list[PainPoint],
    functions: dict[str, Function],
) -> None:
    """Mutates use_cases in place: fills addressable hours and savings."""
    by_id = {pp.pain_id: pp for pp in pain_points}

    for uc in use_cases:
        members = [by_id[pid] for pid in uc.member_pain_ids]
        uc.addressable_hours_year = round(
            sum(m.addressable_hours_year for m in members), 1
        )

        breakdown = []
        totals = {"low": 0.0, "base": 0.0, "high": 0.0}
        for m in members:
            fn = functions.get(m.function_id)
            rate = fn.avg_fully_loaded_hourly if fn else 45.0
            hours_per_task = m.time_cost_per_occurrence_min / 60.0
            scenarios = {}
            for name, (saved, adoption) in SCENARIOS.items():
                ann = saved * hours_per_task * m.est_annual_volume * rate * adoption
                scenarios[name] = {
                    "time_saved_fraction": saved,
                    "adoption_rate": adoption,
                    "annual_savings": round(ann),
                }
                totals[name] += ann
            breakdown.append({
                "pain_id": m.pain_id,
                "title": m.title or m.workflow or m.description[:40],
                "function": fn.name if fn else m.function_id,
                "minutes_per_task": m.time_cost_per_occurrence_min,
                "tasks_per_year": m.est_annual_volume,
                "hours_per_task": round(hours_per_task, 2),
                "addressable_hours_year": round(hours_per_task * m.est_annual_volume, 1),
                "fully_loaded_hourly": rate,
                "scenarios": scenarios,
                "formula": "time_saved x (min/60) x tasks/yr x $/hr x adoption",
            })

        uc.savings_breakdown = breakdown
        uc.est_savings_low = round(totals["low"])
        uc.est_savings_base = round(totals["base"])
        uc.est_savings_high = round(totals["high"])
        uc.p_and_l_line = _pnl_line(uc)
