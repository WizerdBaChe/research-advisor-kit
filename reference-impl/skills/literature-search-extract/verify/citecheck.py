#!/usr/bin/env python3
r"""citecheck v2 — the machine half of this skill's anti-fabrication gate.

WHY THIS EXISTS. Everything the skill did before this file was self-report: the
same model that might fabricate a citation also decided whether the citation was
fabricated. Two measurements say that is not enough:

  * ALCE (Gao et al., EMNLP 2023, arXiv:2305.14627): on ELI5, even the best
    systems "lack complete citation support 50% of the time" — the citation is
    real, the claim is not in it.
  * Search Arena (Miroyan et al., ICLR 2026, arXiv:2506.05334, n=24,069):
    people rate answers higher for having MORE citations "even when the cited
    content does not directly support the attributed claims".

So the dangerous failure is not the invented DOI. It is the REAL source cited
for something it does not say — invisible to a reader, invisible to identifier
resolution, and rewarded by human judgement.

THE MOVE. Whether a source SUPPORTS a claim is not machine-determinable without
an entailment model. But it becomes determinable if the writer must name the
exact span it relies on: a script cannot judge support, and it CAN check that
the quoted span exists verbatim in the retrieved text. That turns an opinion
into a falsifiable statement. A fabricated support span fails here, loudly,
without any ML.

V2 (2026-09-11, from a university library's AI-literacy guide, slides 20-24) closes
four holes v1 left open, each a real failure the guide documents:
  * the "half-real" citation (real title, wrong author, right journal — p23):
    v1 compared only the first surname and the year. v2 compares title, every
    listed author, and venue against the resolved record (`expect_*` fields).
  * "do not rely on the DOI alone" (p24: a real IEEE OA article whose DOI shows
    DOI NOT FOUND): a DOI that does not resolve is no longer an automatic FAIL —
    v2 asks Semantic Scholar for the title and, when the record's own DOI string
    matches, reports WARN `doi-not-yet-active` with the confirmation channel.
  * "AI is insensitive to numbers" (p20): every number in the CLAIM must appear
    in the SUPPORT SPAN — a transcription check a script can settle.
  * the text itself: v1 never asked where `sources/<name>.txt` came from, so a
    text typed from memory passed the span check. v2 reads `sources/manifest.json`
    (written by fetchsrc.py) and rules on route + sha256; a text no instrument
    produced is the fabrication vector, and it now has a name.
  Plus: retraction (Crossref `updated-by[]` on the cited work — `update-to` sits
  on the NOTICE, verified live 2026-09-11 on 10.1016/S0140-6736(97)11096-0) and
  the access route the row claims, checked against the host policy.

WHAT IT RULES ON, and only this (gate-severity-by-consumer, 2026-08-26):

  FAIL — determinable and closed:
    identifier does not resolve anywhere · resolved record contradicts the
    citation (surname, year ±1, title, a listed author, a venue with ZERO shared
    tokens) · cited work is RETRACTED and the row does not say so · a number in
    the claim is absent from the span · support_span absent from the text ·
    source text has no manifest entry / sha256 differs / route hand_to_user ·
    access_route the policy refuses for that host · user_provided text in Mode 2
    · no locator · access tag above what was retrieved
  WARN — undeterminable here, forwarded not vetoed (each names its promotion):
    doi-not-yet-active with S2 title confirmation (-> FAIL when the confirmed
    record is older than one year, or the DOI strings differ) · venue partial
    overlap · a correction/erratum notice · numbers on a row marked derived /
    [synthesis] / [converted] / [read from figure] · user_provided text in Mode 1
    (-> FAIL in Mode 2, no human downstream) · legacy run without a manifest
    (-> FAIL when run.json.created >= 2026-09-12) · missing expect_* on a
    [full] numeric row (-> FAIL under the same legacy trigger) · a published
    version exists for a cited preprint · network down · [secondary] rows
  NEVER RULES ON: whether the span, granted it exists, actually entails the
    claim. That stays a human/model judgement and the ledger makes it auditable
    by printing claim and span side by side.

INPUT — an evidence ledger, JSONL, one load-bearing claim per line. Write it
BEFORE running this (the gate must not be able to destroy what it rejects):

  {"claim_id": "C1",
   "claim": "Single-crystal Ag films reach L_spp = 200 um at 780 nm.",
   "source_id": "10.1126/science.1174655",    # DOI | arXiv:2305.14627 | PMID:… | ISBN:…
                                               # (v1's example carried 10.1021/nl803811g for "Nagpal 2009" — a real
                                               #  DOI that belongs to Zuloaga et al.; v2's own metadata check caught it)
   "cite_as": "Nagpal 2009",                   # what the deliverable prints
   "expect_year": 2009,                        # optional, checked if present
   "expect_title": "Ultrasmooth patterned metals for plasmonics and metamaterials",
   "expect_authors": ["Nagpal", "Lindquist", "Oh", "Norris"],   # surnames, any subset
   "expect_venue": "Science",
   "locator": "Fig. 3",
   "access_tag": "full",                       # full|partial|abstract|secondary
   "access_route": "script",                   # script|webfetch|browser_headless|browser_user|local_pdf|user_provided
   "source_url": "https://…",                  # optional; host is policy-checked with access_route
   "support_span": "propagation length of 200 um",   # verbatim from the source
   "source_text": "sources/nagpal2009.txt",    # what was actually retrieved (fetchsrc.py wrote it)
   "derived": false,                           # true = numbers are computed/converted, not transcribed
   "cite_as_retracted": false}                 # true = the deliverable cites the work AS retracted

Usage:
    python citecheck.py ledger.jsonl [--mode 2]          # full run (Mode 2 = returned to a caller)
    python citecheck.py ledger.jsonl --offline           # structure + spans + provenance, no network
    python citecheck.py --retraction-sweep <ledger|.txt|.bib|.json>   # rubric §3b, 1 req/s
    python citecheck.py --selftest [--offline]           # two-sided calibration (stubs when offline)
    python citecheck.py ledger.jsonl --json

Exit: 0 = no FAIL. 1 = at least one FAIL. 2 = bad usage.
review-when: Crossref, Semantic Scholar or the arXiv export API changes its response
shape; the host policy schema changes; the legacy trigger date passes (2026-09-12).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                    # spannorm: the shared normal form, imported below
sys.path.insert(0, str(HERE.parent / "connectors"))
try:
    import access_policy  # noqa: E402
except Exception:                                           # noqa: BLE001
    access_policy = None  # type: ignore

TIMEOUT = 15
_BASE_UA = "literature-search-extract-citecheck/2 (local, interactive)"
LEGACY_CUTOFF = "2026-09-12"     # runs created on/after this date must carry a manifest + access_route
S2 = "https://api.semanticscholar.org/graph/v1"

# CONTACT IS PER-HOST, NEVER GLOBAL. A contact-bearing User-Agent buys politeness
# (arXiv 429s unidentified clients harder, and identification is the channel for
# asking about a higher rate). But it also leaves an attributable query trail on
# whichever host receives it, so consent is per-service and does not generalise:
# the user approved arXiv on 2026-08-27 and declined Unpaywall and the Crossref
# polite pool in the same breath. One shared UA would have quietly overridden
# that. Add a host here ONLY on an explicit per-service approval.
_ARXIV_CONTACT = __import__("os").environ.get("LSE_ARXIV_CONTACT", "").strip()  # public kit: opt-in, your own address, arXiv only
CONTACT_BY_HOST = {h: _ARXIV_CONTACT for h in ("arxiv.org", "export.arxiv.org") if _ARXIV_CONTACT}
TAG_RANK = {"secondary": 0, "abstract": 1, "partial": 2, "full": 3}
AGENT_ROUTES = ("script", "webfetch", "browser_headless", "browser_user")
ALL_ROUTES = AGENT_ROUTES + ("local_pdf", "user_provided", "hand_to_user")
DERIVED_MARKERS = ("[synthesis]", "[converted", "[read from figure]", "[computed", "[derived")
RETRACTION_TYPES = {"retraction", "retracted", "withdrawal", "withdrawn", "removal", "partial_retraction"}
CONCERN_TYPES = {"expression_of_concern", "concern"}
VENUE_STOP = {"of", "the", "and", "on", "in", "for", "a", "an", "&", "de", "la", "le"}


def ua_for(url: str) -> dict:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    contact = CONTACT_BY_HOST.get(host)
    return {"User-Agent": f"{_BASE_UA} mailto:{contact}" if contact else _BASE_UA}


# --------------------------------------------------------------------------
# normalization — a quote survives a PDF; it should survive this too
# --------------------------------------------------------------------------
# The rule itself lives in spannorm.py and NOWHERE ELSE: this gate and fetchsrc's excerpt
# cutter have to fold text identically or the cutter removes what the gate then demands to
# find. They used to be two implementations that measurably disagreed (see that module's
# header). `norm` here is that module's function, not a copy of it.
from spannorm import LIGATURES, norm, norm_with_map  # noqa: E402,F401  (re-exported: callers and evals import citecheck.norm)
import pagestore  # noqa: E402  (page pointers: `textbook:<id>#p=N` / `pages:<pdf>#p=N`, see that module)


_DOC_NUMS: dict[str, list[str]] = {}


def _doc_numbers(pres) -> list[str] | None:
    """numbers_in() of a page pointer's whole document, once per PDF per run."""
    k = str(pres.pdf)
    if k not in _DOC_NUMS:
        doc = pagestore.document_text(pres)
        _DOC_NUMS[k] = numbers_in(doc) if doc else []
    return _DOC_NUMS[k] or None


def span_present(span: str, haystack: str) -> bool:
    s = norm(span or "")
    return bool(s.strip()) and s in norm(haystack)  # a blank span is "in" every text (review 2026-11-07)


def fold_marks(s: str) -> str:
    """Strip combining marks after NFKD: Müller == Muller, Ångström == Angstrom (QA 2026-09-11 F-9).
    Used for NAME comparison only — never for spans, where 'µm' vs 'um' must stay a difference."""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", norm(s)) if len(t) >= 2 and t not in VENUE_STOP}


def title_match(expect: str, got: str) -> bool:
    """Containment of the shorter token set in the longer, >= 0.6 — undoes subtitles and punctuation, not wording."""
    if not (expect or "").strip() or not (got or "").strip():
        return True                      # nothing to compare is not a contradiction
    a, b = _tokens(expect), _tokens(got)
    if norm(expect) in norm(got) or norm(got) in norm(expect):
        return True
    if not a or not b:
        return norm(expect) == norm(got)  # degenerate titles: exact after normalisation (QA F-8)
    return len(a & b) / min(len(a), len(b)) >= 0.6


