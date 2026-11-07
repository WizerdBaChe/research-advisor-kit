# Seeded fixture — FM-CLOSURE (NOT a real manifest)

> Calibration input for `tools/profile-lint.py`'s FM-CLOSURE rule (imported from
> `tools/profile_frontmatter.py`). Two-sided: one file whose generated card matches its
> row (must stay silent), one whose aliases drifted (must FAIL), one with no card at all
> while a sibling has one (must FAIL — adoption detected from the tree).
>
> Run:  `python tools/profile-lint.py --root evals/fixtures/frontmatter-drift`
> Expected, exactly: **2 FAIL, 0 WARN** — both FM-CLOSURE, on `drift/notes.md` and
> `missing/notes.md`. Keywords are chosen disjoint and longer than three characters so
> the routing-anchor checks stay silent; every row is `reference` so node-schema checks
> do not run.

## Manifest

| Type | File | Parent | Load trigger (keywords) | Covers / role | Active triggers? |
|---|---|---|---|---|---|
| reference | `okay/notes.md` | okay | quartz resonator, 石英諧振 | Positive control: card equals the row | no |
| reference | `drift/notes.md` | drift | copper pillar, 銅柱 | Negative control: card lists a stale alias | no |
| reference | `missing/notes.md` | missing | glass frit sealing | Negative control: no card while siblings carry one | no |
