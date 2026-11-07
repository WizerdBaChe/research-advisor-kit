# Design ids cited in the code

The literature service's run store (`reference-impl/skills/literature-search-extract/loop/`, `consumers/`)
cites invariants `INV-n` and decisions `D-Ln` from its design of record,
`references/lse-feedback-loop-design.md`. That design file is not shipped (`verify/unshipped_paths.txt`,
class origin-history). This page gives each id the code cites, in the design's own terms, so a reader
does not need the unshipped file. INV-8 and INV-14 are not cited in this repository and are left out.

## Invariants

| id | invariant |
|---|---|
| INV-1 | Every run that reaches P4.5 persists its ledger, retrieved texts and both contracts in its run folder before `citecheck.py` runs, and the gate reads the ledger from that folder. No floating ledger. |
| INV-2 | Persistence changes nothing in the deliverable's content; the ledger is still not a deliverable. |
| INV-3 | One source, one key, computed by one function (`idkey.normalize`) with a fixed precedence. A source without a formal identifier gets an `unresolved:` key and is never dropped; that key always travels with its `unresolved_basis`, and two different bases under one hash are reported as a COLLISION, never merged (D-L19). |
| INV-4 | The search step may not start until `runs.py open` has run the reuse check and written `reuse_check` into `run.json`; its trail line goes into `search_trail`. `runs.py register` refuses a run without `reuse_check`, and `runs.py check` V7 fails it (D-L18). |
| INV-5 | Every deliverable ends with a loop footer; a Mode 2 result contract carries `run_id` and `sources[].key`. |
| INV-6 | Exactly one sanctioned write-back path (`reflux.py`). Every write-back is an event appended through it, validated against the schema, referencing an existing `run_id`/`claim_id` or a well-formed key, and never edited or deleted: a wrong event is answered by a later event. The file is not OS-protected; this rests on a single-user trust assumption, and a second writer moves the log to SQLite (D-L8). |
| INV-7 | A participant is a registry row: adding a consumer, store or artifact kind changes no code path and no hand-edited file other than `consumers/registry.json`; `references/bridge.md` is regenerated from the rows. |
| INV-9 | The Zotero item key is a join key, never the identity key; Zotero is never written. |
| INV-10 | Retrieved texts (`sources/*.txt`) never leave the machine: excluded from any share package, export or outbound sheet; no credential value or personal key appears in any record. |
| INV-11 | An invalidation is recorded, never deleted: the run or claim gains `wasInvalidatedBy` and `invalidatedAtTime`; the folder stays; `runs.py affected <key>` lists every run, claim and consumer that cited the key. |
| INV-12 | Loop instruments rule only on what they can determine; `runs.py check` ships with a good and a bad fixture and refuses to report if either side is empty; severity by consumer (FAIL where a tool parses, WARN where a person or model reads). |
| INV-13 | An unavailable home never aborts a literature run and never passes silently: the run opens in the fallback folder with `filed: false`, and `search_trail` and `gaps` say "run not filed: home unavailable". Until adopted, such a run is not in `index.json`, so write-back events cannot target it. |

## Decisions

| id | question | decision |
|---|---|---|
| D-L7 | how identifiers are detected and normalised | use `idutils` (BSD-3), isolated behind `loop/idkey.py`; replacing it with hand-written patterns touches one file |
| D-L8 | how write-back events are stored | append-only JSONL in the run home; SQLite is the named replacement, built only when a second concurrent writer appears |
| D-L17 | is `bridge.md` hand-written or generated | generated from the registry rows (`runs.py bridge`), with a `generated-from` hash that `check --registry` uses to catch a stale copy |
| D-L18 | how the reuse check became a gate | `runs.py open` runs it and writes `run.json.reuse_check`; `register` refuses a run without it; `check` V7 fails it |
| D-L19 | what to do when two `unresolved:` keys collide | the hash is the id, the basis is the identity: the basis is stored beside the key and compared on every join; same hash with different bases prints COLLISION and is reported separately, never merged |
