#!/usr/bin/env python3
r"""apabib — APA 7 reference entries generated from DOIs / arXiv ids, never typed by hand.

WHY THIS EXISTS (R20, BB10). A published article's reference list was hand-typed and invented
author initials; an evidence run's bibliography carried Fritzsch 2019's authors in the wrong order
(known error N-012). Every field here comes from a registry record fetched at run time:
Crossref for a Crossref DOI, DataCite for a DataCite DOI (found through doi.org/ra), the arXiv
API for an arXiv id. A field the registry does not state is left out; an id whose record cannot be
fetched is emitted as `需人工確認 (needs manual check)` with the reason and NO entry body. This
tool never guesses an author, initial, title or year.

HTTP goes through verify/fetchsrc.py (`_get`: per-hop host policy, polite User-Agent, arXiv
pacing) and every first host is judged by connectors/access_policy.py BEFORE the request, with a
per-invocation count so a host's `max_per_run` is respected (DataCite is an unlisted host: one
call per invocation, a second DataCite DOI is flagged needs-manual-check, not fetched).

Why a script and not `inbox.py bib --apa`: `inbox.py bib` derives from every run in the vault with
no input list and writes under Bibliography/; this takes an explicit id list (or one run's
sources), writes nothing unless `--out`, and needs no vault. `inbox.py` is untouched by it.

Usage:
    python apabib.py <id> [<id> ...] [--ids-file f.txt] [--run <run_dir>] [--out f.md] [--json]
        <id>   10.xxxx/yyy | doi:10.xxxx/yyy | https://doi.org/10.xxxx/yyy | arxiv:2608.15135 | 1807.10059
        --run  with ids: also write a diff report of the fetched records against that run's
               ledger.jsonl (expect_authors / expect_year / expect_title); without ids: the ids are the
               run's DOI/arXiv sources.
    python apabib.py --selftest

Output: Markdown — APA entries sorted by first author, then the needs-manual-check list, then (with --run) the
diff report. Exit: 0 every id fetched · 1 usage · 2 selftest failed · 3 at least one id needs manual check.
Entry text uses *...* for italics. Titles are printed as the registry states them (sentence-case
conversion needs a human: proper nouns); a title that looks Title Case is listed in the footer.
review-when: Crossref / DataCite / arXiv change their record fields; access_policy.decide changes its
signature; APA 7 reference formats are revised (8th edition).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import urllib.parse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "connectors"))
import access_policy  # noqa: E402
import fetchsrc  # noqa: E402

TOOL = "apabib/1"
DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s\"<>?#]+)", re.I)
ARXIV_NEW = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
ARXIV_OLD = re.compile(r"^([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?$", re.I)
ENDASH = "–"
MANUAL = "需人工確認 (needs manual check)"

GET = fetchsrc._get   # tests swap this for canned answers: (url) -> (status, body bytes, content_type, final_url)


# ---------------------------------------------------------------- ids
def parse_id(raw: str) -> tuple[str, str] | None:
    """('doi', lower-cased doi) | ('arxiv', versionless id) | None. A 10.48550/arxiv.X DOI is the arXiv id X."""
    s = (raw or "").strip()
    low = s.lower()
    for pre in ("arxiv:", "arxiv.org/abs/", "https://arxiv.org/abs/", "http://arxiv.org/abs/"):
        if low.startswith(pre):
            s = s[len(pre):]
            break
    else:
        m = DOI_RE.search(s)
        if m:
            doi = m.group(1).rstrip(".,;)")
            mm = re.match(r"10\.48550/arxiv\.(.+)$", doi, re.I)
            if mm:
                return "arxiv", re.sub(r"v\d+$", "", mm.group(1))
            return "doi", doi
    for rx in (ARXIV_NEW, ARXIV_OLD):
        m = rx.match(s.strip())
        if m:
            return "arxiv", m.group(1)
    return None


# ---------------------------------------------------------------- guarded fetch
class Guard:
    """Per-invocation host accounting on top of the policy file."""

    def __init__(self) -> None:
        self.used: dict[str, int] = {}
        self.unlisted: set[str] = set()
        self.pol = access_policy.load()

    def get(self, url: str) -> tuple[int, bytes, str]:
        host = access_policy.host_of(url)
        ok, reason, row = access_policy.decide(host, "script", self.pol, used_on_host=self.used.get(host, 0),
                                               distinct_unlisted=len(self.unlisted - {host}))
        if not ok:
            return -1, reason.encode("utf-8"), ""            # -1 = refused by policy, nothing sent
        self.used[host] = self.used.get(host, 0) + 1
        if row.get("unlisted"):
            self.unlisted.add(host)
        if GET is fetchsrc._get:
            fetchsrc._pace(host)
        r = GET(url)
        if r[0] == 0:                                        # transport failure (timeout): one more try
            if GET is fetchsrc._get:
                fetchsrc._pace(host)
            r = GET(url)
        return r[0], r[1], r[2]


def _year(parts) -> int | None:
    try:
        return int(parts["date-parts"][0][0])
    except Exception:                                        # noqa: BLE001
        return None


def meta_crossref(doi: str, g: Guard) -> dict:
    st, body, _ = g.get("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe=""))
    if st != 200:
        return {"ok": False, "via": "crossref", "status": st, "body": body[:160].decode("utf-8", "replace")}
    try:
        m = json.loads(body)["message"]
    except Exception:                                        # noqa: BLE001
        return {"ok": False, "via": "crossref", "status": st, "body": "unparseable record"}

    def people(key):
        out = []
        for a in m.get(key) or []:
            if a.get("family") or a.get("given"):
                out.append({"family": a.get("family", ""), "given": a.get("given", ""), "suffix": a.get("suffix", "")})
            elif a.get("name"):
                out.append({"org": a["name"]})
        return out

    # `created`/`deposited`/`indexed` are Crossref record dates, not publication dates: a record
    # with none of the four below has no year (n.d., manual check), never its deposit year.
    year = None
    for k in ("issued", "published", "published-print", "published-online"):
        year = _year(m.get(k) or {})
        if year:
            break
    return {"ok": True, "via": "crossref", "kind": m.get("type", ""), "doi": doi,
            "authors": people("author"), "editors": people("editor"), "year": year,
            "title": (m.get("title") or [""])[0], "containers": m.get("container-title") or [],
            "volume": m.get("volume", ""), "issue": m.get("issue", ""),
            "pages": m.get("page", "") or m.get("article-number", ""), "publisher": m.get("publisher", ""),
            "edition": m.get("edition-number", "")}


def meta_datacite(doi: str, g: Guard) -> dict:
    st, body, _ = g.get("https://api.datacite.org/dois/" + urllib.parse.quote(doi, safe=""))
    if st != 200:
        return {"ok": False, "via": "datacite", "status": st, "body": body[:160].decode("utf-8", "replace")}
    try:
        a = json.loads(body)["data"]["attributes"]
    except Exception:                                        # noqa: BLE001
        return {"ok": False, "via": "datacite", "status": st, "body": "unparseable record"}
    authors = []
    for c in a.get("creators") or []:
        if c.get("familyName") or c.get("givenName"):
            authors.append({"family": c.get("familyName", ""), "given": c.get("givenName", ""), "suffix": ""})
        elif c.get("name"):
            authors.append({"org": c["name"]})
    t = ((a.get("titles") or [{}])[0]).get("title", "")
    rt = ((a.get("types") or {}).get("resourceType") or "")
    return {"ok": True, "via": "datacite", "kind": "datacite:" + (rt or (a.get("types") or {}).get("resourceTypeGeneral", "")),
            "doi": doi, "authors": authors, "editors": [], "year": a.get("publicationYear"),
            "title": t, "containers": [], "volume": "", "issue": "", "pages": "", "publisher": a.get("publisher", ""),
            "edition": ""}


def meta_arxiv(aid: str, g: Guard) -> dict:
    st, body, _ = g.get("https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(aid))
    if st != 200:
        return {"ok": False, "via": "arxiv", "status": st, "body": body[:160].decode("utf-8", "replace")}
    try:
        root = ET.fromstring(body)
        ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
        e = root.find("a:entry", ns)
        if e is None or e.find("a:title", ns) is None or "Error" in (e.findtext("a:title", "", ns) or ""):
            return {"ok": False, "via": "arxiv", "status": st, "body": "no entry for this id"}
        names = [(x.findtext("a:name", "", ns) or "").strip() for x in e.findall("a:author", ns)]
        pub = e.findtext("a:published", "", ns) or ""
        doi_pub = e.findtext("x:doi", "", ns) or ""
        jref = e.findtext("x:journal_ref", "", ns) or ""
    except Exception:                                        # noqa: BLE001
        return {"ok": False, "via": "arxiv", "status": st, "body": "unparseable record"}
    authors, warn = [], []
    for n in names:
        toks = n.split()
        if len(toks) < 2:
            authors.append({"org": n} if n else {"org": "?"})
            warn.append(f"author {n!r}: single token, kept whole")
            continue
        # arXiv states one display string, not a family/given split: last token = family is an INFERENCE.
        authors.append({"family": toks[-1], "given": " ".join(toks[:-1]), "suffix": "", "inferred": True})
        if len(toks) > 2 or any(t[:1].islower() for t in toks):
            warn.append(f"author {n!r}: family/given split inferred (arXiv gives one display string); check")
    if doi_pub:
        warn.append(f"arXiv lists a published version: doi {doi_pub}; APA prefers citing that")
    if jref:
        warn.append(f"arXiv journal_ref: {jref}")
    return {"ok": True, "via": "arxiv", "kind": "preprint", "arxiv_id": aid, "doi": "", "authors": authors,
            "editors": [], "year": int(pub[:4]) if pub[:4].isdigit() else None,
            "title": e.findtext("a:title", "", ns), "containers": [], "volume": "", "issue": "", "pages": "",
            "publisher": "arXiv", "edition": "", "warnings": warn}


def fetch_meta(kind: str, ident: str, g: Guard) -> dict:
    if kind == "arxiv":
        return meta_arxiv(ident, g)
    m = meta_crossref(ident, g)
    if m["ok"] or m["status"] != 404:
        return m
    # Crossref does not know it: which registration agency does?
    st, body, _ = g.get("https://doi.org/ra/" + urllib.parse.quote(ident, safe=""))
    ra = ""
    if st == 200:
        try:
            ra = (json.loads(body)[0].get("RA") or "")
        except Exception:                                    # noqa: BLE001
            ra = ""
    if ra.lower() == "datacite":
        return meta_datacite(ident, g)
    m["body"] = (m.get("body") or "") + (f"; doi.org/ra says registration agency {ra!r}" if ra else
                                         f"; doi.org/ra lookup status {st} (DOI not registered?)")
    return m


# ---------------------------------------------------------------- APA 7 formatting
def initials(given: str) -> str:
    out = []
    for tok in given.replace("’", "'").split():
        if tok[:1].islower():                                # a particle (da, van): kept as written, never an initial
            out.append(tok)
            continue
        parts = [p for p in tok.split("-") if p]
        done = []
        for p in parts:
            ch = next((c for c in p if c.isalpha()), "")
            if ch:
                done.append(ch.upper() + ".")
        if done:
            out.append("-".join(done))
    return " ".join(out)


def one_author(a: dict) -> str:
    if "org" in a:
        return a["org"]
    ini = initials(a.get("given", ""))
    s = a.get("family", "") + (f", {ini}" if ini else "")
    if a.get("suffix"):
        s += f", {a['suffix']}"
    return s


def author_list(auths: list[dict]) -> str:
    names = [one_author(a) for a in auths]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}, & {names[1]}"
    if len(names) <= 20:
        return ", ".join(names[:-1]) + f", & {names[-1]}"
    return ", ".join(names[:19]) + f", . . . {names[-1]}"


def editor_list(eds: list[dict]) -> str:
    def nm(a):                                               # editors in running text: initials first
        if "org" in a:
            return a["org"]
        ini = initials(a.get("given", ""))
        return (ini + " " if ini else "") + a.get("family", "")
    names = [nm(e) for e in eds]
    if not names:
        return ""
    body = names[0] if len(names) == 1 else (f"{names[0]} & {names[1]}" if len(names) == 2
                                              else ", ".join(names[:-1]) + f", & {names[-1]}")
    return f"{body} ({'Ed.' if len(names) == 1 else 'Eds.'})"


def clean_title(t: str) -> str:
    t = re.sub(r"<[^>]+>", "", t or "")
    t = re.sub(r"\s+:\s+", ": ", t)
    return re.sub(r"\s+", " ", t).strip()


def looks_title_case(t: str) -> bool:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", t) if len(w) > 3]
    return len(words) >= 4 and sum(w[0].isupper() for w in words) / len(words) > 0.6


def endp(s: str) -> str:
    return s if s.endswith((".", "?", "!")) else s + "."


def pages_fmt(p: str) -> str:
    return re.sub(r"\s*[-–—]+\s*", ENDASH, p.strip()) if p else ""


def format_apa(meta: dict) -> str:
    """One APA 7 entry (Markdown, *italic*) from a fetched metadata dict. Only fields present are used."""
    title = clean_title(meta.get("title", ""))
    kind = meta.get("kind", "")
    year = meta.get("year")
    ytxt = f"({year})" if year else "(n.d.)"
    doi = meta.get("doi", "")
    url = f"https://doi.org/{doi}" if doi else (f"https://arxiv.org/abs/{meta['arxiv_id']}" if meta.get("arxiv_id") else "")
    auth = author_list(meta.get("authors") or [])
    pages = pages_fmt(meta.get("pages", ""))
    cont = [clean_title(c) for c in meta.get("containers") or [] if c]
    pub = meta.get("publisher", "")
    italic_title = False                                     # the work stands alone (book, preprint, thesis, report)
    mid = ""                                                 # what follows the title

    if kind == "journal-article":
        j = cont[0] if cont else ""
        vol = meta.get("volume", "")
        iss = meta.get("issue", "")
        jtxt = f"*{j}" + (f", {vol}*" if vol else "*") if j else ""
        if j and iss:
            jtxt += f"({iss})"
        mid = ", ".join(x for x in (jtxt, pages) if x)
        mid = endp(mid) if mid else ""
    elif kind in ("proceedings-article", "book-chapter", "reference-entry", "book-part"):
        book = cont[-1] if cont else ""
        series = cont[:-1] if kind == "book-chapter" and len(cont) > 1 else []
        eds = editor_list(meta.get("editors") or [])
        extra = ([", ".join(series)] if series else []) + ([f"pp. {pages}"] if pages else [])
        paren = f" ({', '.join(extra)})" if extra else ""
        inpart = "In " + (eds + ", " if eds else "") + (f"*{book}*" if book else "")
        mid = (inpart + paren + ".") if book else ""
        if pub:
            mid += f" {endp(pub)}"
    elif kind == "posted-content" or kind == "preprint":
        italic_title = True
        mid = "[Preprint]." + (f" {endp(pub)}" if pub else "")
        if meta.get("arxiv_id"):
            title_extra = f" (arXiv:{meta['arxiv_id']})"
            title = title + title_extra
            mid = "[Preprint]. arXiv."
    elif kind in ("book", "monograph", "edited-book", "reference-book", "textbook"):
        italic_title = True
        ed = meta.get("edition", "")
        if ed:
            title += f" ({ed}{'th' if not str(ed).isdigit() else ''} ed.)" if not str(ed).isdigit() else f" ({ed} ed.)"
        mid = endp(pub) if pub else ""
    elif kind == "dissertation" or kind.startswith("datacite:") and "thesis" in kind.lower():
        italic_title = True
        low = kind.lower()
        lvl = ("Master's thesis" if "master" in low else "Doctoral dissertation" if ("doctor" in low or "phd" in low)
               else "Bachelor's thesis" if "bachelor" in low else "Thesis")
        mid = f"[{lvl}{', ' + pub if pub else ''}]."
    else:
        mid = ", ".join(x for x in ([*cont[:1]] + [pub]) if x)
        mid = endp(mid) if mid else ""

    if italic_title:
        i = title.rfind(" (arXiv:")
        ttxt = f"*{title[:i]}*{title[i:]}" if i > 0 else f"*{title}*"
        ttxt = ttxt if mid.startswith("[") else endp(ttxt)
    else:
        ttxt = endp(title)
    head = f"{endp(auth)} {ytxt}." if auth else ""
    if not auth:                                             # APA: title moves to the author position
        head = f"{ttxt} {ytxt}."
        ttxt = ""
    parts = [head, ttxt, mid, url]
    return " ".join(p for p in parts if p).replace("  ", " ")


# ---------------------------------------------------------------- run diff
def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in s if not unicodedata.combining(c)).casefold())


def load_run_rows(run_dir: Path) -> list[dict]:
    p = run_dir / "ledger.jsonl"
    rows = []
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def run_sources(rows: list[dict]) -> dict[str, dict]:
    """Distinct sources of a ledger by id: first row wins for the expect_* fields."""
    out: dict[str, dict] = {}
    for r in rows:
        sid = str(r.get("source_id") or "").strip()
        if sid and sid not in out:
            out[sid] = r
    return out


def diff_entry(meta: dict, rows_by_src: dict[str, dict], ident: tuple[str, str]) -> dict:
    """Compare a fetched record with the run's row for the same work (key, else normalised title)."""
    row = None
    for sid, r in rows_by_src.items():
        p = parse_id(sid)
        if p and (p[0], p[1].lower()) == (ident[0], ident[1].lower()):
            row = r
            break
    how = "id"
    if row is None:
        mt = _fold(meta.get("title", ""))
        for sid, r in rows_by_src.items():
            if mt and _fold(r.get("expect_title", "")) == mt:
                row, how = r, "title"
                break
    if row is None:
        return {"status": "not-in-run"}
    problems = []
    reg = [_fold(a.get("family", a.get("org", ""))) for a in meta.get("authors") or []]
    exp = [_fold(x) for x in (row.get("expect_authors") or [])]
    reg_disp = [a.get("family", a.get("org", "")) for a in meta.get("authors") or []]
    if exp and reg and exp != reg:
        n = min(len(exp), len(reg))
        if sorted(exp) == sorted(reg):
            problems.append("authors: ORDER differs")
        elif exp == reg[:len(exp)]:
            problems.append("authors: run lists a prefix (registry has more)")        # truncation, not an error
        elif reg[:n] == exp[:n]:
            problems.append("authors: registry has more / fewer")
        else:
            problems.append("authors: SET differs")
    if row.get("expect_year") and meta.get("year") and int(row["expect_year"]) != int(meta["year"]):
        problems.append(f"year: run {row['expect_year']} vs registry {meta['year']}")
    if row.get("expect_title") and _fold(row["expect_title"]) != _fold(meta.get("title", "")):
        problems.append("title differs")
    return {"status": "DIFF" if problems else "match", "matched_by": how, "problems": problems,
            "run_authors": list(row.get("expect_authors") or []), "registry_authors": reg_disp,
            "run_year": row.get("expect_year"), "registry_year": meta.get("year"),
            "run_title": row.get("expect_title"), "registry_title": clean_title(meta.get("title", ""))}


