"""Controlled vocabulary (Stage 3).

Everything must map onto these fixed lists so different wordings of the same
idea become comparable. The LLM picks from these lists rather than inventing
labels. Keep small and reviewed.
"""

# Category tags: what kind of work the pain point is.
CATEGORIES = [
    "manual data entry",
    "document or report generation",
    "status summarization",
    "scheduling and coordination",
    "approvals and routing",
    "reconciliation",
    "search and retrieval",
    "data quality cleanup",
    "vendor and SaaS spend",
]

# AI levers: the mechanism by which AI would address it.
LEVERS = [
    "deflection",
    "drafting",
    "summarization",
    "extraction and structuring",
    "prediction and flagging",
    "scheduling optimization",
    "spend analysis",
    "search and retrieval",
    "reconciliation",
]

# P&L lines a savings hypothesis can hit (Stage 6).
PNL_LINES = ["labor", "vendor spend", "rework"]
