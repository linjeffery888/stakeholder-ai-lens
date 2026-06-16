"""Ingestion: turn raw interview files into Interview objects.

Supported inputs (point at a single file or a whole folder):
  - .txt / .md   one transcript per file (clean or messy notes format)
  - .docx        one transcript per file (parsed with stdlib, no extra deps)
  - .csv         bulk: one row per interview, with a raw_notes column

Function mapping: each transcript names its function in the header. We map that
name to a function_id from functions.json. If a transcript names a function we
do not have on file, we auto-register a lightweight Function (flagged) so the
pipeline still runs rather than dropping the interview. Real cost numbers for a
new function can be filled in later.

Stdlib only, to match the rest of the project. No em-dashes.
"""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .models import Function, Interview

TEXT_EXTS = {".txt", ".md", ".text"}
DOCX_EXT = ".docx"
CSV_EXT = ".csv"

# index/manifest files that are not transcripts
SKIP_NAMES = {"_index.csv", "index.csv", "_readme.md", "readme.md"}


@dataclass
class IngestResult:
    interviews: list
    functions: dict           # function_id -> Function (incl. any auto-added)
    added_function_ids: list  # function_ids we had to create on the fly
    skipped: list             # (filename, reason) for anything we could not parse


# ---------------------------------------------------------------------------
# Function-name resolution
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    """Normalize a function name for fuzzy matching: lowercase, drop the
    parenthetical, collapse separators."""
    name = re.sub(r"\(.*?\)", "", name or "")
    name = name.lower().replace("&", "and")
    name = re.sub(r"[^a-z0-9]+", " ", name).strip()
    return name


def _slug_id(name: str) -> str:
    base = _norm(name).replace(" ", "-")
    return f"FN-{base}"[:48] or "FN-unknown"


class FunctionResolver:
    """Maps a free-text function name (or function_id) to a Function, creating
    a placeholder if we have never seen it."""

    def __init__(self, functions: dict):
        self.functions = dict(functions)
        self.added: list = []
        self._by_id = {fid: f for fid, f in self.functions.items()}
        self._by_norm = {_norm(f.name): fid for fid, f in self.functions.items()}

    def resolve(self, raw: str) -> str:
        raw = (raw or "").strip()
        if not raw:
            return self._placeholder("Unspecified")
        # exact function_id?
        if raw in self._by_id:
            return raw
        # normalized name match
        fid = self._by_norm.get(_norm(raw))
        if fid:
            return fid
        # substring match either direction (handles "QA" vs "Quality Assurance")
        nraw = _norm(raw)
        for nname, fid in self._by_norm.items():
            if nraw and (nraw in nname or nname in nraw):
                return fid
        return self._placeholder(raw)

    def _placeholder(self, name: str) -> str:
        fid = _slug_id(name)
        n = 2
        while fid in self._by_id and self._by_id[fid].name != name:
            fid = f"{_slug_id(name)}-{n}"
            n += 1
        if fid not in self._by_id:
            f = Function(
                function_id=fid,
                name=name,
                description="(auto-registered from ingest; fill in cost basis)",
                headcount=10,
                est_annual_cost_base=10 * 50 * 2080,
                avg_fully_loaded_hourly=50.0,
            )
            self.functions[fid] = f
            self._by_id[fid] = f
            self._by_norm[_norm(name)] = fid
            self.added.append(fid)
        return fid


# ---------------------------------------------------------------------------
# Header parsing for .txt / .docx transcripts
# ---------------------------------------------------------------------------

_FIELD_RE = re.compile(
    r"^(interview id|interviewee|title|role|function|date|interviewer)\s*[:]\s*(.+)$",
    re.IGNORECASE,
)
# messy header line 1:  "Function name // Stakeholder (Role)"
_MESSY_HEAD = re.compile(r"^(.*?)\s*//\s*(.*?)\s*\((.*?)\)\s*$")
# messy header line 2:  "2026-06-11 - interviewer - INT-005"
_MESSY_META = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*-\s*(.*?)\s*-\s*(INT-\d+)\s*$",
                         re.IGNORECASE)


def parse_transcript_text(text: str, fallback_id: str = "") -> dict:
    """Pull metadata + raw_notes out of a transcript string. Tolerant of both
    the clean (labelled) and messy (shorthand) layouts the generator emits, and
    of arbitrary plain notes (everything becomes raw_notes)."""
    meta = {"interview_id": "", "function": "", "stakeholder": "",
            "role": "", "date": "", "raw_notes": ""}

    lines = text.splitlines()

    # messy layout: detect the "A // B (C)" first content line
    for ln in lines[:4]:
        m = _MESSY_HEAD.match(ln.strip())
        if m:
            meta["function"] = m.group(1).strip()
            meta["stakeholder"] = m.group(2).strip()
            meta["role"] = m.group(3).strip()
            break

    body_start = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        fm = _FIELD_RE.match(s)
        if fm:
            key = fm.group(1).lower()
            val = fm.group(2).strip()
            if key == "interview id":
                meta["interview_id"] = val
            elif key == "interviewee":
                meta["stakeholder"] = val
            elif key == "title" or key == "role":
                meta["role"] = val
            elif key == "function":
                meta["function"] = val
            elif key == "date":
                meta["date"] = val
            body_start = i + 1
            continue
        mm = _MESSY_META.match(s)
        if mm:
            meta["date"] = meta["date"] or mm.group(1)
            meta["interview_id"] = meta["interview_id"] or mm.group(3).upper()
            body_start = i + 1

    # raw_notes = everything after the header block, minus pure separator lines
    body = []
    for ln in lines[body_start:]:
        if set(ln.strip()) <= {"-", "=", " "} and ln.strip():
            continue
        body.append(ln)
    raw_notes = "\n".join(body).strip()
    # if header parsing found nothing useful, keep the whole text as notes
    if not raw_notes:
        raw_notes = text.strip()
    meta["raw_notes"] = raw_notes

    if not meta["interview_id"]:
        meta["interview_id"] = fallback_id
    return meta


