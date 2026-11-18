# Changelog

All notable changes to this repository. Versions follow semantic versioning: minor = new capability,
patch = fix. Format after Keep a Changelog.

## [1.1.0] - 2026-11-18

New capability in the librarian and two hook changes, refreshed from the origin: 19 of the 96 files shipped in
v1.0.2 changed (77 are byte-identical) and 5 files are added (`apabib.py`, `notice_budget.py`, three test files),
101 in all. Declared edits E7-E10 and one screen allowance are new, see `docs/BUILD-SPEC.md` §9.

### Added

- Four whole-corpus output formats in `output-format-catalog.md` / `output-templates.md` (twelve in all):
  assumption census, method census, concept lineage, researcher genealogy. They need a gathered corpus of at
  least 5 sources and describe that corpus, never the field. `tier-framework.md` §5 points at them.
- `verify/apabib.py` (+ `loop/tests/test_apabib.py`): APA 7 reference entries generated from DOIs / arXiv ids
  from registry records (Crossref, DataCite, arXiv API) through the shipped host policy; an id whose record
  cannot be fetched is printed as needs-manual-check with no entry body (exit 3); `--run` diffs the records
  against a run's ledger (author order, year, title).
- `loop/runs.py register` / `inbox.py ingest --apply`: a measured stderr notice when the central bibliography lacks
  the run's sources, with the refresh command; `register --export-bib` runs it at once (networked, slow).
  `scripts/zotero_ris_export.py` fills a missing RIS author or year from the registries and keeps both papers
  when two sources share a cite id (`loop/tests/test_bib_stale.py`, `test_ris_fill.py`).
- `connectors/textbook_index.py`: cleaner exports, a table-of-contents page check, a typed `toc.json` sidecar,
  figure extraction with captions read from the figure's bottom edge. `connectors/textbook_ocr.py`: rapidocr and
  VLM engines next to the Windows engine, chosen per page class, and a per-page text-layer decision. Not
  exercised here (they need a textbook library); `ocr_bench.py` and its answer file are not shipped.
- `hooks/notice_budget.py`: once-per-session budget for `literature_host_guard.py` notices; fail-open (a missing
  or broken budget prints every notice, as before).
- `verification-gate.md`: set-level check "unknown proper nouns queried, not forwarded" (names the origin's term-log
  tool, not shipped), and the reference-list tool section.

### Changed

- `secret_file_guard.py` no longer gates a remote URL path (`curl https://host/.env`; `file://` and `C://x/.env` still
  deny) nor the JS property access `el.dataset.key` (a bare `dataset.key` still denies). Two-sided cases:
  must-deny 50 -> 57, must-pass 53 -> 57.
- `literature_host_guard.py`: its notices pass the notice budget (one per host per session); an unlisted-script row is
  written only when the call runs (a later deny in the same call leaves no row and no count), and `noticed` is set
  only for a notice that printed. Tests N-13 to N-15.
- `literature-search-extract` SKILL.md: four detail blocks moved to `references/` (host access policy, central
  bibliography freshness, reference-list tool, recall-check rationale); line references in `docs/DEVELOPER.md` and the
  flow diagram's source map re-pointed (several were already two lines off in v1.0.2).
- `loop/tests`: 54 -> 76 passing, 2 skipped. `docs/EVIDENCE.md` gains four enforcement-map rows; its line numbers are
  refreshed (14 moved, 0 lost).

### Fixed

- `test_bib_stale.py` removed `LSE_RUN_HOME` / `LSE_BIB_HOME` after each case even when the caller had set them, and
  `test_ris_fill.py` needed a run home it did not set: with the variables preset (as `verify/run_controls.py` sets
  them) 3 cases failed. Declared edits E8, E9 (the origin keeps the defect until its own fix lands).
- `test_apabib.py`'s two live-registry cases ran whenever the machine was online, so K2's count depended on
  connectivity and a control touched the network; they now need `LSE_LIVE_TESTS=1` (E10).

### Limits (new)

- `runs.py register` calls the origin's research-graph tool (`tools/research-graph/rg.py`) after a register when it is
  present; it is not shipped, so here the call returns at once and the genealogy table is built by hand. E7 says so in
  `tier-framework.md`. The unshipped paths the text cites are listed in `verify/unshipped_paths.txt` (class `origin-tool`).

## [1.0.2] - 2026-11-07

Fixes found by four outside agents' reviews of v1.0.1 (one ran the controls on macOS).

### Fixed

- `verify/citecheck.py`: a whitespace-only `support_span` was "found" in every text; unreadable ledger
  lines and an empty ledger exited 0; a run folder without `run.json` was judged as a legacy run (WARN
  instead of FAIL on provenance). Each now fails; four selftest cases cover them.
- `verify/citecheck.py --selftest` no longer needs PyMuPDF: without it the 20 page-pointer cases are
  skipped and the tally line says so (before, K1k crashed on `import fitz`).
- `verify/citecheck.py --json` keeps stdout pure JSON (diagnostics go to stderr), so `--json > citecheck.json`
  parses; a ledger with a UTF-8 BOM (PowerShell) no longer makes row 1 unreadable. Selftest: 107 cases, 53/54.
- `verify/fetchsrc.py` never opens a url whose scheme is not http or https (`file:`, `data:`), neither the
  first one nor a redirect hop; `loop/runs.py check` reads a BOM ledger like citecheck does.
