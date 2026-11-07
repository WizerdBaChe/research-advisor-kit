#!/usr/bin/env python3
"""Deterministic simulation of Gate A Step 0 rung 1, and the single manifest parser.

WHY THIS EXISTS
---------------
`_routing.md` claims which words load which file. Until now nothing executed that
claim; the only instrument that ever caught a routing defect was a full 14-case
subagent re-run. This module makes the claim *runnable*, so `profile-lint.py` can
rule on keyword shape and `eval-impact.py` can rule on which cases a change moved.

It is deliberately ONE function's worth of behaviour. SKILL.md Step 0's resolution
ladder has four rungs; only rung 1 is mechanically decidable:

    1. Literal anchor hit -- "the user's wording CONTAINS a row's trigger keyword"
    2. Scope match against the Covers/role column        <- judgment, not simulated
    3. Two-plus candidates -> ask a disambiguation question <- judgment
    4. No candidate -> generic framework                 <- judgment

Rungs 2-4 are exactly the "prose-forced routing" the eval suite records as an
accepted class (evals.json known_limitation, cases 8 A1 and 10 A3). This module
does not model them and must never be read as ruling on them: a file absent from
`load_set()` is not a routing defect, it is a file that rung 1 alone does not reach.

MATCHING IS CASE-SENSITIVE, AND THAT IS NOT A STYLE CHOICE
----------------------------------------------------------
Measured on the 14 eval prompts, 2026-08-26. Case-insensitive matching makes
`TI` (a `topological_insulator.md` trigger) fire on 4 of 14 prompts -- including
case 1, a CNN image-segmentation question with no physics content, because `ti`
occurs inside ordinary English words. `RIN` (relative intensity noise) fires on
any prompt containing "ring". 38 of the manifest's 302 keywords are ASCII
acronyms of 3 characters or fewer. Lower-casing the corpus manufactures false
loads at exactly the rate the acronyms appear, so the scan matches the case the
manifest author wrote. Chinese keywords are unaffected either way.

MATCHING IS VARIANT-INSENSITIVE, AND THAT IS THE OPPOSITE TRADE (added 2026-08-26)
---------------------------------------------------------------------------------
`fold()` puts prompt and keyword into Unicode NFKC before comparing, so the
compatibility variants of ONE term are one term: `Bi₂Se₃`/`Bi2Se3`, `Z₂`/`Z2`,
`µLED`(U+00B5)/`μLED`(U+03BC), `cm²`/`cm2`, full-width `Ｂｉ２Ｓｅ３`.

This is not the same trade as `_routing.md` § Maintenance's "a false load is worse
than prose-carried routing". That rule governs BROAD keywords -- a generic word that
matches a sibling profile's scenario is a different question wearing the same string.
A variant is the same question wearing a different codepoint, so folding cannot
manufacture a semantically false load; it can only recover a miss. User ruling
2026-08-26: for this class a miss is worse than an extra load, because the consumer
is an LLM that can discard an extra file but cannot read one that never loaded.

Chosen over enumerating variants in the manifest because no hand-written list of
"forms a user might type" is ever complete -- NFKC is Unicode's own equivalence
table, so the long tail is covered without a maintainer remembering it exists.
`profile-lint.py` reports a row that hand-lists two forms of one keyword as
REDUNDANT-VARIANT for the same reason.

Measured over 14 prompts x 302 keywords before adoption: exactly ONE load-set moves
(case 4 gains `bi2se3_material.md`, which is what that case's assertion 1 has always
claimed), 13 prompts unmoved, no keyword changed. NFKC does not case-fold, so the
case-sensitivity result above survives intact (`TI`/`RIN`: 0/14 raw, 0/14 folded).
Known side effect, measured and accepted: NFKC also folds full-width CJK punctuation
(`，`->`,`). One keyword in the whole manifest contains ASCII punctuation that this can
newly reach -- `線寬 (linewidth vs CD)` on a `reference` row, which is pulled on
demand anyway -- and the gain there is recall, not a false load.

Stdlib only. Read-only. No CLI -- this is a library for the two tools above.
"""

import re
import unicodedata

MANIFEST_ROW = re.compile(
    r"^\|\s*(base|sub-profile|reference|boundary)\s*\|\s*`([^`]+)`\s*\|([^|]*)\|([^|]*)\|([^|]*)\|",
    re.M,
)


def fold(text):
    """The canonical form both sides of a keyword comparison are put into.

    NFKC and nothing else. Deliberately NOT casefold(): the case-sensitivity result in
    the module docstring is a measurement, and folding case would revert it silently.
    Every caller that compares a keyword against text must go through here, or the two
    tools drift into different notions of what "matches".
    """
    return unicodedata.normalize("NFKC", text)


