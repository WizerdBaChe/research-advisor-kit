# BUILD SPEC - research-advisor-kit: a research-stage advisor and a citation-checked literature service

Audience: an agent (or a builder) who will install, adapt or rebuild these two capabilities. English.
The normative sources are the two skills under `reference-impl/skills/` and the rule
`reference-impl/rules/literature-access.md`; this spec is their contract summary plus everything that is
about the PACK (layout, environment, acceptance, declared edits). Where this file and a `SKILL.md`
disagree, the `SKILL.md` wins and this file has a defect.

## 0. What it is, in one paragraph

Two Claude Code skills that work as a pair. `scientific-research-guide` is the research ADVISOR: it
locates where the user is on a 7-tier research framework (Tier 0 framing to Tier 7 cross-cutting), runs
five gates (A triage with Step 0 domain routing and Step 0.5 scope check, B verify-before-asserting,
C non-intrusion, D deliverable form, E iteration feedback), returns a six-part diagnosis (locate, done,
missing, next, risks, method guidance), and keeps continuity in a user-owned `research-state.md`.
Domain knowledge sits in pluggable "domain profiles" (Layer B) registered in `domains/_routing.md`; this
kit ships the maintenance rules and tools for them but no profile. `literature-search-extract` is the
LIBRARIAN service the advisor delegates to (Mode 2 request/result contract): it finds sources, tags what
was actually read, extracts with locators into a caller-specified format, and refuses to ship a claim whose
support it cannot show. Its gate is a script: every load-bearing claim gets an evidence-ledger row naming
the exact support span, and `verify/citecheck.py` proves the span is verbatim in the retrieved text, that
the numbers in the claim are in the span, that metadata and provenance match, and that the work is not
retracted. A host access policy (a JSON file, a PreToolUse hook, and the fetch tool) keeps the agent off
hosts whose terms forbid agents and hands anti-bot challenges to the user.

## 1. Components and who calls whom

| component | path (under `reference-impl/`) | role |
|---|---|---|
| advisor | `skills/scientific-research-guide/` | SKILL.md (gates), `references/` (tier framework, method selection, deliverables, user-supplied citations inbox rules), `domains/` (empty manifest, template, expansion guide), `tools/` (profile-lint, routing_sim, eval-impact, profile_frontmatter), `evals/` (five domain-free cases + lint fixtures) |
| librarian | `skills/literature-search-extract/` | SKILL.md (P1-P5), `references/`, `connectors/` (registry, probe, access_policy, local corpus tools), `verify/` (citecheck, fetchsrc, pagestore, spannorm, staleclaim), `loop/` (run store, identity keys, reflux, inbox, schemas, tests), `consumers/` (caller registry) |
| host access hook | `hooks/literature_host_guard.py`, `hooks/literature-host-policy.json` | PreToolUse deny of agent fetches to `agent_banned` / `institutional_only` hosts and of browser surfaces the policy does not grant |
| secret hook | `hooks/secret_file_guard.py`, `tools/secret-guard-test/` | PreToolUse deny of reads that would print `connectors/.env` values |
| hook support | `hooks/deny_receipt.py`, `hooks/_lib/roots.py`, `hooks/_lib/telemetry.py` | deny receipts, machine roots from `host.toml`, locked log appends |
| rule | `rules/literature-access.md` | the prose boundary the hook, the policy and `fetchsrc.py` implement |

Call graph: the user's turn reaches the advisor (Gate A: continuity check, Step 0 routing, Step 0.5 scope
check, tier mapping, six-part diagnosis). A pure retrieval or extraction turn, and any Gate B need for
sources, goes to the librarian with a request contract. The librarian runs P1 targets, P2 search
(connectors, local corpus, WebSearch/WebFetch, recall check), P3 triage and access tags, P4 extraction
with locators, P4.5 evidence ledger and `citecheck.py`, P5 deliverable with gaps, confidence and `run_id`.
Fetched text enters only through `verify/fetchsrc.py` (which consults `connectors/access_policy.py`); the
hook is the same policy at the tool layer for every other fetch path. Evidence runs are persisted by
`loop/runs.py` and are re-usable by later runs (`reuse_check`).

## 2. Advisor contract (normative; source: scientific-research-guide SKILL.md)

- Advisor, not operator: no analysis code, experiment execution, dataset change, tool install or commit
  unless the user asks; offer and wait (Gate C). Reading files the user points at is always fine.
