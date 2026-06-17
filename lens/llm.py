"""LLM access for extraction (Stage 2) and dedup adjudication (Stage 4).

Two backends behind one interface:
  - live: real Anthropic API (claude-haiku-4-5), structured JSON out.
  - mock: deterministic fixtures, so the demo runs end-to-end with no API key.

Pick with mode="live" | "mock" | "auto" (auto -> live if a key is present).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

MODEL = "claude-haiku-4-5"
_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data"


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a local, git-ignored .env into the environment
    so live mode turns on automatically. Real env vars take precedence."""
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        # fill if unset OR present-but-blank (some shells export an empty var);
        # a real non-empty value already in the environment still wins.
        if not os.environ.get(key):
            os.environ[key] = val.strip().strip('"').strip("'")


_load_dotenv()


def have_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def resolve_mode(mode: str) -> str:
    if mode == "auto":
        return "live" if have_key() else "mock"
    return mode


def _extract_json(text: str):
    """Pull the first JSON value out of a model response."""
    text = text.strip()
    # strip code fences if present
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = min([i for i in (text.find("["), text.find("{")) if i != -1])
    depth, in_str, esc, open_c = 0, False, False, text[start]
    close_c = "]" if open_c == "[" else "}"
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    return json.loads(text[start:])


class LLM:
    def __init__(self, mode: str = "auto"):
        self.mode = resolve_mode(mode)
        self._client = None
        self._mock_extractions = None

    # ---- live client (lazy) ----
    def _client_or_init(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def _call(self, system: str, user: str, max_tokens: int = 2000) -> str:
        msg = self._client_or_init().messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text

    # ---- Stage 2: extraction ----
    def extract_pain_points(self, interview: dict, taxonomy: dict) -> list:
        if self.mode == "mock":
            fixtures = self._mock_extract(interview["interview_id"])
            if fixtures:
                return fixtures
            # interview not in fixtures (e.g. pasted live in the dashboard):
            # fall back to a keyword-based extractor so the demo still flows.
            return self._mock_extract_freeform(interview["raw_notes"])
        system = (
            "You extract distinct operational pain points from a stakeholder "
            "interview note. Return ONLY valid JSON: an array of objects. No prose.\n"
            "Each object has keys: title (a short label, max 5 words), "
            "description, workflow (short, max 6 words), "
            "time_cost_per_occurrence_min (number), est_annual_volume (number), "
            "severity (low|med|high), ai_addressability (low|med|high), "
            "category_tags (array, choose only from CATEGORIES), "
            "ai_lever (choose only from LEVERS).\n"
            f"CATEGORIES: {taxonomy['categories']}\n"
            f"LEVERS: {taxonomy['levers']}\n"
            "Tagging guidance: when work is about assembling or compiling a "
            "status picture from multiple systems or sources, tag it "
            "'status summarization' with lever 'summarization', whichever "
            "function it occurs in, so the same problem is comparable across "
            "functions.\n"
            "One object per distinct problem. Estimate numbers from the note; "
            "if unstated, give a reasonable estimate."
        )
        user = (
            f"Function: {interview['function_id']}\n"
            f"Interview: {interview['interview_id']}\n\n"
            f"Notes:\n{interview['raw_notes']}"
        )
        return _extract_json(self._call(system, user))

    # ---- assistive org research (suggestions only, never auto-applied) ----
    def research_org(self, company_name: str) -> dict:
        """Estimate org economics for a company. Live: Claude with web search.
        Returns {total_headcount, spend_lines:[{label,annual_spend}], rationale,
        sources, confidence, web}. These are SUGGESTIONS to be human-confirmed."""
        name = (company_name or "").strip()
        if not name:
            return {"error": "no company name"}
        if self.mode == "mock":
            return self._mock_research(name)
        system = (
            "You research a company's size and its ADDRESSABLE DISCRETIONARY "
            "SPEND for an AI cost-savings estimate. Return ONLY JSON: "
            "{\"total_headcount\": int, "
            "\"spend_lines\": [{\"label\": str, \"annual_spend\": int_USD}], "
            "\"rationale\": str, \"sources\": [{\"title\":str,\"url\":str}], "
            "\"confidence\": 0-1}. Find current headcount.\n"
            "CRITICAL: spend_lines must be ONLY the discretionary spend a software/"
            "vendor-rationalization tool could realistically touch: SaaS & software, "
            "cloud infrastructure, discretionary/professional-services vendors, "
            "contingent labor, subscriptions. A common benchmark for software is "
            "$7,000-$12,000 per employee/yr if no figure is found.\n"
            "DO NOT include total operating expense, total SG&A, R&D / clinical-trial "
            "costs, payroll/salaries, or COGS/manufacturing materials. Those are NOT "
            "addressable by spend rationalization and would massively overstate the "
            "opportunity. This is the addressable pool, not the P&L.\n"
            "For private companies data is uncertain, so lower the confidence and say "
            "so in the rationale. Estimate, never invent precision."
        )
        try:
            msg = self._client_or_init().messages.create(
                model=MODEL, max_tokens=1500,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                system=system,
                messages=[{"role": "user", "content": f"Company: {name}"}],
            )
            text = "".join(getattr(b, "text", "") for b in msg.content
                           if getattr(b, "type", None) == "text")
            data = _extract_json(text)
            data["web"] = True
            return data
        except Exception:
            # web search unavailable: estimate from the model's own knowledge
            try:
                text = self._call(
                    system + " You have NO web access; estimate from general "
                    "knowledge and set confidence accordingly.",
                    f"Company: {name}", max_tokens=700)
                data = _extract_json(text)
                data["web"] = False
                return data
            except Exception as e:
                return {"error": f"research failed: {e}"}

    def _mock_research(self, name: str) -> dict:
        return {
            "total_headcount": 250,
            "spend_lines": [
                {"label": "SaaS & software", "annual_spend": 2000000},
                {"label": "Contingent labor / vendors", "annual_spend": 1200000},
            ],
            "rationale": f"(mock) illustrative estimate for {name}; no live lookup "
                         "in offline mode. Run --live with a key for web research.",
            "sources": [],
            "confidence": 0.25,
            "web": False,
        }

    def _mock_extract(self, interview_id: str) -> list:
        if self._mock_extractions is None:
            path = _DATA / "mock_extractions.json"
            self._mock_extractions = json.loads(path.read_text())
        return self._mock_extractions.get(interview_id, [])

    # keyword -> (category, lever) for the offline freeform fallback
    _KW = [
        (("status", "summary", "summariz", "compile", "assemble", "dashboard"),
         "status summarization", "summarization"),
        (("reconcil", "variance", "match", "tie out", "ties"),
         "reconciliation", "reconciliation"),
        (("draft", "letter", "memo", "write", "appeal", "report"),
         "document or report generation", "drafting"),
        (("search", "find", "look up", "lookup", "retriev", "sop", "policy", "document"),
         "search and retrieval", "search and retrieval"),
        (("schedul", "coordinat", "calendar", "book"),
         "scheduling and coordination", "scheduling optimization"),
        (("invoice", "vendor", "spend", "license", "subscription"),
         "vendor and SaaS spend", "spend analysis"),
        (("data entry", "enter", "copy", "manual"),
         "manual data entry", "extraction and structuring"),
    ]

    # lines that are scaffolding/metadata, not pain content
    _SKIP_MARKERS = (
        "format:", "interview id", "interviewee", "interviewer", "date:",
        "title:", "function:", "background", "current role", "pain point",
        "where time goes", "closing note", "===", "---",
    )

    def _mock_extract_freeform(self, notes: str) -> list:
        """Very rough offline extractor: split the note into sentences and turn
        each substantive one into a pain point with a keyword-guessed tag.
        Only used in mock mode for interviews not in the fixtures.

        Focuses on the pain-points section when the note has one, and skips
        header/heading/metadata lines so the offline demo stays sensible."""
        text = notes.strip()
        low_all = text.lower()
        idx = low_all.find("pain point")
        if idx >= 0:
            nl = text.find("\n", idx)
            region = text[nl + 1:] if nl >= 0 else text[idx:]
            for stop in ("closing note", "\nclosing", "\n----"):
                cut = region.lower().find(stop)
                if cut >= 0:
                    region = region[:cut]
        else:
            region = text
        # drop scaffolding lines and leading bullet/number markers
        kept = []
        for ln in region.splitlines():
            s = ln.strip()
            low = s.lower()
            if not s or set(s) <= {"-", "=", " "}:
                continue
            if any(low.startswith(m) or low == m.strip(":") for m in self._SKIP_MARKERS):
                continue
            s = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", s)
            if s:
                kept.append(s)
        region = " ".join(kept)

        out = []
        for sent in re.split(r"(?<=[.!?])\s+", region.strip()):
            s = sent.strip()
            if len(s) < 25:
                continue
            low = s.lower()
            cat, lever = "manual data entry", "extraction and structuring"
            for kws, c, l in self._KW:
                if any(k in low for k in kws):
                    cat, lever = c, l
                    break
            mins = 30
            mm = re.search(r"(\d+)\s*(?:min|minute)", low)
            if mm:
                mins = int(mm.group(1))
            elif re.search(r"\bhour\b|\bhrs?\b", low):
                mins = 60
            vol = 1000
            vm = re.search(r"(\d[\d,]{2,})", low)
            if vm:
                vol = int(vm.group(1).replace(",", ""))
            words = s.split()
            out.append({
                "title": " ".join(words[:4]),
                "description": s,
                "workflow": " ".join(words[:6]),
                "time_cost_per_occurrence_min": mins,
                "est_annual_volume": vol,
                "severity": "med",
                "ai_addressability": "med",
                "category_tags": [cat],
                "ai_lever": lever,
            })
        return out[:5]

    # ---- Stage 4: match a new pain point against existing canonicals ----
    def best_match(self, new_desc: str, candidates: list) -> dict:
        """candidates: list of {"id": str, "desc": str}. Returns
        {match_id: str|None, confidence: 0-1, reason: str}. Robust to tagging
        drift: judges the underlying problem, not the labels."""
        if not candidates:
            return {"match_id": None, "confidence": 0.0, "reason": "no candidates"}
        if self.mode == "mock":
            best = {"match_id": None, "confidence": 0.0, "reason": "no match"}
            for c in candidates:
                v = self._mock_adjudicate(new_desc, c["desc"])
                if v.get("match") and v["confidence"] > best["confidence"]:
                    best = {"match_id": c["id"], "confidence": v["confidence"],
                            "reason": v["reason"]}
            return best
        listing = "\n".join(f'{i}. [{c["id"]}] {c["desc"]}'
                            for i, c in enumerate(candidates))
        system = (
            "You match a NEW operational pain point against a list of EXISTING "
            "canonical use cases. Pick the one that is the SAME SPECIFIC problem "
            "such that ONE solution would fix BOTH with little adaptation, or "
            "null.\n"
            "MATCH: the same mechanism on the same kind of work, even in "
            "different departments (e.g. assembling a status summary from "
            "multiple systems in patient services vs manufacturing).\n"
            "DO NOT MATCH merely because both involve multiple systems or manual "
            "effort. Reconciliation, status summarization, document drafting, "
            "search, and spend analysis are DIFFERENT problems and never match "
            "each other. When in doubt, return null.\n"
            "confidence is your certainty they are the same problem.\n"
            'Return ONLY JSON: {"match_id": "<id>" or null, "confidence": 0-1, '
            '"reason": "..."}.'
        )
        user = f"NEW: {new_desc}\n\nEXISTING:\n{listing}"
        out = _extract_json(self._call(system, user, max_tokens=400))
        return {
            "match_id": out.get("match_id"),
            "confidence": float(out.get("confidence", 0) or 0),
            "reason": out.get("reason", ""),
        }

    def _mock_adjudicate(self, desc_a: str, desc_b: str) -> dict:
        """Keyword-overlap heuristic standing in for the live model."""
        def toks(s):
            return set(re.findall(r"[a-z]{4,}", s.lower()))
        stop = {"from", "into", "across", "every", "their", "that", "this",
                "with", "each", "than", "them", "they", "have", "data", "time"}
        a, b = toks(desc_a) - stop, toks(desc_b) - stop
        jac = len(a & b) / max(1, len(a | b))
        signal_pairs = [
            ({"status", "summary", "compile", "assemble", "summarization"}, 0.55),
            ({"reconcil", "variance", "ties", "balances"}, 0.55),
            ({"appeal", "letter"}, 0.55),
        ]
        boost = 0.0
        for sig, w in signal_pairs:
            if any(any(s in t for s in sig) for t in a) and any(
                any(s in t for s in sig) for t in b
            ):
                boost += w
        conf = min(0.97, jac + boost)
        return {
            "match": conf >= 0.45,
            "confidence": round(conf, 2),
            "reason": "keyword + signal overlap (mock adjudicator)",
        }