NUM_RE = re.compile(r"(?<![\w.])[-+−]?\d+(?:[.,]\d+)*(?:\s*[eE][-+]?\d+)?(?![\w.])")
# a single bare digit counts only when a unit-like token follows ("3 nm", "5 K", "2%"); "Fig. 3",
# "Table 2", "3 devices" are structure or counts, not measured values (design §3.4; QA F-7)
# numbers_in NFKC-folds its input, which turns the micro sign U+00B5 into Greek mu U+03BC -- a character
# this class did not contain -- so a single-digit value written "5 μm" (or "5 microns", over the 4-letter
# cap) failed the lookahead and was dropped as noise, reading downstream as a missing number.
# Multi-digit values were never affected: the lookahead only gates a lone digit. (a research round, 2026-09-12)
# A written range or list FACTORS THE UNIT OUT to the end: "5-10 nm", "5, 10, 15 or up to 20
# microns". The digit before it is as measured as the one beside the unit, so the lookahead reads
# through any run of further numbers joined by range/list connectives. Reading only the token
# IMMEDIATELY after the digit made the same digit count or not by its position in the enumeration
# ("2-3 μm" kept the 3, dropped the 2) and dropped it from the SPAN's numbers, so a claim quoting
# "5 nm" against a span reading "5-10 nm" was reported as a number the source does not carry.
# Measured on the real ledgers: 5 range occurrences in run l7, plus L7-C16, whose span spells the
# range out as a list — that row is why the rule covers lists and not just ranges (2026-09-12).
_CONNECTIVE = r"(?:[-–—−]|,|;|\bup\s+to\b|\bto\b|\band\b|\bor\b)"
# Possessive (*+, Python 3.11+): a long comma-separated run ("1, 2,3,4,5" in a book index) splits into
# connectives and decimal commas in exponentially many ways, and the plain * backtracked through all of
# them before failing — one index page held citecheck for minutes (2026-10-20, whole-document numeric
# settle for page pointers). The run is taken whole; the unit test after it is unchanged.
_MORE_NUMBERS = rf"(?:\s*(?:{_CONNECTIVE}\s*)+\d+(?:[.,]\d+)*)*+"   # "or up to 20" stacks two
# The unit-like token stays a heuristic — any word of <= 4 letters — MINUS the closed list of
# connectives and citation words below, which used to read as units and admit structure numbers
# ("Fig. 2 and 3 show", "1 of 4 lenses"). Excluding them costs the unit spellings "in" (inches) and
# "at" (technical atmosphere): a bare "2 in" now goes unchecked. That is the safe direction — a
# miss, never a false alarm — and neither unit occurs in this corpus. KNOWN LIMIT that remains: a
# 4-letter word that is not on the list still reads as a unit ("Table 2 to 4 list"), pinned by a
# selftest case. review-when: a real run needs a unit this drops, or a unit vocabulary arrives from
# somewhere authoritative — then replace the heuristic rather than growing this list.
_NOT_A_UNIT = (r"(?!(?i:and|or|of|in|at|on|by|for|per|the|is|are|was|were|from|with|up|to|see"
               r"|eq|fig|ref|vs|et|al|no)(?![A-Za-z]))")
UNIT_AFTER_RE = re.compile(r"\s*" + _MORE_NUMBERS +
                           r"\s*(?:%|°|(?:microns?|micrometres?|micrometers?|nanometres?|nanometers?"
                           r"|millimetres?|millimeters?|decibels?)(?![A-Za-z])"
                           r"|" + _NOT_A_UNIT + r"[A-Za-zµμΩ]{1,4}(?![A-Za-z]))")


def numbers_in(text: str) -> list[str]:
    out = []
    src = unicodedata.normalize("NFKC", text or "")
    for m in NUM_RE.finditer(src):
        tok = m.group(0).replace(" ", "").replace("−", "-")
        if re.fullmatch(r"\d", tok) and not UNIT_AFTER_RE.match(src, m.end()):
            continue
        # thousands separators: 1,000 -> 1000 ; keep 1.5 and 0,5 (a decimal comma) intact
        if re.fullmatch(r"[-+]?\d{1,3}(,\d{3})+(\.\d+)?", tok):
            tok = tok.replace(",", "")
        out.append(tok)
    return out


def _num_value(tok: str):
    try:
        return float(tok.replace(",", "."))
    except ValueError:
        return None


def numeric_mismatch(claim: str, span: str, cite_as: str = "", span_nums: list[str] | None = None) -> list[str]:
    """Numbers in the claim that the span does not carry (as the same string or the same value).
    span_nums: numbers_in(span) already computed (a page pointer's whole document, cached per PDF)."""
    span_nums = numbers_in(span) if span_nums is None else span_nums
    span_vals = {v for v in (_num_value(t) for t in span_nums) if v is not None}
    cite_years = set(re.findall(r"\b(1[89]\d{2}|20\d{2})\b", cite_as or ""))
    missing = []
    for tok in numbers_in(claim):
        bare = tok.lstrip("+-")
        if bare in cite_years:
            continue                     # the citation year, not a measured value
        # the sign is part of the value: "-3.2 nm" is not "3.2 nm" (QA 2026-09-11 F-5); "+3.2" == "3.2" by value
        if tok in span_nums or (tok.startswith("+") and bare in span_nums):
            continue
        v = _num_value(tok)
        if v is not None and v in span_vals:
            continue
        missing.append(tok)
    return missing


# --------------------------------------------------------------------------
# identifier resolution
# --------------------------------------------------------------------------
def _get(url: str) -> tuple[int, str, dict]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=ua_for(url)),
                                    timeout=TIMEOUT) as r:
            return r.status, r.read(400_000).decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, "", dict(exc.headers or {})
    except Exception:                                       # noqa: BLE001
        return 0, "", {}


GET = _get   # the selftest's offline mode swaps this for canned answers


