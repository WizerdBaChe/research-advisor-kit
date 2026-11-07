# Seeded fixture base profile — domain `delta` (NOT a real profile)

> Exists so `evals/fixtures/routing-collision` contains a domain that HAS a base row.
> Without one, `routing_sim.rung1_reachability()` returns `None` for every non-base row in
> the fixture and the reachability rule is never exercised in either direction — the
> fixture would then pass whether the rule works or not.
>
> Its content is the minimum that satisfies `profile-lint.py`'s base-profile schema, so
> this file contributes ZERO findings and the fixture's expected counts stay about
> routing anchors. The physics is deliberately nonsense.

## 1. First Principles and Constraints

The delta rig is a fictional apparatus. Nothing here is a claim about the world.

**Decision point (mandatory Tier 0 confirmation)**: confirm the rig is fictional before
using any number below.

## 2. Measurement and Instrument Rules

| Target | Tool | Applicable conditions | Common misuse | Source [Key] |
|---|---|---|---|---|
| Flange seating | Fictional gauge | Bench only | Treating the fixture as real data | [FixtureNote] |

## 3. Toolchain

No toolchain. This node exists to satisfy the required-heading check.

## 4. Validation Methods

| Method | Applicable conditions | Common error | Correct approach | Source [Key] |
|---|---|---|---|---|
| Bench check | Fixture runs only | Reading the fixture as a profile | Read the fixture note at the top | [FixtureNote] |

## 5. Typical Value Ranges

| Metric | Typical value range | Conditions | Source [Key] |
|---|---|---|---|
| Flange offset | 0–1 (dimensionless, fictional) | Fixture only | [FixtureNote] |

## 6. Pitfalls and Standing Triggers

| Pitfall | Trigger condition | Correct approach | Source [Key] |
|---|---|---|---|
| Treating fixture rows as domain knowledge | Any use outside the linter's calibration | Discard; consult a real profile | [FixtureNote] |

## 7a. Literature Anchors

None. This is a fixture.

## 7b. Source Ledger

| Key | Full citation | Identifier | Access | Status | Verified (date) | Locator | Used in |
|---|---|---|---|---|---|---|---|
| FixtureNote | Fixture self-reference; no external source. | — | [n/a] | Fictional by construction | 2026-08-26 | — | §§1–6 |
