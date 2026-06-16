# Lens (demo)

Turns messy stakeholder interview notes into a prioritized, de-duplicated,
savings-mapped portfolio of AI use cases. This repo is the **synthesis demo**:
the core mechanic (extract, dedup/overlap, roll up, size, rank) running
end-to-end on synthetic interviews. The full ten-stage system is the vision
(see `BUILD_PLAN.md`); this proves the engine on samples.

See `PROJECT_INSTRUCTIONS.md` and `BUILD_PLAN.md` for the design, and
`flowcharts/pipeline.md` for the workflow diagrams.

## Run it

### Dashboard (see it in action)

```bash
pip install -r requirements.txt
python app.py                 # auto: live if ANTHROPIC_API_KEY set, else mock
LENS_MODE=mock python app.py  # force offline mock
python app.py --live --port 8000   # real Claude (needs a real ANTHROPIC_API_KEY)
```

Then open **http://localhost:8000** (default port 8000). The dashboard shows the
prioritized portfolio (click any use case to drill into its provenance), KPIs, a
value/feasibility 2x2, and the resolved overlaps. The right-hand **input area**
lets you paste a new interview note, pick its function, and watch it extract,
de-duplicate against the existing use cases, and re-rank the whole portfolio
live. "Load example" drops in a note that overlaps the status-summarization use
case so you can watch a merge happen; "Reset demo" returns to the base five
interviews. **Download CSV / JSON** exports the current portfolio (and the
server keeps `out/use_cases.json` and `out/pain_points.json` in sync) so a CFO
can take the data away.

### CLI

```bash
python run_demo.py            # auto: live if ANTHROPIC_API_KEY is set, else mock
python run_demo.py --mock     # deterministic fixtures, no API key needed
python run_demo.py --live     # real Anthropic (claude-haiku-4-5) extraction + adjudication
```

`--mock` runs entirely offline using curated extraction fixtures and a heuristic
adjudicator, so the demo is reproducible without a key. `--live` runs the same
pipeline through Claude. (Note: the current shell has `ANTHROPIC_API_KEY` set but
empty, so `--live` needs a real key wired in first.)

Structured output lands in `out/pain_points.json` and `out/use_cases.json`.

## What the demo proves

On 5 synthetic interviews across 3 functions (12 raw pain points):

- **Messy in, comparable out.** Free-text notes become structured, tagged
  pain-point records on one taxonomy.
- **Overlap resolved.** 12 raw points collapse to 9 canonical use cases. Two
  cross-function duplicates merge into single horizontal use cases (status
  summarization across Patient Services + Manufacturing; reconciliation across
  Manufacturing + Finance), plus one same-function merge (claim appeals).
- **No double-counting, full provenance.** Savings aggregate on canonical
  de-duplicated scope; every use case lists its member pain points and source
  interviews.
- **The gate.** A use case with no savings hypothesis cannot be ranked.
- **Prioritized.** RICE ranks the portfolio; the cross-function cases rise to
  the top on reach. Low-confidence merges are flagged for human review.

## 60-90 second walkthrough script

1. "Here are 5 messy interview notes across three functions." (show
   `data/interviews/interviews.json`)
2. "Stage 2 extracts each into structured, tagged pain-point records." (run
   `python run_demo.py --mock`, point at the Stage 2-3 block)
3. "Stage 4 is the heart: a coordinator in Patient Services and a scheduler in
   Manufacturing described the *same* underlying problem, assembling a status
   summary from scattered systems. The cascade merges them into one
   cross-function use case." (point at the `MERGE ... CROSS-FUNCTION` lines)
4. "It rolls up into one prioritized model. That merged use case ranks #1 at
   about \$52K/year from a single build serving two functions, with full
   provenance back to both interviews, and it is flagged for human review
   because the merge confidence was moderate." (point at #1 + provenance)
5. "Every number traces back to a source interview, savings are de-duplicated,
   and the gate means nothing gets ranked without a P&L hypothesis."

## Layout

```
data/functions.json              3 synthetic functions
data/interviews/interviews.json  5 synthetic interview notes (2 overlap seeds)
data/mock_extractions.json       curated Stage-2 fixtures for --mock
lens/taxonomy.py                 controlled vocabulary
lens/models.py                   PainPoint (raw) + UseCase (canonical) entities
lens/llm.py                      Anthropic client + mock backend
lens/extract.py                  Stage 2-3: extract + tag
lens/dedup.py                    Stage 4: dedup + overlap cascade
lens/savings.py                  Stage 5-6: aggregate + size (the gate)
lens/score.py                    Stage 7: RICE + 2x2
lens/pipeline.py                 reusable run_pipeline() used by CLI + dashboard
run_demo.py                      orchestrator + portfolio report (CLI)
app.py                           dashboard server (stdlib http, no deps)
static/index.html                dashboard UI (vanilla JS)
flowcharts/pipeline.md           workflow diagrams (mermaid)
```
