# Lens: comprehensive build plan

Companion to `PROJECT_INSTRUCTIONS.md`. This is the detailed design: architecture, data model, the ten-stage pipeline, the overlap-resolution method, the prioritization math, the savings model, the build roadmap, and the demo spec.

---

## 1. Architecture overview

A simple pipeline with a relational store at the center. Data flows one direction; every stage writes structured output the next stage reads.

```
Interview notes ─▶ [2] Extract ─▶ raw Pain Points
                                      │
                                      ▼
                            [3] Normalize + tag (controlled taxonomy)
                                      │
                                      ▼
                     [4] Deduplicate + resolve overlap ─▶ Canonical Use Cases
                                      │                         │
                                      ▼                         ▼
                         [5] Aggregate / roll up      [6] Savings hypothesis (gate)
                                                              │
                                                              ▼
                                                   [7] Score + prioritize (RICE + 2x2)
                                                              │
                                                              ▼
                                          [8] Resource + roadmap   [9] Govern + maturity
                                                              │
                                                              ▼
                                                     [10] Dashboards + reporting
```

Two layers are sacred: the **raw layer** (Pain Points, one per problem per interview) and the **canonical layer** (Use Cases, the de-duplicated decision unit). Stage 4 is the bridge between them and the hardest part of the system.

## 2. Data model (detailed)

### Functions
| Field | Type | Notes |
|---|---|---|
| function_id | id | |
| name | text | e.g., Patient Services, Manufacturing Coordination, Procurement, Clinical Ops, Finance |
| description | text | |
| headcount | number | drives capacity and savings math |
| est_annual_cost_base | number | fully loaded; rough is fine, flagged as estimate |
| avg_fully_loaded_hourly | number | for savings math |
| leader / stakeholders | text | synthetic for demo |

### Stakeholders
| Field | Type | Notes |
|---|---|---|
| stakeholder_id | id | |
| name | text | synthetic only |
| role, seniority | text | VP, director, manager, IC |
| function_id | link | |

### Interviews
| Field | Type | Notes |
|---|---|---|
| interview_id | id | |
| stakeholder_id, function_id | link | |
| date | date | |
| raw_notes | long text | the messy input |
| status | enum | captured, extracted, reviewed |

### Pain Points (raw layer)
| Field | Type | Notes |
|---|---|---|
| pain_id | id | |
| interview_id, function_id | link | provenance |
| description | text | verbatim-ish problem statement |
| workflow | text | the task or process affected |
| frequency | enum/number | per day / week / month, or occurrences per year |
| time_cost_per_occurrence | number | minutes |
| est_annual_volume | number | occurrences per year |
| severity | enum | low / med / high (pain intensity) |
| ai_addressability | enum | low / med / high (how well AI fits) |
| category_tags | multi-select | from the controlled taxonomy (Stage 3) |
| ai_lever | enum | the mechanism (deflection, summarization, extraction, drafting, scheduling, reconciliation, search) |
| use_case_id | link | assigned in Stage 4 |
| match_confidence | number 0-1 | how sure the merge is |
| status | enum | extracted, tagged, matched, needs_review |

### Use Cases (canonical layer)
| Field | Type | Notes |
|---|---|---|
| use_case_id | id | |
| title | text | canonical name |
| canonical_description | text | the shared underlying problem |
| category | enum | from taxonomy |
| ai_lever | enum | |
| member_pain_ids | link (many) | provenance, the raw points it absorbs |
| affected_functions | link (many) | all functions that raised it |
| cross_functional | bool | true if more than one function |
| prevalence_count | number | how many interviews raised it (the "most common" signal) |
| addressable_hours_year | number | de-duplicated sum across members |
| est_savings_low / base / high | number | from Stage 6 |
| p_and_l_line | enum | which line it hits (labor, vendor spend, rework) |
| feasibility_score | number 0-1 | |
| time_to_value | enum | weeks / quarters |
| confidence | number 0-1 | low until validated |
| rice_score | number | Stage 7 |
| priority_rank | number | |
| maturity_stage | enum | idea, validated, prototyped, approved, deployed |
| owner | text | |

### Taxonomy (controlled vocabulary)
A fixed list of categories and AI levers so everything is comparable. Example categories: manual data entry, document or report generation, status summarization, scheduling and coordination, approvals and routing, reconciliation, search and retrieval, data quality cleanup, vendor and SaaS spend. Example levers: deflection, drafting, summarization, extraction and structuring, prediction and flagging, scheduling optimization, spend analysis.

## 3. The ten-stage pipeline

### Stage 1: Capture
A consistent interview guide per function so inputs are comparable from the start. Same spine every time: where does your team spend the most hours, where are the repetitive or error-prone steps, where do you wait on other teams, what would you stop doing if you could. Accepts typed notes, transcripts, or recordings transcribed to text. The guide standardization is half the battle for later comparability.

