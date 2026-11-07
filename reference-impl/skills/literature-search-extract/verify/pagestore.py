#!/usr/bin/env python3
r"""Page pointers: a ledger row cites PDF pages, never a copied excerpt.

    source_text  textbook:<book_id>#p=127      a book in the local library (library.json id)
                 textbook:<book_id>#p=127-128  a page range (pages joined with a newline)
                 pages:<pdf path>#p=71         any other PDF; relative to the ledger folder or absolute
    page_sha256  ["<16 hex>", ...]             sha256 of each cited page's stored text, taken when the row was written
    pdf_sha256   "<16 hex>"                    sha256 of the PDF when the row was written (finds a renamed book)

`p` is always the 1-based PDF page index; the printed page belongs in the row's `locator`.
The pointer is split on its LAST '#p=' because file names may contain '#'.

Page text lives in exactly one place:
  text-layer PDF   <pdf dir>/<pdf stem>.pages/NNNN.txt, written ONCE by build_store()
                   (`textbook_index.py --pages`). manifest.json beside them records only what
                   cannot be derived: pdf_sha256, page count, created, extractor version.
                   The files are kept, not re-derived on read, because a different PyMuPDF
                   version extracts different text and the row's hash must have fixed bytes to match.
  OCR-sidecar book <pdf dir>/<pdf stem>.ocr/text/NNNN.txt as textbook_ocr.py wrote it; page status
                   (ok / sparse / excluded) is read from <stem>.ocr/manifest.json, never copied.

A store page is never rewritten in place: build_store() skips existing pages, verify_store()
reports drift without writing, and redo=True moves the old file to previous/NNNN.<sha8>.txt
first. Every row citing a redone page then FAILs on its own page_sha256 until a person re-reads it.

What the hashes prove: the cited page's text has not changed since the row was written, and
(pdf_sha256) the PDF file is the one it was written against. They do NOT prove the PDF is the
edition the locator names.
review-when: textbook_ocr.py changes its manifest schema; library.json drops `sha256` or `access`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "textbook-pages@1"
PREFIXES = ("textbook:", "pages:")
SHA_LEN = 16
JOIN = "\n"

# library.json override (selftest); None = load from the TEXTBOOKS root
LIBRARY_OVERRIDE: dict | None = None
_lib_cache: dict | None = None
_pdf_sha_cache: dict[str, str] = {}


def is_pointer(ref) -> bool:
    return isinstance(ref, str) and ref.startswith(PREFIXES)


def parse(ref: str) -> tuple[str, str, int, int]:
    """'textbook:X#p=3-4' -> ('textbook', 'X', 3, 4). Raises ValueError on a malformed pointer."""
    scheme, _, rest = ref.partition(":")
    target, sep, pages = rest.rpartition("#p=")
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", pages)
    if not sep or not target or not m:
        raise ValueError(f"malformed page pointer {ref!r} (want {scheme}:<target>#p=N or #p=N-M)")
    a = int(m.group(1))
    b = int(m.group(2) or a)
    if a < 1 or b < a:
        raise ValueError(f"bad page range in {ref!r}")
    return scheme, target, a, b


def store_dir(pdf: Path) -> Path:
    return pdf.with_name(pdf.stem + ".pages")


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def pdf_sha(pdf: Path) -> str:
    """Full sha256 of a PDF, cached per (path, size, mtime) within the process."""
    st = pdf.stat()
    k = f"{pdf}|{st.st_size}|{st.st_mtime_ns}"
    if k not in _pdf_sha_cache:
        h = hashlib.sha256()
        with open(pdf, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        _pdf_sha_cache[k] = h.hexdigest()
    return _pdf_sha_cache[k]


def textbook_root() -> Path | None:
    env = os.environ.get("TEXTBOOKS_ROOT")
    if env:
        return Path(env)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks" / "_lib"))
        import roots as hkroots  # noqa: PLC0415
        p = hkroots.path("TEXTBOOKS")
        return Path(p) if p else None
    except Exception:                                       # noqa: BLE001
        return None


def library() -> dict:
    global _lib_cache
    if LIBRARY_OVERRIDE is not None:
        return LIBRARY_OVERRIDE
    if _lib_cache is None:
        root = textbook_root()
        p = root / "library.json" if root else None
        _lib_cache = json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else {"books": []}
    return _lib_cache


def find_book(book_id: str, pdf_sha256: str | None = None) -> tuple[dict | None, str]:
    """Library entry by id; falls back to the row's pdf_sha256 prefix (a renamed book keeps its bytes)."""
    books = library().get("books", [])
    for b in books:
        if b.get("id") == book_id:
            return b, "id"
    if pdf_sha256:
        hits = [b for b in books if str(b.get("sha256", "")).startswith(pdf_sha256)]
        if len(hits) == 1:
            return hits[0], "sha256 (book renamed)"
    return None, ""


