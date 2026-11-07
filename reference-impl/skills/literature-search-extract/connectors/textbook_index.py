#!/usr/bin/env python3
r"""Structural index of the local textbook library (<TEXTBOOKS>) — the part of
"抽整" that is pre-built: STRUCTURE, never summaries.

WHAT IT BUILDS, per book (`<book>.index.json` beside the PDF) and for the
library (`<root>\library.json`):
  identity      title / authors / ISBN / edition as found in PDF metadata and
                the first pages' copyright line — recorded with `found_in`, and
                left EMPTY when not found (never filled from model memory)
  text access   text layer, or the OCR sidecar written by textbook_ocr.py
                (excluded pages stay excluded: they read as None here too)
  toc           chapter/section -> PDF page, from the PDF outline when it is a
                real outline, else from a heading scan (marked as such)
  calibration   PDF page index -> PRINTED page number, fitted from page
                headers/footers across the whole book and reported with its
                agreement share — a citation locator is the printed page, and
                the PDF index differs from it by the front matter
  glossary      the book-end index parsed into term -> printed pages -> PDF
                pages: a vocabulary layer beside Author Keywords / Index Terms
                (search-sources.md §Query building) and a snowball seed
  export        `--export` writes one Markdown file per chapter (for the user's
                secondary-analysis tools, e.g. NotebookLM); excluded OCR pages
                appear as a marker line, never as text

WHY NOT SUMMARIES. The library is ~25,000 pages; a generic per-chapter digest
is literature-search-extract failure mode #3 and would go stale against the
question actually asked. Extraction stays a per-question LSE run (P1 target
list -> P4 locator -> P4.5 ledger); this index only makes the right pages
findable and citable.

Usage:
    python textbook_index.py --build [--root <TEXTBOOKS>] [--only <substring>]
    python textbook_index.py --search <terms...>       titles, TOC entries, glossary terms
    python textbook_index.py --locate <book-substr> --printed <n>    printed page -> PDF page
    python textbook_index.py --export <book-substr>    chapter Markdown files
    python textbook_index.py --pages [<book-substr>] [--verify | --redo]   write-once page store (verify/pagestore.py)
    python textbook_index.py --pages --pdf <lecture.pdf>                   the same for a PDF outside the library
    python textbook_index.py --stats
    python textbook_index.py --selftest

Exit: 0 ok, 1 nothing built / no match / a control did not fire, 2 bad usage.
review-when: the library root moves; textbook_ocr.py changes its manifest
schema; a book's outline is regenerated (rebuild that book with --only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import fitz  # pymupdf
import sys as _hksys  # machine roots at run time (platform/codemod_roots.py, build plan H-1)
from pathlib import Path as _HKPath
_hksys.path.insert(0, str(_HKPath(__file__).resolve().parents[3] / "hooks" / "_lib"))
import roots as hkroots  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = hkroots.path("TEXTBOOKS")
SCHEMA = "textbook-index/book@1"
LIB_SCHEMA = "textbook-index/library@1"

# --- heuristics: the single edit point -------------------------------------
JUNK_OUTLINE = re.compile(r"^(?:Page_?\d+|front_?\d+|back_?\d+|p\d+|\d+)$", re.I)
INDEX_TITLES = {"index", "subject index", "索引", "名詞索引", "主題索引", "index of terms"}
ISBN_RE = re.compile(r"ISBN[-\s]*(?:1[03])?[:\s]*([0-9][0-9\- ]{8,16}[0-9Xx])")
EDITION_RE = re.compile(r"\b(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|\d{1,2}(?:st|nd|rd|th))\s+Edition\b", re.I)
EDITION_CN = re.compile(r"第\s*([一二三四五六七八九十\d]+)\s*版")
PRINTED_MAX = 2500
HEADER_LINES = 3            # lines at top/bottom examined for a printed page number
CAL_MIN_AGREE = 0.6         # below this the calibration is 'unreliable'
GLOSSARY_LINE = re.compile(r"^(?P<term>[^\d\n][^\n]{1,80}?)[,，]?\s+(?P<pages>\d{1,4}(?:\s*[,，–\-]\s*\d{1,4})*)\s*[,，]?\s*$")
# a wrapped index entry continues on a line of bare page numbers (Aharony: 'acoustic branch, 319, 320,' / '358, 368, 379')
GLOSSARY_CONT = re.compile(r"^(?P<pages>\d{1,4}(?:\s*[,，–\-]\s*\d{1,4})*)\s*[,，]?\s*$")
GLOSSARY_TAIL_SHARE = 0.15  # scan the last 15 % of pages for an index when the TOC has none
GLOSSARY_PAGE_MIN_SHARE = 0.45  # share of lines matching the index-line shape to call a page an index page
CHAPTER_HEAD = re.compile(r"^(?:CHAPTER|Chapter|第)\s*([0-9０-９一二三四五六七八九十]{1,3})\s*[章.:]?\s*(.{0,80})$")
# ---------------------------------------------------------------------------


# ------------------------------------------------------------- text access
class Book:
    """One PDF plus its optional OCR sidecar. `page_text(i)` is 1-based and
    returns None for a page that has no readable text — a text-layer page
    with nothing on it reads as '', an OCR-excluded page reads as None."""

    def __init__(self, pdf: Path):
        self.pdf = pdf
        self.doc = fitz.open(pdf)
        self.n = self.doc.page_count
        self.side = pdf.with_name(pdf.stem + ".ocr")
        self.manifest = None
        mp = self.side / "manifest.json"
        if mp.exists():
            self.manifest = json.loads(mp.read_text(encoding="utf-8"))
        self._status = {}
        if self.manifest:
            self._status = {r["page"]: r["status"] for r in self.manifest["pages"]}
        # one rule for "this PDF has a text layer": textbook_ocr owns it and its threshold (AP-74)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from textbook_ocr import has_text_layer
        self.text_layer = has_text_layer(self.doc)

    def page_text(self, p: int) -> str | None:
        if self.text_layer:
            return self.doc[p - 1].get_text()
        if self.manifest:
            st = self._status.get(p)
            if st in ("ok", "sparse"):
                f = self.side / "text" / f"{p:04d}.txt"
                return f.read_text(encoding="utf-8") if f.exists() else ""
            return None
        return None

    @property
    def access(self) -> str:
        if self.text_layer:
            return "text-layer"
        if self.manifest:
            return "ocr-sidecar"
        return "none"


# --------------------------------------------------------------- identity
def find_identity(book: Book) -> dict:
    md = {k: v for k, v in book.doc.metadata.items() if v}
    out = {"title": None, "authors": None, "isbn": None, "edition": None, "year": None, "found_in": {}}
    t = md.get("title", "")
    if t and not re.match(r"^[\w\-]+\.pdf$", t) and len(t) > 3:
        out["title"] = t.strip(); out["found_in"]["title"] = "pdf-metadata"
    if md.get("author"):
        out["authors"] = md["author"].strip(); out["found_in"]["authors"] = "pdf-metadata"
    if md.get("subject") and re.fullmatch(r"[0-9Xx\-]{10,17}", md["subject"].strip()):
        out["isbn"] = md["subject"].strip(); out["found_in"]["isbn"] = "pdf-metadata.subject"
    # front-matter scan: first 15 pages that have text
    scanned = 0
    for p in range(1, min(book.n, 40) + 1):
        tx = book.page_text(p)
        if not tx:
            continue
        scanned += 1
        if out["isbn"] is None:
            m = ISBN_RE.search(tx)
            if m:
                out["isbn"] = re.sub(r"[\s\-]", "", m.group(1)); out["found_in"]["isbn"] = f"page {p}"
        if out["edition"] is None:
            m = EDITION_RE.search(tx) or EDITION_CN.search(tx)
            if m:
                out["edition"] = m.group(0).strip(); out["found_in"]["edition"] = f"page {p}"
        if out["year"] is None:
            m = re.search(r"(?:©|Copyright|版权所有|版權所有)\s*(?:\(c\)\s*)?(?:\d{4},\s*)*(\d{4})", tx)
            if m:
                out["year"] = int(m.group(1)); out["found_in"]["year"] = f"page {p}"
        if scanned >= 15:
            break
    return out


# --------------------------------------------------------------------- toc
def build_toc(book: Book) -> tuple[list[dict], str]:
    raw = book.doc.get_toc()
    if raw:
        junk = sum(1 for _, t, _ in raw if JUNK_OUTLINE.match(t.strip()))
        if len(raw) >= 5 and junk / len(raw) < 0.5:
            # some outlines carry lone surrogates (undecodable padding bytes);
            # they cannot be written as UTF-8, so they are dropped from the title
            toc = [{"level": lvl,
                    "title": re.sub(r"[\ud800-\udfff]", "", t).strip().rstrip("\r"),
                    "pdf_page": pg}
                   for lvl, t, pg in raw if pg >= 1]
            return toc, "pdf-outline"
    # contents-page scan: the book's own table of contents in the front matter,
    # printed pages mapped to PDF pages through the calibration afterwards
    contents = _parse_contents_pages(book)
    if len(contents) >= 5:
        return contents, "contents-page (printed pages; pdf_page filled from calibration)"
    # heading scan — chapter level only, from the first lines of each page
    toc = []
    for p in range(1, book.n + 1):
        tx = book.page_text(p)
        if not tx:
            continue
        for line in [ln.strip() for ln in tx.splitlines() if ln.strip()][:4]:
            m = CHAPTER_HEAD.match(line)
            if m and (not toc or toc[-1]["pdf_page"] < p - 3):
                toc.append({"level": 1, "title": line[:100], "pdf_page": p})
                break
    return toc, ("heading-scan (unverified)" if toc else "none")


SEC_NUM = re.compile(r"^(?:Chapter\s+)?(\d{1,2}(?:\.\d{1,2}){0,3})\.?$", re.I)
SEC_INLINE = re.compile(r"^(?:Chapter\s+)?(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(.{3,90}?)\s*\.{0,}\s*(\d{1,4})$", re.I)
CONTENTS_HEAD = re.compile(r"^(contents|table of contents|目\s*录|目\s*次)$", re.I)


def _parse_contents_pages(book: Book) -> list[dict]:
    """Parse the printed table of contents. pymupdf usually emits number,
    title and page as SEPARATE lines (Reed: '1.1' / 'What is Phase?' / '1'), so
    this is a small state machine over lines, with the one-line form as well.
    Entries carry `printed_page`; the caller fills `pdf_page` via calibration."""
    limit = max(20, int(book.n * 0.08))
    start = None
    for p in range(1, limit + 1):
        tx = book.page_text(p)
        if not tx:
            continue
        head = [ln.strip() for ln in tx.splitlines() if ln.strip()][:3]
        if any(CONTENTS_HEAD.match(h) for h in head):
            start = p
            break
    if start is None:
        return []
    entries = []
    empty_pages = 0
    for p in range(start, min(book.n, start + 25) + 1):
        tx = book.page_text(p)
        if not tx:
            continue
        lines = [ln.strip() for ln in tx.splitlines() if ln.strip()]
        found_here = 0
        num, title_parts = None, []
        for ln in lines:
            m1 = SEC_INLINE.match(ln)
            if m1:
                entries.append({"level": m1.group(1).count(".") + 1, "title": f"{m1.group(1)} {m1.group(2).strip()}",
                                "printed_page": int(m1.group(3)), "pdf_page": None})
                found_here += 1
                num, title_parts = None, []
                continue
            # An open entry with a title takes a bare integer as its PAGE first —
            # otherwise '1' / 'Fundamentals' / '1' reads the page as the next
            # chapter number and every entry below p. 100 is swallowed
            # (measured on Reed 2026-09-13: TOC began at 4.8.2, p. 101).
            if num is not None and title_parts and re.fullmatch(r"\d{1,4}", ln):
                entries.append({"level": num.count(".") + 1, "title": f"{num} {' '.join(title_parts)}",
                                "printed_page": int(ln), "pdf_page": None})
                found_here += 1
                num, title_parts = None, []
                continue
            m2 = SEC_NUM.match(ln)
            if m2:
                num, title_parts = m2.group(1), []
                continue
            if num is not None:
                if re.fullmatch(r"[ivxlcdm]{1,6}", ln, re.I):
                    num, title_parts = None, []          # front-matter entry, skip
                elif len(title_parts) < 4:
                    title_parts.append(ln)
                else:
                    num, title_parts = None, []
        if found_here == 0:
            empty_pages += 1
            if entries and empty_pages >= 2:
                break
        else:
            empty_pages = 0
    return entries


# --------------------------------------------------------------- calibrate
def _printed_candidates(text: str) -> list[int]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    edge = lines[:HEADER_LINES] + lines[-HEADER_LINES:]
    out = []
    for ln in edge:
        if re.fullmatch(r"\d{1,4}", ln):
            out.append(int(ln))
            continue
        m = re.match(r"^(\d{1,4})\s+\S", ln) or re.search(r"\S\s+(\d{1,4})$", ln)
        if m and len(ln) < 120:
            out.append(int(m.group(1)))
    return [v for v in out if 1 <= v <= PRINTED_MAX]


def _sane_labels(book: Book) -> dict[int, str] | None:
    """PDF page labels when the file carries real ones (Feynman '1-19', Liu
    'xlix'/'147'); None when absent or junk ('cov001.pdg', '<FEFF>...')."""
    labels = {}
    for i in range(book.n):
        lb = book.doc[i].get_label() or ""
        if lb and not re.search(r"\.pdg$|<FEFF|^cov|^Cover$", lb, re.I):
            labels[i + 1] = lb
    if len(labels) < 0.6 * book.n:
        return None
    return labels


def calibrate(book: Book) -> dict:
    """Map PDF page -> PRINTED page. Position-free and piecewise: every page that
    prints its own number votes for an offset; a vote counts only when a
    neighbour within ±3 pages agrees (a lone number on a page is usually an
    equation or a figure count). Runs of one offset become SEGMENTS, so a scan
    with a missing page (Sze 3rd: offset 6 then 5) still locates. The ruler is
    `coverage` (share of text pages that voted consistently). PDF page labels,
    when sane, are recorded beside the fit and win in `--locate`."""
    votes: dict[int, set[int]] = {}
    text_pages = 0
    for p in range(1, book.n + 1):
        tx = book.page_text(p)
        if not tx:
            continue
        text_pages += 1
        offs = {p - c for c in _printed_candidates(tx) if 0 <= p - c <= 400}
        if offs:
            votes[p] = offs
    labels = _sane_labels(book)
    confirmed: dict[int, int] = {}
    for p, offs in votes.items():
        for off in offs:
            if any(off in votes.get(q, ()) for q in range(p - 3, p + 4) if q != p):
                confirmed[p] = off
                break
    if not confirmed:
        return {"segments": [], "offset": None, "agreement": 0.0, "coverage": 0.0,
                "pages_with_number": len(votes), "labels": "pdf-labels" if labels else None,
                "status": "labels-only" if labels else "none"}
    segments = []
    for p in sorted(confirmed):
        off = confirmed[p]
        if segments and segments[-1]["offset"] == off:
            segments[-1]["pdf_to"] = p
        else:
            segments.append({"pdf_from": p, "pdf_to": p, "offset": off})
    # extend each segment to meet its neighbour (pages without a printed number)
    for k, s in enumerate(segments):
        if k + 1 < len(segments):
            s["pdf_to"] = segments[k + 1]["pdf_from"] - 1
    segments[-1]["pdf_to"] = book.n
    # drop micro-segments (a single spurious agreement) by merging into the neighbour
    segments = [s for s in segments if s["pdf_to"] - s["pdf_from"] >= 2 or len(segments) == 1]
    main = Counter(confirmed.values()).most_common(1)[0]
    coverage = len(confirmed) / text_pages if text_pages else 0.0
    status = "ok" if coverage >= 0.5 else ("weak" if coverage >= 0.2 else "unreliable")
    if labels and coverage < 0.2:
        # Feynman ('1-19' chapter-page labels) and similar: the fit is noise, the
        # file's own labels are the printed pages. Say so instead of shipping a
        # spurious offset.
        return {"segments": [], "offset": None, "agreement": 0.0, "coverage": round(coverage, 3),
                "pages_with_number": len(confirmed), "labels": "pdf-labels", "status": "labels-only",
                "rule": "printed page = PDF page label (see pdf_labels in the book index)"}
    return {"segments": segments, "offset": main[0], "agreement": round(main[1] / len(confirmed), 3),
            "coverage": round(coverage, 3), "pages_with_number": len(confirmed),
            "labels": "pdf-labels" if labels else None, "status": status,
            "rule": "pdf_page = printed_page + offset (per segment)"}


def printed_of(cal: dict, pdf_page: int) -> int | None:
    for s in cal.get("segments", []):
        if s["pdf_from"] <= pdf_page <= s["pdf_to"]:
            v = pdf_page - s["offset"]
            return v if v >= 1 else None
    return None


def pdf_of(cal: dict, printed: int) -> int | None:
    for s in cal.get("segments", []):
        p = printed + s["offset"]
        if s["pdf_from"] <= p <= s["pdf_to"]:
            return p
    return None


# ---------------------------------------------------------------- glossary
def _is_index_page(text: str) -> tuple[bool, int, int]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 12:
        return False, 0, len(lines)
    term_hits = sum(1 for ln in lines if GLOSSARY_LINE.match(ln))
    cont_hits = sum(1 for ln in lines if not GLOSSARY_LINE.match(ln) and GLOSSARY_CONT.match(ln))
    hits = term_hits + cont_hits
    # Term lines must carry the page on their own: a page of answers or a table
    # of numbers is all continuation-shaped lines and is NOT an index (measured
    # 2026-09-13 — counting bare-number lines alone started Yariv's index at an
    # exercise page and the C book's at an appendix).
    ok = term_hits / len(lines) >= 0.3 and hits / len(lines) >= GLOSSARY_PAGE_MIN_SHARE
    return ok, hits, len(lines)


def _expand_pages(s: str) -> list[int]:
    out = []
    for part in re.split(r"\s*[,，]\s*", s):
        m = re.fullmatch(r"(\d{1,4})\s*[–\-]\s*(\d{1,4})", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < b - a <= 40:
                out.extend(range(a, b + 1))
            else:
                out.append(a)
        elif re.fullmatch(r"\d{1,4}", part):
            out.append(int(part))
    return out


def build_glossary(book: Book, toc: list[dict], cal: dict) -> dict:
    # Several outline entries may be called "Index" (Heat transfer: the print
    # index at 981 and a web-supplement index at 1044). Take the candidate whose
    # first three pages parse best, not the first or the last one.
    cands = [e["pdf_page"] for e in toc if e["title"].strip().lower() in INDEX_TITLES]
    start = None
    best = -1
    for c in cands:
        score = 0
        for p in range(c, min(book.n, c + 3) + 1):
            tx = book.page_text(p)
            if tx:
                score += _is_index_page(tx)[1]
        if score > best:
            best, start = score, c
    scanned_from = start
    if start is None:
        # scan the tail for index-shaped pages
        lo = max(1, int(book.n * (1 - GLOSSARY_TAIL_SHARE)))
        prev_ok = False
        for p in range(lo, book.n + 1):
            tx = book.page_text(p)
            ok_here = bool(tx) and _is_index_page(tx)[0]
            if ok_here and prev_ok:          # two consecutive index-shaped pages start the index
                start = p - 1
                scanned_from = f"tail-scan from {lo}"
                break
            prev_ok = ok_here
    if start is None:
        return {"status": "not-found", "terms": {}, "pages": [], "lines_seen": 0, "lines_parsed": 0}
    terms: dict[str, list[int]] = {}
    pages_used = []
    seen = parsed = 0
    last_main = None
    gap = 0
    for p in range(start, book.n + 1):
        tx = book.page_text(p)
        if not tx:
            continue
        ok, hits, total = _is_index_page(tx)
        if not ok:
            gap += 1
            if gap >= 3:
                break
            continue
        gap = 0
        pages_used.append(p)
        last_key = None
        for ln in [ln.strip() for ln in tx.splitlines() if ln.strip()]:
            seen += 1
            m = GLOSSARY_LINE.match(ln)
            if not m:
                mc = GLOSSARY_CONT.match(ln)
                if mc and last_key:
                    parsed += 1
                    for pg in _expand_pages(mc.group("pages")):
                        if pg not in terms[last_key]:
                            terms[last_key].append(pg)
                    continue
                last_key = None
                # a bare heading line (no pages) may start a main entry with sub-entries following
                if 2 <= len(ln) <= 60 and not re.search(r"\d", ln):
                    last_main = ln.rstrip(",，")
                continue
            parsed += 1
            term = m.group("term").strip().rstrip(",，")
            pages = _expand_pages(m.group("pages"))
            if not pages:
                continue
            # sub-entry heuristics: leading dash / indentation lost in extraction; keep as "main: sub"
            if term.startswith(("-", "–", "—")) and last_main:
                term = f"{last_main}: {term.lstrip('-–— ')}"
            elif term[0].islower() and last_main and len(term.split()) <= 4 and last_main[0].isupper():
                pass  # lowercase entries are normal in indexes; do not force nesting
            else:
                last_main = term
            key = unicodedata.normalize("NFKC", term)
            last_key = key
            terms.setdefault(key, [])
            for pg in pages:
                if pg not in terms[key]:
                    terms[key].append(pg)
    share = round(parsed / seen, 3) if seen else 0.0
    return {"status": "ok" if terms else "empty", "start_pdf_page": start, "scanned_from": scanned_from,
            "pages": pages_used, "lines_seen": seen, "lines_parsed": parsed, "parse_share": share,
            "terms": terms}


# ---------------------------------------------------------------- per book
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_folder_readme(pdf: Path) -> str | None:
    r = pdf.parent / "README.md"
    return r.read_text(encoding="utf-8") if r.exists() else None


def index_book(pdf: Path, root: Path) -> dict:
    b = Book(pdf)
    ident = find_identity(b)
    toc, toc_src = build_toc(b)
    cal = calibrate(b)
    labels = _sane_labels(b) if cal.get("labels") else None
    for e in toc:
        if e.get("pdf_page") is None and e.get("printed_page") is not None:
            e["pdf_page"] = pdf_of(cal, e["printed_page"])
        elif e.get("pdf_page") is not None:
            e["printed_page"] = printed_of(cal, e["pdf_page"])
        if labels and e.get("pdf_page"):
            e["pdf_label"] = labels.get(e["pdf_page"])
            if e.get("printed_page") is None and e["pdf_label"] and re.fullmatch(r"\d{1,4}", e["pdf_label"]):
                e["printed_page"] = int(e["pdf_label"])
    toc = [e for e in toc if e.get("pdf_page")]
    gl = build_glossary(b, toc, cal)
    off = cal.get("offset")
    ocr_summary = None
    if b.manifest:
        ocr_summary = {"summary": b.manifest["summary"], "excluded_pages": b.manifest["excluded_pages"],
                       "language": b.manifest["engine"]["language"]}
    rec = {
        "schema": SCHEMA,
        "id": pdf.stem,
        "path": str(pdf),
        "relpath": str(pdf.relative_to(root)),
        "subject_folder": pdf.parent.name,
        "sha256": sha256_file(pdf),
        "pages": b.n,
        "access": b.access,
        "identity": ident,
        "toc_source": toc_src,
        "toc_entries": len(toc),
        "calibration": cal,
        "glossary": {k: v for k, v in gl.items() if k != "terms"} | {"term_count": len(gl["terms"])},
        "ocr": ocr_summary,
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    detail = dict(rec)
    detail["toc"] = toc
    detail["glossary"] = dict(rec["glossary"])
    detail["glossary"]["terms"] = gl["terms"]
    if off is not None:
        detail["glossary"]["pdf_page_rule"] = "pdf_page = pdf_of(calibration.segments, printed)"
    if labels:
        detail["pdf_labels"] = labels
    (pdf.with_name(pdf.stem + ".index.json")).write_text(
        json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def build(root: Path, only: str | None) -> int:
    books = []
    for pdf in sorted(root.rglob("*.pdf")):
        if only and only.lower() not in str(pdf).lower():
            continue
        try:
            rec = index_book(pdf, root)
        except Exception as e:  # noqa: BLE001
            print(f"ERR {pdf.name[:60]}: {e}")
            continue
        books.append(rec)
        c = rec["calibration"]
        print(f"{rec['pages']:5d}p {rec['access']:12s} toc={rec['toc_entries']:4d} ({rec['toc_source'][:12]:12s}) "
              f"cal={str(c.get('offset')):>5s} cov={c.get('coverage', 0):.2f} seg={len(c.get('segments', [])):2d} {c.get('status'):10s} "
              f"gloss={rec['glossary']['term_count']:5d} isbn={rec['identity']['isbn'] or '-':15s} {pdf.name[:45]}")
    lib_path = root / "library.json"
    existing = {}
    if lib_path.exists() and only:
        old = json.loads(lib_path.read_text(encoding="utf-8"))
        existing = {b["id"]: b for b in old.get("books", [])}
    for b in books:
        existing[b["id"]] = b
    lib = {"schema": LIB_SCHEMA, "root": str(root), "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "books": sorted(existing.values(), key=lambda x: x["relpath"])}
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"library.json: {len(lib['books'])} books -> {lib_path}")
    return 0 if books else 1


# ------------------------------------------------------------------ query
def _load_lib(root: Path) -> dict:
    p = root / "library.json"
    if not p.exists():
        print("no library.json — run --build first", file=sys.stderr)
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


def search(root: Path, terms: list[str], limit: int = 40) -> int:
    lib = _load_lib(root)
    q = [_norm(t) for t in terms]
    hits = []
    for b in lib["books"]:
        det = json.loads(Path(b["path"]).with_name(b["id"] + ".index.json").read_text(encoding="utf-8"))
        off = b["calibration"].get("offset")
        name = b["id"][:60]
        blob = _norm(" ".join(filter(None, [b["id"], b["identity"].get("title") or "", b["identity"].get("authors") or ""])))
        if all(t in blob for t in q):
            hits.append((3, name, "BOOK", "", ""))
        for e in det["toc"]:
            if all(t in _norm(e["title"]) for t in q):
                hits.append((2, name, f"TOC L{e['level']}", e["title"][:70], f"pdf {e['pdf_page']} / printed {e.get('printed_page')}"))
        for term, pages in det["glossary"].get("terms", {}).items():
            if all(t in _norm(term) for t in q):
                pp = pages[:8]
                pdfp = [pdf_of(b["calibration"], p) for p in pp] if off is not None else []
                hits.append((1, name, "INDEX", term[:70], f"printed {pp} / pdf {pdfp}"))
    hits.sort(key=lambda h: (-h[0], h[1]))
    for _, name, kind, what, where in hits[:limit]:
        print(f"{kind:7s} {name:60s} {what:70s} {where}")
    if len(hits) > limit:
        print(f"... {len(hits) - limit} more")
    return 0 if hits else 1


def locate(root: Path, book_sub: str, printed: int) -> int:
    lib = _load_lib(root)
    for b in lib["books"]:
        if book_sub.lower() in b["id"].lower():
            cal = b["calibration"]
            det = json.loads(Path(b["path"]).with_name(b["id"] + ".index.json").read_text(encoding="utf-8"))
            labels = det.get("pdf_labels") or {}
            by_label = [int(k) for k, v in labels.items() if v == str(printed)]
            p = pdf_of(cal, printed)
            if p is None and not by_label:
                print(f"{b['id'][:60]}: printed {printed} not locatable (calibration {cal['status']})"); return 1
            print(f"{b['id'][:60]}: printed {printed} -> pdf page {p} (fit, coverage {cal.get('coverage')}, {cal['status']})"
                  + (f"; pdf label match -> {by_label}" if by_label else ""))
            return 0
    print("no such book"); return 1


def stats(root: Path) -> int:
    lib = _load_lib(root)
    bs = lib["books"]
    acc = Counter(b["access"] for b in bs)
    toc = Counter(b["toc_source"].split(" ")[0] for b in bs)
    cal = Counter(b["calibration"]["status"] for b in bs)
    gl = sum(1 for b in bs if b["glossary"]["term_count"] > 0)
    isbn = sum(1 for b in bs if b["identity"]["isbn"])
    print(f"books {len(bs)} | pages {sum(b['pages'] for b in bs)} | access {dict(acc)} | toc {dict(toc)} | "
          f"calibration {dict(cal)} | glossary {gl} books, {sum(b['glossary']['term_count'] for b in bs)} terms | isbn found {isbn}")
    exc = [(b['id'][:40], len(b['ocr']['excluded_pages'])) for b in bs if b.get('ocr')]
    if exc:
        print("OCR excluded pages:", exc)
    return 0


# ------------------------------------------------------------------ export
def _slug(s: str, n: int = 50) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:n].rstrip("_.") or "untitled"


def export(root: Path, book_sub: str) -> int:
    lib = _load_lib(root)
    target = [b for b in lib["books"] if book_sub.lower() in b["id"].lower()]
    if not target:
        print("no such book"); return 1
    for b in target:
        pdf = Path(b["path"])
        det = json.loads(pdf.with_name(b["id"] + ".index.json").read_text(encoding="utf-8"))
        bk = Book(pdf)
        off = b["calibration"].get("offset")
        chapters = [e for e in det["toc"] if e["level"] == 1] or [{"title": "whole book", "pdf_page": 1}]
        outdir = pdf.with_name(pdf.stem + ".chapters")
        outdir.mkdir(exist_ok=True)
        written = 0
        for k, ch in enumerate(chapters):
            a = ch["pdf_page"]
            z = (chapters[k + 1]["pdf_page"] - 1) if k + 1 < len(chapters) else bk.n
            if z < a:
                continue
            lines = [f"# {ch['title']}", "",
                     f"- book: {b['identity'].get('title') or b['id']}",
                     f"- authors: {b['identity'].get('authors') or '(not found in file)'}",
                     f"- edition / isbn: {b['identity'].get('edition') or '?'} / {b['identity'].get('isbn') or '?'}",
                     f"- pdf pages {a}–{z}" + (f" = printed {printed_of(b['calibration'], a)}–{printed_of(b['calibration'], z)}" if off is not None else " (no printed-page calibration)"),
                     f"- source sha256: {b['sha256'][:16]}…  access: {b['access']}",
                     "- personal study copy generated from the user's own file; not for redistribution", ""]
            excluded = []
            for p in range(a, z + 1):
                tx = bk.page_text(p)
                pr = printed_of(b["calibration"], p) if off is not None else None
                marker = f"[p. {pr}]" if pr is not None else f"[pdf {p}]"
                if tx is None:
                    excluded.append(p)
                    lines.append(f"\n{marker} (page excluded by the OCR gate — not included)\n")
                    continue
                lines.append(f"\n{marker}\n")
                lines.append(tx.rstrip())
            if excluded:
                lines.insert(8, f"- OCR-excluded pages in this chapter: {excluded}")
            name = f"{k + 1:02d}_{_slug(ch['title'])}.md"
            (outdir / name).write_text("\n".join(lines), encoding="utf-8")
            written += 1
        print(f"{b['id'][:60]}: {written} chapter files -> {outdir}")
    return 0


# -------------------------------------------------------------- notes
def notes(root: Path, book_sub: str | None) -> int:
    """One reading-map note per book, beside the PDF, for the Obsidian viewer.
    A REBUILT artefact (rule PR-3 in the positioning eval): regenerate after
    every --build; never hand-edit. Human-read → Traditional Chinese labels,
    the book's own titles untouched. Contains structure only, no summaries."""
    lib = _load_lib(root)
    n = 0
    for b in lib["books"]:
        if book_sub and book_sub.lower() not in b["id"].lower():
            continue
        pdf = Path(b["path"])
        det = json.loads(pdf.with_name(b["id"] + ".index.json").read_text(encoding="utf-8"))
        idn = b["identity"]
        cal = b["calibration"]
        L = ["---", f"kind: textbook-reading-map", f"book_id: \"{b['id']}\"", f"generated: {b['built']}",
             "generator: literature-search-extract/connectors/textbook_index.py --notes",
             "note: 由索引產生的重建物，勿手改；重跑 --build 後再 --notes 即更新", "---", "",
             f"# {idn.get('title') or b['id']}", "",
             "## 書目（只寫檔案裡找得到的；空白＝檔案沒寫，不是不知道）", "",
             f"- 作者 (authors)：{idn.get('authors') or ''}",
             f"- 版本 (edition)：{idn.get('edition') or ''}　ISBN：{idn.get('isbn') or ''}　年份：{idn.get('year') or ''}",
             f"- 檔案：`{b['relpath']}`　{b['pages']} 頁　sha256 `{b['sha256'][:16]}…`",
             f"- 文字取得 (access)：{b['access']}", ""]
        L += ["## 頁碼對位（引用時寫印刷頁碼）", "",
              f"- 狀態：**{cal.get('status')}**　涵蓋率 {cal.get('coverage', 0)}　主偏移 {cal.get('offset')}（pdf 頁 = 印刷頁 + 偏移）"]
        for s in cal.get("segments", [])[:12]:
            L.append(f"  - pdf {s['pdf_from']}–{s['pdf_to']}：偏移 {s['offset']}")
        if cal.get("labels"):
            L.append("- 檔案帶有 PDF 頁標籤 (page labels)，`--locate` 會一併比對")
        if cal.get("status") in ("unreliable", "none", "labels-only"):
            L.append("- ⚠ 對位不可靠：引用前以頁首／頁尾的印刷頁碼為準，並在 ledger 註明")
        L.append("")
        if b.get("ocr"):
            o = b["ocr"]
            L += ["## OCR 側檔", "",
                  f"- 語言 {o['language']}；狀態計數 {o['summary']}",
                  f"- **不納入的頁（排除，無文字）**：{o['excluded_pages'] or '無'}", ""]
        L += [f"## 目錄（來源：{b['toc_source']}）", ""]
        for e in det["toc"][:400]:
            ind = "  " * (max(1, e.get("level", 1)) - 1)
            pp = e.get("printed_page")
            lab = e.get("pdf_label")
            loc = f"p. {pp}" if pp else (f"label {lab}" if lab else "")
            L.append(f"{ind}- {e['title']}　（pdf {e['pdf_page']}{'，' + loc if loc else ''}）")
        if len(det["toc"]) > 400:
            L.append(f"- …共 {len(det['toc'])} 條，其餘見 index.json")
        g = b["glossary"]
        L += ["", "## 書末索引（詞彙層）", "",
              f"- 狀態 {g.get('status')}；詞條 {g.get('term_count', 0)}；解析率 {g.get('parse_share', 0)}"
              + ("（<0.5，詞條僅供提示）" if (g.get('parse_share') or 0) < 0.5 and g.get('term_count') else ""),
              f"- 查詢：`python textbook_index.py --search <詞>`（命中列 INDEX）；完整詞表在 `{b['id']}.index.json`", ""]
        ch = pdf.with_name(pdf.stem + ".chapters")
        if ch.exists():
            L += ["## 章節匯出（NotebookLM 等二次分析用，私人研讀副本）", ""]
            L += [f"- `{f.name}`" for f in sorted(ch.glob("*.md"))]
            L.append("")
        pdf.with_name(pdf.stem + ".md").write_text("\n".join(L), encoding="utf-8")
        n += 1
    print(f"notes written: {n}")
    return 0 if n else 1


