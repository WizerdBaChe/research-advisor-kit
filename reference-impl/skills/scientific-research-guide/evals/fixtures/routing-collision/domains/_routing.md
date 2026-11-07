# Seeded fixture — routing-anchor checks (NOT a real manifest)

> Calibration input for `tools/profile-lint.py`'s `KEYWORD-OVERLAP`, `WEAK-ANCHOR`, and
> overlap-register-closure checks. Deliberately two-sided: it seeds one of each finding AND
> two overlaps that must stay silent, so a check that fires on everything fails this fixture
> instead of scoring 100% on it.
>
> Run:  `python tools/profile-lint.py --root evals/fixtures/routing-collision`
>
> Expected, exactly:
>   FAIL  2 × register closure          — one file-closure break (the row naming
>           `ghost/never.md`) and one DEAD row (`widget etch`: real files, real keyword,
>           but the containing spelling, so it exempts nothing)
>   WARN  4 × KEYWORD-OVERLAP           — one of each reportable shape:
>           · `widget` (beta) ⊂ `widget etch` (alpha) — beta has NO base row, so
>             reachability is undeterminable and the finding is forwarded, not vetoed
>           · `flange` (delta/note) ⊂ `delta rig flange` (alpha) — non-base row whose
>             domain IS reached by the containing keyword. **Regression control for the
>             2026-08-26 reachability loosening: if this goes silent, the loosening has
>             over-reached.**
>           · `delta rig` (delta.md) ⊂ `delta rig flange` (alpha) — base row, always
>             reachable, no reachability test applies
>           · `TiO2 film` (beta) ≡ `TiO₂ film` (gamma) — collides only after Unicode
>             folding; catches a linter that compares raw strings while the matcher folds
>   WARN  1 × WEAK-ANCHOR               — `TIM` (beta) as a bare infix in `OPTIMAL SETTING`
>   WARN  1 × REDUNDANT-VARIANT         — gamma lists `mu2 form` and `mu₂ form`
>   silent: `sprocket` ⊂ `sprocket press` — non-base row whose domain is NOT reached by
>           the containing keyword; this is the finding the loosening exists to remove
>   silent: `OPTIMAL SETTING` ⊂ `OPTIMAL SETTING extra` — same domain (alpha), exempt in code
>   silent: `zeta` ⊂ `zeta probe`       — declared in § Known keyword overlaps below
>
> Every row except `delta.md` is `reference` type so the profile-schema checks do not
> run: this fixture is about the manifest's keyword shape, not about node structure. The
> one base row exists because reachability is undeterminable in a domain that has none —
> without it the reachability rule would never be exercised in either direction here.

## Manifest

| Type | File | Parent | Load trigger (keywords) | Covers / role | Active triggers? |
|---|---|---|---|---|---|
| reference | `alpha/notes.md` | alpha | widget etch, OPTIMAL SETTING, zeta probe, delta rig flange, sprocket press | Seeded row: owns the longer form of every colliding keyword | no |
| reference | `alpha/other.md` | alpha | OPTIMAL SETTING extra, deep clean | Negative control: same domain as `alpha/notes.md`, so its overlap must stay silent | no |
| reference | `beta/notes.md` | beta | widget, TIM, TiO2 film | Seeded row: the short keyword that collides across domains, the weak anchor, and the ASCII half of the fold-only collision | no |
| reference | `gamma/notes.md` | gamma | zeta, TiO₂ film, mu2 form, mu₂ form | Negative control for the register, plus the Unicode half of the fold-only collision and the redundant-variant pair | no |
| base | `delta.md` | — | delta rig | Gives domain `delta` a base row, so reachability is DETERMINABLE for `delta/note.md`. Sits at the manifest root like every live base row — a base row's domain is its own file stem, so `delta/base.md` would have made the domain `base` and silently broken the control | yes (Node 6) |
| reference | `delta/note.md` | delta | flange, sprocket | The two-sided reachability control: `flange`'s container reaches `delta`, `sprocket`'s does not | no |

## Known keyword overlaps (lint exception register)

| Row A | Row B | Overlapping keyword | Why the overlap is intended | Recorded |
|---|---|---|---|---|
| `gamma/notes.md` | `alpha/notes.md` | `zeta` | Negative control — a declared overlap must be suppressed. If this row starts appearing as a WARN, the register is not being read. | 2026-08-26 |
| `ghost/never.md` | `alpha/notes.md` | `phantom` | Seeded closure break — `ghost/never.md` has no manifest row, so this row must FAIL. This is the hole that scraping the disambiguation tables for exceptions opens: that scan harvests `cpo.md`, a file `_routing.md` declares must never exist. | 2026-08-26 |
| `beta/notes.md` | `alpha/notes.md` | `widget etch` | Seeded DEAD row — both files exist and `widget etch` is a genuine trigger of `alpha/notes.md`, so a keyword-membership test passes it. But the column holds the SHORT keyword and `widget etch` is the CONTAINING one, so this row consumes no exemption key and the `widget` finding still fires. Must FAIL. Taken from a real mistake made while triaging the live register on 2026-08-26. | 2026-08-26 |