### Stage 2: Extract
For each interview, an LLM extracts every distinct pain point into the raw schema above. Discrete, auditable, one record per problem. This is the core of the demo and the same pattern as the ByteDance extraction LLM: messy input, standardized JSON output.

Example output record:
```json
{
  "description": "Coordinators manually compile benefit-verification status from three systems for each patient case",
  "workflow": "Benefit verification before treatment scheduling",
  "frequency": "per case",
  "time_cost_per_occurrence_min": 30,
  "est_annual_volume": 4000,
  "severity": "high",
  "ai_addressability": "high",
  "category_tags": ["status summarization", "manual data entry"],
  "ai_lever": "summarization",
  "source_interview_id": "INT-014",
  "function_id": "FN-patient-services"
}
```

### Stage 3: Normalize and tag
Map each raw pain point onto the controlled taxonomy (category and lever) so different wordings of the same idea become comparable. This is what makes "the same problem in two functions" detectable in Stage 4. Tagging is LLM-assisted with the taxonomy supplied in the prompt, so it picks from a fixed list rather than inventing labels.

### Stage 4: Deduplicate and resolve overlap (the hard part, and the answer to the interview question)

Goal: collapse 1,500 raw pain points into 50 to 150 canonical use cases, merge cross-function duplicates, and never double-count. A four-step cascade, mirroring the confidence-scored approach I built at ByteDance:

1. **Taxonomy pre-filter.** Only compare pain points sharing a category and lever. This shrinks the comparison space massively.
2. **Semantic match.** Embed each pain-point description. Compare against the existing canonical use-case library by cosine similarity.
   - Similarity above 0.90: auto-merge into the existing use case.
   - Similarity 0.75 to 0.90: send to LLM adjudication (next step).
   - Similarity below 0.75: spawn a new canonical use case.
3. **LLM adjudication for the middle band.** Ask the model a precise yes or no: "Do these two describe the same underlying problem that one solution would fix?" with both descriptions. Record the answer and a confidence. This catches semantic matches embeddings miss and splits false matches.
4. **Human review queue.** Any merge below a confidence threshold, and any merge that would combine two high-savings items, routes to a person. The system proposes, a human confirms. Wrong merges are the one thing that can hide value, so they are gated.

**Cross-function handling.** When pain points from different functions map to one use case, set `cross_functional = true` and add every function to `affected_functions`. This is not just cleanup. A problem raised by five functions is a horizontal opportunity worth more than a single-team fix, and Stage 7 rewards it.

**Avoiding double-counted savings.** Aggregate `addressable_hours_year` at the canonical level from the member pain points, but de-duplicate overlapping scope. If two pain points describe the same hours from two angles, count the hours once. The model keeps provenance (`member_pain_ids`) so a reviewer can always see what rolled up and catch a double-count. Savings are computed on the canonical use case, never summed naively from raw points.

This is the precise answer to "how do you make sure pain points across two functions are not overlapping or double-counted": you never decide on raw points, you decide on canonical use cases, the cascade reconciles overlap with confidence scoring and human review, cross-function reach becomes a priority signal, and savings aggregate on de-duplicated scope with full provenance.

### Stage 5: Aggregate and roll up
Per canonical use case, compute prevalence (how many interviews and functions raised it, which surfaces the most common pain points), total addressable hours, and the affected headcount. This is the "single model everything rolls up into" view.

### Stage 6: Hypothesize savings (the gate)
For each use case, build a lever-to-P&L estimate. Core formula, summed across affected functions over de-duplicated scope:

```
annual_savings =
  time_saved_fraction
  x hours_per_task
  x tasks_per_year
  x fully_loaded_hourly_cost
  x adoption_rate
```

Produce three scenarios (conservative, base, optimistic) by flexing `time_saved_fraction` and `adoption_rate`. Map each to a P&L line (labor hours, vendor or SaaS spend, error rework). The gate: a use case with no savings hypothesis cannot proceed to prioritization, full stop.

### Stage 7: Score and prioritize
Two views, used together.

**RICE-adapted score** (clean, defensible, recognized):
```
score = (Reach x Impact x Confidence) / Effort
```
- Reach: number of functions or people affected (prevalence). Rewards cross-functional reach.
- Impact: the base-case annual savings (or a 1 to 5 tier).
- Confidence: 0 to 1, low until a controlled comparison validates the assumption. The gate lives here too.
- Effort: implementation effort in person-weeks or build cost.

**Value-versus-feasibility 2x2** for the portfolio: plot savings against feasibility. Top-right (high value, high feasibility) are quick-win pilots. High value, low feasibility go on the roadmap with dependencies named. Low value drops out.