# ---------------------------------------------------------------------------
# .docx text extraction (stdlib: docx is a zip of XML)
# ---------------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_to_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(f"{_W}p"):
        runs = [t.text for t in p.iter(f"{_W}t") if t.text]
        paras.append("".join(runs))
    return "\n".join(paras)


# ---------------------------------------------------------------------------
# Top-level ingest
# ---------------------------------------------------------------------------

def _interview_from_meta(meta: dict, resolver: FunctionResolver) -> Interview:
    return Interview(
        interview_id=meta.get("interview_id") or "",
        function_id=resolver.resolve(meta.get("function") or meta.get("function_id", "")),
        raw_notes=meta.get("raw_notes", ""),
        stakeholder=meta.get("stakeholder", ""),
        role=meta.get("role", ""),
        seniority=meta.get("seniority", ""),
        date=meta.get("date", ""),
        status="captured",
    )


def _ingest_csv(path: Path, resolver: FunctionResolver, out: list, skipped: list):
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        cols = {c.lower().strip(): c for c in (reader.fieldnames or [])}
        notes_col = next((cols[k] for k in
                          ("raw_notes", "notes", "transcript", "raw notes", "body")
                          if k in cols), None)
        if not notes_col:
            skipped.append((path.name,
                            "csv has no raw_notes/notes/transcript column"))
            return
        fn_col = next((cols[k] for k in
                       ("function", "function_id", "department", "function name")
                       if k in cols), None)
        for i, row in enumerate(reader, 1):
            notes = (row.get(notes_col) or "").strip()
            if not notes:
                continue
            meta = {
                "interview_id": (row.get(cols.get("interview_id", "")) or "").strip()
                                or f"{path.stem}-{i:03d}",
                "function": (row.get(fn_col) if fn_col else "") or "",
                "stakeholder": (row.get(cols.get("stakeholder", "")) or "").strip(),
                "role": (row.get(cols.get("role", "")) or row.get(cols.get("title", ""))
                         or "").strip() if (cols.get("role") or cols.get("title")) else "",
                "date": (row.get(cols.get("date", "")) or "").strip(),
                "raw_notes": notes,
            }
            out.append(_interview_from_meta(meta, resolver))


def _ingest_one_file(path: Path, resolver: FunctionResolver, out: list, skipped: list):
    ext = path.suffix.lower()
    try:
        if ext == CSV_EXT:
            _ingest_csv(path, resolver, out, skipped)
        elif ext == DOCX_EXT:
            text = docx_to_text(path)
            meta = parse_transcript_text(text, fallback_id=path.stem)
            out.append(_interview_from_meta(meta, resolver))
        elif ext in TEXT_EXTS:
            text = path.read_text(errors="replace")
            meta = parse_transcript_text(text, fallback_id=path.stem)
            out.append(_interview_from_meta(meta, resolver))
        else:
            skipped.append((path.name, f"unsupported extension {ext}"))
    except Exception as e:  # one bad file should not sink the batch
        skipped.append((path.name, f"parse error: {e}"))


def ingest(path, functions: dict) -> IngestResult:
    """Ingest a file or a folder into Interview objects.

    functions: existing {function_id: Function} (from functions.json). Returned
    result includes any functions auto-registered for names we did not know.
    """
    p = Path(path)
    resolver = FunctionResolver(functions)
    out: list = []
    skipped: list = []

    if p.is_dir():
        files = sorted(
            f for f in p.iterdir()
            if f.is_file() and f.name.lower() not in SKIP_NAMES
            and f.suffix.lower() in (TEXT_EXTS | {DOCX_EXT, CSV_EXT})
            and not f.name.startswith("~$")
        )
        if not files:
            raise FileNotFoundError(f"no ingestible files in {p}")
        for f in files:
            _ingest_one_file(f, resolver, out, skipped)
    elif p.is_file():
        _ingest_one_file(p, resolver, out, skipped)
    else:
        raise FileNotFoundError(f"no such path: {p}")

    # de-duplicate interview_ids so downstream caches stay stable
    seen: dict = {}
    for iv in out:
        base = iv.interview_id or "INT"
        iid = base
        n = 2
        while iid in seen:
            iid = f"{base}-{n}"
            n += 1
        seen[iid] = True
        iv.interview_id = iid

    return IngestResult(
        interviews=out,
        functions=resolver.functions,
        added_function_ids=resolver.added,
        skipped=skipped,
    )
