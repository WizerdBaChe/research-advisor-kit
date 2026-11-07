# Third-party notices

Checked on 2026-11-07. Everything else in this repository is the author's own work (see `LICENSE`,
`LICENSE-DOCS`). Facts below were checked against the shipped files of `reference-impl/` and against the
installed package metadata on the machine that produced `verify/controls_run.txt`.

## Vendored code and copied text

None found. A search of `reference-impl/` for licence headers, SPDX identifiers, "vendor", "adapted from"
and "copied from" returned no vendored library and no code copied from another project. The only
imports outside the Python standard library are the optional or test-time packages in the table below,
which you install yourself and which are not included here.

## One short quotation from a publisher's terms of use

`reference-impl/hooks/literature-host-policy.json` (the `ieeexplore.ieee.org` row and the
`agent_banned` class description) quotes one sentence of the IEEE Xplore Terms of Use, Institutional
Subscribers, list of prohibited uses: using robots or intelligent agents to "access, search and/or
systematically download" any portion of IEEE Xplore. It is quoted as the licence basis for denying agent
access to that host; the file records that the terms were read on 2026-09-10. The wording belongs to
IEEE; check the current terms before relying on the quotation (the policy's `review_when` line lists "IEEE
changes its Terms of Use"). `reference-impl/rules/literature-access.md` paraphrases the same term and
quotes only the three verbs.

## Licences named as facts about hosts

The same policy file names the content licence of some open hosts (for example CC BY-SA 4.0 for an online
encyclopedia, CC BY-NC-SA 3.0 and CC BY-NC-ND 4.0 for two web-edition handbooks, CC0 for an open scholarly
index) as the `licence_basis` of a row. These are facts recorded so the agent knows what it may retain; no
content from those hosts is included in this repository.

## Test fixtures

- `reference-impl/skills/literature-search-extract/loop/tests/fixtures/good-run/` and `bad-run/`: the
  retrieved text ("Park 2022"), the DOI (`10.0000/fake.2022.234`, a reserved non-existent prefix) and the
  ledger rows are fictional, written for this kit.
- `reference-impl/skills/scientific-research-guide/evals/fixtures/`: the `routing-collision` and
  `frontmatter-drift` domain trees describe fictional apparatus ("the delta rig is a fictional apparatus");
  `research-state.example.md` is an example tracker written by the author.
- Bibliographic strings in the identifier-normalisation tests and selftests (for example real DOI strings,
  a 1997 paper title, a manufacturer datasheet number) are citations used as
  parser inputs. A bibliographic citation is a fact, not the cited work's expression; no licence is claimed
  for them, and none of the cited works is reproduced. The retraction control in `verify/citecheck.py`
  uses the identifier of a well-known retracted article against offline stub data; no network response is
  stored.

## Runtime dependencies (installed by you, not shipped)

| package | used by | licence (from its installed metadata, 2026-11-07) |
|---|---|---|
| idutils 1.7.0 | `loop/idkey.py` identifier validation (required by K1e and K2) | BSD-3-Clause (Invenio project) |
| jsonschema 4.26 | `loop/runs.py` run-record validation (required by K2) | MIT |
| pytest 9.1 | `loop/tests/` (K2) | MIT |
| PyMuPDF 1.26 | PDF text in normal use (`fetchsrc.py`, `pagestore.py`, `citecheck.py` page pointers); no acceptance control needs it | **GNU AGPL-3.0 or Artifex commercial licence** - read it before you distribute anything built on it |

| Pillow 12.3 | `connectors/textbook_ocr.py` page images for OCR (optional tool) | MIT-CMU (HPND) |
| pypdf | `verify/fetchsrc.py` fallback PDF text when PyMuPDF is absent (guarded import, optional) | BSD-3-Clause |
| PyYAML | `loop/tests/test_runs.py` one test (guarded import, skipped without it) | MIT |
| Playwright + Chromium | `docs/assets/build_assets.py` only (regenerating the README images; not needed to use the kit) | Apache-2.0 (Playwright); Chromium BSD-3-Clause and others |

Most call sites import PyMuPDF lazily inside functions (as `fitz`); the two textbook tools
(`connectors/textbook_index.py`, `connectors/textbook_ocr.py`) import it at module level and require it. The
repository does not include or modify PyMuPDF. `connectors/textbook_ocr.py` also calls the Windows
`Windows.Media.Ocr` system API (Windows only). The README images are rendered with system fonts by family
name (Noto Serif TC, Cascadia Mono, Consolas); no font file is shipped. The kit also calls public metadata APIs (Crossref, Semantic Scholar, arXiv, NCBI) at
run time under their own terms; `reference-impl/hooks/literature-host-policy.json` records the basis and
the per-host caps for each.
