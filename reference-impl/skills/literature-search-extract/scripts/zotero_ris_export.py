#!/usr/bin/env python3
"""zotero_ris_export.py — build a Zotero-importable RIS file from a bib JSON.

Part of the literature-search-extract skill. Pure stdlib (urllib only); no pip.

Input: a JSON file describing bibliography items:

    {
      "collection": "optional default collection name",
      "items": [
        {
          "id": "desmet2021",                      # required, unique key
          "doi": "10.1109/JPHOT.2020.3039900",     # preferred identifier
          "first_author": "Desmet", "year": 2021,   # optional, for status log
          "title": "short label",                  # optional, for status log
          "attachments": ["D:\\path\\file.pdf"],  # optional -> RIS L1 lines
          "notes": "free text -> RIS N1 line",     # optional
          "manual": {                              # fallback / no-DOI items
            "type": "JOUR",                        # RIS TY (JOUR/CONF/RPRT...)
            "title": "...", "authors": ["Last, First", "..."],
            "year": 2026, "venue": "...", "volume": "", "issue": "",
            "pages": "", "publisher": "", "url": ""
          }
        }
      ]
    }

Metadata source per item (in order):
  1. DOI content negotiation: GET https://doi.org/<doi>
     Accept: application/x-research-info-systems  (Crossref & DataCite both
     serve RIS directly; verified 2026-08-31)
  2. Crossref REST: GET https://api.crossref.org/works/<doi> -> JSON -> RIS
  3. "manual" metadata block -> RIS
Gap fills after the record is built (each named in the status log):
  - a DOI record with no PY/Y1/DA takes Crossref's publication year, else the
    item's ledger "year" with an N1 line saying so (never a deposit date);
  - a manual arXiv item with no authors or year reads them from the arXiv API
    through verify/apabib.py's access-policy guard.

This script's own fetcher contacts only doi.org and api.crossref.org; the
arXiv fill goes through apabib's guarded fetch. Output file is
"<collection-name>.ris" in --out-dir; Zotero's File->Import (with "Place
imported collections and items into new collections" checked) then creates a
collection named exactly after the file. The local Zotero HTTP API cannot do
this: /api/ is read-only and /connector/saveItems ignores collection targeting
(verified 2026-08-31), so file import IS the supported named-collection path.

Usage:
  python zotero_ris_export.py ITEMS.json --collection-name "My Collection" \
      [--out-dir DIR] [--sleep 0.7]
  python zotero_ris_export.py ITEMS.json --collection-name "My Collection" \
      [--out-dir DIR] --check          # lint an already-produced RIS only
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "zotero-ris-export/1.0 (literature-search-extract skill; stdlib urllib)"}
RIS_ACCEPT = "application/x-research-info-systems"
ALLOWED_HOSTS = ("doi.org", "api.crossref.org")
EOL = "\r\n"  # RIS canonical line ending; Zotero accepts it on every platform


def _get(url: str, accept: str | None = None, timeout: int = 40,
         retries: int = 2) -> bytes:
    host = urllib.parse.urlparse(url).netloc
    if host not in ALLOWED_HOSTS:
        raise RuntimeError(f"refusing non-allowlisted host: {host}")
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
        except Exception as e:  # noqa: BLE001 - network layer, retry once
            last_err = e
            if attempt < retries:
                time.sleep(1.5)
                continue
            raise
    raise RuntimeError(str(last_err))


# ---------------------------------------------------------------- RIS helpers

def parse_ris_records(text: str) -> list[list[tuple[str, str]]]:
    """Parse RIS text into records of (TAG, value) pairs. Lenient."""
    records, current = [], []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            continue
        m = re.match(r"^([A-Z][A-Z0-9])  ?-  ?(.*)$", line)
        if not m:
            m2 = re.match(r"^([A-Z][A-Z0-9])  ?-$", line)
            if m2:
                m = m2
        if m:
            tag = m.group(1)
            val = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
            if tag == "TY" and current:
                records.append(current)
                current = []
            current.append((tag, val))
            if tag == "ER":
                records.append(current)
                current = []
        elif current:
            # continuation line -> append to previous value
            t, v = current[-1]
            current[-1] = (t, v + " " + line.strip())
    if current:
        records.append(current)
    return records


def record_to_text(rec: list[tuple[str, str]]) -> str:
    body = [f"{t}  - {v}".rstrip() for t, v in rec if t != "ER"]
    body.append("ER  - ")
    return EOL.join(body) + EOL


def ris_from_doi(doi: str) -> list[tuple[str, str]] | None:
    url = "https://doi.org/" + urllib.parse.quote(doi, safe="/().;:")
    raw = _get(url, accept=RIS_ACCEPT)
    text = raw.decode("utf-8", errors="replace").lstrip("\ufeff")
    recs = parse_ris_records(text)
    return recs[0] if recs else None


CSL_TO_RIS_TYPE = {
    "journal-article": "JOUR", "article-journal": "JOUR",
    "proceedings-article": "CONF", "paper-conference": "CONF",
    "posted-content": "RPRT", "report": "RPRT", "preprint": "RPRT",
    "book": "BOOK", "chapter": "CHAP", "book-chapter": "CHAP",
    "dataset": "DATA", "standard": "STAND",
}


def ris_from_crossref(doi: str) -> list[tuple[str, str]] | None:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/().;:")
    data = json.loads(_get(url).decode("utf-8", errors="replace").lstrip("\ufeff"))
    msg = data.get("message", {})
    if not msg:
        return None
    rec: list[tuple[str, str]] = []
    rec.append(("TY", CSL_TO_RIS_TYPE.get(msg.get("type", ""), "GEN")))
    for a in msg.get("author", []) or []:
        if a.get("family"):
            rec.append(("AU", f"{a['family']}, {a.get('given', '')}".rstrip(", ")))
        elif a.get("name"):
            rec.append(("AU", a["name"]))
    title = (msg.get("title") or [""])[0]
    if title:
        rec.append(("TI", title))
    cont = (msg.get("container-title") or [""])
    if cont and cont[0]:
        rec.append(("T2", cont[0]))
    for c in cont[1:]:                     # a chapter's book title often follows its series title
        if c:
            rec.append(("T3", c))
    year = None
    for k in ("published-print", "published-online", "issued"):
        dp = msg.get(k, {}).get("date-parts", [[None]])
        if dp and dp[0] and dp[0][0]:
            year = dp[0][0]
            break
    if year:
        rec.append(("PY", str(year)))
    if msg.get("volume"):
        rec.append(("VL", str(msg["volume"])))
    if msg.get("issue"):
        rec.append(("IS", str(msg["issue"])))
    page = msg.get("page") or msg.get("article-number")
    if page:
        if "-" in str(page):
            sp, ep = str(page).split("-", 1)
            rec.append(("SP", sp))
            rec.append(("EP", ep))
        else:
            rec.append(("SP", str(page)))
    rec.append(("DO", doi))
    if msg.get("URL"):
        rec.append(("UR", msg["URL"]))
    if msg.get("publisher"):
        rec.append(("PB", msg["publisher"]))
    return rec


def ris_from_manual(man: dict) -> list[tuple[str, str]]:
    rec: list[tuple[str, str]] = [("TY", man.get("type", "GEN"))]
    for a in man.get("authors", []) or []:
        rec.append(("AU", a))
    if man.get("title"):
        rec.append(("TI", man["title"]))
    if man.get("venue"):
        rec.append(("T2", man["venue"]))
    if man.get("year"):
        rec.append(("PY", str(man["year"])))
    for src, tag in (("volume", "VL"), ("issue", "IS"), ("pages", "SP"),
                     ("publisher", "PB"), ("url", "UR")):
        if man.get(src):
            rec.append((tag, str(man[src])))
    return rec


# ------------------------------------------------------------------- pipeline

def build_record(item: dict) -> tuple[list[tuple[str, str]] | None, str]:
    """Return (record, source_label). record=None on total failure."""
    doi = item.get("doi", "").strip()
    if doi:
        try:
            rec = ris_from_doi(doi)
            if rec and any(t == "TI" or t == "T1" for t, _ in rec):
                if not any(t == "DO" for t, _ in rec):
                    rec.append(("DO", doi))
                return rec, "doi.org RIS"
        except Exception as e:  # noqa: BLE001
            print(f"    doi.org RIS failed ({e}); trying Crossref JSON")
        try:
            rec = ris_from_crossref(doi)
            if rec:
                return rec, "crossref JSON"
        except Exception as e:  # noqa: BLE001
            print(f"    crossref JSON failed ({e})")
    if item.get("manual"):
        return ris_from_manual(item["manual"]), "manual metadata"
    return None, "FAILED"


YEAR_TAGS = {"PY", "Y1", "DA"}
ARXIV_ABS = re.compile(r"arxiv\.org/abs/([^\s?#]+?)(?:v\d+)?$", re.I)


def _apabib():
    """verify/apabib.py, imported lazily: it carries the access-policy guard for export.arxiv.org."""
    vdir = str(Path(__file__).resolve().parent.parent / "verify")
    if vdir not in sys.path:
        sys.path.insert(0, vdir)
    import apabib  # noqa: E402
    return apabib


def fill_year(rec: list[tuple[str, str]], item: dict, crossref=None) -> tuple[list[tuple[str, str]], str]:
    """A DOI record with no year (doi.org RIS omits PY for some book chapters): take Crossref's
    publication date, else the evidence-run ledger's year, named in an N1 line. Never a deposit date."""
    if YEAR_TAGS & {t for t, _ in rec} or not item.get("doi"):
        return rec, ""
    crossref = crossref or ris_from_crossref
    try:
        cr = crossref(item["doi"].strip()) or []
    except Exception as e:  # noqa: BLE001
        print(f"    crossref year lookup failed ({e})")
        cr = []
    py = next((v for t, v in cr if t == "PY"), "")
    if py:
        return rec + [("PY", py)], "year from Crossref"
    # A Springer chapter DOI is <book DOI>_<n>; the book record often carries the year the chapter
    # lacks. Taken only when that record is a book whose title is the chapter's container title.
    m = re.match(r"^(10\.1007/.+)_\d+$", item["doi"].strip())
    conts = {v.strip().lower() for t, v in cr if t in ("T2", "T3") and v.strip()}
    if m and conts:
        try:
            book = crossref(m.group(1)) or []
        except Exception as e:  # noqa: BLE001
            print(f"    crossref book lookup failed ({e})")
            book = []
        bpy = next((v for t, v in book if t == "PY"), "")
        btitle = next((v for t, v in book if t == "TI"), "")
        if bpy and dict(book).get("TY") == "BOOK" and btitle.strip().lower() in conts:
            note = f"year from the Crossref book record {m.group(1)}; the chapter record has none"
            if item.get("year") and str(item["year"]) != bpy:
                note += f"; the evidence-run ledger says {item['year']} (needs manual check)"
            return rec + [("PY", bpy), ("N1", note)], "year from Crossref book record"
    if item.get("year"):
        return rec + [("PY", str(item["year"])),
                      ("N1", "year from the evidence-run ledger; doi.org and Crossref list none")], \
            "year from run ledger"
    return rec, ""


