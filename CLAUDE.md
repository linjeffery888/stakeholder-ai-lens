# Lens — Stakeholder AI use-case discovery (project context for Claude Code)

This is a standalone project. It is NOT part of inBeat or any other repo.

Lens turns raw stakeholder interview notes into a prioritized, de-duplicated,
savings-mapped portfolio of AI use cases. Full product spec is in
`PROJECT_INSTRUCTIONS.md`; the detailed design (data model, ten-stage pipeline,
overlap-resolution method, scoring math) is in `BUILD_PLAN.md`. Read those for
intent. This file is the fast orientation plus current build state.

## Core idea (do not violate)

- Two-layer model: raw **Pain Points** (evidence, ~1,500 level) collapse into
  canonical **Use Cases** (the decision unit, ~50-150 level). Only prioritize
  canonical use cases, never raw pain points.
- The gate: no savings hypothesis, no prioritization. Hard rule.
- Savings aggregate on de-duplicated canonical scope with full provenance. No
  double-counting.
- Low-confidence merges route to a human review queue, never silently merged.
- Cross-functional reach is a priority signal, not just hygiene.
- Synthetic data only. Decision-support, not an actor on production systems.
- Writing style: no em-dashes, concise, American spelling.

## What is built (demo, runs end-to-end)

Pipeline Stages 2-7 on 5 synthetic interviews across 3 functions:
extract+tag -> dedup/overlap cascade -> aggregate -> savings (gate) -> RICE +
2x2. Two run surfaces, both call `lens/pipeline.py:run_pipeline` so numbers match.

- `python run_demo.py [--mock|--live]` — CLI portfolio report.
- `python app.py [--mock|--live] [--port 8000]` — browser dashboard at
  localhost:8000 (portfolio, 2x2, provenance drill-down, live interview input
  area, CSV/JSON export). Stdlib only.
- `--mock` runs offline (fixtures in `data/mock_extractions.json` + heuristic
  adjudicator). `--live` uses the Anthropic API (`claude-haiku-4-5`); needs a
  real `ANTHROPIC_API_KEY`.

## Layout

```
data/                 synthetic functions + interviews + mock fixtures
lens/taxonomy.py      controlled vocabulary
lens/models.py        PainPoint (raw) + UseCase (canonical)
lens/llm.py           Anthropic client + mock/offline backend
lens/extract.py       Stage 2-3 extract + tag
lens/dedup.py         Stage 4 dedup + overlap cascade (the hard part)
lens/savings.py       Stage 5-6 aggregate + size (the gate)
lens/score.py         Stage 7 RICE + 2x2
lens/pipeline.py      run_pipeline() shared by CLI + dashboard
run_demo.py / app.py  CLI / dashboard server
static/index.html     dashboard UI
flowcharts/           mermaid workflow diagrams
```

## Conventions

- Keep raw and canonical layers strictly separate in the schema.
- Every automated decision (extraction, tag, merge) carries a confidence score
  and a source reference.
- Small inspectable stages over one giant prompt; each stage auditable.
- Synthetic fixtures for all tests and demos. No em-dashes in generated text.
