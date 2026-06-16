"""Core entities. Two layers stay strictly separate:

  raw layer       -> PainPoint   (one problem per interview, the ~1,500 level)
  canonical layer -> UseCase     (de-duplicated decision unit, the ~50-150 level)

Only canonical use cases are ever prioritized.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Function:
    function_id: str
    name: str
    description: str = ""
    headcount: int = 0
    est_annual_cost_base: float = 0.0
    avg_fully_loaded_hourly: float = 45.0


@dataclass
class Interview:
    interview_id: str
    function_id: str
    raw_notes: str
    stakeholder: str = ""
    role: str = ""
    seniority: str = ""
    date: str = ""
    status: str = "captured"


@dataclass
class PainPoint:
    """Raw layer. One extracted problem from one interview."""
    pain_id: str
    interview_id: str
    function_id: str
    description: str
    title: str = ""
    workflow: str = ""
    time_cost_per_occurrence_min: float = 0.0
    est_annual_volume: float = 0.0
    severity: str = "med"          # low / med / high
    ai_addressability: str = "med"  # low / med / high
    category_tags: list = field(default_factory=list)
    ai_lever: str = ""
    # assigned in Stage 4
    use_case_id: Optional[str] = None
    match_confidence: float = 0.0
    status: str = "extracted"      # extracted, tagged, matched, needs_review

    @property
    def addressable_hours_year(self) -> float:
        return (self.time_cost_per_occurrence_min / 60.0) * self.est_annual_volume

    def to_dict(self):
        return asdict(self)


@dataclass
class SavingsScenario:
    time_saved_fraction: float
    adoption_rate: float
    annual_savings: float


@dataclass
class UseCase:
    """Canonical layer. A de-duplicated cluster of related pain points."""
    use_case_id: str
    title: str
    canonical_description: str
    category: str
    ai_lever: str
    member_pain_ids: list = field(default_factory=list)
    affected_functions: list = field(default_factory=list)
    cross_functional: bool = False
    prevalence_count: int = 0          # how many interviews raised it
    addressable_hours_year: float = 0.0
    # Stage 6 (savings)
    est_savings_low: float = 0.0
    est_savings_base: float = 0.0
    est_savings_high: float = 0.0
    p_and_l_line: str = "labor"
    savings_breakdown: list = field(default_factory=list)  # per-member derivation
    # Stage 7 (scoring)
    feasibility_score: float = 0.5
    confidence: float = 0.3            # low until validated; governs priority
    reach: int = 0
    effort_person_weeks: float = 4.0
    rice_score: float = 0.0
    priority_rank: int = 0
    quadrant: str = ""
    maturity_stage: str = "idea"
    needs_review: bool = False
    review_reasons: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