- Gate A order: continuity check (`research-state.md` if present), Step 0 domain routing through
  `domains/_routing.md` (four-rung ladder: literal anchor, scope match with stated basis, two-plus
  candidates then ONE routing question, none then generic framework and say so), Step 0.5 scope check,
  tier mapping, six-part diagnosis.
- Step 0.5: a turn with no research-stage question (find papers, make an evidence table) skips tier
  mapping and diagnosis, hands the search to the librarian, and treats any loaded profile as search context
  only.
- Gate B: method canon, reporting standards and tool facts are verified against a current source before
  being asserted; the sourcing sub-task is delegated to the librarian, the judgement stays with the advisor.
- Gate D: default NEW file, never overwrite a research document; updating `research-state.md` is offered
  and written only on the user's yes, appended not rewritten.
- Gate E: a downstream failure names the upstream tier to revisit; a symptom that recurs a second time
  triggers a current-versus-canonical comparison plus one diagnostic question before any further advice.
- With no profile loaded the advisor answers from the generic tier framework and says so.

## 3. Librarian contract (normative; source: literature-search-extract SKILL.md and references)

- Request contract fields: `purpose`, `question`, `source_types`, `scope`, `output_format`, `depth`,
  `language`. Result contract (always returned, also on partial failure): `findings`, `sources`, `gaps`,
  `confidence`, `search_trail`, `run_id`.
- Zero fabrication: no invented citation, identifier, locator, number or quotation; an honest gap is a valid
  deliverable. "Not found in searched sources" ships only after the P2 recall check (a withheld known item
  must be surfaced by the queries as run).
- Access tags on every source: `[full]`, `[partial]`, `[abstract]`, `[secondary]`; the tag follows the source
  into the deliverable.
- Every extracted item carries a locator; quantitative items keep value, unit, uncertainty and conditions;
  conflicts between sources are recorded with both positions and go to `confidence`, never averaged.
- Copyright boundary: short quotations with locator, paraphrase by default, never full sections.
- P4.5: one JSONL ledger row per load-bearing claim (claim, identifier, locator, access tag, exact support
  span, path to the retrieved text, access route); every numeric or disputed claim gets a row at every depth.
- Host access: paywalled or agent-banned hosts are handed to the user as a named DOI/URL plus query pack;
  a challenge is a routing signal, never retried with another User-Agent, browser or profile.

## 4. Run folder contract

