# Connectors — routing registered data systems into P2

Companion to SKILL.md P2. A **connector** is a data-collection system on this
machine that is neither WebSearch nor a plain fetch: a local tool holding a
paid API key, a reference manager, a patent database, a rendering browser. The
contract, the secret boundary, and how to add one live in
`../connectors/README.md`; this file is the routing rule only.

Registry: `../connectors/registry.json` · Probe: `../connectors/probe.py`

## Where connectors sit on the P2 ladder

Insert ABOVE the local-corpus rung, because a connector holds primary
documents the open web does not index well:

```
0. source-provided (user named the sources)          -- unchanged, still first
1. CONNECTORS whose source_class matches the need    <- new rung
2. local corpus (Zotero / local PDF folder — prism RETIRED 2026-08-27)
3. WebSearch + WebFetch discovery
```

Route to a connector when the information need's **source class** matches one it
declares — not because it exists. A patent connector is not a shortcut for a
journal question.

| Need in the question | Connector class | Registered today |
|---|---|---|
| Patent prior art, claim language, applicant's own filings | `patents` | `patentsgrabber` (live) |
| A JS-heavy page of a named document on a host whose policy row lists `browser_headless` | `extract_render` | `browser_session` (available) — a 403 / challenge / consent wall on a publisher is NOT this class; it is hand-to-user |
| **Which surface may touch which host, and how many per run** | `access_policy` | `access_policy.py` (live) — reads `~/.claude/hooks/literature-host-policy.json`; every fetch consults it first (§ below) |
| Already-collected corpus | `local_corpus` | `zotero_local` (metadata) + `local_pdf_library` (files) — `prism` RETIRED, do not probe |
| Broad scholarly graph, coverage checks | `scholarly_index` | `semantic_scholar`, `openalex` (needs key) |
| A legal OA copy of a paywalled DOI | `oa_resolver` | `unpaywall` (needs user email) |
| Full text behind a subscription | `access_upgrade`, `publisher_api` | `institutional_proxy`, `ieee_xplore` (need user) |
| Standards documents | `standards` | none — an honest permanent gap |
| **A material constant / thermophysical value** ("what is the literature value of X") | `data_compilation` | `reference_data_compilations` (available) — cite THROUGH to the primary source, `credibility-rubric.md` §5b |
| Agency or government technical report | `reports` | `agency_reports` (available) — NTRS, OSTI; free full text |
| A method described in reproducible detail | `theses` | `theses_repositories` (available) — NDLTD Taiwan, institutional repositories |
| A number that lives in deposited data, not a table | `datasets_software` | `zenodo` (available, 60 req/hr keyless) |
| Chinese-language / Taiwanese venue | `regional_index` | `airiti_library` (needs_user — institutional access) |

The bottom five were added 2026-09-03. They were not previously declined; they were
**never considered**, which is a different and worse condition: a declined channel shows
up in `gaps` as a known cost, while an unconsidered class makes a question look like it
has no answer anywhere. Routing rule is unchanged — match the question's source class,
never route to a connector because it exists.

## access_policy — the host routing table, read before any fetch

`rules/literature-access.md` is the rule; `~/.claude/hooks/literature-host-policy.json`
is that rule as a table (rule tier — the machine-wide hook `hooks/literature_host_guard.py`
reads the same file, so the skill and the harness cannot disagree); this skill only READS it.

```
python ../connectors/access_policy.py --url <u> [--surface script|webfetch|browser_headless|browser_user] --check
python ../connectors/access_policy.py --host ieeexplore.ieee.org
python ../connectors/access_policy.py --url <u> --surface script --check --run <run folder> --record   # count a script call against a run
python ../connectors/access_policy.py --selftest        # 27 cases, 10 must-allow / 17 must-refuse (measured 2026-11-03; re-take: this command)
```

Five classes, and what each means for P2: `open` (any listed surface, full text may be
kept) · `metadata_api` (script/webfetch only — the licensed automation route) ·
`landing_page` (what the public page shows, human pace, `max_per_run` small, retention
excerpt) · `agent_banned` (ToU forbids agents, or bot management answered — **hand the
named document to the user**) · `institutional_only` (Scopus, Web of Science, airiti,
the library discovery layer — the agent ships a query pack, the user runs it). An
**unlisted** host gets one script/webfetch of a named URL and no browser surface; more
than three distinct unlisted hosts in one run is a sweep and stops. The policy is
fail-closed: with the file unreadable, only the built-in public-API core is reachable.

