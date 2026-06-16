# Lens: AI Use-Case Discovery and Prioritization System
## Project instructions and parameters

> Codename "Lens" because it brings a messy, 1,500-item discovery into focus. Rename freely. If you build this with Claude Code, copy this file to `CLAUDE.md` so it auto-loads as project context.

---

## 1. What this is

Lens turns raw stakeholder discovery into a prioritized, de-duplicated, savings-mapped portfolio of AI use cases. It is the operating tool behind an AI Strategy and Operations diagnostic: interview across business functions, capture pain points, resolve overlap, hypothesize savings, and rank what to build, with every number traceable back to the interview it came from.

The core idea is a two-layer model. You capture many raw pain points (roughly 1,500 if 100 interviews each surface 15), then collapse them into a much smaller set of canonical use cases (roughly 50 to 150). You never prioritize raw pain points. You prioritize canonical use cases. The layer in between, which resolves overlap and de-duplicates, is the heart of the system.

## 2. Why this exists (the questions it must answer)

This project was sparked by a real interview for the Iovance AI Strategy Associate role. The interviewer pushed on a concrete scenario, and Lens is the answer to it. Every question below is a design requirement:

1. If 100 interviews each give 15 pain points, how do you keep track of all 1,500?
2. How do you prioritize them?
3. How do you hypothesize the savings for each?
4. How do you allocate resources against them?
5. How do you surface the most common pain points?
6. How do you weight and choose which to address?
7. How do you make sure a pain point raised in two different business functions is not treated as two separate things (overlap and double-counting)?
8. How do you keep track of all of it properly, over time?

Lens answers each of these mechanically, not with hand-waving. See `BUILD_PLAN.md` for the detailed method behind each.

## 3. Goals and what success looks like

- Ingest unstructured interview notes and produce structured, comparable pain-point records automatically.
- Collapse overlapping pain points across functions into canonical use cases, with provenance preserved.
- Produce a defensible, ranked portfolio of AI use cases with savings hypotheses and a clear "what to do first."
- Make the whole thing legible to a CFO and an IT platform owner: every priority traces to a number, and every number traces to its source interviews.
- Be buildable by one person on tools they already use, and demoable in an afternoon.

## 4. Scope: the demo versus the full system

Keep these strictly separated so the near-term build stays small.

**The demo (near-term, an afternoon).** Stage 2 extraction plus a taste of Stage 4 dedup and Stage 5 roll-up, on 4 to 6 synthetic interviews. It shows: messy notes in, standardized comparable pain-point records out, the same problem from two functions merging into one canonical use case, and a simple rolled-up view. This is the proof of concept to send and walk through. It does NOT interview anyone, run at scale, or touch real data.

**The full system (the vision).** The complete ten-stage pipeline with dashboards, scoring, resource mapping, and governance tracking. Built in phases (see roadmap in `BUILD_PLAN.md`).

Do not let "demo" inflate into "production system." The demo proves the mechanism on samples; the scale and the live interviewing are narrated as the vision, not executed.

## 5. Principles and parameters (non-negotiable)

- **Two-layer model.** Raw pain points are evidence. Canonical use cases are the unit of decision. Prioritize the latter only.
- **The gate.** No P&L mapping, no prioritization. A use case without a savings hypothesis cannot be ranked. This is a hard rule, not a guideline.
- **Savings are hypotheses until validated.** Every savings number is an estimate until a controlled comparison confirms it. Confidence stays low until then, and low confidence caps the priority score.
- **Provenance always.** Every canonical use case lists its member pain points and source interviews. Nothing is orphaned, and any number can be drilled back to its origin.
- **No double-counting.** Aggregate savings at the canonical level over de-duplicated scope. If two pain points describe the same hours, count them once. Flag possible double-counts for human review.
- **Human-in-the-loop.** Low-confidence merges and all savings sign-offs go to a review queue. The system proposes; a person confirms.
- **Overlap is a feature, not just hygiene.** A use case raised by many functions is a horizontal, high-leverage opportunity. Surface cross-functional reach as a priority signal.
- **Synthetic data only** for the demo and anything shared externally. No real Iovance internals, ever.
- **Decision-support, not an actor.** Lens analyzes and recommends. It does not act on production, regulated, or GxP systems.
- **Built on tools I actually use.** Airtable, Claude and the Anthropic API, Python, n8n or Make, Retool or Hex, Coze. No exotic dependencies.
- **Writing style.** No em-dashes. Concise and specific. American spelling.

## 6. Data model (high level)

Six core entities, linked. Full schema in `BUILD_PLAN.md`.

| Entity | One-line role |
|---|---|
| Function | A business function or department being diagnosed (headcount, cost base). |
| Stakeholder | A person interviewed (synthetic for the demo). |
| Interview | One conversation, with raw notes or transcript. |
| Pain Point (raw) | One extracted problem from one interview. The 1,500-level layer. |
| Use Case (canonical) | A de-duplicated cluster of related pain points. The decision layer. |
| Savings Hypothesis | The lever-to-P&L estimate for a use case. |

## 7. Pipeline at a glance

Capture, then Extract, then Normalize and tag, then Deduplicate and resolve overlap, then Aggregate and roll up, then Hypothesize savings, then Score and prioritize, then Allocate resources, then Govern and track, then Report. Ten stages, detailed in `BUILD_PLAN.md`.

## 8. Tech stack

- **Data backbone:** Airtable (relational tables, linked records, built-in interfaces). Postgres or SQLite if it outgrows Airtable.
- **Extraction and adjudication:** Claude via the Anthropic API, for pain-point extraction and low-confidence dedup judgments. The pattern mirrors the data-extraction LLM and confidence-scoring cascade I built at ByteDance.
- **Semantic dedup:** an embeddings model plus cosine-similarity clustering against a canonical use-case library.
- **Orchestration:** Python, or n8n / Make for no-code flows.
- **Dashboards:** Retool or Hex, or Airtable interfaces for the MVP.
- **Fast prototyping:** Coze for a conversational extraction agent.

## 9. Working conventions (for any builder, including Claude Code)

- Keep raw and canonical layers strictly separate in the schema.
- Every automated decision (extraction, tag, merge) carries a confidence score and a source reference.
- Anything below the confidence threshold routes to a human review queue, never silently merged.
- Prefer small, inspectable steps over one giant prompt. Extract, then tag, then match, then score, as discrete stages you can audit.
- Use synthetic data fixtures for all tests and demos.
- No em-dashes in any generated text or documents.

## 10. Definition of done (demo)

- 4 to 6 synthetic interview notes ingest into structured pain-point records in one consistent schema.
- At least one pain point from two different functions correctly merges into a single canonical use case, with both functions listed and provenance preserved.
- A simple rolled-up view shows canonical use cases ranked, with a rough savings hypothesis on each and the gate visibly enforced.
- A 60 to 90 second walkthrough explains: messy in, comparable out, overlap resolved, rolls up into one prioritized model.
