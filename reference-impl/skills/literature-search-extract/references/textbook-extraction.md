---
xi: 1
what: 從本機教科書庫（<TEXTBOOKS>）定向抽取的規則——按目錄導航、印刷頁碼定位子、掃描件的 OCR 側檔與排除頁、書末索引當詞彙層、出處欄位寫法 (rules for targeted extraction from the local textbook library: navigate by TOC, printed-page locators, OCR sidecars with excluded pages, book-end index as a vocabulary layer, provenance field)
tags: [literature-search-extract, textbooks, local-corpus, connector, extraction]
aliases: [教科書抽取規則, textbook extraction rules, textbook_library rules]
date: 2026-09-13
status: live
---

# Textbook extraction — rules for the `textbook_library` connector

Machine-read; English by contract. Reached from `search-sources.md` §Local PDF library
(textbooks) and from the `textbook_library` row in `connectors/registry.json`. SKILL.md
P1→P5 is unchanged: this file only says what a BOOK changes about P2 routing, P3 access
tags, P4 locators and P5 provenance. Positioning and the measured inventory:
`~/.claude/references/lse-textbook-corpus-positioning-eval_2026-09-13.md`.

## 0. Why a book is not a long paper

A textbook is read for **what the field already agrees on** — definitions, canonical
derivations, typical ranges, the vocabulary a question should be asked in — while a paper
is read for one new claim. Three consequences, each a rule below: the section is found
through the book's own TOC and index, never by paging (§2); the locator is the PRINTED page
or section, which survives a reader change and an edition note (§3); and the deliverable
quotes a definition or a number with its conditions, never a digest of a chapter (§4).
A whole-book summary is failure mode #3 with a bigger surface — it is never pre-built.

## 1. What the connector provides (run `--stats` for the live numbers)

- `connectors/textbook_index.py --build` writes `<root>\library.json` and one
  `<book>.index.json` beside every PDF: identity (only what the file itself states —
  ISBN/edition/year from metadata or the copyright page, with `found_in`; **empty means
  not found, never fill it from memory**), TOC → PDF page, printed-page calibration,
  the parsed book-end index (glossary), OCR status.
