"""Lens demo orchestrator.

Runs the synthesis pipeline on synthetic interviews and prints the ranked,
de-duplicated, savings-mapped portfolio with provenance.

    python run_demo.py            # auto: live if ANTHROPIC_API_KEY is set, else mock
    python run_demo.py --mock     # force deterministic fixtures (no API)
    python run_demo.py --live     # force real Anthropic calls

Writes structured output to out/ for inspection or a dashboard.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lens.models import Function, Interview
from lens.llm import LLM, resolve_mode
from lens.extract import extract_all
from lens.dedup import deduplicate
from lens.savings import aggregate_and_size
from lens.score import score_portfolio
from lens.pipeline import default_org

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "out"


def load_functions() -> dict[str, Function]:
    raw = json.loads((DATA / "functions.json").read_text())
    return {f["function_id"]: Function(**f) for f in raw}


def load_interviews() -> list[Interview]:
    raw = json.loads((DATA / "interviews" / "interviews.json").read_text())
    return [Interview(**iv) for iv in raw]


def fmt_usd(n: float) -> str:
    return f"${n:,.0f}"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--mock", action="store_true", help="force mock fixtures")
    g.add_argument("--live", action="store_true", help="force live Anthropic calls")
    args = ap.parse_args()
    mode = "mock" if args.mock else "live" if args.live else "auto"
    resolved = resolve_mode(mode)

    functions = load_functions()
    interviews = load_interviews()
    fn_name = {fid: f.name for fid, f in functions.items()}
    llm = LLM(mode=mode)

    print("=" * 74)
    print(f"  LENS  |  synthesis demo  |  LLM mode: {resolved.upper()}")
    print("=" * 74)
    print(f"  {len(interviews)} interviews across {len(functions)} functions\n")

    # Stage 2 + 3: extract and tag
    pain_points = extract_all(interviews, llm)
    print(f"[Stage 2-3] Extracted {len(pain_points)} raw pain points (tagged on taxonomy)")
    for pp in pain_points:
        print(f"    {pp.pain_id:<12} {fn_name[pp.function_id]:<24} "
              f"[{pp.category_tags[0]} / {pp.ai_lever}]")
    print()

    # Stage 4: dedup + resolve overlap
    use_cases = deduplicate(pain_points, functions, llm)
    merged = sum(len(uc.member_pain_ids) for uc in use_cases) - len(use_cases)
    print(f"[Stage 4]   {len(pain_points)} pain points -> {len(use_cases)} canonical "
          f"use cases  ({merged} merged away)")
    for uc in use_cases:
        if len(uc.member_pain_ids) > 1:
            funcs = ", ".join(fn_name[f] for f in uc.affected_functions)
            tag = "CROSS-FUNCTION" if uc.cross_functional else "same-function"
            print(f"    MERGE {uc.use_case_id}: {uc.member_pain_ids}  [{tag}: {funcs}]")
    print()

    # Stage 5 + 6: aggregate + savings (the gate)
    aggregate_and_size(use_cases, pain_points, functions, default_org(functions))

    # Stage 7: score + prioritize
    ranked, gated = score_portfolio(use_cases, pain_points, functions)
    print(f"[Stage 6-7] Sized savings and scored. "
          f"{len(ranked)} ranked, {len(gated)} gated out (no savings hypothesis)\n")

    # Portfolio report
    print("=" * 74)
    print("  PRIORITIZED PORTFOLIO  (RICE: Reach x Impact x Confidence / Effort)")
    print("=" * 74)
    pp_by_id = {p.pain_id: p for p in pain_points}
    for uc in ranked:
        funcs = ", ".join(fn_name[f] for f in uc.affected_functions)
        flag = "  <REVIEW>" if uc.needs_review else ""
        print(f"\n  #{uc.priority_rank}  {uc.title}   "
              f"[RICE {uc.rice_score}]  {uc.quadrant}{flag}")
        print(f"      problem    : {uc.canonical_description}")
        print(f"      category   : {uc.category} / {uc.ai_lever}   -> P&L: {uc.p_and_l_line}")
        print(f"      reach      : {uc.reach} function(s) ({funcs}), "
              f"raised in {uc.prevalence_count} interview(s)"
              f"{'  [horizontal]' if uc.cross_functional else ''}")
        print(f"      savings/yr : low {fmt_usd(uc.est_savings_low)}  |  "
              f"base {fmt_usd(uc.est_savings_base)}  |  high {fmt_usd(uc.est_savings_high)}")
        print(f"      confidence : {uc.confidence} (unvalidated)   "
              f"feasibility {uc.feasibility_score}   effort ~{uc.effort_person_weeks}wk")
        # provenance drill-down
        print(f"      provenance :")
        for pid in uc.member_pain_ids:
            p = pp_by_id[pid]
            print(f"          {pid}  ({p.interview_id}, {fn_name[p.function_id]})  "
                  f"{p.time_cost_per_occurrence_min:.0f}min x {p.est_annual_volume:.0f}/yr")

    if gated:
        print("\n" + "-" * 74)
        print("  GATED OUT (no savings hypothesis, cannot be prioritized):")
        for uc in gated:
            print(f"    {uc.use_case_id} {uc.title}")

    total_base = sum(uc.est_savings_base for uc in ranked)
    print("\n" + "=" * 74)
    print(f"  TOTAL SIZED OPPORTUNITY (base, de-duplicated): {fmt_usd(total_base)}/yr")
    quick = [u for u in ranked if u.quadrant == "quick win"]
    print(f"  Quick wins (high value, high feasibility): "
          f"{', '.join(u.title for u in quick) or 'none'}")
    print("=" * 74)

    # write structured artifacts
    OUT.mkdir(exist_ok=True)
    (OUT / "pain_points.json").write_text(
        json.dumps([p.to_dict() for p in pain_points], indent=2))
    (OUT / "use_cases.json").write_text(
        json.dumps([u.to_dict() for u in (ranked + gated)], indent=2))
    print(f"\n  Wrote out/pain_points.json and out/use_cases.json")


if __name__ == "__main__":
    main()
