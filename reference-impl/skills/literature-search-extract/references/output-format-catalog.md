# Output format catalog

Moved out of `SKILL.md` on 2026-10-12 (WC-15c headroom pass: the file stood at the
300-line cap), table unchanged. `SKILL.md` Mode 1 infers `output_format` from the
task verb via the "Use when" column below; the request contract's `output_format`
field takes one of these rows or a caller-specified template; P5 shapes the
deliverable by it. Ready-to-copy templates for each row: `references/output-templates.md`.

| Format | Use when | Shape |
|---|---|---|
| Inline summary | quick answer, few sources | prose, cited claims |
| Annotated bibliography | caller needs a reading list | per-source: citation, 2–4 sentence relevance note, access tag |
| Evidence table | claim-by-claim support needed | rows = claims; cols = source, locator, supports/contradicts, quality |
| Method summary | reproduce/understand a technique | steps, required inputs, assumptions, stated validity range, per-step locators |
| Parameter sheet | numeric values needed | rows = parameter; cols = value±unc., unit, conditions, source+locator |
| Comparison matrix | choosing between methods/materials/models | rows = options; cols = caller's criteria; every cell cited |
| Quote pack | exact wording needed (definitions, standards) | short quotes + full locators |
| Concept matrix | literature review, gap scoping | rows = sources; cols = ledger concepts; cell = locator or —; empty column = gap candidate |