def strip_comments(text):
    """Drop HTML-commented blocks -- `_routing.md` keeps example rows in one."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def parse_manifest(routing_text):
    """Return {relpath: {type, parent, keywords, covers}} from `_routing.md` rows.

    `relpath` is relative to `domains/`, forward-slashed. Commented example rows are
    skipped. This is the repo's only manifest parser -- `profile-lint.py` imports it
    rather than keeping a second copy that would drift.
    """
    rows = {}
    for m in MANIFEST_ROW.finditer(strip_comments(routing_text)):
        rel = m.group(2).replace("\\", "/")
        rows[rel] = {
            "type": m.group(1),
            "parent": m.group(3).strip(),
            "keywords": [k.strip() for k in m.group(4).split(",") if k.strip()],
            "covers": m.group(5).strip(),
        }
    return rows


def domain_of(relpath, row):
    """The domain a row belongs to: its parent for a branch, its own stem for a base.

    Two rows sharing a domain are expected to share vocabulary -- a sub-profile
    extends its parent's keywords by design (`_routing.md` How-Gate-A-uses step 3).
    Overlap checks use this to tell an intended family resemblance from a genuine
    cross-domain collision.
    """
    parent = (row.get("parent") or "").strip()
    if parent and parent not in ("-", "—"):
        return parent
    return relpath.rsplit("/", 1)[-1][:-3] if relpath.endswith(".md") else relpath


def load_set(rows, prompt):
    """Step-0 rung 1 over one prompt: {relpath: [keywords that hit]}.

    Substring containment over `fold()`ed text, case-sensitive, in manifest order.
    See the module docstring for why the case is preserved and the variants are not.

    This is a FLAT scan of every row, and that over-approximates documented Gate A on
    purpose. Step 0 is two-level -- `base` rows are always scanned, a `sub-profile` only
    when its parent domain matched, `reference`/`boundary` only when their topic is
    explicitly engaged (SKILL.md Step 0, `_routing.md` How-Gate-A step 3). Measured over
    the 14 eval prompts, the two models differ on cases 4 and 6 only. The flat model is
    kept HERE because this function's consumer is `eval-impact.py`, a selector whose safe
    direction is over-selection: a load-set that is too large re-grades a case that did
    not need it, one that is too small silently skips a case that did. `profile-lint.py`
    is the opposite consumer -- it reports findings a human acts on -- so it applies the
    reachability rule instead of reading this function as ground truth.
    """
    folded = fold(prompt)
    hits = {}
    for rel, row in rows.items():
        matched = [k for k in row["keywords"] if fold(k) in folded]
        if matched:
            hits[rel] = matched
    return hits


def rung1_reachability(rows, rel, row, text):
    """Can `text` alone put row `rel` in play at Step 0 rung 1? True / False / None.

    Documented Gate A is two-level (SKILL.md Step 0; `_routing.md` How-Gate-A steps 2-4):

        base                    always scanned                    -> True
        sub-profile             only if its parent domain matched -> depends on `text`
        reference / boundary    only when their topic is engaged  -> depends on `text`

    So for a non-base row the question reduces to: does `text` reach that row's DOMAIN,
    i.e. contain one of the domain's `base` row keywords?

    `None` means the manifest cannot answer -- the domain has no `base` row at all, so
    there is nothing to test reachability against. It is returned rather than guessed
    because the caller's suppression path is a veto: an instrument may rule only on what
    it can determine, and for everything else the correct output is downgrade-and-forward,
    never a silent dismissal. Callers must treat None as "report it".
    """
    if row.get("type") == "base":
        return True
    domain = domain_of(rel, row)
    base_keywords = [k for r2, row2 in rows.items()
                     if row2.get("type") == "base" and domain_of(r2, row2) == domain
                     for k in row2["keywords"]]
    if not base_keywords:
        return None
    folded = fold(text)
    return any(fold(k) in folded for k in base_keywords)


def token_bounded(needle, haystack):
    """True when `needle` occurs in `haystack` aligned to token boundaries.

    Callers compare `fold()`ed strings -- this function itself is a plain string
    predicate and does no normalization.

    This is the line between the two overlap classes the linter reports:

      boundary-aligned  `KOH` in `KOH etch`         -> a real routing overlap. Every
                        `silicon photonics` in       prompt that legitimately targets
                        `silicon photonics packaging` the longer keyword also loads
                                                     the shorter keyword's file.
      infix             `TI` in `carrier depletion`  -> not a routing overlap between
                        `RIN` in `GRIN coupler`      those two rows; it is evidence
                        `SPP` in `LSPP`              that the short keyword matches
                                                     inside ordinary words at all.

    Reporting both as one finding buries the first class under ~35 rows of the
    second, so they are separated here and reported as different rules.
    """
    for m in re.finditer(re.escape(needle), haystack):
        before = haystack[m.start() - 1] if m.start() > 0 else ""
        after = haystack[m.end()] if m.end() < len(haystack) else ""
        if not (before.isalnum() or after.isalnum()):
            return True
    return False