# ---------------------------------------------------------------- driver
def build(idents: list[tuple[str, str, str]], run_dir: Path | None = None, g: Guard | None = None) -> dict:
    g = g or Guard()
    rows_by_src = run_sources(load_run_rows(run_dir)) if run_dir else {}
    entries, manual, diffs, title_case = [], [], [], []
    for raw, kind, ident in idents:
        if kind == "bad":
            manual.append({"id": raw, "reason": "not a DOI or arXiv id"})
            continue
        meta = fetch_meta(kind, ident, g)
        if not meta["ok"]:
            why = (f"{meta['via']} status {meta['status']}: refused by access policy — {meta.get('body', '')}"
                   if meta["status"] == -1 else f"{meta['via']} status {meta['status']}"
                   + (f" ({meta['body']})" if meta.get("body") else ""))
            manual.append({"id": raw, "reason": why})
            continue
        if not (meta.get("authors") or meta.get("title")):
            manual.append({"id": raw, "reason": f"{meta['via']} returned a record with no authors and no title"})
            continue
        entry = format_apa(meta)
        entries.append({"id": raw, "key": f"{kind}:{ident}", "apa": entry, "via": meta["via"],
                        "sort": _fold(one_author(meta["authors"][0])) if meta.get("authors") else _fold(meta.get("title", "")),
                        "warnings": meta.get("warnings", []), "meta": meta})
        if looks_title_case(clean_title(meta.get("title", ""))):
            title_case.append(f"{kind}:{ident}")
        if run_dir:
            d = diff_entry(meta, rows_by_src, (kind, ident))
            d["id"] = f"{kind}:{ident}"
            diffs.append(d)
    entries.sort(key=lambda e: e["sort"])
    return {"entries": entries, "manual": manual, "diffs": diffs, "title_case": title_case, "run": str(run_dir or "")}


