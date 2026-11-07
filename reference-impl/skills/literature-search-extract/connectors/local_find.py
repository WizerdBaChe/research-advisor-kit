r"""Full-text search of the LOCAL evidence stores, with citation-ready locators.

One call answers "which book / which earlier literature run already says X, and on what
page" -- the step that otherwise takes a grep, an awk for the nearest page marker and a
library.json lookup per hit.

Stores (roots from adapt/host.toml, never spelled here):
  textbooks   TEXTBOOKS root: each book's `<id>.chapters/*.md` export (textbook_index.py
              --export). Locator = the nearest preceding `[p. N]` marker, printed with
              the book's calibration status; markers that restart inside a book are flagged.
  literature  NOTES_VAULT/literature/**.md (EvidenceRuns, PaperSurvey, Bibliography,
              Inbox, Standards): path:line plus the nearest Markdown heading.

  python local_find.py "390 to 7[0-9]0 nm"                 both stores, case-insensitive
  python local_find.py "visible (light|region)" --in textbooks --book Saleh
  python local_find.py "edge coupler" --in literature --limit 20
  python local_find.py --selftest

A hit is a place to open, not evidence: read the page (formulas and OCR pages from the
page image) before a ledger row cites it -- references/textbook-extraction.md §2.
Exit 0 = hits, 1 = none, 2 = usage / selftest failure.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks" / "_lib"))
import roots as hkroots  # noqa: E402

PAGE = re.compile(r"^\[p\. (\d+)\]\s*$")
HEADING = re.compile(r"^#{1,6}\s+(.*)")
TRIM = 170


# AP-74 copy-of: hooks/_lib/tree.py::is_reparse — research-papers ships this skill without hooks/_lib (rules/tree-walk-reparse.md, packaged helper)
def _is_link(p: Path) -> bool:
    st = os.lstat(p)
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _line_hits(lines, rx):
    """(index, text) per match; a phrase broken across two lines is caught on the pair."""
    for i, ln in enumerate(lines):
        if rx.search(ln):
            yield i, ln
        elif i + 1 < len(lines):
            pair = ln.rstrip() + " " + lines[i + 1].lstrip()
            if rx.search(pair) and not rx.search(lines[i + 1]):
                yield i, pair


def _short(s: str, n: int = TRIM) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def find_textbooks(root: Path, rx, book_sub=None, per_book=5):
    lib = json.loads((root / "library.json").read_text(encoding="utf-8"))
    hits, no_export, books = [], [], 0
    for b in lib["books"]:
        if book_sub and book_sub.lower() not in b["id"].lower():
            continue
        exp = Path(b["path"]).with_name(b["id"] + ".chapters")
        if not exp.is_dir():
            no_export.append(b["id"][:50])
            continue
        books += 1
        cal = b.get("calibration", {}).get("status", "?")
        ed = (b.get("identity") or {}).get("edition") or "edition not stated"
        last, reset, found = -1, False, []
        for md in sorted(exp.glob("*.md")):  # flat folder: no tree walk
            lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
            page, ocr = None, any("access: ocr" in ln for ln in lines[:8])
            marks = {}
            for i, ln in enumerate(lines):
                m = PAGE.match(ln)
                if m:
                    page = int(m.group(1))
                    if page < last:
                        reset = True
                    last = page
                marks[i] = page
            for i, text in _line_hits(lines, rx):
                found.append((md.stem, marks.get(i), ocr, i + 1, text))
        for stem, page, ocr, lno, text in found[:per_book]:
            hits.append({"store": "TB", "book": b["id"][:48], "edition": ed, "chapter": stem[:40],
                         "printed": page, "calibration": cal, "markers_reset": reset, "ocr": ocr,
                         "line": lno, "text": _short(text)})
        if len(found) > per_book:
            hits.append({"store": "TB", "book": b["id"][:48], "more": len(found) - per_book})
    return hits, books, no_export


def find_literature(vault: Path, rx, per_file=3):
    base = vault / "literature"
    hits, files, pruned = [], 0, []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        keep = []
        for d in dirnames:
            if _is_link(Path(dirpath) / d):
                pruned.append(str(Path(dirpath) / d))
            else:
                keep.append(d)
        dirnames[:] = keep
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            p = Path(dirpath) / fn
            files += 1
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            head, heads = None, {}
            for i, ln in enumerate(lines):
                m = HEADING.match(ln)
                if m:
                    head = m.group(1).strip()
                heads[i] = head
            for n, (i, text) in enumerate(_line_hits(lines, rx)):
                if n >= per_file:
                    break
                hits.append({"store": "LIT", "path": str(p.relative_to(vault)), "line": i + 1,
                             "heading": _short(heads.get(i) or "", 60), "text": _short(text)})
    return hits, files, pruned


def show(h):
    if "more" in h:
        return f"TB   {h['book']}  ... {h['more']} more hits in this book (narrow with --book)"
    if h["store"] == "TB":
        p = f"p.{h['printed']}" if h["printed"] is not None else "p.?"
        warn = []
        if h["calibration"] in ("unreliable", "labels-only", "weak"):
            warn.append(f"calibration {h['calibration']}")
        if h["markers_reset"]:
            warn.append("page markers restart in this book: read the page header")
        if h["ocr"]:
            warn.append("OCR text: formulas from the page image")
        w = f"  [{'; '.join(warn)}]" if warn else ""
        return f"TB   {h['book']} | {h['edition']} | {h['chapter']} | {p}{w}\n       {h['text']}"
    return f"LIT  {h['path']}:{h['line']} | {h['heading']}\n       {h['text']}"


def run(pattern, where="all", book=None, limit=40, out=print):
    rx = re.compile(pattern, re.I)
    total, summary = [], []
    if where in ("all", "textbooks"):
        tb = hkroots.path("TEXTBOOKS")
        if tb is None or not (tb / "library.json").exists():
            summary.append("textbooks: TEXTBOOKS root unset or no library.json (skipped)")
        else:
            h, n, missing = find_textbooks(tb, rx, book)
            total += h
            summary.append(f"textbooks: {sum(1 for x in h if 'more' not in x)} shown from {n} books"
                           + (f"; {len(missing)} without chapter export (textbook_index.py --export): {missing}" if missing else ""))
    if where in ("all", "literature") and not book:
        nv = hkroots.path("NOTES_VAULT")
        if nv is None or not (nv / "literature").is_dir():
            summary.append("literature: NOTES_VAULT/literature missing (skipped)")
        else:
            h, n, pruned = find_literature(nv, rx)
            total += h
            summary.append(f"literature: {len(h)} hits in {n} files"
                           + (f"; reparse-point skipped: {pruned}" if pruned else ""))
    for h in total[:limit]:
        out(show(h))
    if len(total) > limit:
        out(f"... {len(total) - limit} more (raise --limit or narrow the pattern)")
    for s in summary:
        out("# " + s)
    return total


def selftest() -> int:
    """Controls on the live stores: each must fire, or the store is UNDETERMINED (not PASS)."""
    ok, buf = True, []
    tb = hkroots.path("TEXTBOOKS")
    if tb is None or not (tb / "library.json").exists():
        print("UNDETERMINED: no textbook library on this machine")
        return 2
    # 1. positive: a phrase known to sit on Schubert 1st ed. printed p.222
    h = run(r"390 to 720 nm", "textbooks", "Schubert", out=buf.append)
    pages = [x.get("printed") for x in h if "more" not in x]
    print(f"  positive (Schubert '390 to 720 nm'): pages {pages}")
    ok &= 222 in pages
    # 2. positive across a line break: 'eye sensitivity' ends one line, 'function is greater' starts the next
    h = run(r"eye sensitivity function is greater", "textbooks", "Schubert", out=buf.append)
    print(f"  line-break pair: {len(h)} hit(s)")
    ok &= len(h) >= 1
    # 3. negative: a phrase in no book
    h = run(r"zzqx no such phrase", "textbooks", out=buf.append)
    print(f"  negative: {len(h)} hit(s)")
    ok &= len(h) == 0
    # 4. reset flag: Saleh's export restarts its [p. N] markers per chapter; Schubert's do not
    s = [x for x in run(r"visible", "textbooks", "Saleh", out=buf.append) if "more" not in x]
    k = [x for x in run(r"visible", "textbooks", "Schubert", out=buf.append) if "more" not in x]
    print(f"  markers_reset Saleh={s[0]['markers_reset'] if s else None} Schubert={k[0]['markers_reset'] if k else None}")
    ok &= bool(s) and s[0]["markers_reset"] and bool(k) and not k[0]["markers_reset"]
    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 2


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pattern", nargs="?", help="regular expression, case-insensitive")
    ap.add_argument("--in", dest="where", choices=["all", "textbooks", "literature"], default="all")
    ap.add_argument("--book", help="book id substring (textbooks only)")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.pattern:
        ap.print_usage()
        return 2
    return 0 if run(a.pattern, a.where, a.book, a.limit) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