`$LSE_RUN_HOME/<run>/` (default `${NOTES_VAULT}/literature/EvidenceRuns`): `run.json` (schema
`loop/schemas/run.schema.json`, including `reuse_check`), `ledger.jsonl`, `citecheck.json` (the gate's
output), `record.md` (the human record; the index is built from it), `sources/manifest.json` (written by
`fetchsrc.py`: per text the URL, host, route, status, sha256, retention state) and `sources/<name>.txt`.
Retention follows the host policy row: `full` for open hosts, `excerpt` for landing pages and unlisted
hosts (the full text stays in scratch, `fetchsrc.py excerpt` derives windows around the ledger's spans).
Worked fixtures: `skills/literature-search-extract/loop/tests/fixtures/good-run/` (must pass) and
`bad-run/` (must fail).

## 5. Gate design (applies to every gate here)

- A gate rules only on what it can determine; anything else is a WARN with its reason, never a veto
  (citecheck proves a span is present, not that it supports the claim; the offline mode skips identifier
  resolution and says so).
- Two-sided calibration: each gate family has a selftest or test with a known-good input that must pass and
  a known-bad input that must fail, and the run prints both asserted values.
- Provenance is checked against the instrument's own record (`sources/manifest.json` sha256), not against
  the model's report of it.
- Domain-profile maintenance is gated by script: manifest closure, register closure, keyword overlap and
  weak-anchor warnings, generated front-matter closure (`profile-lint.py`), and re-run selection by declared
  dependency (`eval-impact.py`).

## 6. Build order that worked

Install roots and hooks first (section 8), then run the acceptance controls on the untouched tree
(section 7), then register the hooks, then author your first domain profile (section 8) and re-run K7-K9
style checks on it. Register the hooks before the first literature wave: the rule's own origin record
(`rules/literature-access.md`, 2026-09-10) is a wave in which a VPN made paywalled publishers reachable and
the next thought was a headless browser with a logged-in profile; the prose rule alone had not stopped that
intent, hence the tool-layer deny.

## 7. Acceptance (`verify/run_controls.py`; every line prints both asserted values)

Run `python -X utf8 verify/run_controls.py <new-scratch-dir>` from the repo root. It copies
`reference-impl/` to the scratch folder, sets `HK_HOST_TOML=verify/host.toml`, `LSE_RUN_HOME`, `LSE_INBOX`,
`LSE_BIB_HOME` and `CLAUDE_TELEMETRY_DIR` inside it, clears `LSE_ARXIV_CONTACT`, mutates the copy and
deletes it. No control touches the network. A control that reports `MISMATCH` makes the exit code 1.
Machine tolerance: Python 3.11 or newer (tomllib), pytest, and the packages in section 8 (`idutils`,
`jsonschema`) must be importable.

| id | what | must pass (expected value) | must fail (expected value) |
|---|---|---|---|
| K1a | `connectors/access_policy.py --selftest` | exit 0, output matches "refused at the same count" | an unlisted host is still refused at the same count (inside) |
| K1b | `connectors/pdf_index.py --selftest` | exit 0, "6 cases (4 must-parse / 2 must-degrade-without-inventing), 0 broken" | the 2 must-degrade cases (inside) |
| K1c | `connectors/probe.py --selftest` | exit 0, "5 cases, 0 broken - scanner is two-sided" | (inside) |
| K1d | `connectors/zotero_local.py --selftest` | exit 0, prints the NOTE that it calibrates citation shaping and mark provenance on a fixture | (inside) |
| K1e | `loop/idkey.py --selftest` | exit 0, "17 cases (12 must-parse / 4 must-unresolve / 1 must-differ), 0 broken" | the 4 must-unresolve and 1 must-differ cases (inside) |
| K1f | `loop/inbox.py --selftest` | exit 0, "selftest: PASS" | (inside) |
| K1g | `loop/reflux.py --selftest` | exit 0, "5 cases (2 must-reject / 3 must-accept), 0 broken" | the 2 must-reject cases (inside) |
| K1h | `loop/runs.py --selftest` | exit 0, output contains "calibrated" | (inside) |
| K1i | `verify/fetchsrc.py --selftest` | exit 0, "0 broken - calibrated" | refused host, challenge, per-host cap (inside, stub transport) |
| K1j | `verify/staleclaim.py --selftest` | exit 0, "8 cases (5 must-pass / 3 must-fail), 0 broken" | the 3 must-fail cases (inside) |
| K1k | `verify/citecheck.py --selftest --offline` | exit 0, "105 cases (53 must-pass / 52 must-fail), 0 broken" (without PyMuPDF: 85 cases and "[page-pointer cases skipped: no PyMuPDF]") | the 52 must-fail cases (inside) |
| K2 | `pytest loop/tests` | exit 0, "53 passed" | (assertions inside, incl. register refusing a FAIL citecheck.json) |
| K3 | `hooks/tests/test_literature_host_guard.py` | exit 0 and "ALL TESTS PASSED" | the D-* deny cases (inside) |
| K4 | `tools/secret-guard-test/test_secret_file_guard.py` | exit 0 and "failures: 0"; must-deny 50, must-pass 53 | the 50 must-deny shapes; 3 undetermined and 3 unclassifiable-shape (fail-open) are reported, not counted |
| K5 | citecheck support check on `good-run` | support verdict `OK` (span found verbatim) | the same row with "22 um" changed to "48 um" in span and "= 22 μm" to "= 48 μm" in claim: support verdict `FAIL` |
| K6 | `literature_host_guard.py` fed a WebFetch payload | arXiv URL: silent allow (exit 0, no output) | the IEEE Xplore document URL: `permissionDecision` = `deny` |
| K7 | `profile-lint.py --root` on three trees | shipped skill root: (0 FAIL, 0 WARN) | `evals/fixtures/routing-collision`: (2, 6); `evals/fixtures/frontmatter-drift`: (2, 0) |
| K8 | `eval-impact.py --files` against the shipped (empty) manifest | `references/method-selection.md`: RE-RUN 3 of 5 cases (2, 3, 5) | `references/deliverables.md`: 0 cases |
| K9 | add one manifest row to `_routing.md` | row with no file: 1 FAIL, output contains "missing file: demo_domain.md" | same row plus an unfilled copy of `_template.md`: closure message gone, FAIL count 11 (template placeholders) |

Not counted (reported as `UNDT`): `connectors/local_find.py --selftest` and `connectors/textbook_ocr.py
--selftest` need a local textbook library; on a machine without one they exit non-zero and the transcript
says so. The expected final line on a clean machine is `19/19 controls ok, 2 undetermined (not counted)`.
Every control reads the repo's files only: `run_controls.py` sets `CLAUDE_CONFIG_DIR` to an empty scratch
folder and `LSE_HOST_POLICY` to the shipped policy file, so an installed `~/.claude` cannot change a verdict.
Packages: `verify/requirements.txt`.

Visual or judgement acceptance (whether the advisor's diagnosis is useful, whether an extraction is the
right one) is a human check; the controls prove the gates, not the judgement.

## 8. Adapt to your environment (re-check before trusting)

- **Layout.** `reference-impl/` is laid out like a Claude Code config home (`CLAUDE_HOME` in
  `hooks/_lib/roots.py` is the parent of `hooks/`). Copy `skills/*`, `hooks/*`, `rules/*`, `tools/*` into
  your config home, keeping relative paths. `connectors/access_policy.py` finds the policy at
  `$LSE_HOST_POLICY`, else `<CLAUDE_CONFIG_DIR or ~/.claude>/hooks/literature-host-policy.json`.
- **Machine roots (`host.toml`).** `roots.py` raises `HostFileMissing` when no host file exists (a guard that
  silently lost its settings would fail open). Copy `verify/host.toml` to `<config home>/adapt/host.toml`
  or point `HK_HOST_TOML` at it. Keys (schema `hk-host/1`): `WORK_ROOT`, `SHARE_ROOT`, `DATA_ROOT`,
  `NOTES_VAULT` (evidence runs, bibliography and inbox default under `${NOTES_VAULT}/literature/`),
  `TEXTBOOKS` (local textbook library for `local_find.py` / `textbook_index.py`). A value of `none`, empty
  or a relative path counts as unset; every optional root may be unset and the controls need none.
  A data-folder role not set on its own falls back to `DATA_ROOT/<role>`.
- **Environment variables.**

  | variable | effect |
  |---|---|
  | `LSE_RUN_HOME` | folder of evidence runs; overrides `${NOTES_VAULT}/literature/EvidenceRuns`; `runs.py` exits with a message when neither is set |
  | `LSE_INBOX` | the hand-to-user inbox (missing full texts and where found PDFs wait) |
  | `LSE_BIB_HOME` | the project bibliography folder (Zotero close-out) |
  | `LSE_ARXIV_CONTACT` | OPT-IN. Your own address, sent in the polite User-Agent to arXiv hosts only (`arxiv.org`, `export.arxiv.org`). Empty or unset means no contact string is sent at all. The kit never ships anyone's address; consent is per service and per user |
  | `LSE_HOST_POLICY` | alternative path of the host policy file |
  | `LSE_FETCH_SCRATCH` | scratch folder for non-open full texts before excerpting |
  | `HK_HOST_TOML` | location of `host.toml` (tests, or a config home without `adapt/`) |
  | `CLAUDE_TELEMETRY_DIR` | redirects hook logs and deny receipts (default `<config home>/telemetry`) |

- **Python packages.** Python 3.11 or newer. Required by the controls and the run store: `pytest`,
  `idutils==1.7.0` (`loop/idkey.py` refuses to guess identifiers without it), `jsonschema` (`loop/runs.py`
  validates run records; without it validation reports an error instead of running). Optional: `pymupdf`
  (PDF text in normal use; no control needs it; AGPL, see `THIRD_PARTY_NOTICES.md`).
- **Hook registration (`settings.json`, `hooks.PreToolUse`).** Two entries, each a `command` hook with
  `timeout` 30, command `python -X utf8 "<config home>/hooks/<file>"`. Both read the tool-call JSON on stdin
  and write a `permissionDecision` JSON on a deny.

  | hook file | matcher |
  |---|---|
  | `literature_host_guard.py` | `WebFetch\|Bash\|PowerShell\|mcp__(Claude_Browser\|claude-in-chrome)__(navigate\|preview_start\|browser_batch)\|mcp__playwright-headless__browser_navigate` |
  | `secret_file_guard.py` | `Read\|Grep\|Bash\|PowerShell` |

  Shape of one entry:
  `{"hooks": {"PreToolUse": [{"matcher": "<matcher>", "hooks": [{"type": "command", "command": "python -X utf8 \"<config home>/hooks/<file>\"", "timeout": 30}]}]}}`.
  When your environment names its browser tools differently, extend the matcher AND the surface mapping in
  `literature_host_guard.py` (`surface_for`); the guard only judges tool names it maps. The hook fails OPEN
  on an unreadable or missing policy file (it then denies nothing and logs a loud `policy_unreadable` row),
  while `access_policy.py` on the skill side fails CLOSED; keep the policy file next to the hook and watch
  for that log row. Check with K3 and K6 after registering, then make one real WebFetch of an `agent_banned`
  host from a session and see the deny.
- **Connectors and credentials.** `connectors/.env.example` is the template; copy it to
  `connectors/.env` and fill only the connectors you want (OpenAlex key, Unpaywall email, Crossref mailto,
  Semantic Scholar key, ...). Once the file is named `.env`, `secret_file_guard` denies the agent reading it
  in every permission mode; debugging a 401 is `python connectors/probe.py --id <name>`, which loads the
  key itself and reports only presence. `connectors/registry.json` paths are `${NAME}/rest` tokens resolved
  through `roots.py`. The contact addresses in the template (Unpaywall, Crossref) are privacy choices: the
  address is sent with every request, so leave them empty unless your user decides otherwise.
- **The host policy is the user's file.** Rows describe one deployment's measured facts (an institutional
  subscription, a measured challenge). The institution field ships as `<your institution>`; with a different
  institution every institutional row is void until re-checked. Propose row changes to your user; never
  edit a row to get past a deny.
- **Domain routing starts empty.** `domains/_routing.md` ships with the rules (How Gate A uses this
  manifest, Clusters, Known keyword overlaps, Maintenance) and an empty manifest table. To add the first
  profile: (1) read `domains/domain-expansion-guide.md` (when a profile is warranted, the 7-node structure,
  the quality checklist); (2) copy `domains/_template.md` to `domains/<domain>.md` and fill it; (3) add one
  manifest row to `domains/_routing.md` using the row templates in the HTML comment (types `base`,
  `sub-profile`, `reference`, `boundary`; only list files that exist); (4) run
  `python tools/profile-lint.py` from the skill root until 0 FAIL (the unfilled template alone gives FAIL,
  K9); (5) if your vault wants generated cards, `python tools/profile_frontmatter.py --sync`; (6) run
  `python tools/eval-impact.py --update-baseline` so the routing baseline reflects the new row set, and
  re-run the cases it lists. Add a `## Disambiguation: <cluster>` section when two rows share a keyword on
  purpose, and register the overlap in the table.
- **Language.** Human deliverables are Traditional Chinese with English terms inline; code, config and
  machine-read returns are English. Changing language is a content decision, not a code change.
- **Not shipped, referenced by provenance lines.** The origin's `ops/` files, design records under
  `references/`, `rules/hook-deny-message.md`, the browser-pane hook and its allowlist. They explain where
  rules came from; nothing runs through them. The full list is `verify/unshipped_paths.txt`.

## 9. Declared edits relative to the origin (everything else is byte-identical)

Origin = the author's config home at the release date. `reference-impl/` keeps the origin's layout and is
rebuilt by the maintainer's refresh script from an explicit file list (92 files, plus 3 derived and 1
overlay). Each edit below must hit its stated count or the build stops before writing. Not shipped: see
`verify/unshipped_paths.txt`.