def fill_arxiv(rec: list[tuple[str, str]], item: dict, meta=None) -> tuple[list[tuple[str, str]], str]:
    """A manual arXiv item whose ledger carried no authors or year: read them from the arXiv API
    through apabib's policy guard. Authors are arXiv display strings split last-token-as-family,
    an inference the N1 line states."""
    url = str((item.get("manual") or {}).get("url", ""))
    m = ARXIV_ABS.search(url)
    tags = {t for t, _ in rec}
    if not m or ({"AU", "A1"} & tags and YEAR_TAGS & tags):
        return rec, ""
    if meta is None:
        ab = _apabib()
        md = ab.meta_arxiv(m.group(1), ab.Guard())
    else:
        md = meta(m.group(1))
    if not md.get("ok"):
        print(f"    arXiv metadata unavailable ({md.get('status')}: {md.get('body', '')})")
        return rec, ""
    added, inferred = [], False
    if not {"AU", "A1"} & tags:
        for a in md.get("authors") or []:
            if a.get("org"):
                added.append(("AU", a["org"]))
            else:
                added.append(("AU", f"{a['family']}, {a['given']}".rstrip(", ")))
                inferred = inferred or bool(a.get("inferred"))
    if not YEAR_TAGS & tags and md.get("year"):
        added.append(("PY", str(md["year"])))
    if not added:
        return rec, ""
    if inferred:
        added.append(("N1", "authors from the arXiv API; family/given split inferred from display names"))
    head = [p for p in rec if p[0] == "TY"]
    return head + added + [p for p in rec if p[0] != "TY"], "authors/year from arXiv API"