def _crossref(doi: str) -> dict:
    status, body, _ = GET("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe=""))
    if status != 200:
        return {"ok": False, "via": "crossref", "status": status}
    try:
        m = json.loads(body)["message"]
    except Exception:                                       # noqa: BLE001
        return {"ok": False, "via": "crossref", "status": status}
    parts = (m.get("issued", {}).get("date-parts") or [[None]])[0]
    upd = []
    for u in m.get("updated-by") or []:
        d = (u.get("updated") or {}).get("date-parts") or [[None]]
        upd.append({"type": str(u.get("type", "")).lower(), "doi": u.get("DOI", ""),
                    "date": "-".join(str(x) for x in d[0] if x is not None), "label": u.get("label", "")})
    return {"ok": True, "via": "crossref",
            "title": (m.get("title") or [""])[0],
            "year": parts[0] if parts else None,
            "authors": [a.get("family", "") for a in m.get("author", [])],
            "venue": (m.get("container-title") or [""])[0],
            "doi": m.get("DOI", ""), "updated_by": upd}


def _s2(path: str) -> dict | None:
    status, body, _ = GET(f"{S2}/{path}")
    if status != 200:
        return None
    try:
        return json.loads(body)
    except Exception:                                       # noqa: BLE001
        return None


def _s2_record(p: dict) -> dict:
    return {"ok": True, "via": "semanticscholar", "title": p.get("title") or "",
            "year": p.get("year"), "authors": [a.get("name", "").split()[-1] if a.get("name") else ""
                                                for a in p.get("authors") or []],
            "venue": p.get("venue") or "", "doi": ((p.get("externalIds") or {}).get("DOI") or ""),
            "updated_by": []}


S2_FIELDS = "title,year,authors,venue,externalIds"


def s2_by_id(sid: str) -> dict | None:
    p = _s2(f"paper/{urllib.parse.quote(sid, safe=':')}?fields={S2_FIELDS}")
    return _s2_record(p) if p and p.get("title") else None


def s2_by_title(title: str) -> dict | None:
    p = _s2(f"paper/search?query={urllib.parse.quote(title)}&limit=3&fields={S2_FIELDS}")
    if not p:
        return None
    for cand in p.get("data") or []:
        if title_match(title, cand.get("title") or ""):
            return _s2_record(cand)
    return None


def resolve(source_id: str) -> dict:
    """{'ok', 'via', 'title', 'year', 'authors', 'venue', 'doi', 'updated_by', 'status'}."""
    sid = (source_id or "").strip()
    low = sid.lower()

    if low.startswith("arxiv:") or re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", sid):
        aid = sid.split(":", 1)[1] if ":" in sid else sid
        status, body, _ = GET("https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(aid))
        if status != 200 or "<entry>" not in body:
            return {"ok": False, "via": "arxiv", "status": status}
        title = re.search(r"<entry>.*?<title>(.*?)</title>", body, re.S)
        year = re.search(r"<published>(\d{4})", body)
        authors = re.findall(r"<name>(.*?)</name>", body)
        return {"ok": True, "via": "arxiv", "kind": "preprint", "arxiv_id": aid,
                "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else "",
                "year": int(year.group(1)) if year else None,
                "authors": [a.split()[-1] for a in authors if a.strip()], "venue": "arXiv", "doi": "",
                "updated_by": []}

    if low.startswith("10.") or low.startswith("doi:"):
        doi = sid.split(":", 1)[1] if low.startswith("doi:") else sid
        return _crossref(doi)

    if low.startswith("pmid:"):
        pmid = sid.split(":", 1)[1]
        status, body, _ = GET("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
                              f"esummary.fcgi?db=pubmed&retmode=json&id={pmid}")
        if status != 200:
            return {"ok": False, "via": "pubmed", "status": status}
        try:
            rec = json.loads(body)["result"][pmid]
        except Exception:                                   # noqa: BLE001
            return {"ok": False, "via": "pubmed", "status": status}
        yr = re.match(r"(\d{4})", rec.get("pubdate", "") or "")
        return {"ok": True, "via": "pubmed", "title": rec.get("title", ""),
                "year": int(yr.group(1)) if yr else None,
                "authors": [a.get("name", "").split()[0] for a in rec.get("authors", [])],
                "venue": rec.get("fulljournalname") or rec.get("source") or "", "doi": "",
                "updated_by": []}

    return {"ok": False, "via": "unsupported", "status": 0}


# --------------------------------------------------------------------------
# metadata comparison — flags CONTRADICTION only, never absence
# --------------------------------------------------------------------------
def _surname_in(surname: str, authors: list[str]) -> bool:
    s = fold_marks(norm(surname))
    return any(s and a and (s in fold_marks(norm(a)) or fold_marks(norm(a)) in s) for a in authors)


def _as_list(v) -> list:
    """expect_authors written as a bare string is ONE author, not a sequence of letters (QA F-6)."""
    if v is None or v == "":
        return []
    if isinstance(v, str):
        return [v]
    return list(v) if isinstance(v, (list, tuple, set)) else [str(v)]


def metadata_conflicts(row: dict, meta: dict) -> list[tuple[str, str]]:
    """[(verdict, detail)] — FAIL on a contradiction, WARN on weak venue overlap."""
    out: list[tuple[str, str]] = []
    cite = (row.get("cite_as") or "").strip()
    surname = cite.split()[0] if cite else ""
    authors = [a for a in (meta.get("authors") or []) if a]
    if surname and authors and not _surname_in(surname, authors):
        out.append(("FAIL", f"cite_as names '{surname}' but the resolved record's authors are {authors[:4]}"))

    want = row.get("expect_year")
    if want is None:
        m = re.search(r"\b(1[89]\d{2}|20\d{2})\b", cite)
        want = int(m.group(1)) if m else None
    got = meta.get("year")
    if want and got and abs(int(want) - int(got)) > 1:
        out.append(("FAIL", f"cite_as implies {want}, resolved record says {got}"))

    et = row.get("expect_title")
    if et and meta.get("title") and not title_match(et, meta["title"]):
        out.append(("FAIL", f"expect_title {et[:50]!r} is not the resolved title {meta['title'][:50]!r} — "
                            "the half-real citation (right DOI, wrong paper) — the library guide p23"))

    for a in _as_list(row.get("expect_authors")):
        if authors and not _surname_in(str(a), authors):
            out.append(("FAIL", f"expect_authors lists '{a}' but the resolved record has {authors[:6]}"))

    ev = row.get("expect_venue")
    if ev and meta.get("venue"):
        a, b = _tokens(ev), _tokens(meta["venue"])
        if a and b:
            if not (a & b):
                out.append(("FAIL", f"expect_venue {ev!r} shares no token with the resolved venue {meta['venue']!r}"))
            elif not a <= b and not b <= a:
                out.append(("WARN", f"venue overlap weak: {ev!r} vs resolved {meta['venue']!r} — confirm the venue "
                                    "(promotion: zero shared tokens is already FAIL)"))
    return out


# --------------------------------------------------------------------------
# provenance — the manifest fetchsrc.py wrote beside the texts
# --------------------------------------------------------------------------
def load_manifest(base: Path) -> dict | None:
    p = base / "sources" / "manifest.json"
    if not p.exists():
        return None
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
        return m if isinstance(m, dict) and isinstance(m.get("entries"), dict) else None
    except Exception:                                       # noqa: BLE001
        return None


def manifest_entry(manifest: dict | None, ref: str) -> dict | None:
    if not manifest or not ref:
        return None
    name = Path(ref).name
    for key, e in manifest["entries"].items():
        if Path(e.get("file") or f"{key}.txt").name == name or f"{key}.txt" == name:
            return e
    return None


def run_created(base: Path) -> str | None:
    p = base / "run.json"
    if not p.exists():
        return None
    try:
        return (json.loads(p.read_text(encoding="utf-8")).get("run") or {}).get("created")
    except Exception:                                       # noqa: BLE001
        return None


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sha_lf(p: Path) -> str:
    """sha256 of the file with CRLF folded to LF — the ONLY difference this check forgives.

    A fetchsrc before 2026-09-12 hashed the text in memory (LF) and then wrote it through
    Windows text mode (CRLF), so the recorded hash describes bytes that never reached the disk.
    A file matching here is byte-identical to what was retrieved apart from line endings — which
    norm() collapses anyway, so no verdict downstream can turn on it. Anything else still FAILs.
    """
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------
def check_row(row: dict, base: Path, offline: bool, *, manifest: dict | None = None,
              mode: int = 1, created: str | None = None, policy: dict | None = None,
              today: dt.date | None = None) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    try:
        mode = int(mode)                 # a caller passing "2" gets Mode 2, not silently Mode 1 (QA F-15)
    except (TypeError, ValueError):
        mode = 1
    tag = (row.get("access_tag") or "").strip().lower()
    today = today or dt.date.today()
    legacy = not created or created[:10] < LEGACY_CUTOFF
    claim = row.get("claim") or ""
    derived = bool(row.get("derived")) or any(k in claim.lower() for k in DERIVED_MARKERS)

    if not row.get("locator"):
        out.append(("locator", "FAIL",
                    "no locator — an extracted item nobody can re-find is not "
                    "traceable, whatever it cites"))
    if tag not in TAG_RANK:
        out.append(("access_tag", "FAIL", f"access_tag {tag!r} is not one of {sorted(TAG_RANK)}"))

    # ---- identifier + metadata + retraction ---------------------------------
    sid = row.get("source_id")
    meta: dict = {}
    if not sid:
        out.append(("identifier", "FAIL", "no source_id"))
    elif offline:
        out.append(("identifier", "WARN", "--offline: resolution skipped"))
    else:
        meta = resolve(sid)
        if not meta.get("ok") and str(sid).lower().lstrip("doi:").startswith("10."):
            # "do not rely on the DOI alone" (the library guide p24): a real, recent article can
            # show DOI NOT FOUND while the indexers already carry it.
            doi = str(sid).split(":", 1)[1] if str(sid).lower().startswith("doi:") else str(sid)
            alt = s2_by_id(f"DOI:{doi}") or (s2_by_title(row["expect_title"]) if row.get("expect_title") else None)
            if alt:
                same = norm(alt.get("doi") or "") == norm(doi)
                old = alt.get("year") and int(alt["year"]) < today.year - 1
                if same and not old:
                    meta = {**alt, "doi_not_active": True}
                    out.append(("identifier", "WARN",
                                f"doi-not-yet-active: {sid} -> Crossref/doi.org {meta.get('status', '404')}, but Semantic "
                                f"Scholar carries {alt['title'][:48]!r} ({alt.get('year')}) with the same DOI string. "
                                "Confirm on the publisher page or the library discovery layer; promotion to FAIL: "
                                "record older than one year, or DOI strings differ"))
                elif same and old:
                    out.append(("identifier", "FAIL",
                                f"{sid} does not resolve and the confirmed record is from {alt.get('year')} — a DOI "
                                "still inactive a year after publication is a wrong DOI, not a registration lag"))
                else:
                    out.append(("identifier", "FAIL",
                                f"{sid} does not resolve; the title matches a record whose DOI is "
                                f"{alt.get('doi') or '(none)'} — the DOI string in the citation is wrong"))
            else:
                out.append(("identifier", "FAIL",
                            f"{sid} did not resolve via crossref (HTTP {meta.get('status')}) nor via Semantic Scholar — "
                            "an identifier that does not resolve must not appear in a deliverable (SKILL.md failure mode #1)"))
        elif not meta.get("ok"):
            out.append(("identifier", "FAIL",
                        f"{sid} did not resolve via {meta.get('via')} — an identifier that does not resolve "
                        "must not appear in a deliverable (SKILL.md failure mode #1)"))
        if meta.get("ok"):
            conflicts = metadata_conflicts(row, meta)
            for v, d in conflicts:
                out.append(("metadata", v, d))
            if not any(v == "FAIL" for v, _ in conflicts) and not meta.get("doi_not_active"):
                out.append(("identifier", "OK",
                            f"{sid} -> {meta['via']}: {(meta.get('title') or '')[:56]!r} ({meta.get('year')})"))
            # retraction / correction — on the cited WORK's own record
            for u in meta.get("updated_by") or []:
                t = u.get("type", "")
                if t in RETRACTION_TYPES:
                    if row.get("cite_as_retracted"):
                        out.append(("retraction", "WARN",
                                    f"cited AS retracted (notice {u.get('doi')}, {u.get('date')}) — keep that wording "
                                    "in the deliverable"))
                    else:
                        out.append(("retraction", "FAIL",
                                    f"the cited work is RETRACTED (notice DOI {u.get('doi')}, {u.get('date')}); it may "
                                    "not support a claim — cite the retraction or drop the claim (rubric §3)"))
                elif t in CONCERN_TYPES:
                    out.append(("retraction", "WARN", f"expression of concern on the cited work ({u.get('doi')}, "
                                                      f"{u.get('date')}) — state it beside the claim"))
                else:
                    out.append(("retraction", "WARN", f"{t or 'update'} notice {u.get('doi')} ({u.get('date')}) — check "
                                                      "the corrected value before quoting a number from this work"))
            if meta.get("kind") == "preprint":
                pub = s2_by_id(f"arXiv:{meta.get('arxiv_id', '')}")
                if pub and pub.get("doi") and not pub["doi"].lower().startswith("10.48550/"):   # arXiv's own DOI
                    out.append(("preprint", "WARN", f"a published version exists (DOI {pub['doi']}) — cite it and re-check "
                                                    "the number there (rubric §2)"))
            if tag == "full" and numbers_in(claim) and not (row.get("expect_title") or row.get("expect_authors")):
                out.append(("metadata", "FAIL" if not legacy else "WARN",
                            "a [full] numeric row carries no expect_title / expect_authors — the half-real citation "
                            "check cannot run" + ("" if not legacy else f" (promotion to FAIL: run created >= {LEGACY_CUTOFF})")))

    # ---- support span + numeric transcription -------------------------------
    # Span checking follows the TEXT, not the tag. An [abstract] row is a claim
    # about a text that WAS retrieved — the tag limits what may be claimed from
    # it, not whether the quote can be verified. Only [secondary] is exempt:
    # there the text was never in hand, which is what the tag means.
    span, ref = row.get("support_span"), row.get("source_text")
    text = None
    settle_nums = None
    if tag == "secondary":
        out.append(("support", "WARN",
                    "[secondary] row — the text was never retrieved, so no span "
                    "is checkable. Attribute as 'B, as cited in A' and keep A's "
                    "own row in the ledger"))
    elif not span:
        out.append(("support", "FAIL",
                    "no support_span. A [full]/[partial] claim must name the "
                    "exact text it rests on, or its support is unfalsifiable — "
                    "the failure mode ALCE and Search Arena both measured"))
    elif not ref:
        out.append(("support", "WARN",
                    "support_span given but no source_text stored, so it cannot "
                    "be verified. Store what was retrieved BEFORE the gate runs"))
    elif pagestore.is_pointer(ref):
        # A page pointer cites PDF pages directly (pagestore.py). Its own branch: the stored-file
        # branch below stays exactly as it was for every legacy source_text.
        pres = pagestore.resolve(ref, base, row.get("pdf_sha256"))
        if pres.error:
            out.append(("support", "FAIL", pres.error))
        else:
            unread = [f"p{pg.n} {pg.status}" for pg in pres.pages if pg.text is None]
            if unread:
                out.append(("support", "FAIL", f"{ref}: cited page(s) have no readable text ({', '.join(unread)}) — "
                                               "an excluded or missing page cannot carry a quote"))
            else:
                text = pres.text
                if span_present(span, text):
                    out.append(("support", "OK", f"span found verbatim on {ref.rsplit('#', 1)[1]} of "
                                                 f"{pres.pdf.name} ({pres.route}, {len(text):,} chars)"))
                else:
                    out.append(("support", "FAIL", f"support_span is NOT on the cited page(s) {ref.rsplit('#', 1)[1]} "
                                                   f"of {pres.pdf.name}: {span[:64]!r}"))
                # the numeric check settles a number missing from the span against the retrieved text:
                # for a page pointer that is the whole document, not just the cited pages
                settle_nums = _doc_numbers(pres)
                sparse = [pg.n for pg in pres.pages if pg.status == "sparse"]
                if sparse and tag == "full":
                    out.append(("access_tag", "FAIL", f"[full] on OCR page(s) {sparse} marked sparse — the most such a "
                                                      "page supports is [partial] (textbook-extraction.md §3)"))
            pp = pagestore.printed_pages(pres)
            want, want_pdf = pagestore.locator_pages(row.get("locator") or "")
            if pp and any(pp) and want and not (set(v for v in pp if v) & want):
                out.append(("locator", "WARN", f"locator names printed p.{sorted(want)[:4]} but the pointer's PDF "
                                               f"page(s) print as {pp} (calibration ok) — check which one is right"))
            if want_pdf and pres.pages and not ({pg.n for pg in pres.pages} & want_pdf):
                out.append(("locator", "WARN", f"locator names PDF page {sorted(want_pdf)[:4]} but the pointer cites "
                                               f"{[pg.n for pg in pres.pages]} — check which one is right"))
    else:
        p = (base / ref) if not Path(ref).is_absolute() else Path(ref)
        entry = manifest_entry(manifest, ref)
        if not p.exists():
            if entry and entry.get("retention_state") == "pending-excerpt":
                out.append(("support", "FAIL", f"source_text {ref} not yet derived — run `fetchsrc.py excerpt` "
                                               "(licensed full text stays in scratch)"))
            else:
                out.append(("support", "FAIL", f"source_text {ref} not found"))
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
            if span_present(span, text):
                out.append(("support", "OK", f"span found verbatim in {p.name} ({len(text):,} chars)"))
            else:
                out.append(("support", "FAIL",
                            f"support_span is NOT in {p.name}. Either the quote "
                            f"was reconstructed from memory or the wrong source "
                            f"was attached: {span[:64]!r}"))
            if tag == "full" and len(text) < 2000 and not (entry and entry.get("retention_state") == "excerpt"):
                out.append(("access_tag", "WARN",
                            f"tagged [full] but only {len(text):,} chars stored — "
                            f"if that is an abstract, the tag overstates"))
    if span and tag != "secondary":
        missing = numeric_mismatch(claim, span, row.get("cite_as") or "")
        if missing and derived:
            out.append(("numeric", "WARN", f"numbers {missing} in the claim are not in the span; the row is marked "
                                           "derived — the derivation must be shown beside the claim (P4 exactness)"))
        elif missing:
            # Not in the span: settle it against the WHOLE retrieved text before ruling. Absent from
            # both is a transcription the source never carried (closed -> FAIL); present elsewhere in
            # the text is a span that stopped short (open -> WARN, promotion: extend the span).
            in_text = (numeric_mismatch(claim, "", row.get("cite_as") or "", span_nums=settle_nums)
                       if settle_nums is not None else numeric_mismatch(claim, text, row.get("cite_as") or "")) if text else None
            if text is None:
                out.append(("numeric", "WARN", f"numbers {missing} are not in the span and no source text is stored "
                                               "to settle them — store the text, then re-run"))
            elif in_text:
                out.append(("numeric", "FAIL", f"numbers {in_text} appear in the claim but nowhere in the retrieved "
                                               "text — a transcription the source does not carry (the library guide p20: AI "
                                               "is insensitive to numbers). Mark `derived: true` only if it was computed"))
            else:
                out.append(("numeric", "WARN", f"numbers {missing} are in the retrieved text but not in the support "
                                               "span — extend the span to the sentence that carries them (a number "
                                               "found elsewhere in the text is a screen, not a proof)"))
        elif numbers_in(claim):
            out.append(("numeric", "OK", f"every number in the claim is in the span ({numbers_in(claim)})"))

    # ---- provenance: where did sources/<name>.txt come from? -----------------
    route = (row.get("access_route") or "").strip().lower()
    if ref and tag != "secondary" and pagestore.is_pointer(ref):
        # The row carries the hash of each page it relied on; a store page that changed since
        # (re-OCR, --redo, a hand edit) FAILs here even though file and store agree with each other.
        pres = pagestore.resolve(ref, base, row.get("pdf_sha256"))
        want = row.get("page_sha256")
        if pres.error:
            out.append(("provenance", "FAIL", pres.error))
        elif not isinstance(want, list) or len(want) != len(pres.pages):
            out.append(("provenance", "FAIL", f"page pointer row has no page_sha256 for its {len(pres.pages)} page(s) — "
                                              "write it with a ledger writer that stamps the hashes (ct.write_ledger)"))
        else:
            moved = [pg.n for pg, h in zip(pres.pages, want)
                     if pg.sha is None or not str(h) or not pg.sha.startswith(str(h))]
            if moved:
                out.append(("provenance", "FAIL", f"page text of p{moved} in {pres.pdf.name} differs from the hash this row "
                                                  "was written against — the page changed after it was cited; re-read it"))
            else:
                out.append(("provenance", "OK", f"{pres.pdf.name} p{pres.pages[0].n}"
                                                + (f"-{pres.pages[-1].n}" if len(pres.pages) > 1 else "")
                                                + f": {pres.route} page store, page sha256 matches the row"
                                                + (f" (book found by {pres.found_by})" if pres.found_by.startswith("sha") else "")))
            if pres.pdf is not None and pres.pdf.exists():
                cur = pagestore.pdf_sha(pres.pdf)
                if row.get("pdf_sha256") and not cur.startswith(str(row["pdf_sha256"])):
                    out.append(("provenance", "WARN", f"{pres.pdf.name} is not the PDF this row was written against "
                                                      f"(pdf_sha256 {row['pdf_sha256']} vs {cur[:pagestore.SHA_LEN]}) — "
                                                      "a reposted lecture or replaced book; re-read the cited page"))
                if pres.store_pdf_sha and pres.store_pdf_sha != cur:
                    out.append(("provenance", "WARN", f"the page store of {pres.pdf.name} was built from a different PDF "
                                                      "file — rebuild it with `textbook_index.py --pages --redo`"))
        if not pres.error:
            grade, why = pagestore.admission(pres.book)
            has_num = bool(numbers_in(claim))
            for scope, reason in why:
                if scope == "numbers" and not has_num:
                    continue
                out.append(("admission", "FAIL" if grade == "rejected" else "WARN", f"{grade}: {reason}"))
        if not route:
            route = "local_pdf"
        elif route not in ("local_pdf", "user_provided"):
            out.append(("access_route", "FAIL", f"access_route {route!r} on a page pointer — a page store is read from a "
                                                "local PDF (local_pdf, or user_provided for a file the user supplied)"))
    elif ref and tag != "secondary":
        if manifest is None:
            out.append(("provenance", "FAIL" if not legacy else "WARN",
                        "no sources/manifest.json — the text was not produced by fetchsrc.py, so its origin is "
                        "unverifiable" + ("" if not legacy else f" (legacy run; promotion to FAIL: run created >= {LEGACY_CUTOFF})")))
        else:
            entry = manifest_entry(manifest, ref)
            p = (base / ref) if not Path(ref).is_absolute() else Path(ref)
            if entry is None:
                out.append(("provenance", "FAIL", f"{Path(ref).name} has no manifest entry — a text no instrument "
                                                  "produced is the fabrication vector this check exists for"))
            else:
                er = entry.get("route", "")
                if er == "hand_to_user":
                    out.append(("provenance", "FAIL", f"manifest says {Path(ref).name} was refused/challenged "
                                                      f"(hand_to_user: {str(entry.get('reason', ''))[:60]}); a text under "
                                                      "that name was typed, not retrieved"))
                elif er == "user_provided":
                    out.append(("provenance", "FAIL" if mode == 2 else "WARN",
                                f"{Path(ref).name} is a user-provided passage (origin not machine-verifiable)"
                                + (" — FAIL in Mode 2: no human downstream can refute it" if mode == 2 else
                                   " — the deliverable's source list prints [user-provided passage]")))
                # WHERE a text came from and WHETHER it was edited after it was stored are two
                # different claims. The branches above rule on the first; this one rules on the
                # second, and it runs for EVERY stored file that has a recorded hash — including
                # user_provided, which used to return at its origin branch and never reach here.
                # A pasted source is exactly where a file trimmed until a span matches would
                # otherwise pass unseen (a research round L7, 2026-09-12: 14 paste-route sources, zero
                # byte coverage). Origin being unverifiable does not make the bytes unverifiable.
                # hand_to_user is excluded: it stores no file, and a file under that name is
                # already the FAIL above. Two provenance lines on one row is the honest shape.
                if er != "hand_to_user" and p.exists():
                    if not entry.get("sha256_file"):
                        out.append(("provenance", "WARN", f"{Path(ref).name}: the manifest records no sha256, so whether "
                                                          "the file was edited after storage cannot be determined — "
                                                          "re-store it with fetchsrc.py"))
                    elif _sha(p) == entry["sha256_file"]:
                        out.append(("provenance", "OK", f"{Path(ref).name}: route {er}, host {entry.get('host') or '-'}, "
                                                        f"http {entry.get('http_status', '-')}, sha256 matches"))
                    elif _sha_lf(p) == entry["sha256_file"]:
                        out.append(("provenance", "WARN",
                                    f"{Path(ref).name} differs from the manifest ONLY in line endings (CRLF on disk, "
                                    "LF hashed) — a pre-2026-09-12 fetchsrc wrote it in text mode after hashing it. "
                                    "The content is the retrieved content; nothing was edited. Re-fetch (or "
                                    "`fetchsrc.py excerpt --redo`) to restore an exact byte match"))
                    else:
                        out.append(("provenance", "FAIL", f"{Path(ref).name} sha256 differs from the manifest — the text was "
                                                          "edited after retrieval"))
                if route and er and route != er and not (route in AGENT_ROUTES and er == "script"):
                    out.append(("access_route", "FAIL", f"row says access_route {route!r} but the manifest recorded "
                                                        f"{er!r}"))
                if not route:
                    route = er

    # ---- access route vs host policy ------------------------------------------
    if tag != "secondary":
        if not route:
            out.append(("access_route", "FAIL" if not legacy else "WARN",
                        "no access_route — a citation-bearing row states how the text was obtained "
                        "(rules/literature-access.md)" + ("" if not legacy else f" (promotion: run created >= {LEGACY_CUTOFF})")))
        elif route not in ALL_ROUTES:
            out.append(("access_route", "FAIL", f"access_route {route!r} is not one of {ALL_ROUTES}"))
        elif route == "hand_to_user" and tag in ("full", "partial", "abstract"):
            out.append(("access_route", "FAIL", "access_route hand_to_user with a text-bearing tag — nothing was "
                                                "retrieved, so nothing can be quoted; the user's passage is user_provided"))
        elif route in AGENT_ROUTES and access_policy is not None:
            host = ""
            entry = manifest_entry(manifest, ref) if ref else None
            if entry and entry.get("host"):
                host = entry["host"]
            elif row.get("source_url"):
                host = access_policy.host_of(row["source_url"])
            if host:
                allowed, why, rowp = access_policy.decide(host, route, policy)
                if not allowed:
                    out.append(("access_route", "FAIL", f"policy refuses {route} on {host} ({rowp.get('class')}): "
                                                        f"{why[:110]}"))
                else:
                    out.append(("access_route", "OK", f"{route} on {host}: {rowp.get('class')} row"))
    return out


# --------------------------------------------------------------------------
# retraction sweep (credibility-rubric §3b) — every DOI in a file, paced
# --------------------------------------------------------------------------
# `)` is legal inside a DOI (Lancet: 10.1016/S0140-6736(97)11096-0); only an UNBALANCED trailing `)` is
# the surrounding parenthesis (QA 2026-09-11 F-4)
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>\]},;]+")


