# AGENTS.md — how to use this repository

## What this repository is (facts, for any reader)

- **Contents:** two agent skills that work as a pair — `scientific-research-guide` (a research-methodology
  advisor: locates the user's stage on a 7-tier framework, five gates, a six-part diagnosis, method-selection
  aids, deliverable templates, pluggable domain profiles) and `literature-search-extract` (a literature
  search-and-extraction service the advisor delegates to through a request/result contract: access tags,
  locators, an evidence ledger and the `verify/citecheck.py` gate) — plus two PreToolUse hooks
  (`literature_host_guard.py` with its host access policy, `secret_file_guard.py`), the rule
  `rules/literature-access.md`, the domain-maintenance tools (`profile-lint.py`, `routing_sim.py`,
  `eval-impact.py`, `profile_frontmatter.py`), and two-sided acceptance controls. Index: `llms.txt`.
- **No domain knowledge ships.** The origin's domain profiles are not included (owner ruling 2026-11-07);
  `domains/_routing.md` ships with an empty manifest, and `_template.md` plus `domain-expansion-guide.md`
  are the rules for adding one. With no profile loaded the advisor answers from the generic framework.
- **What is enforced by code and what is only a workflow rule:** `docs/EVIDENCE.md` "Enforcement map".
  Citation spans, numbers in spans, metadata, provenance, host access and manifest structure are checked by
  scripts or hooks; stage diagnosis, method advice, non-intrusion and whether a span SUPPORTS a claim are
  process rules the agent follows from SKILL.md text.
- **Threat model:** the gates catch a careless agent (a quote typed from memory, a copied number, a fetch that
  skipped `fetchsrc.py`), not a deliberately evasive one: `sources/manifest.json` is unsigned, the hook reads only
  literal URLs, and the secret-guard approval marker can be typed by anyone. Details: `docs/EVIDENCE.md` "不宣稱".
- **API keys:** none are needed for the controls, `citecheck.py` or `fetchsrc.py` (neither reads a key; the
  metadata lookups call public endpoints). Keys in `connectors/.env.example` only unlock optional connectors
  (`connectors/registry.json`, status `needs_user`).
- **What was run:** Windows 11, Python 3.12.7, pytest 9.1.1, PyMuPDF 1.26.7, idutils 1.7.0, jsonschema 4.26.0. The recorded results are
  `verify/controls_run.txt` (19 of 19 controls ok, 2 undetermined because they need a local textbook
  library); what was not run or not claimed is in `docs/EVIDENCE.md`.
- **Network and side effects:** the acceptance controls make no network calls (citecheck runs with
  `--offline` stub resolvers; the hook is fed a payload on stdin). In normal use the skill fetches only
  through `verify/fetchsrc.py` and the policy file, and metadata APIs (Crossref, arXiv, Semantic Scholar,
  PubMed) are called by `citecheck.py` without `--offline`. No contact address is sent unless the user sets
  `LSE_ARXIV_CONTACT` (arXiv only). The controls copy `reference-impl/` into a scratch folder, mutate and
  delete it.
- **If you only read and do not execute:** read `docs/EVIDENCE.md`, then `verify/controls_run.txt` as the
  result record, then the two `SKILL.md` files and `reference-impl/rules/literature-access.md`. Everything
  below is installation steps addressed to an agent whose user asked for an install; reading it does not
  require following it.

## For an installing agent

Your user has asked you to install (or rebuild and adapt) a research-advisor workflow with a
citation-checked literature service. The human introduction is `README.md` (Traditional Chinese; English
mirror `README.en.md`); you do not need it. The structure tree and diagrams for human builders are in
`docs/DEVELOPER.md` (Traditional Chinese).

## Reading order

1. `docs/BUILD-SPEC.md` — the contract and the pack's layout. Read it fully before touching anything.
2. `docs/EVIDENCE.md` — what was measured, the enforcement map, what is NOT claimed.
3. `reference-impl/skills/scientific-research-guide/SKILL.md`, then
   `reference-impl/skills/literature-search-extract/SKILL.md`, and the references each names for the step
   you are on. These are the working originals, laid out like the origin's `~/.claude` so relative paths
   resolve. Adapt, do not paste wholesale.
