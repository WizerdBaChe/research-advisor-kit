#!/usr/bin/env python3
r"""Index a local PDF library so P2 can rank it before touching the web.

WHY AN INDEX AND NOT A GLOB. SKILL.md P2 says to inventory a PDF folder before
extracting, and `search-sources.md` spells out the procedure — but doing it by
reading page 1 of every candidate costs a full-text read per file just to learn
what the file IS. For a Zotero-managed library that is pure waste: the filename
already carries author, year and title, and one cheap pass turns the whole
folder into a searchable table. Extraction then opens only the PDFs the P1
target list actually needs.

WHAT IT DOES NOT DO. It does not read PDF content, does not resolve DOIs, and
does not claim its metadata is authoritative. A filename is a convenience, not a
citation: anything that reaches a deliverable still goes through identifier
resolution (P2) and the P4.5 support-span check. The index answers "do I already
have something on this?", never "here is the correct citation".

COLLECTION BIAS IS REPORTED, NOT HIDDEN. `--stats` prints the year distribution
and the size of the library, because a personal library reflects its owner's
reading history. `search-sources.md` requires that any claim resting ONLY on the
local library be marked in search_trail; the numbers here are what that mark
cites (rubric section 6, bubble check).

Usage:
    python pdf_index.py --build                 index the registered root
    python pdf_index.py --build --root <path>   index somewhere else
    python pdf_index.py --search perovskite hysteresis
    python pdf_index.py --stats
    python pdf_index.py --selftest              two-sided calibration of the parser

Exit: 0 ok, 1 nothing indexed / no match, 2 bad usage.
review-when: the library moves, or Zotero changes its attachment naming scheme
(the parser's patterns are the single edit point).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "registry.json"
sys.path.insert(0, str(HERE))
import regload  # noqa: E402  (registry loader: expands ${ROOT} path fields)
INDEX = HERE / "pdf-index.json"

# --- CONFIG: filename parsing, the single edit point ----------------------
# Zotero writes "<authors> - <year> - <title>.pdf". The author part carries a
# localized "and others" marker that differs per UI language, so the pattern
# must not depend on it: everything before the first " - <4 digits> - " is the
# author field, whatever language it is in.
MAIN = re.compile(r"^(?P<authors>.+?)\s+-\s+(?P<year>\d{4})\s+-\s+(?P<title>.+)$")
# Fallbacks for hand-named files.
# NOT \b: an underscore is a word character, so \b never fires in
# `paper_2019` — the exact shape a hand-saved download takes. Bound on digits
# instead, which is what actually matters (do not read 2019 out of 120193).
YEAR_ANYWHERE = re.compile(r"(?<![0-9])(1[89]\d{2}|20\d{2})(?![0-9])")
ETAL = re.compile(r"(\s*(?:…等|和others|et al\.?|等)\s*)$", re.IGNORECASE)
# ---------------------------------------------------------------------------


def parse_name(stem: str) -> dict:
    """Author/year/title from a filename. Absent fields are None, never guessed."""
    m = MAIN.match(stem)
    if m:
        authors = ETAL.sub("", m.group("authors")).strip(" -–—")
        return {"authors": authors or None,
                "year": int(m.group("year")),
                "title": m.group("title").strip(),
                "parsed": "zotero"}
    y = YEAR_ANYWHERE.search(stem)
    return {"authors": None,
            "year": int(y.group(1)) if y else None,
            "title": stem.strip(),
            "parsed": "fallback"}


def registered_root() -> str | None:
    try:
        reg = regload.load(REGISTRY)
    except Exception:                                   # noqa: BLE001
        return None
    for c in reg.get("connectors", []):
        if c.get("id") == "local_pdf_library":
            return ((c.get("invoke") or {}).get("root")) or None
    return None


def build(root: Path) -> dict:
    rows = []
    for pdf in sorted(root.rglob("*.pdf")):
        try:
            st = pdf.stat()
        except OSError:
            continue
        meta = parse_name(pdf.stem)
        rows.append({
            **meta,
            "path": str(pdf),
            # Zotero keeps one attachment per 8-char item-key folder; carrying
            # the key means a later zotero.sqlite reader can join on it.
            "item_key": pdf.parent.name if len(pdf.parent.name) == 8 else None,
            "mb": round(st.st_size / 1048576, 2),
        })
    payload = {"root": str(root), "count": len(rows), "files": rows}
    INDEX.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


def load() -> dict | None:
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        return None


def search(terms: list[str]) -> int:
    idx = load()
    if not idx:
        print("no index yet — run: python pdf_index.py --build")
        return 2
    needles = [t.casefold() for t in terms]
    hits = []
    for f in idx["files"]:
        hay = f"{f.get('authors') or ''} {f.get('year') or ''} {f['title']}".casefold()
        score = sum(1 for n in needles if n in hay)
        if score:
            hits.append((score, f))
    hits.sort(key=lambda x: (-x[0], -(x[1].get("year") or 0)))
    if not hits:
        print(f"no match for {' '.join(terms)} in {idx['count']} indexed PDFs.")
        print("An empty local result never means 'literature not found' — go to P2 web "
              "discovery and say in search_trail that the local library was checked.")
        return 1
    print(f"{len(hits)} of {idx['count']} indexed PDFs match {' '.join(terms)!r}:\n")
    for score, f in hits[:25]:
        who = f.get("authors") or "?"
        yr = f.get("year") or "????"
        print(f"  [{score}] {who} ({yr}) — {f['title'][:70]}")
        print(f"        {f['path']}")
    print("\nAccess tag: reading one of these gives [full]. Filename metadata is NOT a "
          "citation — resolve the identifier before it reaches a deliverable.")
    return 0


def stats() -> int:
    idx = load()
    if not idx:
        print("no index yet — run: python pdf_index.py --build")
        return 2
    years = Counter(f["year"] for f in idx["files"] if f.get("year"))
    unparsed = sum(1 for f in idx["files"] if f["parsed"] == "fallback")
    print(f"root:    {idx['root']}")
    print(f"indexed: {idx['count']} PDFs "
          f"({round(sum(f['mb'] for f in idx['files']), 1)} MB)")
    print(f"parsed:  {idx['count'] - unparsed} from the Zotero pattern, "
          f"{unparsed} by fallback (author/year may be missing on those)")
    if years:
        lo, hi = min(years), max(years)
        print(f"years:   {lo}–{hi}, median {sorted(years.elements())[len(list(years.elements())) // 2]}")
        recent = sum(v for k, v in years.items() if k >= hi - 2)
        print(f"         {recent} ({round(100 * recent / sum(years.values()))}%) from the last 3 years")
    print("\nCOLLECTION BIAS — quote these numbers in search_trail whenever a claim "
          "rests only on this library. A personal library is a reading history, not "
          "a survey: what is missing from it is invisible from inside it.")
    return 0


def selftest() -> int:
    cases = [
        ("Dong …等 - 2025 - Scalable Vision Language Model Training",
         {"authors": "Dong", "year": 2025, "parsed": "zotero"}),
        ("Wann和others - 1996 - A Comparative Study of Advanced MOSFET Concepts",
         {"authors": "Wann", "year": 1996, "parsed": "zotero"}),
        ("Zhao - 2021 - The Main Progress of Perovskite Solar Cells in 2020–2021",
         {"authors": "Zhao", "year": 2021, "parsed": "zotero"}),
        # A title containing a year must not be mistaken for the year field.
        ("Guo …等 - 2020 - Tetragonal MAPbI3 under Strain",
         {"authors": "Guo", "year": 2020, "parsed": "zotero"}),
        # Hand-named files degrade, they do not invent an author.
        ("some_downloaded_paper_2019", {"authors": None, "year": 2019, "parsed": "fallback"}),
        ("notes", {"authors": None, "year": None, "parsed": "fallback"}),
    ]
    bad = 0
    print(f"{'verdict':9} case")
    print("-" * 74)
    for stem, want in cases:
        got = parse_name(stem)
        ok = all(got.get(k) == v for k, v in want.items())
        bad += 0 if ok else 1
        print(f"{'ok' if ok else 'BROKEN':9} {stem[:58]}")
        if not ok:
            print(f"{'':9}   want {want}, got "
                  f"{ {k: got.get(k) for k in want} }")
    print("-" * 74)
    n_named = sum(1 for _, w in cases if w['authors'])
    print(f"{len(cases)} cases ({n_named} must-parse / {len(cases) - n_named} "
          f"must-degrade-without-inventing), {bad} broken — "
          f"{'parser is calibrated' if not bad else 'PARSER IS NOT TRUSTWORTHY'}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--root")
    ap.add_argument("--search", nargs="+")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if args.build:
        root = Path(args.root) if args.root else (
            Path(registered_root()) if registered_root() else None)
        if not root:
            print("no root: pass --root, or set invoke.root on the "
                  "local_pdf_library entry in registry.json")
            return 2
        if not root.exists():
            print(f"root does not exist: {root}")
            return 2
        payload = build(root)
        print(f"indexed {payload['count']} PDFs from {root}")
        print(f"index written to {INDEX}")
        return 0 if payload["count"] else 1
    if args.search:
        return search(args.search)
    if args.stats:
        return stats()
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