**`max_per_run` is one count per run, shared by every script surface (2026-11-03).** The count
is the sum of `sources/manifest.json` (what `fetchsrc.py` retrieved) and
`<run>/sources/host-calls.jsonl` (what any other script logged with `access_policy.py --check
--run <run> --record`, or `access_policy.gate(...)` from Python). `fetchsrc.py fetch` reads the
sum, so a plain script's call counts against the same cap, and the other way round. Rules:
record immediately BEFORE the request; a refused call (exit 1) is not recorded and consumes
nothing; two runs never share a count. A script that does not name its run is not counted by
this path — that is the gap, not a feature. The machine-wide hook `hooks/literature_host_guard.py`
cannot see runs, so it only covers a plain shell script by SESSION and only as a notice: the
second retrieval-verb call (curl, urllib, requests …) to an UNLISTED host in one session gets
one non-blocking notice naming this route. An API that really needs many calls needs a policy
row with a larger `max_per_run` (the user's edit; the unlisted default of 1 is a named-document
cap, not a metadata-API cap).

Three consequences the executor keeps:

- **The instrument is `../verify/fetchsrc.py`**, not WebFetch, for anything that will be
  cited: it consults the policy, records `host / route / status` per source in
  `sources/manifest.json`, treats a challenge as `HAND-TO-USER` (exit 3), and keeps
  licensed full text out of the run folder (excerpt windows only — `feedback-loop.md`).
- **A refused or challenged host goes to `gaps` as "not retrieved, hand-to-user"** — the
  deliverable then carries a query pack (`output-templates.md`), and the user's reading
  is the licensed act. Never "not found".
- **`search_trail` names the policy row** it acted under (`policy row: www.nature.com
  landing_page, 1/5`) — a fetch without a row name is a fetch nobody can audit.

## Three rules, in the order they get violated

**R1 — Probe before route, once per session.**
`python ../connectors/probe.py --id <id>`. A `FAIL` means do not route here.
The check that earns its keep is `contract`: a **running process can be older
than its own source**. Measured 2026-08-26 — the live PatentsGrabber server
lacked `/api/query` while the source had it; routing there would have returned
404, and a 404 read as **"no results found"** is a false negative that looks
exactly like a true one. Restart the connector, re-probe, then route.

**R2 — Never exceed the declared `access_ceiling`.**
The ceiling is what the connector can physically deliver. A metadata-only
channel can never produce a `[full]` tag, however complete its JSON looks.
Cap first, then downgrade further for what you actually read.

**R3 — `search_trail` names the connector and what it spent.**
Use the entry's `search_trail_label`. If the connector reports a live meter
(PatentsGrabber returns `ops.quota` on every card), copy the string verbatim —
a quoted meter is evidence; a remembered one is a guess.

## patentsgrabber — field mapping

Front door is **`/api/query?q=`** (a number returns a card, anything else
returns a search list). `/api/patent` is US-only: it rejects `EP1000000A1` with
"cannot interpret as a US patent number" (measured 2026-08-26). `/api/library`
costs no quota — use it as the probe and as the P2 reuse-before-re-search check.

The card already carries most of what P4 demands, so extraction is mapping, not
invention:

| Card field | Use as |
|---|---|
| `description_blocks[].num` | **paragraph locator** — cite as `(US…B2, ¶[0042])`, the patent equivalent of a page number |
| `claims[].num`, `claims[].dependent` | **claim locator** and independence; `independent_claims` lists the ones that define scope |
| `provenance.<field>.source` | which source each field came from — `Google Patents` or `EPO OPS`. Copy into the source list; this is per-field access honesty the skill otherwise has to reconstruct |
| `missing` | goes straight into `gaps` — the tool already states which fields it could not get and why |
| `classifications.truncated` / `.total` / `.cap` | a truncated list is a `gaps` entry, not a complete one. Same for `family`, `citations`, `legal_events` |
| `ops.quota` | the cost string for `search_trail` |
| `_fetched_at` | **retrieval timestamp** — see below |
| `legal_status`, `legal_events` | validity. A patent's claims are only prior art as published; legal status decides whether it also blocks |
| `backward_citations` / `forward_citations` | citation chasing, patent-side — same backward/forward logic as `search-sources.md` |

**Access tags for patent sources:**

- `[full]` — description and claims present (US only when Google Patents has
  the document; EP from Google Patents or OPS full text).
- `[partial]` — OPS bibliographic card, no full text. This is the NORMAL state
  for a recent US publication: OPS carries US publications months before Google
  indexes them, but OPS full text does not cover the US at all. Never present
  such a card as full text.
- Language: the EPO publishes an EP specification in the **filing language
  only**. A German EP case is German; the card says so. Extract in the source
  language, deliver in the contract language, and quote the original when
  wording is load-bearing (`search-sources.md`, non-English section).

**Terms boundary that reaches the deliverable:** EPO OPS T&C 3.2 forbids making
OPS data itself available to the public. Local reading and quoting into a
private deliverable is fine; a report the user intends to PUBLISH must flag
which content came from OPS so they can strip it. Google Patents:
single-document pages only, never its search endpoint.

## local_pdf_library — the corpus rung

Root: the user's Zotero attachment store (`~/Zotero/storage`), 116 indexed
PDFs, 1996–2026, median 2023, 47% from the last three years. It is the **only live
`local_corpus`** since prism retired.

