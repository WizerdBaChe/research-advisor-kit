# Domain Routing Manifest

> Single source of truth for **which domain files exist** and **when to load each**.
> Gate A Step 0 (SKILL.md) consults this file before loading any Layer-B content.
> Keep it terse — this file is read on every domain-triage turn. One row per file.

> **Public kit (research-advisor-kit):** the origin's domain profiles are not shipped. This file keeps its rules and its empty structure; add your own rows as you author profiles (`domain-expansion-guide.md`, `_template.md`).

## How Gate A uses this manifest

### The four rungs in full (moved from SKILL.md 2026-09-06, BODY_CAP trim)

SKILL.md keeps the ladder's shape and the rule that a fuzzy question is routed
rather than guessed; these are the matching rules each rung depends on.

1. **Literal anchor hit** — the user's wording contains a row's trigger keyword
   → load; standing triggers fire normally. Match **case-sensitively** (`TI`,
   `RIN`, `SPP` and 35 other short acronyms hit inside ordinary words once
   lower-cased) but **variant-insensitively**: compare in Unicode NFKC, so
   `Bi₂Se₃` matches the manifest's `Bi2Se3`, `Z2` matches `Z₂`, `μLED` matches
   `µLED`, and a full-width or superscript spelling matches its plain form. The
   manifest lists ONE spelling per term and relies on this.
2. **Scope match, no literal hit** (vague/fuzzy phrasing): match the described
   physical system and observable against the rows' `Covers / role` column and
   the Clusters/disambiguation sections below. Exactly one candidate → load it
   and **state the routing basis in one line** ("loading X — the question is
   about ⟨scope⟩") so a misroute is visible and correctable; never answer
   silently from a guessed profile.
3. **Two-plus candidates** (typically within a cluster) → ask ONE routing
   question taken from the relevant disambiguation table's own axis (those
   tables are pre-written clarification scripts), instead of speculatively
   loading several profiles. A question genuinely spanning two profiles still
   loads both and states which owns the governing constraint. **Exception** —
   on a pure retrieval turn (Step 0.5) do NOT block the handoff with a routing
   question: pick the best-scope candidate as search context and state the basis.
4. **No candidate** → proceed with the generic framework and say so; do not
   improvise domain-expert claims without Gate B verification.

Never compensate for a missed fuzzy match by adding broad manifest keywords —
keywords are precision anchors (a false load is worse than prose routing, see
§ Maintenance); recall for fuzzy phrasing is owned by this ladder.

### The load sequence

1. **Identify domain** — match the user's field against the `base` rows' triggers.
2. **Load the base profile** — always load the matched domain's base profile alongside
   the tier framework. Its standing triggers — Node 6's `Trigger condition` rows (primary),
   Node 1's constraints + Decision point, the Node 2/4 warning columns, and the Conflict
   Notes questions (`domain-expansion-guide.md` §3.6) — become standing if-then rules for
   the whole turn.
3. **Scan sub-profiles of that domain** — for every `sub-profile` row whose parent is the
   matched domain, check its load trigger against the user's wording. On a match, **load it
   and activate its own standing triggers** (they fire like the base profile's).
4. **Pull references on demand only** — `reference` / `boundary` rows are loaded only when
   the specific topic is explicitly engaged; they carry no standing triggers. A `boundary`
   row's job is to route the user *out* to a sibling domain when they cross the edge.
5. **Fuzzy questions (no literal keyword hit)** — the keyword column is a precision anchor,
   not the whole recall path. Route by the `Covers / role` column plus the Clusters /
   disambiguation sections below, per SKILL.md Step 0's resolution ladder: one candidate →
   load with a stated routing basis; several → ask the disambiguation table's own axis
   question; none → generic framework. Never widen recall by adding broad keywords
   (§ Maintenance). *Authoring consequence*: write `Covers / role` in the asker's frame
   (what the question is about) — it doubles as the fuzzy-routing index.

**How a keyword is compared (the matching rule).** Case-**sensitive** — `TI`, `RIN`, `SPP`
and 35 other short ASCII acronyms match inside ordinary words once lower-cased, measured
2026-08-26 over the eval prompts. Variant-**insensitive** — put both the user's wording and
the keyword into Unicode NFKC before comparing, so the compatibility spellings of one term
are one term: `Bi₂Se₃` = `Bi2Se3`, `Z₂` = `Z2`, `µLED`(U+00B5) = `μLED`(U+03BC), `cm²` = `cm2`,
full-width `Ｂｉ２Ｓｅ３` = `Bi2Se3`. A row therefore lists **one** spelling of a term and
never a variant list — see § Maintenance. `tools/routing_sim.py` implements exactly this.

Type semantics are defined in `domain-expansion-guide.md` §2 (the two-gate decision tree).


## Manifest

| Type | File | Parent | Load trigger (keywords) | Covers / role | Active triggers? |
|---|---|---|---|---|---|

<!--
Add rows as content is authored. Only list files that ACTUALLY EXIST (Gate A will try to
load what it finds here). Row templates, one per content type:

| base        | `<domain>.md`              | —        | <keywords the asking user types> | <what the question is about> | yes (Node 6) |
| sub-profile | `<domain>/<branch>.md`     | <domain> | <branch keywords>                | <branch scope>               | yes (Node 6) |
| reference   | `<domain>/<topic>.md`      | <domain> | <topic keywords>                 | <reference note>             | no |
| boundary    | `<domain>/<edge>.md`       | <domain> | <edge keywords>                  | routes OUT to a sibling domain | no |
-->

## Clusters

> A **sibling cluster** is N peer base profiles that partition ONE physical system — each pair
> passes Gate 1's divergence conditions against the other, so no shared parent exists (a base
> built on their thin intersection would be a fake parent). Shape definition, intersection
> test, and registration requirements: `domain-expansion-guide.md` §2. One entry per cluster.