def render(res: dict) -> str:
    out = ["## 參考文獻 (APA 7)", ""]
    for e in res["entries"]:
        out.append(e["apa"])
        for w in e["warnings"]:
            out.append(f"  - 注意 (check): {w}")
        out.append("")
    if res["manual"]:
        out += ["", f"## {MANUAL}", ""]
        for m in res["manual"]:
            out.append(f"- {MANUAL}: `{m['id']}` — {m['reason']}")
    if res["diffs"]:
        out += ["", f"## 與 evidence run 書目的差異 (diff vs run `{Path(res['run']).name}`)", ""]
        for d in res["diffs"]:
            if d["status"] == "not-in-run":
                out.append(f"- `{d['id']}`: not in the run's ledger")
            elif d["status"] == "match":
                out.append(f"- `{d['id']}`: match (by {d['matched_by']})")
            else:
                out.append(f"- `{d['id']}`: **DIFF** (matched by {d['matched_by']}) — " + "; ".join(d["problems"]))
                out.append(f"    - run authors:      {', '.join(d['run_authors'])}")
                out.append(f"    - registry authors: {', '.join(d['registry_authors'])}")
    if res["title_case"]:
        out += ["", "註: 下列題名依來源原樣輸出，看起來是 Title Case，APA 7 要求句首大寫 (sentence case)，需人工調整專有名詞: "
                + ", ".join(res["title_case"])]
    return "\n".join(out) + "\n"