- `connectors/textbook_ocr.py` gives a scanned book (no text layer) a `<book>.ocr\`
  sidecar: one text file per ACCEPTED page and a manifest listing every page's status.
  **Pages the gate excluded (`skew`, `garbage`, `error`) have no text and are named in
  `excluded_pages`** — user ruling 2026-09-13: wrong data is worse than no data. A
  question that lands on an excluded page is a `gaps` entry ("page N excluded by the OCR
  gate: <reason>; hand-to-user"), never a guess from neighbouring pages.
- `--search <terms>` ranks book titles, TOC entries and index terms; `--locate <book>
  --printed <n>` turns a printed page into a PDF page; `--export <book>` writes one
  Markdown file per chapter for the user's own secondary-analysis tools.
- `connectors/local_find.py "<regex>"` searches the RUNNING TEXT of every chapter export
  and of earlier literature runs (`NOTES_VAULT/literature/**.md`) in one call. Each textbook
  hit carries edition, chapter file and the nearest `[p. N]` marker, flagged when the
  book's calibration is unreliable, its markers restart per chapter (read the page
  header), or the text is OCR (formulas from the page image). A book without an export is
  named in the summary line: run `--export` for it.

## 2. P2 — route and navigate

1. Route here when `source_types` includes `textbooks` and the need is a definition,
   a canonical formulation, a typical range or a vocabulary — `references/
   extraction-playbook.md` §0 says which needs live in a book. Web channels
   (`search-sources.md` §Google Books) stay the discovery path for a book the library
   lacks; the library never proves a canonical text does not exist.
2. `--search` first for a topic (TOC, index terms); `local_find.py` first for a fact stated
   in running text (a range, a value, a phrase) and to see whether an earlier run already
   holds it. A hit is a **place to open**, not a source yet: open the TOC entry's
   page range (or the index term's pages) and read those pages only, ≤20 pages per Read.
3. Recall control (SKILL.md P2) applies: before "the library has nothing on X", check that
   a term you know the book covers is found by the same query.

## 3. P3/P4 — access tag and locator

- Access tag: `[full]` for a text-layer page and for an OCR page with status `ok`;
  `[partial]` for an OCR page with status `sparse` (figure/blank page — the picture is
  unread); an excluded page is **not accessible** (gap, see §1).
- **Locator = edition + section + printed page**, e.g. `(Saleh & Teich, 3rd ed.,
  §3.1-A, p. 80)`. The PDF page index lives in the row's page pointer (§3a), never in a
  second field. The printed page comes from the calibration (`pdf_page = printed + offset`); when
  the book's calibration status is `unreliable` (agreement below 0.6 — per-chapter
  numbering, two-offset scans), read the number off the page header and say so.
- Edition rules from `credibility-rubric.md` §5 bind: cite the edition read; when the
  identity block has no edition/ISBN, the citation says "edition not stated in file" and
  the gap names it — a later human fills it from the physical book, not the model.
- OCR text is evidence for WORDS, not for equations or figures: a formula quoted from an
  OCR page is re-read from the page image (pymupdf `get_pixmap`) before it enters a
  ledger row; the support span records `ocr` as its route.
- Quote short; paraphrase by default; a page image never enters a deliverable.

## 3a. Evidence is a page pointer, never a copied excerpt (2026-10-20)

- **A ledger row cites PDF pages:** `source_text: "textbook:<library id>#p=N"` (or `#p=N-M`)
  for a library book, `"pages:<pdf path>#p=N"` for any other PDF (a lecture). `p` is the
  PDF page index; the printed page stays in the `locator`. Layout and rules:
  `verify/pagestore.py` (the one copy); citecheck reads pointers in their own branch.
- **The row carries what it relied on:** `page_sha256` (16 hex per cited page) and
  `pdf_sha256` (16 hex), stamped by the writer when the row is first written and never
  re-stamped. A page that changes afterwards (re-OCR, `--redo`, a hand edit) FAILs the row
  until a person re-reads it; a replaced PDF is a WARN. A renamed book is found again by
  `pdf_sha256`.
- **Page text exists once:** a text-layer PDF gets `<pdf stem>.pages\NNNN.txt` written once by
  `textbook_index.py --pages` (`--pdf <path>` for a lecture; `--verify` reports drift,
  `--redo` rewrites and keeps the old page in `previous\`); an OCR book is read from its
  `.ocr\text` in place. Copying page text into a project folder is the defect this replaces.
- **The numeric check settles a number missing from the span against the whole document,**
  not just the cited pages: the source of a pointer is the book.
- **`.chapters` exports stay a reading aid** for the user's own tools (user ruling
  2026-10-20: no converted reading layer); they are never cited.

## 3b. Source admission: a source is screened before it is cited (user suggestion 2026-10-20)

- `pagestore.admission(book)` grades every library book `citable` · `limited` ·
  `proposed-reject` · `rejected`. citecheck FAILs a row on a `rejected` source and WARNs
  on the others' reasons; ct.locate_page never places a span on a rejected source.
- **Measured limits are derived at read time, never stored:** OCR text limits NUMBERS
  (confirm on the page image); an edition/ISBN neither `textbook_index` found nor a person
  read off a page limits the row ("the edition is the file name's claim").
- **What needs a reader lives in `<TEXTBOOKS root>\admission.json`:** `identity_confirmed`
  (the page and the words read), `duplicate_of` (a copy of another book: the canonical
  book is cited, the copy only when it alone carries the passage), `status` + `reason`.
  `rejected` takes a user ruling; a model proposes `proposed-reject`.

## 4. P5 — provenance field for a textbook row

User ruling 2026-09-13: for this source class the access/licence field states
**provenance only** — which book, which edition, which place:
`access: local textbook copy · <book id> · <edition or "edition not stated">
· printed p. N (pdf N) · route: text-layer | ocr`. No route chain or licence basis is
required beyond that. The redistribution limit of `rules/literature-access.md` still
holds: the deliverable carries the quote, the number and the locator, not the pages.

## 5. The book-end index as a vocabulary layer (user ruling 2026-09-13, Q4)

The parsed glossary is a keyword layer beside the three a database exposes (author
keywords, controlled vocabulary, index terms — `search-sources.md` §Query building) and a
snowball seed: the terms a canonical text indexes are the terms the field's papers use.
Use: seed the vocabulary ledger's synonym column from `--search <concept>` INDEX hits
before the first database query; log `textbook index (<book>)` as the layer's origin in
`search_trail`. Limits: the parser is a line-shape heuristic — `library.json` prints
`parse_share` per book; a book below 0.5 has a noisy glossary and its terms are hints only.

## 6. What this connector never does

- Never rewrites or "cleans" OCR text; never fills an excluded page.
- Never builds chapter summaries or concept notes — those are per-question LSE runs, and
  their organised output goes to the knowledge vault under its own rules (user ruling
  2026-09-13, Q2: `<TEXTBOOKS>` is the raw shelf; Obsidian is the reader).
- Never renames or modifies a PDF; a renamed book is re-linked by the sha256 in its
  sidecar manifest and index file.

review-when: `textbook_ocr.py` or `textbook_index.py` changes a schema; the library root
moves; a calibration status flips for a book already cited (re-check its printed-page
locators); the user changes the provenance-field ruling.
