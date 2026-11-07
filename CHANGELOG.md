# Changelog

All notable changes to this repository. Versions follow semantic versioning: minor = new capability,
patch = fix. Format after Keep a Changelog.

## [1.0.2] - 2026-11-07

Fixes found by four outside agents' reviews of v1.0.1 (one ran the controls on macOS).

### Fixed

- `verify/citecheck.py`: a whitespace-only `support_span` was "found" in every text; unreadable ledger
  lines and an empty ledger exited 0; a run folder without `run.json` was judged as a legacy run (WARN
  instead of FAIL on provenance). Each now fails; four selftest cases cover them (105 cases, 53/52).
- `verify/citecheck.py --selftest` no longer needs PyMuPDF: without it the 20 page-pointer cases are
  skipped and the tally line says so (before, K1k crashed on `import fitz`).
- `loop/runs.py register` refuses a run whose `citecheck.json` carries a FAIL (before, only the later
  `check` V8 reported it, after the run was already marked delivered).
- `verify/fetchsrc.py` follows redirects itself and judges every hop's host before sending it: a DOI
  resolver that redirects to a banned publisher no longer gets that request sent.
- `connectors/access_policy.py --selftest` restores `LSE_HOST_POLICY` instead of dropping it.
- `verify/run_controls.py` points `CLAUDE_CONFIG_DIR` at an empty scratch folder and `LSE_HOST_POLICY` at
  the shipped policy: K1a and K6 had read an installed `~/.claude`, so a fresh machine got 17/19 (16/19
  without PyMuPDF). The `good-run` fixture claim no longer carries a "± 3" its source does not have.
- Advisor statistics (`method-selection.md`, `tier-framework.md` §5.6): bootstrap is no longer the
  small-sample default (Hesterberg 2015); Welch by default, post-hoc tests (Tukey, Dunnett, Dunn + Holm),
  trend tests and mixed models added; AUC-PR no longer called better than AUC-ROC under imbalance
  (McDermott et al. 2024); sources listed in the file. Eval case 2's third assertion now requires a
  design-fitted follow-up test.
- `literature-search-extract` SKILL.md: P4.5 "narrows" failure mode #8 (it was "catches"); its
  description no longer routes to an unshipped dispatch file (declared edit E6). `verification-gate.md`
  case count updated.
- `docs/EVIDENCE.md`: the ALCE figure carries its ELI5 condition; PyMuPDF and isolation facts corrected;
  the threat model (careless agent, not an evasive one) stated; new enforcement rows; line refs remapped.
- `verify/unshipped_paths.txt`: five cited origin paths that were missing (`report_fp.py`,
  `exit_route.py`, `ops_health_nudge.py`, two paper-story files).

### Added

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