def clean_doi(raw: str) -> str:
    d = raw.rstrip(".,;:")
    while d.endswith(")") and d.count(")") > d.count("("):
        d = d[:-1].rstrip(".,;:")
    return d


def dois_in_text(text: str) -> list[str]:
    seen, out = set(), []
    for m in DOI_RE.finditer(text):
        d = clean_doi(m.group(0))
        if d and d.lower() not in seen:
            seen.add(d.lower())
            out.append(d)
    return out


def dois_in_file(path: Path) -> list[str]:
    return dois_in_text(path.read_text(encoding="utf-8", errors="replace"))


# the sweep's own two-sided control: a DOI that MUST show a retraction and one that must NOT
SWEEP_CONTROLS = (("10.1016/S0140-6736(97)11096-0", True), ("10.1126/science.1174655", False))


def sweep_calibrated() -> bool:
    """Both controls behave, in the same invocation, or no rate is printed (design §3.4; QA F-12)."""
    good = True
    for d, want in SWEEP_CONTROLS:
        m = _crossref(d)
        kinds = [u["type"] for u in (m.get("updated_by") or [])] if m.get("ok") else None
        got = None if kinds is None else any(k in RETRACTION_TYPES for k in kinds)
        ok = got == want
        good &= ok
        print(f"  control {'ok ' if ok else 'BROKEN'} {d}: retracted={got} (want {want})"
              + ("" if m.get("ok") else f" — HTTP {m.get('status')}"))
    return good


def retraction_sweep(path: Path, pace: float = 1.0) -> int:
    dois = dois_in_file(path)
    print(f"retraction sweep: {len(dois)} DOI(s) in {path.name}, {pace:.0f} req/s, Crossref updated-by[]")
    if not sweep_calibrated():
        print("CALIBRATION FAILED — the controls did not behave (resolver down or shape changed); no rate printed")
        return 2
    flagged = 0
    backed_off = False
    for i, d in enumerate(dois):
        if i:
            time.sleep(pace)
        status, body, headers = GET("https://api.crossref.org/works/" + urllib.parse.quote(d, safe=""))
        if status in (429, 503) and not backed_off:
            wait = float(headers.get("Retry-After") or headers.get("x-rate-limit-interval", "1s").rstrip("s") or 5)
            print(f"  {status} — backing off once for {wait:.0f}s (x-rate-limit-limit={headers.get('x-rate-limit-limit')})")
            time.sleep(min(wait, 30))
            backed_off = True
            status, body, headers = GET("https://api.crossref.org/works/" + urllib.parse.quote(d, safe=""))
        m = _crossref(d) if status == 200 else {"ok": False, "status": status}
        if not m.get("ok"):
            print(f"  ?     {d}  (HTTP {m.get('status')} — not resolvable here; check the publisher page)")
            continue
        upd = m.get("updated_by") or []
        kinds = [u["type"] for u in upd]
        if any(k in RETRACTION_TYPES for k in kinds):
            flagged += 1
            print(f"  RETRACTED {d}  {m['title'][:50]!r} — notice {[u['doi'] for u in upd if u['type'] in RETRACTION_TYPES]}")
        elif upd:
            print(f"  note  {d}  {kinds} {[u['doi'] for u in upd]}")
        else:
            print(f"  ok    {d}  {m['title'][:50]!r} ({m.get('year')})")
    print(f"{flagged} retracted of {len(dois)}; sweep date {dt.date.today().isoformat()} — record it in the run's "
          "review_when (T-1)")
    return 1 if flagged else 0