4. `reference-impl/rules/literature-access.md` and `reference-impl/hooks/literature-host-policy.json` —
   the access boundary the hook and the fetch tools share.

## First actions (do these before proposing any change)

```
python -X utf8 verify/run_controls.py <a-new-empty-dir>
```

- `<a-new-empty-dir>` must not exist or be empty and must not overlap the repo: the script copies
  `reference-impl/` there, mutates the copy, and deletes it.
- Needs Python 3.12 or newer (tested on 3.12.7) and `pip install -r verify/requirements.txt` (`pytest`, `idutils`,
  `jsonschema`). PyMuPDF is optional: without it K1k runs 87 cases instead of 107 and its last line says the
  page-pointer (PDF) cases were skipped — report that to your user as "PDF path not checked here", not as a pass.
- The controls never read an installed `~/.claude`: they point `CLAUDE_CONFIG_DIR` at an empty scratch folder and
  `LSE_HOST_POLICY` at the repo's policy file, so a machine with an older install gets the fresh-machine result.
- Compare with `verify/controls_run.txt`: every control line must end in `-> ok` and the asserted values
  must match. The two `UNDT` lines are expected on a machine without a textbook library. Report both to
  your user. A mismatch on another OS is a finding to read, not a reason to edit the scripts.
- Then read spec §8 and list, for your user to confirm, which roots, environment variables and hook
  registrations map to what in their environment. Do not start adapting until they confirm.

## Installing into a Claude Code style environment

The tree under `reference-impl/` maps 1:1 onto a `~/.claude` home:

| repo path | install to | needed for |
|---|---|---|
| `reference-impl/skills/scientific-research-guide/` | `~/.claude/skills/scientific-research-guide/` | the advisor; `domains/` starts empty |
| `reference-impl/skills/literature-search-extract/` | `~/.claude/skills/literature-search-extract/` | the literature service, citecheck, fetchsrc, run store |
| `reference-impl/hooks/literature_host_guard.py`, `literature-host-policy.json` | `~/.claude/hooks/` | publisher access boundary at the tool layer (register it, spec §8) |
| `reference-impl/hooks/secret_file_guard.py`, `deny_receipt.py` | `~/.claude/hooks/` | keeps `connectors/.env` keys out of reads (register it, spec §8) |
| `reference-impl/hooks/_lib/{roots,telemetry}.py` | `~/.claude/hooks/_lib/` | machine roots and locked log appends; skip if your home already has them |
| `reference-impl/hooks/tests/`, `reference-impl/tools/secret-guard-test/` | same paths under `~/.claude/` | the hooks' own tests |
| `reference-impl/rules/literature-access.md` | `~/.claude/rules/` | the prose rule the hook enforces |
| `verify/host.toml` | `~/.claude/adapt/host.toml` (or point `HK_HOST_TOML` at it) | roots.py refuses to guess without a host file |

Set `LSE_RUN_HOME` (and optionally `LSE_INBOX`, `LSE_BIB_HOME`) to a folder for evidence runs, or set
`NOTES_VAULT` in host.toml. Copy `connectors/.env.example` to `connectors/.env` only if your user has API keys.

## Adaptation rules

- Keep the gates two-sided: when you change a gate, keep or add its known-bad input and show it still fails.
- `hooks/literature-host-policy.json` is the user's file: propose a row change, never make one on your own,
  and never answer a 403 / CAPTCHA by changing User-Agent, browser or profile.
- `LSE_ARXIV_CONTACT` stays empty unless your user gives an address for arXiv; consent is per service.
- A new domain profile follows `domains/domain-expansion-guide.md`; `profile-lint.py` 0 FAIL and an
  `eval-impact.py --update-baseline` belong to the same change as the manifest row.
- The skills write Traditional Chinese for human deliverables; changing the language is a content decision
  for your user, not a code change.

## What not to adopt without your user's decision

- The institution-scoped rows of the policy file (`institutional_only`, `institutional_vpn`): they describe
  one subscription; with a different institution every such row is void until re-checked.
- The origin's provenance lines (dates, lesson ids, `<NOTES_VAULT>`, `<TEXTBOOKS>`): they explain where a
  rule came from; they are not dependencies.
- The notes-vault front-matter cards (`profile_frontmatter.py`): useful only if your user keeps an
  Obsidian-style vault over `domains/`.