Weights are configurable. Confidence acts as a governor so unvalidated, exciting demos cannot outrank a proven, banked win.

### Stage 8: Allocate resources and roadmap
Map each prioritized use case to the teams and roles it touches, the implementation effort, and dependencies (shared data, shared platform work). Sequence into waves: quick wins first to build momentum and bank early savings, then the larger validated builds. Output a phased roadmap with owners and rough effort.

### Stage 9: Govern and track maturity
Each use case moves through a maturity pipeline: idea, validated (controlled comparison passed), prototyped, governance-approved, deployed. The system tracks status, generates a one-page governance brief per use case (problem, lever, savings methodology, validation evidence, risk), and keeps the audit trail. This is how you "keep track of all of it properly over time."

### Stage 10: Dashboards and reporting
- Portfolio dashboard: ranked use cases, the 2x2, total opportunity, banked versus projected.
- Function view: opportunities and savings by function.
- Most-common-pain view: use cases by prevalence.
- Cross-functional view: the horizontal opportunities.
- Provenance drill-down: click a use case, see its member pain points and source interviews.
- Exec summary: the top 10, the total sized prize, and the quick wins in flight.

## 4. Worked example (synthetic, illustrative only)

Two interviews, two functions, raising what looks like two problems but is one.

- Patient Services, INT-014: "Coordinators spend about 30 minutes per case compiling benefit-verification status across three systems." 4,000 cases per year.
- Manufacturing Coordination, INT-031: "Schedulers spend roughly 25 minutes per order assembling a status summary from the orchestration system and email." 3,000 orders per year.

Stage 3 tags both as `status summarization`. Stage 4 embeds them, similarity lands in the middle band, LLM adjudication says yes, same underlying problem (assemble a status summary from multiple sources), so they merge into one canonical use case "Automated status summarization," `cross_functional = true`, affected functions = [Patient Services, Manufacturing Coordination].

Stage 6 savings, base case, time saved 50 percent, adoption 70 percent, fully loaded 45 dollars per hour:
- Patient Services: 0.5 x 0.5h x 4000 x 45 x 0.7 = about 31,500 dollars per year.
- Manufacturing: 0.5 x (25/60)h x 3000 x 45 x 0.7 = about 19,700 dollars per year.
- Canonical total: about 51,000 dollars per year from one build serving two functions.

Stage 7: high reach (two functions), solid impact, decent confidence once a controlled comparison runs, low-to-medium effort. It scores as an early quick win. The point: one solution, two functions, savings aggregated without double-counting, full provenance back to INT-014 and INT-031.

## 5. Build roadmap (phases)

| Phase | Deliverable | Rough effort |
|---|---|---|
| 0 | Airtable base with the six tables and the taxonomy | half a day |
| 1 | Extraction pipeline: interview text to raw pain points (the demo) | half to one day |
| 2 | Tagging plus dedup cascade to canonical use cases | one to two days |
| 3 | Savings model and RICE plus 2x2 prioritization | one to two days |
| 4 | Dashboards, roll-up views, provenance drill-down | one to two days |
| 5 | Resource and roadmap mapping, governance and maturity tracking | one to two days |

## 6. The demo spec (what to actually build first, for Najam)

Scope: Phase 1 plus a visible taste of Phase 2 and 5, on 4 to 6 synthetic interviews. Roughly an afternoon.

Build:
1. Write 4 to 6 synthetic interview notes across 3 functions, deliberately seeding two that overlap (like the worked example).
2. Extraction: a Claude prompt or Coze flow that turns each note into structured pain-point records.
3. A light dedup pass that merges the seeded overlap into one canonical use case with both functions attached.
4. A simple Airtable or Sheet view showing canonical use cases ranked with a rough savings figure and the gate visible.
5. A 60 to 90 second screen recording walking through: messy in, comparable out, the two-function overlap resolving into one, rolling up into a prioritized list.

Framing when you send it: "a quick sketch of the synthesis step, the core mechanic, on a few sample interviews to show how they come out comparable and roll up." Humble, clearly a sketch, synthetic data.

## 7. Risks and mitigations

- **Over-scoping the demo.** Build only the synthesis proof on samples. The full pipeline is the vision, not the demo.
- **Bad merges hiding value.** Confidence thresholds plus a human review queue for low-confidence and high-savings merges.
- **Double-counted savings.** Aggregate on de-duplicated canonical scope with provenance, never naive sums of raw points.
- **False precision on savings.** Always three scenarios, always flagged as hypotheses until a controlled comparison validates them.
- **Taxonomy drift.** Keep the category and lever lists controlled and small; review periodically.
- **Privacy and compliance.** Synthetic data only for anything shared. Decision-support, never an actor on regulated systems.
