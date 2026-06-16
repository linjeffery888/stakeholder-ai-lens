"""Stage 7: score and prioritize (RICE + value/feasibility 2x2).

    rice = (Reach x Impact x Confidence) / Effort

  Reach       cross-functional prevalence (functions affected). Rewards
              horizontal opportunities.
  Impact      base-case annual savings, in $K.
  Confidence  0-1, low until a controlled comparison validates the savings
              assumption. Acts as a governor: an exciting but unvalidated use
              case cannot outrank a proven win.
  Effort      implementation effort in person-weeks.

The gate from Stage 6 lives here too: a use case with no savings hypothesis
gets no score and drops out of the ranking.
"""

from __future__ import annotations

from .models import PainPoint, UseCase, Function

ADDRESSABILITY = {"low": 0.0, "med": 0.5, "high": 1.0}

# --- bounded RICE impact (textbook 0.25-3 scale), so a single large dollar
# figure cannot dominate the ranking. Raw savings stay visible separately. ---
def _impact_tier(savings_base: float) -> float:
    if savings_base >= 1_000_000:
        return 3.0      # massive
    if savings_base >= 250_000:
        return 2.0      # high
    if savings_base >= 50_000:
        return 1.0      # medium
    if savings_base >= 10_000:
        return 0.5      # low
    return 0.25         # minimal

# --- transparent, parameterized TCO so we report NET, not just gross.
# These are assumptions (like adoption rates), not researched per-use-case
# costs; precise TCO is a post-selection exercise on funded use cases. ---
BUILD_COST_PER_WEEK = 7000.0   # blended fully-loaded build cost per person-week
RUN_COST_FRACTION = 0.20       # annual run cost (inference + license + upkeep)


def _apply_tco(uc: UseCase) -> None:
    uc.run_cost_fraction = RUN_COST_FRACTION
    uc.implementation_cost = round(uc.effort_person_weeks * BUILD_COST_PER_WEEK)
    keep = 1.0 - RUN_COST_FRACTION
    uc.est_net_savings_low = round(uc.est_savings_low * keep)
    uc.est_net_savings_base = round(uc.est_savings_base * keep)
    uc.est_net_savings_high = round(uc.est_savings_high * keep)
    monthly_net = uc.est_net_savings_base / 12.0
    uc.payback_months = round(uc.implementation_cost / monthly_net, 1) if monthly_net > 0 else 0.0


def _feasibility(uc: UseCase, members: list[PainPoint]) -> float:
    """Higher when AI fits well; lower for cross-function integration work."""
    if members:
        addr = sum(ADDRESSABILITY.get(m.ai_addressability, 0.5) for m in members) / len(members)
    else:
        addr = 0.5
    score = 0.3 + 0.6 * addr
    if uc.cross_functional:
        score -= 0.1  # more integration surface
    return round(max(0.1, min(1.0, score)), 2)


def _effort_weeks(uc: UseCase, members: list[PainPoint]) -> float:
    base = 3.0
    if uc.cross_functional:
        base += 2.0 * (len(uc.affected_functions) - 1)
    if uc.ai_lever in ("reconciliation", "spend analysis"):
        base += 2.0  # data integration heavy
    return round(base, 1)


def _confidence(uc: UseCase, members: list[PainPoint]) -> float:
    """Unvalidated by definition in the demo, so capped low. More evidence
    (more interviews raising it) lifts it slightly, but never past the cap."""
    if members:
        addr = sum(ADDRESSABILITY.get(m.ai_addressability, 0.5) for m in members) / len(members)
    else:
        addr = 0.5
    conf = 0.30 + 0.10 * addr + 0.03 * (uc.prevalence_count - 1)
    return round(min(0.50, conf), 2)  # cap: nothing validated yet


def _quadrant(uc: UseCase, savings_median: float) -> str:
    high_value = uc.est_savings_base >= savings_median
    high_feas = uc.feasibility_score >= 0.6
    if high_value and high_feas:
        return "quick win"
    if high_value and not high_feas:
        return "roadmap (high value, lower feasibility)"
    if not high_value and high_feas:
        return "easy but small"
    return "deprioritize"


def score_portfolio(
    use_cases: list[UseCase],
    pain_points: list[PainPoint],
    functions: dict[str, Function],
) -> tuple[list[UseCase], list[UseCase]]:
    """Returns (ranked, gated). Gated = no savings hypothesis, excluded."""
    by_id = {pp.pain_id: pp for pp in pain_points}

    ranked, gated = [], []
    for uc in use_cases:
        members = [by_id[pid] for pid in uc.member_pain_ids]
        # the gate
        if uc.est_savings_base <= 0:
            reason = "no savings hypothesis (gated out)"
            if reason not in uc.review_reasons:  # idempotent across recomputes
                uc.review_reasons.append(reason)
            gated.append(uc)
            continue
        uc.feasibility_score = _feasibility(uc, members)
        uc.effort_person_weeks = _effort_weeks(uc, members)
        uc.confidence = _confidence(uc, members)
        _apply_tco(uc)
        # bounded impact (0.25-3) instead of raw $K, so no single large figure
        # runs away with the ranking; magnitude is still shown as the $ savings.
        uc.impact_score = _impact_tier(uc.est_savings_base)
        uc.rice_score = round(
            (uc.reach * uc.impact_score * uc.confidence) / uc.effort_person_weeks, 2
        )
        ranked.append(uc)

    # rank WITHIN track so top-down spend estimates never cross-rank against
    # bottoms-up, interview-grounded labor cases
    median = _median([u.est_savings_base for u in ranked])
    for track_name in ("labor", "spend"):
        track_ucs = [u for u in ranked if u.track == track_name]
        track_ucs.sort(key=lambda u: u.rice_score, reverse=True)
        for i, uc in enumerate(track_ucs, start=1):
            uc.priority_rank = i
            uc.maturity_stage = "idea"
            uc.quadrant = _quadrant(uc, median)
    ranked.sort(key=lambda u: (u.track != "labor", u.priority_rank))
    return ranked, gated


def _median(values: list) -> float:
    if not values:
        return 0
    s = sorted(values)
    return s[len(s) // 2]
