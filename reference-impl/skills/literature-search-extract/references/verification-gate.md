# Verification gate — proving the deliverable against the documents

Companion to SKILL.md P4→P5. This is the step between "extraction is written"
and "deliverable ships". Tool: `../verify/citecheck.py`.

Everything the skill did before this file was **self-report**: the same model
that might fabricate a citation also decided whether the citation was
fabricated. That is not a check — it is the same judgement twice.

## The three failure modes, ranked by how hard they are to see

| # | Failure | Visible to a reader? | Caught by | Evidence it is real |
|---|---|---|---|---|
| F1 | Invented identifier — DOI/arXiv/page that does not exist | only if they click | identifier resolution (already in P2) | Tow Center/CJR 2025: across 1,600 queries, 8 AI search products cited wrongly >60% of the time; Gemini and Grok 3 returned more fabricated than correct links |
| F2 | **Real source, cited for something it does not say** | **no** | support-span check (this gate) | ALCE (arXiv:2305.14627): on ELI5 even the best systems "lack complete citation support 50% of the time" |
| F3 | Real source, real support, but the number lost its conditions | only to a specialist | P4 exactness rule + locator | SKILL.md failure mode #4 |

**F2 is the one to build for.** It survives every check the skill had, it is
invisible in the finished document, and it is actively *rewarded*: Search Arena
(arXiv:2506.05334, ICLR 2026, n=24,069 conversations) found people rate answers
higher for carrying more citations **even when the cited content does not
support the attributed claim**. Citation density reads as rigor. So a
deliverable that "looks well-cited" is evidence of nothing, including to its
own author.

## The move that makes F2 checkable

Whether a source *supports* a claim needs an entailment judgement, which a
script cannot make. But it becomes checkable if the writer must name the exact
span it relies on:

> A script cannot judge support. A script CAN check that the quoted span exists
> verbatim in the retrieved text.

That converts "trust me, it says so" into a falsifiable statement. A
reconstructed-from-memory quote fails immediately, with no model in the loop.
The residual judgement — does this real span actually entail this claim — stays
human, but the ledger prints claim and span side by side, so it takes seconds
instead of a re-read.

## The evidence ledger

One JSONL line per load-bearing claim, written **before** the gate runs:

```json
{"claim_id":"C1","claim":"Single-crystal Ag films reach L_spp = 200 um at 780 nm.",
 "source_id":"10.1126/science.1174655","cite_as":"Nagpal 2009","expect_year":2009,
 "expect_title":"Ultrasmooth patterned metals for plasmonics and metamaterials",
 "expect_authors":["Nagpal","Lindquist","Oh","Norris"],"expect_venue":"Science",
 "locator":"Fig. 3","access_tag":"full","access_route":"script",
 "support_span":"propagation length of 200 um at 780 nm","source_text":"sources/nagpal2009.txt"}
```

