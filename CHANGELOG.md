# Changelog

All notable changes to this repository. Versions follow semantic versioning: minor = new capability,
patch = fix. Format after Keep a Changelog.

## [1.0.1] - 2026-11-07

### Added

- `docs/assets/flow.build.mjs`: the README flow diagram as a rendered reader figure (`flow.zh-TW.png`,
  `flow.en.png` and their SVGs). Every node and line maps to a SKILL.md passage (`--mapping`, copied into
  `docs/DEVELOPER.md`); model asserts for endpoints, diagonals, arrowhead run, edges through nodes or group
  labels, crossings, parallel runs and chip placement, with six deliberately broken controls (`--selftest`).
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