# ---------------------------------------------------------------- selftest
def selftest(root: Path) -> int:
    ok = True
    # 1. junk-outline detection: a per-page outline must be rejected
    fake = [(1, f"Page_{i}", i) for i in range(1, 40)]
    junk = sum(1 for _, t, _ in fake if JUNK_OUTLINE.match(t))
    if junk / len(fake) < 0.5:
        print("FAIL junk-outline control did not fire"); ok = False
    else:
        print("  junk-outline control fired (39/39 junk)")
    # 2. calibration on a known book: Reed, pdf 61 shows printed 40 (measured 2026-09-13)
    reed = next((p for p in root.rglob("*.pdf") if "Silicon Photonics An Introduction" in p.name), None)
    if reed:
        cal = calibrate(Book(reed))
        print(f"  Reed calibration: offset {cal.get('offset')} coverage {cal.get('coverage')} segments {cal.get('segments')}")
        if cal.get("offset") != 21 or cal["status"] != "ok" or pdf_of(cal, 40) != 61:
            print("FAIL positive control: Reed printed 40 must map to pdf 61 (offset 21)"); ok = False
    # 2b. two-offset control: Sze 3rd ed. has printed 94 at pdf 100 and 395 at pdf 400 (offsets 6 and 5)
    sze = next((p for p in root.rglob("*.pdf") if "3rd_ed_Physics of Semiconductor" in p.name), None)
    if sze:
        cal = calibrate(Book(sze))
        got = (pdf_of(cal, 94), pdf_of(cal, 395))
        print(f"  Sze 3rd two-offset control: printed 94 -> pdf {got[0]}, printed 395 -> pdf {got[1]}; segments {len(cal.get('segments', []))}")
        if got != (100, 400):
            print("FAIL two-offset control: expected (100, 400)"); ok = False
    else:
        print("  (Reed not found — calibration positive control skipped)")
    # 2c. contents-page parser regression: entries whose page number is a small
    # integer must survive (Reed '1' / 'Fundamentals' / '1' — swallowed before the fix)
    if reed:
        ents = _parse_contents_pages(Book(reed))
        first = ents[0]["title"] if ents else None
        print(f"  Reed contents parse: {len(ents)} entries, first = {first!r}")
        if not ents or not first.startswith("1 Fundamentals") or ents[0]["printed_page"] != 1:
            print("FAIL contents-page control: first entry must be '1 Fundamentals' at printed 1"); ok = False
    # 3. glossary parser: synthetic index page must parse; a prose page must NOT look like an index
    synthetic = "\n".join(["Index", "absorption coefficient, 45, 102–104", "adiabatic taper, 210",
                           "Bragg grating, 88, 91", "coupling efficiency, 12, 13, 300", "effective index, 33"] * 3)
    is_idx, hits, total = _is_index_page(synthetic)
    prose = "\n".join(["The effective index of the mode depends on the waveguide geometry and the wavelength."] * 15)
    is_prose_idx, _, _ = _is_index_page(prose)
    print(f"  glossary control: synthetic index detected={is_idx} ({hits}/{total}); prose detected={is_prose_idx}")
    if not is_idx or is_prose_idx:
        print("FAIL glossary page detection controls"); ok = False
    m = GLOSSARY_LINE.match("absorption coefficient, 45, 102–104")
    if not m or _expand_pages(m.group("pages")) != [45, 102, 103, 104]:
        print("FAIL glossary line parse"); ok = False
    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def pages_cmd(root: Path | None, book_sub: str, pdf: str | None, verify: bool, redo: bool) -> int:
    """--pages: the write-once per-page store citations point at (layout and rules: verify/pagestore.py).
    OCR-sidecar books need no store: their .ocr/text pages are read in place."""
    sys.path.insert(0, str(HERE.parent / "verify"))
    import pagestore  # noqa: PLC0415
    if pdf:
        targets = [Path(pdf)]
    else:
        if root is None:
            print("--pages needs --root or --pdf"); return 2
        bs = _load_lib(root)["books"]
        hits = [b for b in bs if book_sub.lower() in b["id"].lower()]
        for b in hits:
            if b["access"] != "text-layer":
                print(f"{b['id'][:60]}: {b['access']} — cited pages are read from its .ocr/text in place, no store")
        targets = [Path(b["path"]) for b in hits if b["access"] == "text-layer"]
    if not targets:
        print("no text-layer PDF matched"); return 1
    for t in targets:
        if not t.exists():
            print(f"{t}: not found"); return 1
        if verify:
            drift = pagestore.verify_store(t)
            print(f"{t.name[:60]}: {len(drift)} page(s) differ from a fresh extraction {drift[:20]}")
            continue
        rep = pagestore.build_store(t, redo=redo)
        print(f"{t.name[:60]}: written {len(rep['written'])}, kept {len(rep['kept'])}, redone {rep['redone'][:20]}, "
              f"no text on {len(rep['empty'])} page(s) {rep['empty'][:20]}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=str(DEFAULT_ROOT) if DEFAULT_ROOT else None)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--only", help="build only PDFs whose path contains this substring")
    ap.add_argument("--search", nargs="+")
    ap.add_argument("--locate", help="book substring")
    ap.add_argument("--printed", type=int)
    ap.add_argument("--export", help="book substring")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--notes", nargs="?", const="", metavar="BOOK", help="write <book>.md reading maps (all books, or one)")
    ap.add_argument("--pages", nargs="?", const="", metavar="BOOK",
                    help="write the per-page text store of text-layer books (verify/pagestore.py); with --pdf, of any PDF")
    ap.add_argument("--pdf", help="with --pages: a PDF outside the library (lecture); always read through its text layer")
    ap.add_argument("--verify", action="store_true", help="with --pages: report store pages that differ from a fresh extraction")
    ap.add_argument("--redo", action="store_true", help="with --pages: rewrite changed pages, moving the old text to previous/")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.pages is not None or a.pdf:
        return pages_cmd(Path(a.root) if a.root else None, a.pages or "", a.pdf, a.verify, a.redo)
    if a.root is None:
        ap.error("--root is required: TEXTBOOKS root unset in adapt/host.toml")
    root = Path(a.root)
    if a.selftest:
        return selftest(root)
    if a.build:
        return build(root, a.only)
    if a.notes is not None:
        return notes(root, a.notes or None)
    if a.search:
        return search(root, a.search)
    if a.locate:
        if a.printed is None:
            print("--locate needs --printed"); return 2
        return locate(root, a.locate, a.printed)
    if a.export:
        return export(root, a.export)
    if a.stats:
        return stats(root)
    ap.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