def book_id_for(pdf: Path) -> str | None:
    """The library id of a PDF (by path, then by sha256), or None when it is not a library book."""
    rp = str(pdf.resolve()).lower()
    books = library().get("books", [])
    for b in books:
        if str(Path(b.get("path", "")).resolve()).lower() == rp:
            return b["id"]
    s = pdf_sha(pdf)
    for b in books:
        if b.get("sha256") == s:
            return b["id"]
    return None


# --------------------------------------------------------------------------- build
def _has_store_manifest(d: Path) -> dict | None:
    m = d / "manifest.json"
    return json.loads(m.read_text(encoding="utf-8")) if m.exists() else None


def build_store(pdf: Path, pages: list[int] | None = None, redo: bool = False) -> dict:
    """Write text-layer pages of `pdf` into <stem>.pages/ (all pages, or `pages`). Existing pages are
    kept unless redo=True, which first moves a CHANGED page to previous/NNNN.<sha8>.txt.
    Returns {'written': [...], 'kept': [...], 'redone': [...], 'empty': [...]}."""
    import fitz  # noqa: PLC0415
    pdf = Path(pdf)
    d = store_dir(pdf)
    d.mkdir(exist_ok=True)
    doc = fitz.open(pdf)
    man = _has_store_manifest(d)
    full = pdf_sha(pdf)
    if man is None:
        man = {"schema": SCHEMA, "pdf": pdf.name, "pdf_sha256": full, "pages": doc.page_count,
               "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "extractor": f"pymupdf {getattr(fitz, 'VersionBind', '?')} page.get_text()"}
    elif man.get("pdf_sha256") != full and not redo:
        raise RuntimeError(f"{pdf.name}: the PDF changed since its page store was built "
                           f"({man.get('pdf_sha256', '')[:12]} -> {full[:12]}); rebuild with redo=True (--redo)")
    rep = {"written": [], "kept": [], "redone": [], "empty": []}
    for p in (pages or range(1, doc.page_count + 1)):
        if not 1 <= p <= doc.page_count:
            raise ValueError(f"{pdf.name}: page {p} out of range 1..{doc.page_count}")
        new = doc[p - 1].get_text().encode("utf-8")
        f = d / f"{p:04d}.txt"
        if f.exists():
            old = f.read_bytes()
            if old == new or not redo:
                rep["kept"].append(p)
                continue
            prev = d / "previous"
            prev.mkdir(exist_ok=True)
            shutil.move(str(f), str(prev / f"{p:04d}.{sha_bytes(old)[:8]}.txt"))
            rep["redone"].append(p)
        f.write_bytes(new)
        rep["written"].append(p)
        if not new.strip():
            rep["empty"].append(p)
    if redo:
        man["pdf_sha256"] = full
        man["pages"] = doc.page_count
        man.setdefault("redone", []).append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                             "pages": rep["redone"]})
    (d / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def verify_store(pdf: Path) -> list[int]:
    """Pages whose stored text differs from a fresh extraction (writes nothing)."""
    import fitz  # noqa: PLC0415
    pdf = Path(pdf)
    d = store_dir(pdf)
    doc = fitz.open(pdf)
    return [p for p in range(1, doc.page_count + 1)
            if (d / f"{p:04d}.txt").exists() and (d / f"{p:04d}.txt").read_bytes() != doc[p - 1].get_text().encode("utf-8")]


# --------------------------------------------------------------------------- resolve
@dataclass
class Page:
    n: int
    status: str            # ok | sparse | excluded | missing | out-of-range
    text: str | None = None
    sha: str | None = None


@dataclass
class Resolved:
    ref: str
    pdf: Path | None = None
    route: str = ""        # extraction route: text-layer | ocr
    book: dict | None = None
    found_by: str = ""
    pages: list[Page] = field(default_factory=list)
    store_pdf_sha: str | None = None
    error: str = ""

    @property
    def text(self) -> str | None:
        if self.error or any(p.text is None for p in self.pages):
            return None
        # trailing whitespace dropped per page so a word hyphenated across the page break reads
        # 'recom-\nbine', which spannorm joins; the hashes cover the stored bytes, not this join
        return JOIN.join(p.text.rstrip() for p in self.pages)


def _read(f: Path, n: int, status: str = "ok") -> Page:
    if not f.exists():
        return Page(n, "missing")
    b = f.read_bytes()
    return Page(n, status, b.decode("utf-8", errors="replace"), sha_bytes(b))


def resolve(ref: str, base: Path, pdf_sha256: str | None = None) -> Resolved:
    try:
        scheme, target, a, b = parse(ref)
    except ValueError as e:
        return Resolved(ref, error=str(e))
    r = Resolved(ref)
    if scheme == "textbook":
        book, how = find_book(target, pdf_sha256)
        if not book:
            r.error = f"book {target!r} is not in library.json" + (" (and no library book has that pdf_sha256)" if pdf_sha256 else "")
            return r
        r.book, r.found_by, r.pdf = book, how, Path(book["path"])
        npages = int(book.get("pages") or 0)
        ocr = book.get("access") == "ocr-sidecar"
    else:
        pdf = Path(target)
        r.pdf = pdf if pdf.is_absolute() else (base / pdf)
        r.found_by = "path"
        ocr = False
        npages = 0
    if ocr:
        r.route = "ocr"
        side = r.pdf.with_name(r.pdf.stem + ".ocr")
        try:
            om = json.loads((side / "manifest.json").read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            r.error = f"OCR sidecar manifest missing for {r.pdf.name}"
            return r
        status = {x["page"]: x["status"] for x in om.get("pages", [])}
        npages = npages or len(status)
        for p in range(a, b + 1):
            st = status.get(p)
            if p > npages or st is None:
                r.pages.append(Page(p, "out-of-range"))
            elif st in ("ok", "sparse"):
                r.pages.append(_read(side / "text" / f"{p:04d}.txt", p, st))
            else:
                r.pages.append(Page(p, "excluded"))
        return r
    r.route = "text-layer"
    d = store_dir(r.pdf)
    man = _has_store_manifest(d)
    if man is None:
        r.error = f"no page store for {r.pdf.name} — run `textbook_index.py --pages` (or ct.page_ref) first"
        return r
    r.store_pdf_sha = man.get("pdf_sha256")
    npages = int(man.get("pages") or npages)
    for p in range(a, b + 1):
        r.pages.append(Page(p, "out-of-range") if p > npages else _read(d / f"{p:04d}.txt", p))
    return r


# --------------------------------------------------------------------------- admission
# A source is screened before it is cited. Rulings that need a reader (identity read off a page,
# duplicate copies, rejections) live in <TEXTBOOKS root>/admission.json; limits that can be measured
# (OCR text, identity textbook_index could not find) are derived here at read time and stored nowhere.
ADMISSION_OVERRIDE: dict | None = None
_adm_cache: dict | None = None
GRADES = ("citable", "limited", "proposed-reject", "rejected")


def admission_rulings() -> dict:
    global _adm_cache
    if ADMISSION_OVERRIDE is not None:
        return ADMISSION_OVERRIDE
    if _adm_cache is None:
        root = textbook_root()
        p = root / "admission.json" if root else None
        _adm_cache = json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else {"books": {}}
    return _adm_cache


def admission(book: dict | None) -> tuple[str, list[tuple[str, str]]]:
    """(grade, [(scope, reason)]) for a library book; scope 'all' applies to every row, 'numbers' only to a
    row whose claim carries a number. A non-library PDF (pages:) is a course's own material: citable."""
    if not book:
        return "citable", []
    rule = admission_rulings().get("books", {}).get(book["id"], {})
    status = rule.get("status", "citable")
    reasons: list[tuple[str, str]] = []
    if status in ("rejected", "proposed-reject"):
        reasons.append(("all", rule.get("reason", status)))
    elif status == "limited":
        reasons.append((rule.get("limit", "all"), rule.get("reason", "limited")))
    if rule.get("duplicate_of"):
        status = "limited" if status == "citable" else status
        reasons.append(("all", f"duplicate copy of {rule['duplicate_of'][:60]!r} — cite the canonical book"))
    if book.get("access") == "ocr-sidecar":
        status = "limited" if status == "citable" else status
        reasons.append(("numbers", "OCR text — confirm every number on the page image before quoting it"))
    ident = book.get("identity") or {}
    if not (ident.get("edition") or ident.get("isbn")) and not rule.get("identity_confirmed"):
        status = "limited" if status == "citable" else status
        reasons.append(("all", "edition not confirmed from the PDF (no edition/ISBN found, none read off a page) — "
                               "the locator's edition is the file name's claim"))
    return status, reasons


def canonical(book_id: str) -> str:
    """The book a duplicate copy stands for (itself when it is not a duplicate)."""
    return admission_rulings().get("books", {}).get(book_id, {}).get("duplicate_of") or book_id


_doc_cache: dict[str, str] = {}


def document_text(r: Resolved) -> str | None:
    """Every readable page of the resolved document, joined (cached per PDF). The numeric check settles a
    number missing from the span against this: the source of a page pointer is the whole document."""
    if r.error or r.pdf is None:
        return None
    k = str(r.pdf)
    if k not in _doc_cache:
        if r.book:
            n = int(r.book.get("pages") or 0)
            ref = f"textbook:{r.book['id']}#p=1-{n}"
        else:
            man = _has_store_manifest(store_dir(r.pdf)) or {}
            n = int(man.get("pages") or 0)
            ref = f"pages:{r.pdf}#p=1-{n}"
        full = resolve(ref, r.pdf.parent)
        _doc_cache[k] = JOIN.join((p.text or "").rstrip() for p in full.pages) if not full.error else ""
    return _doc_cache[k] or None


def printed_pages(r: Resolved) -> list[int | None] | None:
    """Printed page of each cited page via the book's calibration, only when that calibration is 'ok'."""
    cal = (r.book or {}).get("calibration") or {}
    if cal.get("status") != "ok":
        return None
    out = []
    for pg in r.pages:
        v = None
        for s in cal.get("segments", []):
            if s["pdf_from"] <= pg.n <= s["pdf_to"]:
                v = pg.n - s["offset"]
                v = v if v >= 1 else None
                break
        out.append(v)
    return out


LOCATOR_PAGES = re.compile(r"(?P<pdf>\bPDF\s+)?(?:\bpp?\.|\bslides?)\s*(?P<a>\d{1,4})(?:\s*[-–]\s*(?P<b>\d{1,4}))?", re.I)


def locator_pages(locator: str) -> tuple[set[int], set[int]]:
    """(printed pages, PDF pages) a locator names: 'p.27' / 'pp.27-29' are printed, 'PDF p.61' and
    'slide 12' are PDF page indexes (a slide deck has no separate printed numbering)."""
    printed: set[int] = set()
    pdf: set[int] = set()
    for m in LOCATOR_PAGES.finditer(locator or ""):
        a = int(m.group("a"))
        b = int(m.group("b") or a)
        if b < a or b - a >= 200:
            continue
        is_pdf = bool(m.group("pdf")) or m.group(0).lower().lstrip().startswith("slide")
        (pdf if is_pdf else printed).update(range(a, b + 1))
    return printed, pdf


def stamp(ref: str, base: Path) -> tuple[list[str], str]:
    """(page_sha256 list, pdf_sha256) a writer stores on a new row. Raises when the pointer does not resolve."""
    r = resolve(ref, base)
    if r.error:
        raise ValueError(r.error)
    bad = [f"p{p.n}:{p.status}" for p in r.pages if p.text is None]
    if bad:
        raise ValueError(f"{ref}: unreadable pages {bad}")
    return [p.sha[:SHA_LEN] for p in r.pages], pdf_sha(r.pdf)[:SHA_LEN]