# --------------------------------------------------------------------------
# calibration — two-sided, and hermetic when --offline
# --------------------------------------------------------------------------
def _stub_get(url: str) -> tuple[int, str, dict]:
    u = urllib.parse.unquote(url)
    if "export.arxiv.org" in u and "2305.14627" in u:
        return 200, ("<feed><entry><title>Enabling Large Language Models to Generate Text with Citations</title>"
                     "<published>2023-05-24T00:00:00Z</published><author><name>Tianyu Gao</name></author>"
                     "<author><name>Howard Yen</name></author><author><name>Jiatong Yu</name></author>"
                     "<author><name>Danqi Chen</name></author></entry></feed>"), {}
    if "api.crossref.org/works/10.1126/science.1174655" in u:
        return 200, json.dumps({"message": {"DOI": "10.1126/science.1174655", "title": ["Ultrasmooth Patterned Metals for "
                                "Plasmonics and Metamaterials"], "issued": {"date-parts": [[2009, 7, 31]]},
                                "container-title": ["Science"], "author": [{"family": "Nagpal"}, {"family": "Lindquist"},
                                {"family": "Oh"}, {"family": "Norris"}]}}), {}
    if "api.crossref.org/works/10.1016/S0140-6736(97)11096-0" in u:
        return 200, json.dumps({"message": {"DOI": "10.1016/s0140-6736(97)11096-0", "title": ["Ileal-lymphoid-nodular "
                                "hyperplasia, non-specific colitis, and pervasive developmental disorder in children"],
                                "issued": {"date-parts": [[1998, 2]]}, "container-title": ["The Lancet"],
                                "author": [{"family": "Wakefield"}, {"family": "Murch"}, {"family": "Anthony"}],
                                "updated-by": [{"type": "correction", "DOI": "10.1016/s0140-6736(04)15715-2",
                                                "updated": {"date-parts": [[2004, 3, 6]]}},
                                               {"type": "retraction", "DOI": "10.1016/s0140-6736(10)60175-4",
                                                "updated": {"date-parts": [[2010, 2, 6]]}}]}}), {}
    if "api.crossref.org/works/10.1109/OJID.2025" in u or "api.crossref.org/works/10.9999" in u:
        return 404, "", {}
    ojid = {"title": "Re-Presenting Immersive Theater Through Mobile XR Display: A Case Study",
            "year": dt.date.today().year, "venue": "IEEE Open Journal on Immersive Displays",
            "externalIds": {"DOI": "10.1109/OJID.2025.3592141"},
            "authors": [{"name": "Yo-Chung Lau"}, {"name": "Tzu-Hsuan Wu"}, {"name": "Cho-Jan Wang"}]}
    if "semanticscholar.org/graph/v1/paper/search" in u and "Immersive Theater" in u:
        return 200, json.dumps({"data": [ojid]}), {}
    if "semanticscholar.org/graph/v1/paper/DOI:10.1109/OJID.2025.3592141" in u:
        return 200, json.dumps(ojid), {}
    if "semanticscholar.org/graph/v1/paper/arXiv:2305.14627" in u:
        return 200, json.dumps({"title": "Enabling Large Language Models to Generate Text with Citations",
                                "externalIds": {"DOI": "10.18653/v1/2023.emnlp-main.398"}, "year": 2023,
                                "authors": [{"name": "Tianyu Gao"}]}), {}
    return 404, "", {}