def enrich(rec: list[tuple[str, str]], item: dict) -> list[tuple[str, str]]:
    rec = [p for p in rec if p[0] != "ER"]
    if item.get("notes"):
        rec.append(("N1", str(item["notes"])))
    for path in item.get("attachments", []) or []:
        rec.append(("L1", path))
        if not Path(path).exists():
            print(f"    WARNING: attachment path does not exist: {path}")
    return rec


def sanity_summary(rec: list[tuple[str, str]]) -> str:
    d = {}
    for t, v in rec:
        d.setdefault(t, v)
    author = d.get("AU", d.get("A1", "?")).split(",")[0]
    year_raw = d.get("PY", d.get("Y1", d.get("DA", "?")))
    year = str(year_raw).split("/")[0]
    title = d.get("TI", d.get("T1", "?"))
    return f"{author} {year} | {title[:70]}"


def lint_ris(path: Path, expected: int | None = None) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    recs = parse_ris_records(text)
    ok = True
    print(f"\n--check: {path}")
    print(f"  records parsed: {len(recs)}"
          + (f" (expected {expected})" if expected is not None else ""))
    if expected is not None and len(recs) != expected:
        ok = False
    for i, rec in enumerate(recs, 1):
        tags = [t for t, _ in rec]
        problems = []
        if tags[0] != "TY":
            problems.append("does not start with TY")
        if "ER" not in tags:
            problems.append("missing ER")
        if not ({"TI", "T1"} & set(tags)):
            problems.append("no title (TI/T1)")
        if not ({"AU", "A1"} & set(tags)):
            problems.append("no author (AU/A1)")
        if not ({"PY", "Y1", "DA"} & set(tags)):
            problems.append("no year (PY/Y1/DA)")
        status = "OK " if not problems else "BAD"
        if problems:
            ok = False
        print(f"  [{i:3d}] {status} {sanity_summary(rec)}"
              + (f"  <- {'; '.join(problems)}" if problems else ""))
    print(f"--check result: {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("items_json", help="path to the bib items JSON file")
    ap.add_argument("--collection-name", required=True,
                    help='output basename; Zotero File->Import names the new '
                         'collection after this file')
    ap.add_argument("--out-dir", default=".", help="output directory")
    ap.add_argument("--sleep", type=float, default=0.7,
                    help="seconds between remote fetches (politeness)")
    ap.add_argument("--check", action="store_true",
                    help="lint the existing output RIS instead of fetching")
    args = ap.parse_args()

    items_path = Path(args.items_json)
    data = json.loads(items_path.read_text(encoding="utf-8-sig"))
    items = data["items"] if isinstance(data, dict) else data
    out_path = Path(args.out_dir) / f"{args.collection_name}.ris"

    if args.check:
        return 0 if lint_ris(out_path, expected=len(items)) else 1

    seen_ids: set[str] = set()
    seen_dois: set[str] = set()
    chunks: list[str] = []
    failures: list[str] = []
    for n, item in enumerate(items, 1):
        iid = item.get("id", f"item{n}")
        if iid in seen_ids:
            print(f"[{n:3d}/{len(items)}] {iid}: DUPLICATE id -> skipped")
            continue
        seen_ids.add(iid)
        doi = item.get("doi", "").strip().lower()
        if doi and doi in seen_dois:
            print(f"[{n:3d}/{len(items)}] {iid}: DUPLICATE doi {doi} -> skipped")
            continue
        if doi:
            seen_dois.add(doi)
        label = f"{item.get('first_author', '?')} {item.get('year', '?')}"
        print(f"[{n:3d}/{len(items)}] {iid} ({label}, doi={item.get('doi', '-')})")
        rec, src = build_record(item)
        if rec is None:
            print("    FAILED: no metadata source succeeded and no manual block")
            failures.append(iid)
            continue
        for fill in (fill_year, fill_arxiv):
            rec, how = fill(rec, item)
            if how:
                src += f" + {how}"
        rec = enrich(rec, item)
        print(f"    ok via {src}: {sanity_summary(rec)}")
        chunks.append(record_to_text(rec))
        time.sleep(max(args.sleep, 0.0))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(chunks), encoding="utf-8", newline="")
    print(f"\nwrote {len(chunks)} records -> {out_path}")
    if failures:
        print(f"FAILED items ({len(failures)}): {', '.join(failures)}")
    lint_ok = lint_ris(out_path, expected=len(chunks))
    return 0 if (not failures and lint_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