def collect_ids(a) -> list[tuple[str, str, str]]:
    raws = list(a.ids or [])
    if a.ids_file:
        raws += [l.strip() for l in Path(a.ids_file).read_text(encoding="utf-8-sig").splitlines()
                 if l.strip() and not l.lstrip().startswith("#")]
    if not raws and a.run:
        raws = [s for s in run_sources(load_run_rows(Path(a.run))) if parse_id(s)]
    seen, out = set(), []
    for r in raws:
        p = parse_id(r)
        k = p or ("bad", r)
        if (k[0], k[1].lower()) in seen:
            continue
        seen.add((k[0], k[1].lower()))
        out.append((r, k[0], k[1]))
    return out


# ---------------------------------------------------------------- selftest (offline; the unit tests carry the rest)
def selftest() -> int:
    bad = 0

    def ok(name, cond):
        nonlocal bad
        print(("ok   " if cond else "FAIL ") + name)
        bad += 0 if cond else 1
    ok("initials hyphen", initials("Chia-Yu") == "C.-Y.")
    ok("parse doi url", parse_id("https://doi.org/10.1007/ABC.1") == ("doi", "10.1007/ABC.1"))
    ok("parse arxiv", parse_id("arXiv:1807.10059v2") == ("arxiv", "1807.10059"))
    ok("parse junk", parse_id("not an id") is None)
    return 2 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--ids-file")
    ap.add_argument("--run")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    idents = collect_ids(a)
    if not idents:
        ap.print_help()
        return 1
    res = build(idents, Path(a.run) if a.run else None)
    text = json.dumps({k: v for k, v in res.items()}, ensure_ascii=False, indent=1, default=str) if a.json else render(res)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"wrote {a.out}  entries={len(res['entries'])} manual={len(res['manual'])}")
    else:
        print(text)
    return 3 if res["manual"] else 0


if __name__ == "__main__":
    sys.exit(main())