def selftest(tmp: Path, offline: bool = False) -> int:
    global GET
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "sources").mkdir(exist_ok=True)
    src = tmp / "source.txt"
    src.write_text(
        "We report a propagation length of 200 um at 780 nm for atomically "
        "smooth single-crystalline silver films. " + ("filler. " * 300),
        encoding="utf-8")

    clean = {"claim_id": "OK1", "claim": "L_spp is 200 um at 780 nm.",
             "source_id": "arXiv:2305.14627", "cite_as": "Gao 2023",
             "locator": "Sec. 3", "access_tag": "full",
             "support_span": "propagation length of 200 um at 780 nm",
             "source_text": str(src)}

    # ---- v1 cases, unchanged (label, row, want_fail): the expectation lives IN the case
    cases = [
        ("must-PASS: clean row", clean, False),
        ("must-PASS: collapsed whitespace",
         {**clean, "support_span": "propagation   length of 200 um  at 780 nm"}, False),
        ("must-PASS: hyphenation across a line break (PDF copy-out)",
         {**clean, "support_span": "propa-\ngation length of 200 um"}, False),
        ("must-PASS: curly quotes and ligature folded",
         {**clean, "support_span": "atomically smooth single-crystalline silver ﬁlms"},
         False),
        # NOT typography: NFKC folds the micro sign to Greek mu, never to "u".
        # 'um' and 'µm' are different characters in the source, so this is a
        # wording difference and MUST fail — the gate never guesses intent.
        ("must-FAIL: 'µm' where the source wrote 'um'",
         {**clean, "support_span": "propagation length of 200 µm at 780 nm"}, True),
        ("must-FAIL: fabricated identifier",
         {**clean, "source_id": "10.9999/this-doi-does-not-exist-12345"}, True),
        ("must-FAIL: real source, span it never said",
         {**clean, "support_span": "propagation length of 900 um at 1550 nm"}, True),
        ("must-FAIL: hedge the source never wrote ('roughly 200')",
         {**clean, "support_span": "propagation length of roughly 200 um"}, True),
        ("must-FAIL: wrong author attached to a real id",
         {**clean, "cite_as": "Nagpal 2009", "expect_year": 2009}, True),
        ("must-FAIL: no locator", {**clean, "locator": ""}, True),
        ("must-FAIL: [full] claim with no span",
         {**clean, "support_span": ""}, True),
    ]

    # ---- v2 cases -------------------------------------------------------------
    nagpal = {**clean, "claim_id": "N1", "source_id": "10.1126/science.1174655", "cite_as": "Nagpal 2009", "expect_year": 2009,
              "expect_title": "Ultrasmooth patterned metals for plasmonics and metamaterials",
              "expect_authors": ["Nagpal", "Lindquist", "Oh", "Norris"], "expect_venue": "Science"}
    wake = {**clean, "claim_id": "W1", "claim": "The 1998 series reported 12 children.", "support_span": "silver films",
            "source_id": "10.1016/S0140-6736(97)11096-0", "cite_as": "Wakefield 1998", "expect_year": 1998,
            "expect_title": "Ileal-lymphoid-nodular hyperplasia, non-specific colitis, and pervasive developmental disorder in children",
            "expect_authors": ["Wakefield"], "derived": True}
    ojid_title = "Re-Presenting Immersive Theater Through Mobile XR Display: A Case Study"
    ojid = {**clean, "claim_id": "D1", "claim": "The case study used a mobile XR display.", "source_id": "10.1109/OJID.2025.3592141",
            "cite_as": "Lau 2025", "expect_year": 2025, "expect_title": ojid_title, "expect_authors": ["Lau", "Wu"],
            "support_span": "silver films"}
    v2_online = [
        ("must-PASS: full metadata (title, 4 authors, venue) matches the record", nagpal, False),
        ("must-FAIL: right DOI, wrong paper (expect_title of another article)",
         {**nagpal, "expect_title": "Plasmonic waveguides in graphene at terahertz frequencies"}, True),
        ("must-FAIL: an author the record does not carry", {**nagpal, "expect_authors": ["Nagpal", "Smith"]}, True),
        ("must-FAIL: venue with zero shared tokens", {**nagpal, "expect_venue": "Optics Express"}, True),
        ("must-PASS (WARN): venue partial overlap", {**nagpal, "expect_venue": "Science Advances"}, False),
        ("must-FAIL: retracted work cited plainly", wake, True),
        ("must-PASS (WARN): retracted work cited AS retracted", {**wake, "cite_as_retracted": True}, False),
        ("must-FAIL: numeric transcription — 250 in the claim, nowhere in the text",
         {**nagpal, "claim": "L_spp is 250 um at 780 nm."}, True),
        ("must-PASS (WARN): number in the text but outside the span (span stopped short)",
         {**nagpal, "support_span": "propagation length of 200 um"}, False),
        ("must-PASS: numeric — 1,000 vs 1000 and 2.0e2 vs 200 are the same value",
         {**nagpal, "claim": "L_spp is 2.0e2 um at 780 nm.", "support_span": "propagation length of 200 um at 780 nm"}, False),
        ("must-PASS (WARN): numeric derived — 400 um total, derived: true",
         {**nagpal, "claim": "Two films give 400 um total.", "derived": True}, False),
        ("must-PASS (WARN): numeric marker [converted] in the claim",
         {**nagpal, "claim": "[converted] L_spp is 0.2 mm at 780 nm."}, False),
        ("must-PASS: the citation year in the claim is not a measured value",
         {**nagpal, "claim": "Nagpal 2009 measured 200 um at 780 nm."}, False),
        ("must-FAIL: [full] numeric row with no expect_title/expect_authors (post-cutoff run)",
         {**clean, "source_id": "10.1126/science.1174655", "cite_as": "Nagpal 2009", "_created": "2026-10-01"}, True),
        ("must-PASS (WARN): same row on a legacy run (pre-cutoff)",
         {**clean, "source_id": "10.1126/science.1174655", "cite_as": "Nagpal 2009", "_created": "2026-09-01"}, False),
        # QA 2026-09-11 amendments
        ("must-FAIL: sign flipped — claim says -200 um, source says 200 um (QA F-5)",
         {**nagpal, "claim": "L_spp shifts by -200 um at 780 nm."}, True),
        ("must-PASS: 'Fig. 3' is structure, not a measured value (QA F-7)",
         {**nagpal, "claim": "Fig. 3: L_spp is 200 um at 780 nm."}, False),
        ("must-FAIL: '3 nm' IS a measured value and the source never says it (QA F-7)",
         {**nagpal, "claim": "L_spp is 200 um at 780 nm with 3 nm roughness."}, True),
        ("must-FAIL: expect_authors as a bare string naming an author the record lacks (QA F-6)",
         {**nagpal, "expect_authors": "Smith"}, True),
        ("must-PASS: expect_authors as a bare string naming a real author", {**nagpal, "expect_authors": "Nagpal"}, False),
    ]
    v2_stub_only = [   # the doi-not-active fixture is stub-only in BOTH modes: its live shape rots the day IEEE registers it
        ("must-PASS (WARN): DOI not yet active, S2 confirms title + same DOI (the library guide p24)", ojid, False),
        ("must-FAIL: DOI not active and the confirmed record carries a DIFFERENT DOI",
         {**ojid, "source_id": "10.1109/OJID.2025.9999999"}, True),
    ]

    # provenance fixtures: a manifest beside two texts
    good_txt = tmp / "sources" / "good.txt"
    good_txt.write_text("We report a propagation length of 200 um at 780 nm. " + "pad " * 200, encoding="utf-8")
    edited_txt = tmp / "sources" / "edited.txt"
    edited_txt.write_text("We report a propagation length of 200 um at 780 nm. " + "pad " * 200, encoding="utf-8")
    orphan_txt = tmp / "sources" / "orphan.txt"
    orphan_txt.write_text("We report a propagation length of 200 um at 780 nm. " + "pad " * 200, encoding="utf-8")
    pasted_txt = tmp / "sources" / "pasted.txt"
    pasted_body = "We report a propagation length of 200 um at 780 nm. " + "pad " * 200
    pasted_txt.write_text(pasted_body, encoding="utf-8")
    # a pasted text edited AFTER it was stored: the manifest keeps the hash of what was handed over.
    # The edit sits OUTSIDE the support span (and carries no newline), so the span check still passes
    # and the line-ending forgiveness cannot absorb it — a FAIL here can only be the byte comparison.
    pasted_edited_txt = tmp / "sources" / "pasted_edited.txt"
    pasted_edited_txt.write_text(pasted_body + "and a sentence nobody handed over. ", encoding="utf-8")
    # line-ending fixtures (2026-09-12): written as BYTES so they are CRLF on every platform, the way a
    # pre-fix fetchsrc left them on Windows. `crlf` is the same content the manifest hash describes;
    # `crlf_edited` is CRLF *and* genuinely altered — the control that the forgiveness below is narrow.
    lf_body = "We report a propagation length of 200 um at 780 nm.\nSecond line.\n" + "pad \n" * 50
    crlf_txt = tmp / "sources" / "crlf.txt"
    crlf_txt.write_bytes(lf_body.replace("\n", "\r\n").encode("utf-8"))
    crlf_edited_txt = tmp / "sources" / "crlf_edited.txt"
    # the edit is OUTSIDE the support span on purpose: the span check still passes, so a FAIL here can
    # only have come from provenance (assert on the value the defect changes, not on the verdict label)
    crlf_edited_txt.write_bytes(lf_body.replace("Second line.", "Second line, silently rewritten.")
                                .replace("\n", "\r\n").encode("utf-8"))
    manifest = {"schema": "lse-sources-manifest@1", "entries": {
        "good": {"file": "sources/good.txt", "route": "script", "host": "open.example", "http_status": 200,
                 "sha256_file": _sha(good_txt)},
        "edited": {"file": "sources/edited.txt", "route": "script", "host": "open.example", "http_status": 200,
                   "sha256_file": "0" * 64},
        "pasted": {"file": "sources/pasted.txt", "route": "user_provided", "host": "", "origin_verifiable": False,
                   "sha256_file": _sha(pasted_txt)},
        "pasted_edited": {"file": "sources/pasted_edited.txt", "route": "user_provided", "host": "",
                          "origin_verifiable": False, "sha256_file": _sha(pasted_txt)},   # the hash as handed over
        # both record the hash of the LF text, which is what the pre-fix writer recorded
        "crlf": {"file": "sources/crlf.txt", "route": "script", "host": "open.example", "http_status": 200,
                 "sha256_file": hashlib.sha256(lf_body.encode("utf-8")).hexdigest()},
        "crlf_edited": {"file": "sources/crlf_edited.txt", "route": "script", "host": "open.example", "http_status": 200,
                        "sha256_file": hashlib.sha256(lf_body.encode("utf-8")).hexdigest()},
        "refused": {"file": "sources/refused.txt", "route": "hand_to_user", "host": "banned.example", "reason": "agent_banned"},
    }}
    (tmp / "sources" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp / "sources" / "refused.txt").write_text("typed from memory " * 50, encoding="utf-8")
    policy = {"schema": "literature-host-policy@1",
              "unlisted_default": {"class": "unlisted", "agent_surfaces": ["script", "webfetch"], "max_per_run": 1,
                                   "retention": "excerpt", "run_cap_distinct_unlisted_hosts": 3},
              "hosts": [{"host": "open.example", "class": "open", "agent_surfaces": ["script", "webfetch", "browser_headless"],
                         "max_per_run": 5, "retention": "full"},
                        {"host": "banned.example", "class": "agent_banned", "agent_surfaces": [], "max_per_run": 0,
                         "retention": "excerpt", "licence_basis": "ToU forbids intelligent agents"}]}
    prov_base = {**nagpal, "claim_id": "P1", "source_text": "sources/good.txt", "access_route": "script", "_created": "2026-10-01",
                 "_manifest": True}
    prov_cases = [
        ("must-PASS: provenance — manifest entry, sha256 matches, route script on an open host", prov_base, False),
        ("must-FAIL: provenance — text edited after retrieval (sha256 differs)",
         {**prov_base, "source_text": "sources/edited.txt"}, True),
        ("must-FAIL: provenance — text with no manifest entry", {**prov_base, "source_text": "sources/orphan.txt"}, True),
        ("must-PASS (WARN): provenance — bytes differ from the manifest only in line endings (pre-fix writer)",
         {**prov_base, "source_text": "sources/crlf.txt"}, False),
        ("must-FAIL: provenance — CRLF file whose content was also edited (line-ending forgiveness is narrow)",
         {**prov_base, "source_text": "sources/crlf_edited.txt"}, True),
        ("must-FAIL: provenance — manifest says hand_to_user but a text exists under that name",
         {**prov_base, "source_text": "sources/refused.txt", "access_route": "user_provided"}, True),
        ("must-PASS (WARN): user_provided passage in Mode 1",
         {**prov_base, "source_text": "sources/pasted.txt", "access_route": "user_provided"}, False),
        ("must-FAIL: user_provided passage in Mode 2", {**prov_base, "source_text": "sources/pasted.txt",
                                                        "access_route": "user_provided", "_mode": 2}, True),
        ("must-FAIL: user_provided text edited after it was stored (the origin is unverifiable; the EDIT is not)",
         {**prov_base, "source_text": "sources/pasted_edited.txt", "access_route": "user_provided"}, True),
        ("must-FAIL: access_route browser_user on an agent_banned host",
         {**prov_base, "source_text": str(src), "access_route": "browser_user", "source_url": "https://banned.example/x",
          "_created": "2026-09-01"}, True),
        ("must-FAIL: row says browser_headless, manifest recorded user_provided",
         {**prov_base, "source_text": "sources/pasted.txt", "access_route": "browser_headless"}, True),
        ("must-FAIL: hand_to_user route with a [full] tag", {**prov_base, "access_route": "hand_to_user"}, True),
        ("must-PASS: no access_route on the row, but the manifest recorded one (route comes from the instrument)",
         {**prov_base, "access_route": ""}, False),
        ("must-FAIL: post-cutoff row with no access_route and no text to read it from",
         {**nagpal, "source_text": "", "access_route": "", "_created": "2026-10-01"}, True),
        ("must-PASS (WARN): legacy run (pre-cutoff) with no manifest and no access_route",
         {**nagpal, "_created": "2026-09-01"}, False),
    ]

    # ---- v3 cases: page pointers (pagestore.py) — hermetic: a 3-page PDF + a fake OCR book ----
    # PyMuPDF is optional: without it these cases are SKIPPED and the tally says so (a skip is not a pass).
    def _ptr_fixture():
        import fitz  # noqa: PLC0415
        import shutil as _sh
        pdir = tmp / "pp"
        if pdir.exists():
            _sh.rmtree(pdir)
        pdir.mkdir()
        pt_pdf = pdir / "lecture.pdf"
        _doc = fitz.open()
        for _t in ("The bandgap of silicon is 1.12 eV at 300 K.",
                   "Minority carriers diffuse until they recom-",
                   "bine at the surface. Lifetime is 10 us."):
            _doc.new_page().insert_text((72, 72), _t)
        _doc.save(pt_pdf)
        _doc.close()
        _sh.copy(pt_pdf, pdir / "edited.pdf")
        pagestore.build_store(pt_pdf)
        pagestore.build_store(pdir / "edited.pdf")
        _s1, _psha = pagestore.stamp("pages:pp/lecture.pdf#p=1", tmp)
        _s2, _ = pagestore.stamp("pages:pp/lecture.pdf#p=2", tmp)
        _s23, _ = pagestore.stamp("pages:pp/lecture.pdf#p=2-3", tmp)
        _s3, _ = pagestore.stamp("pages:pp/lecture.pdf#p=3", tmp)
        _se, _pse = pagestore.stamp("pages:pp/edited.pdf#p=1", tmp)
        _ef = pagestore.store_dir(pdir / "edited.pdf") / "0001.txt"
        _ef.write_bytes(_ef.read_bytes().replace(b"1.12", b"1.21"))      # edited AFTER the row was stamped
        ocr_pdf = pdir / "book.pdf"
        _sh.copy(pt_pdf, ocr_pdf)
        (pdir / "book.ocr" / "text").mkdir(parents=True)
        (pdir / "book.ocr" / "manifest.json").write_text(json.dumps({"schema": "textbook-ocr/manifest@1", "pages": [
            {"page": 1, "status": "ok"}, {"page": 2, "status": "excluded"}, {"page": 3, "status": "sparse"}]}), encoding="utf-8")
        (pdir / "book.ocr" / "text" / "0001.txt").write_text("Energy gap of Si: 1.12 eV.\n", encoding="utf-8")
        (pdir / "book.ocr" / "text" / "0003.txt").write_text("Fig. 3 (partly legible) carrier lifetime\n", encoding="utf-8")
        _ocr_sha = pagestore.pdf_sha(ocr_pdf)
        _lib_prev = pagestore.LIBRARY_OVERRIDE
        pagestore.LIBRARY_OVERRIDE = {"books": [{"id": "Fake OCR Book", "path": str(ocr_pdf), "sha256": _ocr_sha, "pages": 3,
                                                 "access": "ocr-sidecar", "calibration": {"status": "ok", "segments": [
                                                     {"pdf_from": 1, "pdf_to": 3, "offset": 0}]}}]}
        pagestore.LIBRARY_OVERRIDE["books"].append({**pagestore.LIBRARY_OVERRIDE["books"][0], "id": "Rejected Copy",
                                                    "sha256": "0" * 64})
        _adm_prev = pagestore.ADMISSION_OVERRIDE
        pagestore.ADMISSION_OVERRIDE = {"books": {"Rejected Copy": {"status": "rejected", "reason": "selftest: rejected copy"}}}
        _o1, _ = pagestore.stamp("textbook:Fake OCR Book#p=1", tmp)
        _o3, _ = pagestore.stamp("textbook:Fake OCR Book#p=3", tmp)
        pt = {**clean, "claim_id": "PT", "claim": "The slide states the silicon bandgap.", "locator": "slide 1",
              "support_span": "The bandgap of silicon is", "source_text": "pages:pp/lecture.pdf#p=1",
              "page_sha256": _s1, "pdf_sha256": _psha, "access_route": "local_pdf"}
        ob = {**pt, "claim_id": "OB", "locator": "p. 1", "support_span": "Energy gap of Si",
              "source_text": "textbook:Fake OCR Book#p=1", "page_sha256": _o1, "pdf_sha256": _ocr_sha[:16]}
        ptr_cases = [
            ("must-PASS: page pointer — span on the cited page, page + pdf hashes match", pt, False),
            ("must-FAIL: page pointer — span is on p1 but the row cites p2",
             {**pt, "source_text": "pages:pp/lecture.pdf#p=2", "page_sha256": _s2}, True),
            ("must-PASS: page pointer range — a word hyphenated across the page break",
             {**pt, "support_span": "diffuse until they recombine at the surface", "source_text": "pages:pp/lecture.pdf#p=2-3",
              "page_sha256": _s23}, False),
            ("must-FAIL: page pointer — the row's page_sha256 is not the page's", {**pt, "page_sha256": ["0" * 16]}, True),
            ("must-FAIL: page pointer — store page edited after the row was written (span still present)",
             {**pt, "source_text": "pages:pp/edited.pdf#p=1", "page_sha256": _se, "pdf_sha256": _pse}, True),
            ("must-FAIL: page pointer row with no page_sha256", {k: v for k, v in pt.items() if k != "page_sha256"}, True),
            ("must-PASS (WARN): page pointer — PDF replaced since the row was written", {**pt, "pdf_sha256": "f" * 16}, False),
            ("must-FAIL: page pointer — page beyond the PDF", {**pt, "source_text": "pages:pp/lecture.pdf#p=9"}, True),
            ("must-FAIL: page pointer — malformed pointer", {**pt, "source_text": "pages:pp/lecture.pdf"}, True),
            ("must-PASS (WARN): page pointer — a number outside the span but elsewhere in the document (1.12 on p1, p3 cited)",
             {**pt, "claim": "Lifetime is 10 us with a 1.12 eV gap.", "support_span": "Lifetime is 10 us",
              "source_text": "pages:pp/lecture.pdf#p=3", "page_sha256": _s3}, False),
            ("must-FAIL: page pointer — a number the whole document never carries (1.42 eV)",
             {**pt, "claim": "Lifetime is 10 us with a 1.42 eV gap.", "support_span": "Lifetime is 10 us",
              "source_text": "pages:pp/lecture.pdf#p=3", "page_sha256": _s3}, True),
            ("must-FAIL: page pointer with access_route script", {**pt, "access_route": "script"}, True),
            ("must-PASS: OCR book page, status ok", ob, False),
            ("must-FAIL: OCR book page excluded", {**ob, "source_text": "textbook:Fake OCR Book#p=2", "page_sha256": ["x"]}, True),
            ("must-FAIL: [full] on a sparse OCR page",
             {**ob, "support_span": "carrier lifetime", "source_text": "textbook:Fake OCR Book#p=3", "page_sha256": _o3}, True),
            ("must-PASS (WARN): locator printed page disagrees with the calibrated pointer page", {**ob, "locator": "p. 40"}, False),
            ("must-PASS: book renamed — found again by pdf_sha256", {**ob, "source_text": "textbook:Old Name#p=1"}, False),
            ("must-FAIL: unknown book and no pdf_sha256",
             {k: v for k, v in ob.items() if k != "pdf_sha256"} | {"source_text": "textbook:Old Name#p=1"}, True),
            ("must-FAIL: a source the admission rulings reject", {**ob, "source_text": "textbook:Rejected Copy#p=1"}, True),
            ("must-PASS (WARN): OCR book, numeric claim — admission limits numbers, does not reject",
             {**ob, "claim": "Energy gap of Si is 1.12 eV.", "support_span": "Energy gap of Si: 1.12 eV"}, False),
        ]
        return ptr_cases, _lib_prev, _adm_prev

    ptr_skipped = False
    try:
        ptr_cases, _lib_prev, _adm_prev = _ptr_fixture()
    except ImportError:
        ptr_cases, ptr_skipped = [], True
        _lib_prev, _adm_prev = pagestore.LIBRARY_OVERRIDE, pagestore.ADMISSION_OVERRIDE

    bad = 0
    print(f"{'verdict':9} case")
    print("-" * 72)

    def run_case(label, row, want_fail, stub: bool):
        nonlocal bad
        global GET
        prev = GET
        if stub:
            GET = _stub_get
        try:
            mode = int(row.get("_mode", 1))
            created = row.get("_created")
            man = manifest if row.get("_manifest") else None     # only the provenance cases carry a manifest
            checks = check_row({k: v for k, v in row.items() if not k.startswith("_")}, tmp, offline=False,
                               manifest=man, mode=mode, created=created, policy=policy)
        finally:
            GET = prev
        failed = any(v == "FAIL" for _, v, _ in checks)
        ok = failed == want_fail
        bad += 0 if ok else 1
        print(f"{'ok' if ok else 'BROKEN':9} {label}")
        if not ok:
            for n, v, d in checks:
                print(f"{'':9}   {v:5} {n}: {d[:100]}")

    online_stub = offline
    for label, row, want in cases:
        run_case(label, row, want, online_stub)
    print(f"{'':9} -- v2: metadata / retraction / numeric ({'stubbed resolvers' if offline else 'LIVE resolvers'})")
    for label, row, want in v2_online:
        run_case(label, row, want, online_stub)
    print(f"{'':9} -- v2: doi-not-active fixtures (stub resolvers in both modes)")
    for label, row, want in v2_stub_only:
        run_case(label, row, want, True)
    print(f"{'':9} -- v2: provenance / access route ({'stubbed' if offline else 'LIVE'} resolvers, local manifest)")
    for label, row, want in prov_cases:
        run_case(label, row, want, online_stub)
    print(f"{'':9} -- v3: page pointers (pagestore.py; stub resolvers, hermetic PDF + fake OCR book)")
    if ptr_skipped:
        print(f"{'skipped':9} v3 page-pointer cases: PyMuPDF (fitz) is not installed — the PDF path is not calibrated here")
    try:
        for label, row, want in ptr_cases:
            run_case(label, row, want, True)
    finally:
        pagestore.LIBRARY_OVERRIDE = _lib_prev
        pagestore.ADMISSION_OVERRIDE = _adm_prev

    # pure-function regressions from the 2026-09-11 QA pass (no resolver involved)
    print(f"{'':9} -- v2: pure-function regressions (QA 2026-09-11)")

    def _prov_checks(source_text: str, route: str = "") -> list[tuple[str, str, str]]:
        row = {k: v for k, v in prov_base.items() if not k.startswith("_")} | {"source_text": source_text}
        if route:
            row["access_route"] = route      # else prov_base's "script" contradicts the manifest entry
        return check_row(row, tmp, offline=False, manifest=manifest, mode=1, created="2026-10-01", policy=policy)

    _paste_ok = [(n, v) for n, v, _ in _prov_checks("sources/pasted.txt", "user_provided") if n == "provenance"]
    _paste_edited = [(n, v) for n, v, _ in _prov_checks("sources/pasted_edited.txt", "user_provided")
                     if n in ("support", "provenance")]
    _crlf_prov = next((c for c in _prov_checks("sources/crlf.txt") if c[0] == "provenance"), None)
    _crlf_edited_checks = [(n, v) for n, v, _ in _prov_checks("sources/crlf_edited.txt")
                           if n in ("provenance", "support")]
    pure = [
        ("must-PASS: DOI scanner keeps a balanced ')' inside the DOI (QA F-4)",
         dois_in_text("See 10.1016/S0140-6736(97)11096-0 for details.") == ["10.1016/S0140-6736(97)11096-0"]),
        ("must-PASS: DOI scanner drops the surrounding parenthesis (10.1000/xyz)",
         dois_in_text("(10.1000/xyz) and 10.1000/abc.def.") == ["10.1000/xyz", "10.1000/abc.def"]),
        ("must-FAIL: numeric — Unicode minus sign counts as a sign (QA F-5)",
         numeric_mismatch("shift of −3.2 nm", "shift of 3.2 nm") == ["-3.2"]),
        ("must-PASS: numeric — '+3.2' equals '3.2' by value", numeric_mismatch("shift of +3.2 nm", "shift of 3.2 nm") == []),
        ("must-PASS: 'Table 2 lists' yields no measured number (QA F-7)", numbers_in("Table 2 lists 12 devices") == ["12"]),
        ("must-FAIL: degenerate titles 'X' vs 'Y' do not match (QA F-8)", title_match("X", "Y") is False),
        ("must-PASS: surname fold — Müller cited as Muller (QA F-9)", _surname_in("Muller", ["Müller"]) and _surname_in("Müller", ["Muller"])),
        # 2026-09-12 line endings: the verdict must be a named WARN, not a silent pass, and the
        # narrow forgiveness must still reach FAIL when the content itself moved
        ("must-PASS: a CRLF-only difference is a provenance WARN that says so, never OK and never FAIL",
         _crlf_prov is not None and _crlf_prov[1] == "WARN" and "line endings" in _crlf_prov[2]),
        ("must-FAIL: a CRLF file whose content moved is still provenance FAIL, with the span check passing",
         _crlf_edited_checks == [("support", "OK"), ("provenance", "FAIL")]),
        ("must-PASS: check_row(mode='2') behaves as Mode 2 (QA F-15)",
         any(v == "FAIL" and n == "provenance" for n, v, _ in
             check_row({k: v for k, v in prov_base.items() if not k.startswith("_")} | {"source_text": "sources/pasted.txt",
                       "access_route": "user_provided"}, tmp, offline=False, manifest=manifest, mode="2",  # type: ignore[arg-type]
                       created="2026-10-01", policy=policy))),
        # a research round 2026-09-12: two normalizer gaps that read a CORRECT span as suspect.
        # Both are two-sided here: the widened rule must not start swallowing what the
        # narrow one correctly rejected.
        ("must-PASS: '5 μm' (Greek mu U+03BC, what PDF text actually carries) keeps the bare digit",
         numbers_in("± 5 μm ± 3 μm") == ["5", "3"] == numbers_in("± 5 µm ± 3 µm")),
        ("must-PASS: the unit may also be spelled out — '5 microns' is a measured value",
         numbers_in("a value of 5 microns") == ["5"] and numbers_in("a 3 nanometer gap") == ["3"]),
        ("must-PASS: '3 devices' is still a count, not a measured value (the unit gate stays shut)",
         numbers_in("in 3 devices") == [] and numbers_in("Fig. 3 shows") == []),
        ("must-PASS: a '- -' not-reported cell pair before a line break still matches a one-line span",
         span_present("Measured Multi-tip taper 1550 nm -1.50 dB - -",
                      "8 um oxide\nCurrent work\nMeasured Multi-tip taper\n1550 nm\n-1.50 dB \n- \n- \nCurrent work")),
        ("must-PASS: real hyphenation across a line break still folds ('ta-\\nper' -> 'taper')",
         span_present("a taper with a length", "based on a ta-\nper with a length of 500 um")),
        ("must-FAIL: a cell the source never wrote is still not a match",
         span_present("1.50 dB - -", "1.50 dB \n- \nx \n") is False),
        # One input, one output: a word's readings must NOT depend on where the line broke.
        # This property is the rule — the cases under it are only the shapes it was written for.
        ("must-PASS: the normal form is one rule in one place, and holds its own properties",
         not __import__("spannorm").selfcheck() and norm is __import__("spannorm").norm),
        ("must-PASS: every reading of a hyphenated word folds to ONE canonical form",
         norm("a high-\ndensity array") == norm("a high-density array") == norm("a highdensity array")),
        ("must-PASS: a compound split at its own hyphen matches a one-line span (both directions)",
         span_present("wafer-scale high-density arrays", "on wafer-\nscale high-density arrays here")
         and span_present("El-Fiky et al.", "reported by El-\nFiky et al.")),
        ("must-PASS: a hyphen touching a DIGIT is content — a range keeps it and its numbers stay apart",
         norm("1550-\n1600 nm") == norm("1550-1600 nm") == "1550-1600 nm"
         and span_present("1550-1600 nm", "tuned over 1550-\n1600 nm here")),
        ("must-FAIL: fusing a range's numbers is NOT a reading of it ('15501600' was never written)",
         span_present("15501600 nm", "tuned over 1550-\n1600 nm here") is False),
        ("must-FAIL: an identifier the source hyphenated is not the same string unhyphenated",
         span_present("SMF28 fiber", "with SMF-28 fiber") is False),
        # a research round L7 2026-09-12: origin and byte integrity are two claims on one row. The route
        # branch used to return before the byte comparison, so every pasted source — a whole run of
        # them — carried no integrity coverage at all. Both verdicts must now appear, in that order.
        ("must-PASS: an unedited pasted source keeps its origin WARN and now also gets a byte OK",
         _paste_ok == [("provenance", "WARN"), ("provenance", "OK")]),
        ("must-FAIL: a pasted source edited after storage is a byte FAIL beside its origin WARN, "
         "with the span check still passing",
         _paste_edited == [("support", "OK"), ("provenance", "WARN"), ("provenance", "FAIL")]),
        # a research round 2026-09-12: a range partner between a lone digit and its unit. Two-sided —
        # the endpoint becomes checkable, and a range the span does not carry is still caught.
        ("must-PASS: every endpoint of a range or list is a measured value, wherever it sits",
         numbers_in("gaps of 5-10 nm") == ["5", "10"] and numbers_in("2-3 μm") == ["2", "3"]
         and numbers_in("from 5 to 10 nm") == ["5", "10"] and numbers_in("3, 4 and 5 nm") == ["3", "4", "5"]),
        ("must-PASS: the real row that exposed it — a claim's range spelled out as a list in the span",
         numeric_mismatch("tolerances of at least 5-20 microns",
                          "tolerances of at least 5, 10, 15 or up to 20 microns") == []),
        ("must-PASS: a claim quoting '5 nm' against a span reading '5-10 nm' is no longer a mismatch",
         numeric_mismatch("the gap is 5 nm", "measured gaps of 5-10 nm") == []),
        ("must-FAIL: a claim asserting a range the span does not carry is still caught",
         numeric_mismatch("the range is 5-10 nm", "a gap of 10 nm") == ["5"]),
        ("must-PASS: a connective is not a unit — structure numbers stay out",
         numbers_in("Fig. 3-5 shows") == [] and numbers_in("Fig. 2 and 3 display") == []
         and numbers_in("1 of 4 lenses") == [] and numbers_in("Fig. 3 in Smith") == []),
        ("must-PASS: a number with no unit anywhere after it is still not a measurement",
         numbers_in("5, and the 10 nm gap") == ["10"]),
        # The limit that REMAINS, pinned so it is refutable rather than folklore: a <= 4-letter word
        # that is not a connective still reads as a unit. Whoever replaces the heuristic with a real
        # unit vocabulary must change this line deliberately, and say what the new failure direction
        # is — growing the connective list instead is how a heuristic rots into folklore.
        ("must-PASS: short-word limit, pinned — 'list' still reads as a unit after a digit",
         numbers_in("Table 2 to 4 list") == ["2", "4"]),
    ]
    # CLI-level exit rules (review 2026-11-07): the value each defect changes is the printed count / exit code
    import subprocess as _sp

    def _cli(lines: list[str], run_json: bool = True, extra: tuple = (), enc: str = "utf-8",
             split: bool = False):
        d = tmp / f"cli{len(list(tmp.glob('cli*')))}"
        d.mkdir()
        (d / "ledger.jsonl").write_text("".join(l + "\n" for l in lines), encoding=enc)
        if run_json:
            (d / "run.json").write_text(json.dumps({"run": {"created": "2026-09-01"}}), encoding="utf-8")
        p = _sp.run([sys.executable, "-X", "utf8", "-I", str(Path(__file__).resolve()), str(d / "ledger.jsonl"), "--offline",
                     *extra], capture_output=True, text=True, encoding="utf-8", errors="replace")
        return (p.returncode, p.stdout, p.stderr) if split else (p.returncode, p.stdout + p.stderr)

    def _parses(s: str) -> bool:
        try:
            json.loads(s)
            return True
        except ValueError:
            return False

    _row = json.dumps({k: v for k, v in clean.items() if not k.startswith("_")}, ensure_ascii=False)
    _rc_ok, _out_ok = _cli([_row])
    _rc_bad, _out_bad = _cli([_row, "{not json"])
    _rc_empty, _out_empty = _cli([])
    _, _out_new = _cli([_row], run_json=False)
    _, _js_out, _js_err = _cli([_row, "{not json"], run_json=False, extra=("--json",), split=True)
    _rc_bom, _out_bom = _cli([_row], enc="utf-8-sig")
    pure += [
        ("must-FAIL: with --json, stdout is pure JSON (diagnostics on stderr), so `--json > citecheck.json` parses",
         _parses(_js_out) and "judged as a run created today" in _js_err and "unreadable ledger line" in _js_err),
        ("must-FAIL: a UTF-8 BOM ledger (PowerShell) reads like the same ledger without one",
         "unreadable ledger line" not in _out_bom and _rc_bom == _rc_ok),
        ("must-FAIL: a whitespace-only span is found in no text (it would be 'in' every text)",
         span_present("  \n\t", "any text at all") is False and span_present("any", "any text at all")),
        ("must-FAIL: one unreadable ledger line makes the run exit 1 (the same ledger without it reports none)",
         "unreadable ledger line" not in _out_ok and "1 unreadable ledger line" in _out_bad and _rc_bad == 1),
        ("must-FAIL: an empty ledger exits 1 — nothing checked is not a pass",
         _rc_empty == 1 and "ledger has no rows" in _out_empty and "ledger has no rows" not in _out_ok),
        ("must-FAIL: a run dir without run.json is judged as a new run, not legacy",
         "judged as a run created today" in _out_new and "judged as a run created today" not in _out_ok),
    ]
    for label, good in pure:
        bad += 0 if good else 1
        print(f"{'ok' if good else 'BROKEN':9} {label}")
    # the retraction sweep's own calibration gate, on the stub (the live probe below covers the shape)
    prev = GET
    GET = _stub_get
    try:
        sweep_file = tmp / "sweep.txt"
        sweep_file.write_text("cites 10.1016/S0140-6736(97)11096-0 and (10.1126/science.1174655).", encoding="utf-8")
        rc = retraction_sweep(sweep_file, pace=0.0)
        good = rc == 1
        bad += 0 if good else 1
        print(f"{'ok' if good else 'BROKEN':9} must-FLAG: retraction sweep finds the Lancet DOI with its ')' and flags it (rc 1)")
        # controls broken -> no rate: point the good control at a DOI the stub cannot resolve
        saved = SWEEP_CONTROLS
        globals()["SWEEP_CONTROLS"] = (("10.9999/none", True), ("10.1126/science.1174655", False))
        rc = retraction_sweep(sweep_file, pace=0.0)
        globals()["SWEEP_CONTROLS"] = saved
        good = rc == 2
        bad += 0 if good else 1
        print(f"{'ok' if good else 'BROKEN':9} must-REFUSE to print a rate when a sweep control misbehaves (rc 2) (QA F-12)")
    finally:
        GET = prev
    n_pure = len(pure) + 2

    # live probes: informational, never break the calibration
    if offline:
        print(f"{'skipped':9} live probe: Crossref updated-by[] shape on 10.1016/S0140-6736(97)11096-0 (offline)")
        print(f"{'skipped':9} live probe: 10.1109/OJID.2025.3592141 Crossref vs Semantic Scholar (offline)")
    else:
        m = _crossref("10.1016/S0140-6736(97)11096-0")
        kinds = [u["type"] for u in m.get("updated_by") or []]
        print(f"{'probe':9} live: Wakefield 1998 updated-by types = {kinds} "
              f"({'retraction present' if 'retraction' in kinds else 'SHAPE CHANGED — review citecheck'})")
        st, _, _ = GET("https://api.crossref.org/works/10.1109%2FOJID.2025.3592141")
        s2 = s2_by_id("DOI:10.1109/OJID.2025.3592141")
        print(f"{'probe':9} live: OJID DOI crossref={st} s2={'hit' if s2 else 'miss'} "
              f"(the p24 case; when crossref turns 200 the fixture stays stub-only by design)")

    all_cases = cases + v2_online + v2_stub_only + prov_cases + ptr_cases
    n_pass = sum(1 for _, _, w in all_cases if not w) + sum(1 for l, _ in pure if l.startswith("must-PASS")) + 1
    n_fail = len(all_cases) + n_pure - n_pass
    print("-" * 72)
    print(f"{len(all_cases) + n_pure} cases ({n_pass} must-pass / {n_fail} must-fail), {bad} broken — "
          f"{'gate is calibrated' if not bad else 'GATE IS NOT TRUSTWORTHY'}"
          + (" [offline: stub resolvers]" if offline else " [live resolvers]")
          + (" [page-pointer cases skipped: no PyMuPDF]" if ptr_skipped else ""))
    if not n_pass or not n_fail:
        print("ONE-SIDED: a gate that only ever rejects scores 100% here. "
              "Both sides must be populated for this result to mean anything.")
        return 1
    return 1 if bad else 0


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ledger", nargs="?")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--mode", type=int, default=1, choices=(1, 2), help="Mode 2 = result returned to a caller")
    ap.add_argument("--run-created", help="override run.json run.created (legacy trigger)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--retraction-sweep", metavar="FILE", help="rubric §3b: check every DOI in FILE (1 req/s)")
    args = ap.parse_args()

    if args.selftest:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="citecheck-selftest-") as tmp:
            return selftest(Path(tmp), offline=args.offline)
    if args.retraction_sweep:
        p = Path(args.retraction_sweep)
        if not p.exists():
            print(f"not found: {p}")
            return 2
        return retraction_sweep(p)
    if not args.ledger:
        ap.print_help()
        return 2

    path = Path(args.ledger)
    # with --json, stdout is the JSON document (`--json > citecheck.json`): every diagnostic goes to stderr
    say = (lambda s: print(s, file=sys.stderr)) if args.json else print
    if not path.exists():
        say(f"ledger not found: {path}")
        return 2
    base = path.resolve().parent
    manifest = load_manifest(base)
    created = args.run_created or run_created(base)
    if not created:
        # a run with no run.json (or no created date) is judged as a NEW run: a missing record must not buy
        # the legacy WARN side (review 2026-11-07). Pass --run-created to judge a genuinely old run as legacy.
        created = dt.date.today().isoformat()
        say("run.json absent or undated — judged as a run created today (pass --run-created for an old run)")
    policy = access_policy.load() if access_policy else None

    rows = []
    unreadable = 0
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):  # a PowerShell BOM is not a bad row
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            obj = json.loads(line)
        except Exception as exc:                            # noqa: BLE001
            say(f"line {n}: not JSON ({exc}) — FAIL (a row the gate cannot read is a claim it never checked)")
            unreadable += 1
            continue
        if not isinstance(obj, dict):
            say(f"line {n}: JSON but not an object ({type(obj).__name__}) — FAIL (QA F-13)")
            unreadable += 1
            continue
        rows.append(obj)

    results = [{"claim_id": r.get("claim_id", f"row{i}"),
                "claim": r.get("claim", ""),
                "checks": check_row(r, base, args.offline, manifest=manifest,
                                    mode=int(r.get("mode") or args.mode), created=created, policy=policy)}
               for i, r in enumerate(rows, 1)]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"citecheck v2 · manifest {'present' if manifest else 'ABSENT'} · run created {created or '?'} · mode {args.mode}"
              f" · policy {'loaded' if policy else 'UNREADABLE (fail-closed)'}")
        for r in results:
            print(f"\n[{r['claim_id']}] {r['claim'][:70]}")
            for name, verdict, detail in r["checks"]:
                print(f"  {verdict:5} {name:12} {detail}")
        fails = sum(1 for r in results for c in r["checks"] if c[1] == "FAIL")
        warns = sum(1 for r in results for c in r["checks"] if c[1] == "WARN")
        print(f"\n{len(results)} claim(s): {fails} FAIL, {warns} WARN")
        if fails:
            print("A FAIL is not a style note: that claim may not ship as cited.")
    if unreadable:
        say(f"{unreadable} unreadable ledger line(s) — exit 1")
        return 1
    if not rows:
        say("ledger has no rows — nothing was checked, which is not a pass (exit 1)")
        return 1
    return 1 if any(c[1] == "FAIL" for r in results for c in r["checks"]) else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                       # noqa: BLE001
        pass
    raise SystemExit(main())