> **This example was itself a half-real citation until 2026-09-11.** Every earlier
> version of this file (and of `citecheck.py`'s docstring) attached "Nagpal 2009" to
> `10.1021/nl803811g` — a real DOI that belongs to Zuloaga, Prodan & Nordlander, *Nano
> Letters* 2009. v1's check (first surname + year) could not see it: the DOI resolved,
> the year matched, and nothing compared the title. v2's metadata check caught it on its
> first live calibration run. Real title, wrong DOI, right year — the exact shape the
> a university library's guide shows on its slide 23, sitting in the gate's own manual for a year.

The v2 fields are optional but load-bearing: a `[full]` row with a number and no
`expect_title`/`expect_authors` is a row the half-real check cannot run on (WARN on
legacy runs, FAIL on runs created from 2026-09-12). `access_route` is one of `script ·
webfetch · browser_headless · browser_user · local_pdf · user_provided · hand_to_user`;
`derived: true` (or a `[synthesis]` / `[converted …]` / `[read from figure]` marker in the
claim) says the numbers were computed rather than transcribed.

**The text itself comes from `fetchsrc.py`, never from memory.** `sources/<name>.txt`
is written by `python ../verify/fetchsrc.py fetch|local|paste --run <run> --name <name>`,
which consults the host policy first, records `sources/manifest.json` (route, host, HTTP
status, sha256, retention state) and refuses a banned or challenged host with a
`HAND-TO-USER:` line and exit 3. A text with no manifest entry, or whose sha256 no longer
matches, FAILs the provenance check: that is the fabrication vector v1 could not see —
an executor typing the "retrieved text" and passing the span check against their own words.

Two rules about the ledger itself, both learned the hard way elsewhere:

- **Persist before the gate runs.** The retrieved `source_text` and the ledger
  are written first, then checked. A gate must never be able to destroy the
  evidence it rejects — otherwise a failed run leaves nothing to diagnose and
  the re-run pays for the same fetches twice. They live in the run folder
  `<home>/<run_id>/` (`ledger.jsonl` beside `sources/`), which is the path this
  script is pointed at; its `--json` output is stored there as `citecheck.json`
  (`feedback-loop.md`, loop INV-1).
- **The ledger is not the deliverable.** It is the audit trail behind it. It
  stays behind the deliverable — persisted with the run (loop INV-1), never
  pasted into it (INV-2) — unless the caller asks for it.

## What runs, and what it may rule on

`python ../verify/citecheck.py ledger.jsonl`

| check | FAIL (determinable, closed) | WARN (forwarded, with its promotion trigger) |
|---|---|---|
| `identifier` | resolves nowhere (Crossref, arXiv, PubMed, then Semantic Scholar by DOI and by `expect_title`) | **doi-not-yet-active**: Crossref/doi.org 404 but Semantic Scholar carries the same title with the same DOI string (the library guide p24: a real IEEE OA article showed DOI NOT FOUND). Promotion: the confirmed record is older than one year, or the DOI strings differ → FAIL |
| `metadata` | first surname absent · year off by >1 · `expect_title` is not the resolved title · an `expect_authors` surname absent · `expect_venue` shares **zero** tokens with the resolved venue | venue overlap partial (`Nano Lett.` vs `Nano Letters`) · a `[full]` numeric row with no `expect_title`/`expect_authors` (FAIL from 2026-09-12) |
| `retraction` | the cited work carries a Crossref `updated-by` entry of type retraction and the row does not say `cite_as_retracted` | correction / erratum / expression of concern (quote the corrected value); `cite_as_retracted: true` rows |
| `support` | `support_span` absent from the stored text · no span on a text-bearing row · text not found | no `source_text` stored · `[secondary]` rows · licensed text still `pending-excerpt` (run `fetchsrc.py excerpt`) |
| `numeric` | a number in the claim appears **nowhere in the retrieved text** (the citation year in `cite_as` is exempt; `1,000` = `1000` = `1e3`) | the number is in the text but outside the span (extend the span) · the row is `derived` / carries a `[synthesis]`-class marker |
| `provenance` | no manifest entry for the text · sha256 differs from the manifest (edited after retrieval) · manifest says `hand_to_user` but a text exists · `user_provided` in **Mode 2** | `user_provided` in Mode 1 (source list prints `[user-provided passage]`) · the bytes differ from the manifest **only** in line endings — a pre-2026-09-12 `fetchsrc` on Windows hashed LF and wrote CRLF, so the content is intact. It clears only by writing the file again FROM THE RETRIEVAL — a fresh fetch, or `fetchsrc.py excerpt --redo` while the retained scratch copy still exists. Editing the stored bytes in place to silence it is the one change this check cannot tell from tampering, so an old run keeps its WARNs until someone re-derives it from upstream · no manifest at all on a legacy run (FAIL from 2026-09-12) |
| `access_route` | route not in the vocabulary · `hand_to_user` with a text-bearing tag · the host policy refuses that surface on that host (`browser_user` on IEEE Xplore) · row and manifest disagree | no route on a legacy run (FAIL from 2026-09-12) |
| `preprint` | — | an arXiv row whose Semantic Scholar record carries a publisher DOI: cite the published version (rubric §2) |
| `locator` / `access_tag` | no locator · tag not in the vocabulary | `[full]` with a tiny stored text (unless it is an excerpt) |

**Never ruled on:** whether an existing span actually entails the claim. The
gate says nothing it cannot demonstrate — a check that guesses is worse than no
check, because its silence gets trusted.

**Two named limits inside what it does rule on.** Both fail towards a miss, never
towards a false alarm, and both are pinned by a `--selftest` case so they stay
refutable instead of turning into folklore:

- `numeric` reads a **lone** digit as a measurement only when a unit-like token
  follows it, and "unit-like" is a heuristic — any word of ≤4 letters, minus a closed
  list of connectives and citation words. So a short word that is not a unit still
  passes as one (`Table 2 to 4 list`), and, the other way, the unit spellings that sit
  on that list (`2 in`) go unchecked. Multi-digit values are never gated this way.
  review-when and the replacement instruction live beside the rule in `citecheck.py`:
  swap in a real unit vocabulary — do not grow the list.
- `support` compares through the one normal form in `verify/spannorm.py`, which folds
  NFKC **per cluster**. A composition that spans two base characters therefore does not
  compose: conjoining-jamo Hangul and its precomposed spelling stay two strings, so a
  Korean span typed differently from its source would read as absent. Latin-script
  scientific text is unaffected; the trigger is a run whose sources are in a conjoining
  script.

Calibration is two-sided and shipped: `citecheck.py --selftest` runs **81 cases, 45
must-pass / 36 must-fail** (measured 2026-09-12 after the line-ending, normalizer and
range/list rounds; `--selftest` and `--selftest --offline` both green, 0 broken — the
count is what the run prints, not a number kept by hand). v1's 11 cases are kept unchanged; the v2 cases cover
the table above plus the QA regressions of the same day (a flipped sign is a different
number; `Fig. 3` is structure, `3 nm` is a value; `expect_authors` as a bare string is one
author; Müller/Muller fold; a DOI keeps its balanced `)`; the retraction sweep prints no
rate unless its two controls behave in the same invocation).
`--offline` swaps the resolvers for stubs shaped from live responses (Crossref
`updated-by` on Wakefield 1998, the p24 DOI on Semantic Scholar, arXiv's Atom feed), so
the calibration runs without a network; the live mode runs the same cases against the
real APIs and adds two informational **probes** — Crossref still returns `updated-by`
on the retracted work, and the p24 DOI is still 404 at Crossref — whose drift is the
review-when for this file. The doi-not-active fixture is stub-only in both modes on
purpose: the day IEEE registers that DOI, a live version would silently stop testing
the branch. The must-pass side is load-bearing — a gate that rejects everything scores
100% on a one-sided test. It distinguishes typography (PDF hyphenation, ligatures,
curly quotes, collapsed whitespace — must pass) from wording (`µm` where the source
wrote `um`, an added hedge — must fail). It does not guess intent.

**Retraction sweep over a whole bibliography:** `citecheck.py --retraction-sweep
<file>` (rubric §3b) — any file with DOIs in it, 1 request/s, one back-off on 429/503.

## When to run it

**Claim kind first, depth second.** The earlier version scoped the ledger by depth
alone, and that put the hole in the worst possible place: `quick` skipped the file, and
`quick` is what a single parameter lookup runs at — so the one number a user was most
likely to copy into their own work was the one claim in the whole pipeline that nothing
checked. Depth measures how much was searched; it says nothing about how load-bearing
the answer is. A one-source answer is not a low-stakes answer, it is a *thin* one.

| Trigger | Ledger scope | Overrides depth? |
|---|---|---|
| **Numeric claim** — any value the caller could act on, copy, or compute with | one row, always | **yes**, `quick` included |
| **Disputed claim** — sources conflict, or the claim is the one the caller is deciding on | one row per position | **yes**, `quick` included |
| `quick`, everything else | skip the file; still resolve every identifier before citing (P2 rule, unchanged) | — |
| `standard` | adds all load-bearing claims | — |
| `exhaustive` | every extracted item; the ledger is part of the PRISMA record | — |
| any depth, Mode 2 | a `[full]`/`[partial]` claim returned to a caller as fact gets a row — a downstream skill cannot re-check what it did not retrieve | yes |

**Why narrowing rather than softening.** The affordability worry is real and was
recorded before this change (`literature-search-extract-FUTURE-WORK.md` B4: an
unaffordable gate gets skipped silently, and silence still reads as a pass). The answer
is to shrink the *set of claims* the gate covers, never the *strength* of what it checks
on them. A numeric-and-disputed-only ledger at `quick` depth is typically one to three
rows — cheap enough that skipping it saves nothing worth having.

**Still measure it.** B4 stays open until a real `standard`-depth run reports the actual
cost of writing rows. If rows-per-run turns out unaffordable even under this narrowing,
the next move is still narrowing (numeric only), not weakening the span check.

## Reading the result

A FAIL is not a style note. That claim may not ship as cited. The repairs, in
order of what is usually true:

1. **Span not found** → most often the quote was rebuilt from memory. Go back to
   the stored text, find what it actually says, and rewrite the claim to match
   it. If the text does not support the claim at all, the claim is deleted and
   the target becomes a `gaps` entry. Deleting a claim is a valid outcome.
2. **Identifier does not resolve** → do not "fix" it by finding a nearby real
   DOI. Re-locate the source from scratch, or drop it.
3. **Metadata conflict** → the wrong source got attached to the right claim.
   Check whether other rows share the mistake.
4. **Tagged `[full]`, tiny stored text** → the tag was aspirational; downgrade
   it and re-check what the claim rests on.
5. **Number in the claim, nowhere in the text** → the value was transcribed from
   memory or from another paper. Re-read the locator; if the paper carries a
   different value, the claim changes; if it was computed, say so (`derived: true`)
   and show the arithmetic beside the claim.
6. **Half-real citation** (title/author/venue contradiction on a resolving DOI) →
   the DOI belongs to another paper. Re-locate the intended paper by title through
   Crossref `query.bibliographic` or Semantic Scholar; never keep the DOI because it
   "resolves".
7. **doi-not-yet-active** → not a fabrication verdict. Confirm on the publisher page
   or the library discovery layer, cite with the title + venue + the DOI as printed,
   and note the confirmation channel in `search_trail`.
8. **Retracted** → drop the claim, or cite the work AS retracted with the notice DOI
   (`cite_as_retracted: true`) when the retraction itself is the point.
9. **Provenance FAIL** → the text under that name was not produced by `fetchsrc.py`
   (no entry, edited after fetch, or refused host). Re-fetch through the instrument;
   if the host is banned, the route is hand-to-user and the user's passage enters as
   `user_provided`, never as a fetched text.
10. **Access-route refused by the policy** → the fetch was made through a surface the
    host does not grant. The text cannot be used; the row becomes a `gaps` entry and
    the incident is a rule breach to report, not a technicality to relabel.

## The same discipline, turned on this skill's own documents

P4.5 stops an unverified number reaching a deliverable. Nothing was stopping one
reaching this skill's **own** files — and one did:
`literature-search-extract-FUTURE-WORK.md` said
`SKILL.md` was "261 lines", true on 2026-07-12, false from 2026-07-19, unnoticed
for five weeks, then used as a baseline for arithmetic that produced a second
wrong number. A gate that only faces outward is half a gate.

```
python ../verify/staleclaim.py            # FAIL = a line-count claim that is now false
python ../verify/staleclaim.py --selftest # 8 cases, 5 must-pass / 3 must-fail
```

**Coverage is narrow on purpose, and stating the limit is part of using it.** It
re-measures only *line counts of named files*, because that is the one claim
shape a script can settle with no judgement. `116 PDFs`, `155 attachments`,
`47% from the last three years` are not re-derivable from the text, so they get
a WARN at most — for those the discipline is the convention, not the checker:
**a quantity is written as value + measurement date + the command to re-take it,
and one without a date is treated as expired.**

**Why the calibration is not decoration here.** Version 1 of that checker passed
every synthetic case and *missed the real bug*, because a bound word five
characters away from a measurement ("261 lines, over the 250 line cap") vouched
for it. It was only caught by replaying the actual five-week-old file from git
and demanding a FAIL. Both shapes are now permanent regression fixtures. The
lesson generalises: **a green self-test on cases you invented is not evidence
the instrument works on the case you built it for** — replay a real failure, or
you have tested your imagination.

## Set-level checks the script cannot do

Run these by hand before P5, and state the result:

- **Conflicts preserved?** Two sources disagreeing is a finding. The ledger
  holds both rows; `confidence` reports both positions with locators. Never
  average, never quietly pick one.
- **Citation-count illusion.** Search Arena's finding applies to the author too:
  more rows do not mean better support. One `[full]` row with a verified span
  beats five `[abstract]` rows.
- **Single-cluster evidence.** Run `credibility-rubric.md` §6 — one group, one
  citation bubble, one language is not consensus.
- **Retrieval currency.** For any claim whose source can change under the
  citation (legal status, a live database record, a web page, a moving standard),
  record the retrieval date. A stable DOI'd article needs none.