- Python 3.12 or newer is stated (only 3.12.7 was run); three f-strings that 3.11 cannot parse are rewritten.
- `loop/runs.py register` refuses a run whose `citecheck.json` carries a FAIL (before, only the later
  `check` V8 reported it, after the run was already marked delivered).
- `verify/fetchsrc.py` follows redirects itself and checks every hop's scheme and banned hosts before sending it (per-run caps still
  count only the final host): a DOI
  resolver that redirects to a banned publisher no longer gets that request sent.
- `connectors/access_policy.py --selftest` restores `LSE_HOST_POLICY` instead of dropping it.
- `verify/run_controls.py` points `CLAUDE_CONFIG_DIR` at an empty scratch folder and `LSE_HOST_POLICY` at
  the shipped policy: K1a and K6 had read an installed `~/.claude`, so a fresh machine got 17/19 (16/19
  without PyMuPDF). The `good-run` fixture claim no longer carries a "± 3" its source does not have.
- Advisor statistics (`method-selection.md`, `tier-framework.md` §5.6): bootstrap is no longer the
  small-sample default (Hesterberg 2015); Welch by default, post-hoc tests (Tukey, Dunnett, Dunn + Holm),
  trend tests and mixed models added; AUC-PR no longer called better than AUC-ROC under imbalance
  (McDermott et al. 2024); Games-Howell after a Welch ANOVA; sources listed in the file. Eval case 2's third assertion now requires a
  design-fitted follow-up test.
- `literature-search-extract` SKILL.md: P4.5 "narrows" failure mode #8 (it was "catches"); its
  description no longer routes to an unshipped dispatch file (declared edit E6). `verification-gate.md`
  case count updated.
- `docs/EVIDENCE.md`: the ALCE figure carries its ELI5 condition; PyMuPDF and isolation facts corrected;
  the threat model (careless agent, not an evasive one) stated; new enforcement rows; line refs remapped.
- `verify/unshipped_paths.txt`: five cited origin paths that were missing (`report_fp.py`,
  `exit_route.py`, `ops_health_nudge.py`, two paper-story files).

### Added

- `docs/DESIGN-IDS.md`: the INV-n and D-Ln ids the run-store code cites, defined in place (their design
  file is not shipped). Eval case 2 also fails an answer that offers a bootstrap as the small-n first choice.
- `verify/requirements.txt`; README "try the citation check in 30 seconds" with no agent, no key, no
  network; the agent install prompt pins the release tag.

## [1.0.1] - 2026-11-07

### Added

- `docs/assets/flow.build.mjs`: the README flow diagram as a rendered reader figure (`flow.zh-TW.png`,
  `flow.en.png` and their SVGs). Every node and line maps to a SKILL.md passage (`--mapping`, copied into
  `docs/DEVELOPER.md`); model asserts for endpoints, diagonals, arrowhead run, edges through nodes or group
  labels, crossings, parallel or overlapping runs and chip placement, with seven deliberately broken controls
  per language (`--selftest`, each control matched only by its own failure message). A papers-only request is
  drawn with its own exit (the booklist goes to you without a stage diagnosis).
- `docs/assets/build_assets.py --only flow`: renders the two SVGs to PNG and checks in the browser that
  every text sits inside its node, with a known-bad control.

### Changed

- README.md and README.en.md show the rendered flow; the mermaid flow moves into a collapsed text version.

## [1.0.0] - 2026-11-07

First public release.

### Added

- `reference-impl/skills/scientific-research-guide/`: the research advisor (7-tier framework, gates A-E,
  six-part diagnosis, method-selection aids, deliverable templates, `research-state.md` continuity) with
  its domain-maintenance tools (`profile-lint.py`, `routing_sim.py`, `eval-impact.py`,
  `profile_frontmatter.py`), `domains/_template.md`, `domains/domain-expansion-guide.md` and an empty
  `domains/_routing.md`.
- `reference-impl/skills/literature-search-extract/`: the literature service (P1-P5 pipeline, request and
  result contract, evidence ledger, `verify/citecheck.py`, `verify/fetchsrc.py`, run store under `loop/`,
  connectors, references).
- `reference-impl/hooks/`: `literature_host_guard.py` with `literature-host-policy.json`,
  `secret_file_guard.py`, `deny_receipt.py`, `_lib/roots.py`, `_lib/telemetry.py` and their tests;
  `reference-impl/rules/literature-access.md`.
- `verify/run_controls.py`: acceptance controls K1-K9 (19 checks), each two-sided with both asserted
  values printed; `verify/controls_run.txt` is the transcript of the release run.
- `docs/BUILD-SPEC.md`, `docs/EVIDENCE.md` (measured results, origin records, enforcement map),
  `THIRD_PARTY_NOTICES.md`, `verify/unshipped_paths.txt`.

### Changed relative to the origin (declared edits, see `docs/BUILD-SPEC.md` section 9)

- The arXiv polite User-Agent contact address is read from `LSE_ARXIV_CONTACT` (opt-in, empty means no
  contact string is sent at all).
- Lab, institution and library names in provenance lines and in the host policy are generalised; private
  folders become `<NOTES_VAULT>`, `<TEXTBOOKS>` and `~/Zotero/storage`; dates and lesson ids are kept.
- Not shipped: every domain profile, the citation inbox data, the domain evaluation cases (the five
  domain-free cases 1, 2, 3, 5, 11 stay), `STATUS.md`, the personal PDF index and caches.
