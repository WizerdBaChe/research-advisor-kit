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
| Assumption census | "what does this whole set take for granted", before trusting a field-wide consensus | rows = premises shared by ≥2 sources; cols = relying sources+locator, tested-by, if-wrong impact `[synthesis]` |
| Method census | "which methods does this set use, which is thin, which paper is weakest" | rows = method classes (field taxonomy); cols = sources+locator, count, what it can/cannot establish, weakest instance |
| Concept lineage | "who introduced / challenged / refined concept X" | per concept, dated edges source→source typed introduces/challenges/refines/applies, each edge cited from the CITING paper's text |
| Researcher genealogy | "who are these people, which groups/schools, are these results independent" | nodes = researchers/groups; edges typed co-author / affiliation / advisor / heavy-citation, each with its own evidence route |

The last four are **cross-corpus** formats (added 2026-11-17): they need a run corpus
already gathered (≥5 sources; below that, say so and fall back to an evidence table) and
describe THAT corpus, never the field — every "most", "first" or "untested" is scoped
"in this run". Concept lineage follows ideas through citation text; researcher genealogy
follows people through bylines and training — distinct objects, often run together:
genealogy tells whether a premise in the assumption census is shared by independent
groups or by one school (failure mode 7). Origins: a Threads 9-prompt post
(prompts 2, 6, 9) and an Instagram academic-genealogy carousel, both 2026-11.