| Cluster | Members (each owns…) | Ruling |
|---|---|---|

## Disambiguation sections

When a sibling cluster is registered above, or two base rows share a keyword on purpose, add a
`## Disambiguation: <cluster>` section here that routes by what the question is ABOUT (observable +
scope), and name each owner of a shared standard. The origin keeps two such sections; they belong to
its domain profiles and are not shipped.

## Known keyword overlaps (lint exception register)

> **This table is the ONLY exception source for `tools/profile-lint.py`'s `KEYWORD-OVERLAP`
> check.** A pair listed here is a reviewed, intended overlap and is not reported; any other
> cross-domain overlap is reported as a WARN.
>
> It is maintained by hand, deliberately. The obvious alternative — deriving the exceptions by
> scanning the two disambiguation sections below for file names — was tried and rejected on
> 2026-08-26: that scan harvests `cpo.md` from the section whose entire purpose is to declare
> that `cpo.md` must never exist, and its two sections together cover 6 of the 10 base profiles,
> which would blanket-exempt 15 of the 45 base-pairs — precisely the pairs the eval suite's
> collision history is about. An instrument may only rule on what it can DETERMINE; prose cannot
> determine intent, so the exemption is declared as a property of the manifest instead of
> inferred from prose. Same-domain pairs (a base and its own sub-profile/reference) are exempt
> in code and are not listed here.
>
> Adding a row is a routing decision, not a lint fix: it asserts that both files loading together
> is the behaviour you want. If it is not, change the keyword instead.
>
> **The `Overlapping keyword` column holds the SHORT (contained) keyword — Row A's — never the
> containing one.** One row therefore covers every containing spelling at once: `thermal crosstalk`
> exempts the pair for both `ring-to-ring thermal crosstalk` and `microring thermal crosstalk`,
> and a second row naming a containing spelling would exempt nothing. Enforced, not remembered:
> `profile-lint.py` FAILs any row that suppresses nothing — i.e. where the two named rows have no
> overlap on that keyword at all. Naming a real keyword is not enough; a containing spelling is a
> real keyword of a real row and still silences nothing, which is exactly the mistake this catches.
> Keywords here are compared in the same NFKC-folded space as everything else, so the spelling
> in this column need not match the manifest's byte-for-byte.

| Row A | Row B | Overlapping keyword | Why the overlap is intended | Recorded |
|---|---|---|---|---|

## Maintenance

*The examples below name the origin's own profiles (not shipped); the lessons hold for any domain.*

- SKILL.md must NOT hardcode domain file paths — it points here. When you add a domain
  file, add its row here in the same change; that is the only place the load list lives.
- `base` files stay lean (the 7-node profile = the domain's shared core). Specialized
  branches go in `sub-profile` rows, not the base file — see the decision tree.
- **A trigger keyword must be a word the *asking* user would type, not the answer.** Two rejected
  additions from the 2026-08-24 eval pass are worth not repeating: (a) `35.26°` alone was useless
  as a `fiber_chip_passive_alignment` trigger — a user who has made the wedge-half-angle error
  types `54.74°`, never the corrected value — and an English-only phrase does not fire on a
  Chinese prompt, so the Chinese form was added beside it; (b) generic packaging-timeline words
  (`封裝製程`, `封裝前後`, `封裝完之後`) were added to `siph_packaging_reliability` and then
  **reverted**: they matched three sibling profiles' core scenarios verbatim (a V-groove etch-angle
  question says `封裝製程`; a pre/post-attach IL question says `封裝前後`), so the row would have
  over-loaded across the whole cluster. That profile owns qualification and lifetime — a bare
  packaging-timeline word is not evidence of that scope. Where a cross-domain question cannot be
  caught by an honest keyword, let the two profiles' own Cross-Domain Links carry it; that is
  weaker routing but it does not manufacture false loads.
- **A spelling variant is not a broad keyword, and the trade runs the other way.** The rule above
  is about a keyword that means something *wider* than the row's scope. `Bi₂Se₃` beside `Bi2Se3`
  is the same term in a different codepoint: it cannot pull in a question the ASCII form would not
  have pulled in, so it cannot manufacture a false load — it can only recover a miss. User ruling
  2026-08-26: for this class a miss is the worse failure, because the consumer is an LLM that can
  discard an extra file but cannot read one that never loaded. **The fix is the matching rule, not
  the row** — matching is NFKC-folded (see § How Gate A uses this manifest), so list ONE spelling
  and let the fold cover the rest. Hand-listing variants is what the fold replaces: no such list is
  ever complete, and `profile-lint.py` reports a row carrying two spellings of one term as
  REDUNDANT-VARIANT.
- **Recall gaps are found by simulation, not by reading the row.** The 2026-08-26 triage found that
  `topological_insulator.md` had never listed `Bi2Se3` — the domain's single most typed material —
  so eval case 4's prompt matched no base row at all and the Bi₂Se₃ sub-profile was unreachable,
  while the eval's own recorded evidence claimed it loaded. Prose review had passed that row
  repeatedly. `tools/eval-impact.py`'s baseline is what surfaced it; run it after touching a row.

*review-when:* the Step-0 matching rule changes (case sensitivity, folding, or the two-level
scan). All three are stated in § How Gate A uses this manifest and implemented in
`tools/routing_sim.py`; if one moves and the other does not, both this section and the lint
calibration counts in `profile-lint.py`'s docstring are wrong.
