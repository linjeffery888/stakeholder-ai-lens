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
import base64
import hmac
import json
import os
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lens.models import Function, Interview, Organization
from lens.llm import LLM, resolve_mode
from lens.pipeline import run_pipeline, default_org
from lens.ingest import ingest

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

    def __init__(self, mode: str, transcripts: str | None = None,
                 load_cache: bool = False):
        self.mode = mode
        self.functions = load_functions()
        self.transcripts = transcripts
        self.load_cache = load_cache
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self.functions = load_functions()
            if self.transcripts:
                res = ingest(self.transcripts, self.functions)
                self.functions = res.functions
                self.interviews = res.interviews
            else:
                self.interviews = load_base_interviews()
            self.pp_cache = {}
            self._next = 100
            self.org = default_org(self.functions)
            # dirty = the portfolio needs (re)computing. A cached result is
            # served as-is until an interview/org change marks it dirty, so a
            # page load never re-runs the expensive live dedup pass.
            self.last_result = self._load_cached_result() if self.load_cache else None
            self.dirty = self.last_result is None

    def _load_cached_result(self):
        f = ROOT / "out" / "last_portfolio.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                return None
        return None

    def ingest_path(self, path: str) -> dict:
        """Load a folder or .txt/.docx/.csv file of interviews into the session,
        appended to whatever is already loaded."""
        with self.lock:
            res = ingest(path, self.functions)
            self.functions = res.functions
            existing = {iv.interview_id for iv in self.interviews}
            added = 0
            for iv in res.interviews:
                if iv.interview_id in existing:
                    iv.interview_id = f"{iv.interview_id}-dup"
                self.interviews.append(iv)
                added += 1
            self.dirty = True
            return {
                "ingested": added,
                "added_function_ids": res.added_function_ids,
                "skipped": res.skipped,
                "total_interviews": len(self.interviews),
            }

    def set_org(self, fields: dict):
        with self.lock:
            o = self.org
            if "company_name" in fields:
                o.company_name = str(fields["company_name"])[:120]
            if fields.get("total_headcount") not in (None, ""):
                o.total_headcount = max(0, int(float(fields["total_headcount"])))
            if isinstance(fields.get("spend_lines"), list):
                lines = []
                for l in fields["spend_lines"]:
                    label = str(l.get("label", "")).strip()[:80]
                    amt = l.get("annual_spend")
                    if label and amt not in (None, ""):
                        lines.append({"label": label, "annual_spend": max(0.0, float(amt))})
                o.spend_lines = lines
            o.source = fields.get("source", "manual")
            o.confidence = float(fields.get("confidence", 1.0))
            o.notes = str(fields.get("notes", ""))[:600]
            self.dirty = True

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
            self.dirty = True
            return iv.interview_id

    def portfolio(self) -> dict:
        with self.lock:
            # serve the cached result unless something changed
            if not self.dirty and self.last_result is not None:
                return self.last_result
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
            self.dirty = False
            # keep out/ files in sync so the data can be taken away, and persist
            # the full result so it can be reloaded instantly on restart
            OUT = ROOT / "out"
            OUT.mkdir(exist_ok=True)
            (OUT / "use_cases.json").write_text(
                json.dumps(result["ranked"] + result["gated"], indent=2))
            (OUT / "pain_points.json").write_text(
                json.dumps(result["pain_points"], indent=2))
            (OUT / "last_portfolio.json").write_text(json.dumps(result))
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

# Optional HTTP Basic Auth. When LENS_BASIC_USER is set, every request must
# carry matching credentials. Use this whenever the instance is public AND in
# live mode, so strangers cannot spend your API budget.
BASIC_USER = os.environ.get("LENS_BASIC_USER", "")
BASIC_PASS = os.environ.get("LENS_BASIC_PASS", "")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def _auth_failed(self) -> bool:
        if not BASIC_USER:
            return False  # auth disabled
        expected = "Basic " + base64.b64encode(
            f"{BASIC_USER}:{BASIC_PASS}".encode()).decode()
        got = self.headers.get("Authorization", "")
        if hmac.compare_digest(got, expected):
            return False
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Lens"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

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
        if self._auth_failed():
            return
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
        if self._auth_failed():
            return
        length = int(self.headers.get("Content-Length", 0))
        if length > 96 * 1024 * 1024:
            return self._json(413, {"error": "upload too large (96MB limit)"})
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

        if self.path == "/api/ingest":
            path = (payload.get("path") or "").strip()
            if not path:
                return self._json(400, {"error": "path required (folder or "
                                                 ".txt/.docx/.csv file)"})
            try:
                summary = SESSION.ingest_path(path)
                result = SESSION.portfolio()
                result["ingest_summary"] = summary
                return self._json(200, result)
            except FileNotFoundError as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if self.path == "/api/upload":
            files = payload.get("files") or []
            if not files:
                return self._json(400, {"error": "no files provided"})
            tmp = tempfile.mkdtemp(prefix="lens_up_")
            try:
                written = 0
                for f in files:
                    name = os.path.basename(str(f.get("name", "")).strip())
                    b64 = f.get("b64", "")
                    if not name or not b64:
                        continue
                    try:
                        data = base64.b64decode(b64)
                    except Exception:
                        continue
                    with open(os.path.join(tmp, name), "wb") as fh:
                        fh.write(data)
                    written += 1
                if not written:
                    return self._json(400, {"error": "no readable files in upload"})
                summary = SESSION.ingest_path(tmp)
                result = SESSION.portfolio()
                result["ingest_summary"] = summary
                return self._json(200, result)
            except FileNotFoundError as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:
                return self._json(500, {"error": str(e)})
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        if self.path == "/api/reset":
            SESSION.reset()
            return self._json(200, SESSION.portfolio())

        return self._send(404, "not found", "text/plain")


def main():
    global SESSION
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")),
                    help="port (default: $PORT or 8000)")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                    help="bind address (use 0.0.0.0 when hosting; default: $HOST or 127.0.0.1)")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--transcripts", metavar="PATH",
                    help="ingest a folder or .txt/.docx/.csv file of interviews "
                         "at startup instead of the built-in demo set")
    ap.add_argument("--load-cache", action="store_true",
                    help="serve the last saved portfolio (out/last_portfolio.json) "
                         "instantly on startup instead of recomputing")
    args = ap.parse_args()
    mode = "mock" if args.mock else "live" if args.live else os.environ.get("LENS_MODE", "auto")
    resolved = resolve_mode(mode)
    SESSION = Session(mode=mode, transcripts=args.transcripts,
                      load_cache=args.load_cache or os.environ.get("LENS_LOAD_CACHE") == "1")
    if args.transcripts:
        print(f"  Loaded {len(SESSION.interviews)} interviews from {args.transcripts}")

    where = "0.0.0.0" if args.host in ("0.0.0.0", "::") else args.host
    print("=" * 60)
    print(f"  Lens dashboard  |  LLM mode: {resolved.upper()}")
    print(f"  Binding {args.host}:{args.port}"
          + (f"  (local: http://localhost:{args.port})" if where != "0.0.0.0" else ""))
    print(f"  Basic auth: {'ON' if BASIC_USER else 'off'}")
    print("=" * 60)
    if resolved == "mock":
        print("  (mock mode: deterministic fixtures. Set ANTHROPIC_API_KEY for")
        print("   real extraction. On a host, set it as an env var, not in code.)")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
