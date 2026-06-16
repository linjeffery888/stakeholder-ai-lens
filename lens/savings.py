"""Stages 5 + 6: aggregate scope and hypothesize savings (the gate).

Two savings bases, picked per use case by its AI lever:

LABOR (most use cases). Savings come from time returned to people:
    annual_savings = sum over members of
        time_saved_fraction x hours_per_task x tasks_per_year
        x fully_loaded_hourly_cost x adoption_rate

SPEND (spend-analysis levers, e.g. SaaS/vendor review). The prize is recovered
spend, which scales with organization size, not task time:
    annual_savings = addressable_annual_spend x waste_rate x capture_rate
Addressable spend is an organization input (Organization.annual_saas_spend),
split evenly across spend use cases so it is never double counted.

Three scenarios flex the assumptions. The gate: a use case with no savings
hypothesis (base savings == 0) cannot proceed to scoring.
"""

from __future__ import annotations

from .models import PainPoint, UseCase, Function, Organization

# labor: (time_saved_fraction, adoption_rate)
SCENARIOS = {
    "low": (0.30, 0.50),
    "base": (0.50, 0.70),
    "high": (0.70, 0.85),
}

# spend: (waste_rate, capture_rate) — share of spend that is wasteful, and
# the share of that waste a tool realistically recovers
SPEND_SCENARIOS = {
    "low": (0.05, 0.40),
    "base": (0.10, 0.60),
    "high": (0.18, 0.75),
}

PNL_BY_LEVER = {
    "spend analysis": "vendor spend",
    "reconciliation": "rework",
}

SPEND_LEVERS = {"spend analysis"}


def _pnl_line(uc: UseCase) -> str:
    return PNL_BY_LEVER.get(uc.ai_lever, "labor")


def _is_spend(uc: UseCase) -> bool:
    return uc.ai_lever in SPEND_LEVERS


def aggregate_and_size(
    use_cases: list[UseCase],
    pain_points: list[PainPoint],
    functions: dict[str, Function],
    org: Organization | None = None,
) -> None:
    """Mutates use_cases in place: fills addressable hours and savings."""
    by_id = {pp.pain_id: pp for pp in pain_points}

    # addressable spend (sum of the org's spend lines) is split across the
    # spend use cases so it is counted once
    spend_ucs = [uc for uc in use_cases if _is_spend(uc)]
    total_spend = org.addressable_spend() if org else 0.0
    spend_per_uc = (total_spend / len(spend_ucs)) if spend_ucs else 0.0

    for uc in use_cases:
        members = [by_id[pid] for pid in uc.member_pain_ids]
        uc.addressable_hours_year = round(
            sum(m.addressable_hours_year for m in members), 1
        )
        uc.p_and_l_line = _pnl_line(uc)

        if _is_spend(uc):
            _size_spend(uc, members, functions, spend_per_uc)
        else:
            _size_labor(uc, members, functions)


def _size_labor(uc, members, functions):
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
            "basis": "labor",
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


def _size_spend(uc, members, functions, addressable_spend):
    scenarios = {}
    totals = {}
    for name, (waste, capture) in SPEND_SCENARIOS.items():
        ann = addressable_spend * waste * capture
        scenarios[name] = {
            "waste_rate": waste,
            "capture_rate": capture,
            "annual_savings": round(ann),
        }
        totals[name] = round(ann)
    fn = functions.get(members[0].function_id) if members else None
    uc.savings_breakdown = [{
        "basis": "spend",
        "pain_id": members[0].pain_id if members else "",
        "title": (members[0].title if members else uc.title),
        "function": fn.name if fn else "",
        "addressable_spend": round(addressable_spend),
        "scenarios": scenarios,
        "formula": "addressable spend x waste rate x capture rate",
    }]
    uc.est_savings_low = totals["low"]
    uc.est_savings_base = totals["base"]
    uc.est_savings_high = totals["high"]
