# Lens workflow flowcharts

Mermaid diagrams of the pipeline. They render on GitHub, in VS Code (Markdown
Preview Mermaid extension), or at mermaid.live. Three views:

1. End-to-end pipeline (the ten stages, raw vs canonical layers)
2. The Stage 4 dedup + overlap cascade (the hard part)
3. Savings gate + RICE scoring

---

## 1. End-to-end pipeline

The two sacred layers are colored: raw pain points (the ~1,500 level) feed the
bridge at Stage 4, which produces canonical use cases (the ~50-150 decision
level). Only canonical use cases are ever prioritized.

```mermaid
flowchart TD
    A[Interview notes<br/>messy free text] --> B[Stage 2: Extract<br/>LLM, one record per problem]
    B --> C[Stage 3: Normalize + tag<br/>controlled taxonomy]
    C --> R[/Raw Pain Points<br/>~1,500 level/]:::raw

    R --> D{Stage 4:<br/>Deduplicate +<br/>resolve overlap}
    D --> U[/Canonical Use Cases<br/>~50-150 level/]:::canon

    U --> E[Stage 5: Aggregate + roll up<br/>prevalence, addressable hours]
    E --> F{{Stage 6: Savings hypothesis<br/>THE GATE}}
    F -->|has savings| G[Stage 7: Score + prioritize<br/>RICE + value/feasibility 2x2]
    F -->|no savings| X[Gated out<br/>cannot be ranked]:::gate
    G --> H[Stage 8: Resource + roadmap<br/>waves, owners, effort]
    G --> I[Stage 9: Govern + maturity<br/>idea -> validated -> deployed]
    H --> J[Stage 10: Dashboards + reporting<br/>portfolio, 2x2, provenance drill-down]
    I --> J

    classDef raw fill:#fde7c7,stroke:#c8841a,color:#000;
    classDef canon fill:#cfe8d4,stroke:#2e7d46,color:#000;
    classDef gate fill:#f6c9c9,stroke:#b23b3b,color:#000;
```

---

## 2. Stage 4: deduplicate + resolve overlap (the cascade)

For each raw pain point, a four-step cascade decides whether it joins an
existing canonical use case or starts a new one. Confidence is recorded at every
step; low-confidence merges never happen silently, they route to a human.

```mermaid
flowchart TD
    P[New raw pain point] --> T[Step 1: Taxonomy pre-filter<br/>same category + lever only]
    T --> CAND{Any candidate<br/>canonical in group?}
    CAND -->|no| NEW[Spawn new<br/>canonical use case]:::canon

    CAND -->|yes| SIM[Step 2: Similarity<br/>embeddings + cosine<br/>lexical stand-in in demo]
    SIM --> B1{sim >= 0.90?}
    B1 -->|yes| MERGE[Merge into canonical<br/>add member + function]:::canon
    B1 -->|no| ADJ[Step 3: LLM adjudication<br/>same underlying problem?]

    ADJ --> Q{match?}
    Q -->|no| NEW
    Q -->|yes, conf high| MERGE
    Q -->|yes, conf low| REV[Step 4: Human review queue<br/>propose, do not auto-merge]:::review
    REV -->|confirmed| MERGE
    REV -->|rejected| NEW

    MERGE --> XF{More than one<br/>function now?}
    XF -->|yes| CF[cross_functional = true<br/>horizontal opportunity]:::canon
    XF -->|no| DONE[done]

    classDef canon fill:#cfe8d4,stroke:#2e7d46,color:#000;
    classDef review fill:#fff2b8,stroke:#b9960b,color:#000;
```

Key guarantees:
- No double-counting: scope aggregates on the canonical use case, not on raw
  points. Two pain points describing the same hours are counted once.
- Provenance preserved: every canonical keeps `member_pain_ids` and the source
  interviews, so any number drills back to its origin.
- Cross-function reach becomes a priority signal in Stage 7.

---

## 3. Savings gate + RICE scoring (Stages 6-7)

```mermaid
flowchart TD
    U[Canonical use case<br/>+ de-duplicated member hours] --> S[Stage 6: Savings hypothesis]
    S --> SC["annual_savings = sum over members of<br/>time_saved x hours x volume x rate x adoption"]
    SC --> SCN[Three scenarios:<br/>low / base / high]
    SCN --> GATE{base savings > 0?}

    GATE -->|no| OUT[Gated out:<br/>no P&L mapping, no rank]:::gate
    GATE -->|yes| RICE["Stage 7: RICE<br/>(Reach x Impact x Confidence) / Effort"]

    RICE --> CONF[Confidence governor<br/>low until validated -> caps priority]
    CONF --> RANK[Ranked portfolio]
    RANK --> Q2[Value vs feasibility 2x2]
    Q2 --> QW[Quick win<br/>high value + high feasibility]:::win
    Q2 --> RM[Roadmap<br/>high value, low feasibility]
    Q2 --> DP[Deprioritize<br/>low value]

    classDef gate fill:#f6c9c9,stroke:#b23b3b,color:#000;
    classDef win fill:#cfe8d4,stroke:#2e7d46,color:#000;
```
