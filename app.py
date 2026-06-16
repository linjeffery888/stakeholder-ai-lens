"""Lens dashboard server (Python stdlib only).

    python app.py                 # auto mode (live if ANTHROPIC_API_KEY set, else mock)
    LENS_MODE=mock python app.py  # force mock
    python app.py --port 8000

Then open http://localhost:8000 in a browser. You get the prioritized
portfolio, a value/feasibility 2x2, provenance drill-down, and an input area to
paste a new interview note and watch it fold into the model live.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lens.models import Function, Interview, Organization
from lens.llm import LLM, resolve_mode
from lens.pipeline import run_pipeline, default_org

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATIC = ROOT / "static"


def load_functions() -> dict[str, Function]:
    raw = json.loads((DATA / "functions.json").read_text())
    return {f["function_id"]: Function(**f) for f in raw}


def load_base_interviews() -> list[Interview]:
    raw = json.loads((DATA / "interviews" / "interviews.json").read_text())
    return [Interview(**iv) for iv in raw]


class Session:
    """In-memory state for the dashboard. Single shared session for the demo."""

    def __init__(self, mode: str):
        self.mode = mode
        self.functions = load_functions()
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self.interviews = load_base_interviews()
            self.pp_cache: dict = {}
            self._next = 100
            self.last_result = None
            self.org = default_org(self.functions)

    def set_org(self, fields: dict):
        with self.lock:
            o = self.org
            if "company_name" in fields:
                o.company_name = str(fields["company_name"])[:120]
            if fields.get("total_headcount") not in (None, ""):
                o.total_headcount = max(0, int(float(fields["total_headcount"])))
            if fields.get("annual_saas_spend") not in (None, ""):
                o.annual_saas_spend = max(0.0, float(fields["annual_saas_spend"]))
            o.source = fields.get("source", "manual")
            o.confidence = float(fields.get("confidence", 1.0))
            o.notes = str(fields.get("notes", ""))[:600]

    def research(self, company_name: str) -> dict:
        return LLM(mode=self.mode).research_org(company_name)

    def add_interview(self, function_id: str, raw_notes: str,
                      stakeholder: str = "", role: str = ""):
        with self.lock:
            self._next += 1
            iv = Interview(
                interview_id=f"INT-{self._next}",
                function_id=function_id,
                raw_notes=raw_notes,
                stakeholder=stakeholder or "New stakeholder",
                role=role or "",
                status="captured",
            )
            self.interviews.append(iv)
            return iv.interview_id

    def portfolio(self) -> dict:
        with self.lock:
            llm = LLM(mode=self.mode)
            result = run_pipeline(self.interviews, self.functions, llm,
                                  pp_cache=self.pp_cache, org=self.org)
            result["interview_list"] = [
                {"interview_id": iv.interview_id,
                 "function": self.functions[iv.function_id].name,
                 "stakeholder": iv.stakeholder}
                for iv in self.interviews
            ]
            result["function_options"] = [
                {"function_id": fid, "name": f.name}
                for fid, f in self.functions.items()
            ]
            self.last_result = result
            # keep out/ files in sync so the data can be taken away
            OUT = ROOT / "out"
            OUT.mkdir(exist_ok=True)
            (OUT / "use_cases.json").write_text(
                json.dumps(result["ranked"] + result["gated"], indent=2))
            (OUT / "pain_points.json").write_text(
                json.dumps(result["pain_points"], indent=2))
            return result


CSV_COLS = [
    ("priority_rank", "rank"), ("use_case_id", "use_case_id"), ("title", "title"),
    ("category", "category"), ("ai_lever", "ai_lever"),
    ("cross_functional", "cross_functional"), ("reach", "reach_functions"),
    ("prevalence_count", "interviews_raised"), ("p_and_l_line", "p_and_l_line"),
    ("addressable_hours_year", "addressable_hours_year"),
    ("est_savings_low", "savings_low"), ("est_savings_base", "savings_base"),
    ("est_savings_high", "savings_high"), ("confidence", "confidence"),
    ("feasibility_score", "feasibility"), ("effort_person_weeks", "effort_weeks"),
    ("rice_score", "rice_score"), ("quadrant", "quadrant"),
    ("needs_review", "needs_review"),
]


def portfolio_csv(result: dict) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([h for _, h in CSV_COLS] + ["affected_functions", "member_pain_ids"])
    for uc in result["ranked"] + result["gated"]:
        row = [uc.get(k, "") for k, _ in CSV_COLS]
        row.append("; ".join(uc.get("affected_function_names", [])))
        row.append("; ".join(uc.get("member_pain_ids", [])))
        w.writerow(row)
    return buf.getvalue()


SESSION: Session | None = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_text()
            return self._send(200, html, "text/html; charset=utf-8")
        if self.path == "/api/functions":
            return self._json(200, [
                {"function_id": fid, "name": f.name}
                for fid, f in SESSION.functions.items()
            ])
        if self.path == "/api/portfolio":
            try:
                return self._json(200, SESSION.portfolio())
            except Exception as e:
                return self._json(500, {"error": str(e)})
        if self.path in ("/api/export.csv", "/api/export.json"):
            try:
                result = SESSION.last_result or SESSION.portfolio()
            except Exception as e:
                return self._json(500, {"error": str(e)})
            if self.path.endswith(".csv"):
                body = portfolio_csv(result).encode()
                ctype = "text/csv"
                fname = "lens_portfolio.csv"
            else:
                body = json.dumps(result, indent=2).encode()
                ctype = "application/json"
                fname = "lens_portfolio.json"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid JSON"})

        if self.path == "/api/interview":
            notes = (payload.get("raw_notes") or "").strip()
            fid = payload.get("function_id")
            if not notes or fid not in SESSION.functions:
                return self._json(400, {"error": "need raw_notes and a valid function_id"})
            try:
                iid = SESSION.add_interview(
                    fid, notes, payload.get("stakeholder", ""), payload.get("role", ""))
                result = SESSION.portfolio()
                result["added_interview_id"] = iid
                return self._json(200, result)
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if self.path == "/api/org":
            try:
                SESSION.set_org(payload)
                return self._json(200, SESSION.portfolio())
            except (ValueError, TypeError) as e:
                return self._json(400, {"error": f"invalid org fields: {e}"})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if self.path == "/api/research":
            name = (payload.get("company_name") or "").strip()
            if not name:
                return self._json(400, {"error": "company_name required"})
            try:
                return self._json(200, SESSION.research(name))
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if self.path == "/api/reset":
            SESSION.reset()
            return self._json(200, SESSION.portfolio())

        return self._send(404, "not found", "text/plain")


def main():
    global SESSION
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    mode = "mock" if args.mock else "live" if args.live else os.environ.get("LENS_MODE", "auto")
    resolved = resolve_mode(mode)
    SESSION = Session(mode=mode)

    print("=" * 60)
    print(f"  Lens dashboard  |  LLM mode: {resolved.upper()}")
    print(f"  Open  ->  http://localhost:{args.port}")
    print("=" * 60)
    if resolved == "mock":
        print("  (mock mode: deterministic fixtures. New interviews you paste")
        print("   in will extract via the mock heuristic. Start with --live and")
        print("   a real ANTHROPIC_API_KEY for real extraction.)")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