```
python ../connectors/pdf_index.py --search <terms>     # before web discovery
python ../connectors/pdf_index.py --stats              # collection-bias numbers
python ../connectors/pdf_index.py --build              # after the library changes
```

Three rules:

- **The index is not a citation.** It knows only what a filename says — no DOI, no
  journal, no abstract. A local hit still goes through identifier resolution (P2) and
  the P4.5 support-span check. Reading the PDF is genuinely `[full]`; believing the
  filename is not.
- **An empty local result never means "literature not found."** Go to web discovery and
  record in `search_trail` that the library was checked. The tool prints this itself on
  a miss, because that is the moment it gets forgotten.
- **Quote the bias numbers when a claim rests only on this library.** A personal library
  is a reading history, not a survey — what is missing from it is invisible from inside
  it. `--stats` exists to make that quotable rather than hand-waved
  (`credibility-rubric.md` §6).

## zotero_local — the same corpus, as citations

Two views of one library, joined on the Zotero item key. Use whichever the
question needs:

```
python ../connectors/pdf_index.py --search <terms>      # fast, filenames, what is on disk
python ../connectors/zotero_local.py --search <terms>   # DOI, journal, abstract, authors
python ../connectors/zotero_local.py --resolve <KEY>    # one full record + PDF path
python ../connectors/zotero_local.py --stats            # metadata coverage
python ../connectors/zotero_local.py --annotations <KEY> [--json]   # marks on its PDFs + child notes, origin-tagged
```

Measured 2026-08-27 (`--stats`): 157 items, **126 with a DOI (80%)**, 99 with an
abstract, **114 with a PDF on disk**.

- **Ask Zotero before resolving an identifier.** A local hit with a DOI already
  in hand skips the Crossref round-trip entirely. That is the whole point of
  this rung.
- **`[full]` needs a PDF on disk, not good metadata.** 43 of 157 items have
  none; a complete-looking record with no attachment caps at `[abstract]`, and
  the shortfall is a `gaps` entry. `--search` marks each PDF `[on disk]` or
  `[MISSING]` so this is visible rather than assumed.
- **It removes the lookup, not the verification.** Zotero's fields are whatever
  the import put there — a wrong DOI in Zotero is wrong here. Load-bearing
  items still go through P2 resolution and the P4.5 support-span check; they
  just start from a real identifier instead of a filename guess.
- **Marks are attention, not evidence — and not always the user's** (added 2026-09-14,
  user ruling R4). `--annotations` tags every mark with an origin: owner / named / tool /
  external / unattributed (the rule prints with the output). A pre-annotating tool that
  signs its marks is declared once in `invoke.annotation_tool_authors`; until then its
  signed marks read as `named`, never as `owner`. paper-distill imports them at ingest
  (`intake.marked[]`); this skill uses them only as pointers to where to look. Measured
  2026-09-14: 0 annotations and 114 child notes in this library.
- **Read pattern is copy-then-read.** The tool never opens the live database,
  so it works whether or not Zotero is running. Do not switch it to the local
  HTTP API on port 23119 — that would add a dependency on the app being open,
  for nothing.

## Zotero collection close-out (SKILL.md P5 points here)

Standing step for project literature waves. Every wave close-out appends the wave's
newly **READ** papers to the project's bib JSON (`references/<collection>-bib.json`;
item schema documented in `../scripts/zotero_ris_export.py`), then regenerates the RIS:

```
python ../scripts/zotero_ris_export.py <bib.json> \
    --collection-name "<Zotero collection>" --out-dir <project>/references
python ../scripts/zotero_ris_export.py <bib.json> ... --check     # same command, verify
```

- **What goes in:** papers only. Never vendor datasheets, patents, or press; a
  `[secondary]`-only citation stays out (it was never read). Datasheets and patents are
  real sources with real tiers (`credibility-rubric.md` §5b/§5c) — they just do not
  belong in a *paper* bibliography.
- The `--collection-name` **is** the project's Zotero collection name.
- The user refreshes Zotero via File → Import of the RIS. Re-import duplicates existing
  items — merge via Duplicate Items, or hand the user a delta RIS of only the new wave.
- **Never push via `localhost:23119`**: `/api/` is read-only and `/connector/saveItems`
  cannot target a named collection (verified 2026-08-31).
  **review-when**: Zotero ships a writable local API.

## Retrieval timestamps

A connector card carries `_fetched_at`. Record it for any value whose source
can change under the citation — legal status, family membership, a live
database record, any web page. A DOI'd journal article is stable and needs
none; a patent's legal status is not, and a claim about it is only true "as of"
a date. Format: `(EP1000000A1, ¶[0004]) [full] (retrieved 2026-08-26)`.

## When a connector is absent

Absent is not a blocker; unstated absence is. Say which connector was
unavailable, what coverage that costs, and route to the next rung —
`gaps` gets the entry, `search_trail` gets the substitution. This is the
existing degradation ladder in `search-sources.md`, with connectors as its
new top rung.