| id | where | what changed |
|---|---|---|
| E1a | `skills/literature-search-extract/verify/citecheck.py` | the owner's e-mail address in the arXiv polite User-Agent table is removed; the table is built from the `LSE_ARXIV_CONTACT` environment variable for the two arXiv hosts only, and is empty when the variable is unset. Consent stays per host and per user |
| E1b | `skills/literature-search-extract/verify/fetchsrc.py` | the same change for the second copy of that table |
| E2 | `hooks/literature-host-policy.json` (rule R1 below) | the institution's own library discovery-layer host row is removed (it names the institution); the JSON array stays valid |
| E3a | `hooks/_lib/roots.py` | an example folder in a docstring generalised to "a share folder" |
| E3b | `skills/scientific-research-guide/references/tier-framework.md` | the path of a private post-analysis note is replaced by a parenthetical saying the note is not shipped |
| E3c | `skills/scientific-research-guide/tools/profile_frontmatter.py` | the vault design name in a docstring generalised to "notes-vault" |
| E3d | `skills/literature-search-extract/references/feedback-loop.md` | a private vault file path replaced by "the vault's own AGENTS.md" |
| E3e | `skills/literature-search-extract/references/connectors.md` | a private Zotero storage path replaced by `~/Zotero/storage` |
| E4a | `rules/literature-access.md` | three provenance edits: the origin line names "a research-project literature wave" instead of the lab's wave id; the VPN review-when clause names "the one this policy was written under" instead of the school; the ToU argument cites "library argument" |
| E4b | `skills/literature-search-extract/literature-search-extract-FUTURE-WORK.md` | three phrases that named the lab's round, its vocabulary and the school's guide are generalised ("research project round", "research project", "library guide") |
| E4c | `skills/literature-search-extract/references/search-sources.md` | the lab class and the lab measurement named in two provenance parentheses become "the research-project class" and "a research project"; the school's library guide becomes "a university library's guide" |
| E4d | `skills/scientific-research-guide/references/tier-framework.md` | the lab case label becomes "research project case" |
| E4e | `skills/literature-search-extract/connectors/registry.json` | "(school or similar)" becomes "(a university's or similar)" |
| E4f | `hooks/literature-host-policy.json` | the `institution` field starts `<your institution>` instead of the school's name |
| E4g | `hooks/literature_host_guard.py` | the docstring's school-library mention, split across a line break, becomes "A university library's AI-literacy guide" |
| E5a | `skills/scientific-research-guide/SKILL.md` | the description no longer lists the origin's domains; it points at the profiles registered in `domains/_routing.md` (none ship) |
| E5b | `skills/scientific-research-guide/SKILL.md` | the Step 0 example row points at `domains/<domain>.md` and says the public kit ships the manifest empty |
| E5c | `skills/scientific-research-guide/SKILL.md` | the reference-map line about Layer B base profiles says none ship and points at the expansion guide |
| E6 | `skills/literature-search-extract/SKILL.md` | the description's routing line for uncited broad sweeps no longer points at an unshipped dispatch file; it names the task class and says the kit ships no such agent |
| R2 | all text files (8 hits) | the lab's round identifier in provenance lines becomes "a research round" (dates and lesson ids kept) |
| R3 | all text files (11 + 7 + 1 + 0 hits) | the school's library, its guide and its subscription wording become "a university library's", "the library guide", "an institutional subscription"; a fourth rule (a bare school name becomes "the university") is kept as a guard and now hits 0, since E4g handles the one remaining mention |
| R4 | all text files (6 + 6 hits) | the private notes-vault folder and the private textbook folder become the tokens `<NOTES_VAULT>` and `<TEXTBOOKS>` |
| D1 | `skills/scientific-research-guide/domains/_routing.md` (DERIVED) | built from the origin routing manifest: the title, intro and "How Gate A uses this manifest" section are kept verbatim; a public-kit note is added; the manifest table keeps its header and holds only an HTML comment with one row template per content type; the Clusters table keeps its header and no rows; the two origin Disambiguation sections are replaced by a paragraph on when to add one; the Known keyword overlaps table keeps its header and no rows; the Maintenance section is kept with a sentence saying its examples name unshipped profiles |
| D2 | `skills/scientific-research-guide/references/user-supplied-citations.md` (DERIVED) | the origin's citation sets are dropped: the title, a status block, the "Storage and triage rules" section and the "Maintenance" section are kept, and empty skeletons stand in for the candidates table, the duplicate groups and the inbox |
| D3 | `skills/scientific-research-guide/evals/evals.json` (DERIVED) | keeps the five domain-free cases (ids 1, 2, 3, 5, 11); the `run` block is replaced by a note saying why, keeping date, model and method; case 11 (the negative control) stays because it checks the Step 0.5 hand-off with no profile loaded |
| O1 | `skills/scientific-research-guide/evals/routing-baseline.json` (OVERLAY) | NEW, recomputed by `eval-impact.py --update-baseline` on the built kit (empty manifest, five cases, no row set) and stored by the maintainer; the origin file lists the origin's profiles |

The edits are applied by the maintainer's refresh script, which rebuilds `reference-impl/` into a scratch
folder, compares it byte-for-byte with the repo copy, and screens every shipped text file against a private
names list with planted positives; that script, the original strings and the list are not shipped.
Two small allowances in the screen are synthetic drive-path strings that the hook tests need as input.
