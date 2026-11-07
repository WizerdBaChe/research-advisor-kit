#!/usr/bin/env python3
"""Deterministic structural linter for scientific-research-guide domain profiles.

Rules only on what it can DETERMINE (headings, table header cells, marker regexes,
manifest closure). Judgment-level properties (blank cells inside rows, semantic
duplication, citation-key <-> ledger closure) are deliberately out of scope: pipe
characters inside math/abs-value notation make naive cell splitting unreliable, and
a wrong instrument is worse than none (see STATUS.md 2026-08-24, the web:39/54
parsing artifact). Those stay with the human checklist in domain-expansion-guide.md
section 6.

Severity: FAIL (exit 1) for base-profile schema violations, abolished-node residue,
opaque citation markers, manifest closure breaks, and overlap-register closure breaks;
WARN for legacy sub-profile schema drift and for the two routing-anchor checks below
(recorded debt, not silently passed).

ROUTING-ANCHOR CHECKS (added 2026-08-26)
----------------------------------------
`_routing.md` § Maintenance has required since 2026-08-24 that a trigger keyword be a
word the asking user would type, and `domain-expansion-guide.md` §9 step 4 has required
checking a new row's keywords "against every sibling row". Both were enforced only by
human review at authoring time. §3.8's invariant — the remaining gap is surfaced by
instrument, not prose — is what these two checks close.

  KEYWORD-OVERLAP (WARN)  keyword K of one row occurs, aligned to token boundaries,
      inside a keyword of a row in a DIFFERENT domain -- so any prompt that legitimately
      targets the second row also loads the first. Exceptions come from `_routing.md`
      § Known keyword overlaps and from nothing else; same-domain pairs are exempt in
      code (a sub-profile extending its parent's vocabulary is the designed behaviour).
      Containment, not equality, is the test on purpose: on first run this check found
      that `ring-to-ring thermal crosstalk` re-collides with `siph_packaging_reliability`'s
      `thermal crosstalk` -- the very collision the 2026-08-26 authoring pass believed it
      had avoided by not reusing the string verbatim. An equality check reproduces the
      author's own eyeball and would have agreed with them.
  WEAK-ANCHOR (WARN)      a short ASCII keyword that occurs as a bare infix inside
      another domain's keyword -- evidence that it matches inside ordinary words rather
      than at a token boundary. `TI` and `RIN` are the live examples; both are safe today
      only because `routing_sim.load_set()` matches case-sensitively.
  REDUNDANT-VARIANT (WARN) one row lists two keywords that are the same string under
      `routing_sim.fold()` (`Bi2Se3` beside `Bi₂Se₃`). Matching is variant-insensitive,
      so the second form buys no recall -- and a manifest that starts accreting
      hand-written variants is the enumeration the fold exists to replace. Added
      2026-08-26 with the fold, so the mechanism cannot rot back into a keyword list.

None is FAIL yet, and the promotion trigger is named rather than left to "revisit
later": promote when (a) the check has fired on a real authoring pass at least once, AND
(b) the exception register has survived one profile addition without needing an ad-hoc
entry. Until both hold, a wrong instrument is worse than none.

Register closure is FAIL from the start -- determinable closure, the same class already
enforced below. Two shapes: a row naming a FILE with no manifest row, and a DEAD row whose
keyword no overlap between the two named rows can consume. The second exists because the
column holds the SHORT (contained) keyword; a row naming the containing spelling is a real
keyword of a real file and still exempts nothing, so it reads as a standing ruling while
doing nothing. Both fixtures for it are seeded in `evals/fixtures/routing-collision`.

REACHABILITY: WHY SOME OVERLAPS ARE NOT REPORTED (added 2026-08-26)
------------------------------------------------------------------
KEYWORD-OVERLAP's claim is "a prompt matching the LONG keyword also loads the short
keyword's file". That claim needs the short keyword's row to be reachable, and under
documented Gate A not every row is: Step 0 is two-level, so a `sub-profile` is scanned
only when its parent domain matched, and `reference`/`boundary` rows are pulled only
when their topic is engaged. `routing_sim.rung1_reachability()` decides it from the
manifest alone -- does the long keyword contain one of the short row's DOMAIN's base
keywords? Two findings open on 2026-08-26 were this false positive and nothing else:
`KOH` (a topological-insulator sub-profile) inside `KOH etch`, and `depletion` (a
plasmonics sub-profile) inside `carrier depletion` -- neither containing keyword reaches
its domain's base row, so no prompt matching only it can load that file.

This LOOSENS the check, so two things are deliberate. (1) `None` (the domain has no base
row, so reachability is undeterminable) reports, never suppresses -- downgrade-and-forward,
not veto. (2) The fixture carries a reachable sub-profile pair that must still fire; if
that row ever goes silent the loosening has over-reached, which is the regression this
change ships with.

`routing_sim.load_set()` keeps the FLAT model on purpose -- see its docstring. The two
tools want opposite errors: the selector must over-select, this reporter must not cry
wolf, and the severity of each belongs with its own consumer.

Usage:  python tools/profile-lint.py [--root <skill-root>]
Calibration: run against a fixture tree with seeded violations before trusting a
clean report. Two-sided, in BOTH directions -- a gate that rejects everything scores
100% on a one-sided calibration:
    known-bad   python tools/profile-lint.py --root evals/fixtures/routing-collision
                must report 2 FAIL + 6 WARN, exactly:
                  FAIL  file-closure (`phantom`) and dead-row (`widget etch`)
                  WARN  4 KEYWORD-OVERLAP, one of each reportable shape -- undeterminable
                        reachability (`widget`), reachable non-base row (`flange`), base
                        row (`delta rig`), and a pair that collides only after folding
                        (`TiO2 film`/`TiO₂ film`)
                  WARN  1 WEAK-ANCHOR (`TIM`), 1 REDUNDANT-VARIANT (`mu2`/`mu₂ form`)
                Silent in the same fixture, and each is a control in its own right: a
                same-domain pair, a declared pair, and an UNreachable non-base pair
                (`sprocket`). `flange` going silent means the reachability rule has
                over-reached; `sprocket` firing means it is not being applied.
    live tree   python tools/profile-lint.py
                0 FAIL, 0 KEYWORD-OVERLAP, 0 REDUNDANT-VARIANT, 2 WEAK-ANCHOR.

FM-CLOSURE (FAIL, added 2026-09-02, imported from tools/profile_frontmatter.py)
----------------------------------------------------------------------------
Each manifest-registered profile carries a GENERATED leading YAML card (Obsidian
properties + cross-index card) derived from its `_routing.md` row. The rule: once any
manifest file in a tree carries a card, every manifest file must, and each card's
aliases (folded set) / profile_type / parent must equal its row. A tree with no cards is
not judged, so the routing-collision fixture counts above are unchanged. Never hand-edit
the block — `profile_frontmatter.py --sync` regenerates it.
    known-bad   python tools/profile-lint.py --root evals/fixtures/frontmatter-drift
                must report exactly 2 FAIL (drifted alias, missing card), 0 WARN.

                READ THIS BEFORE TRUSTING THAT LINE. Until 2026-08-26 the live tree was
                itself the positive control for KEYWORD-OVERLAP -- it held four real
                findings, so a clean report meant a broken check. That triage closed all
                four (two declared, two removed as instrument false positives), so the
                live tree is now a clean control ONLY, and it can no longer tell a working
                check from a check that returns nothing. The fixture is the only remaining
                positive control for these rules and must be run beside the live tree, not
                instead of it.
"""

import argparse
import re
import sys
from pathlib import Path

from routing_sim import (domain_of, fold, parse_manifest, rung1_reachability,
                         strip_comments, token_bounded)
from profile_frontmatter import check_tree as fm_check_tree

# Required-core columns per node (domain-expansion-guide.md section 3.3 rule 2).
# Matching is substring-based so parenthesised elaborations ("Conditions (material/...)")
# and free extra columns pass.
NODE_CORE = {
    # Node 2's identity column legitimately varies (Measurement target / Tool / Stress);
    # only the payload columns are core.
    "2": ["Applicable conditions", "Common misuse"],
    "4": ["Method", "Applicable conditions", "Common error", "Correct approach"],
    "5": ["Metric", "Typical value range", "Conditions"],
    "6": ["Pitfall", "Trigger condition", "Correct approach"],
}
SOURCE_COL = "Source"  # additionally required on base profiles for nodes 2/4/5/6

OPAQUE = re.compile(r"\[(?:web|ref):\d+\]|\[\^\d+\]")
CHECKLIST = "AI Decision-Trigger Checklist"
DECISION_POINT = "Decision point (mandatory Tier 0 confirmation)"
AUTHORING_NOTES = re.compile(r"^### Authoring notes", re.M)

EXCLUDED = {"_template.md", "_routing.md", "domain-expansion-guide.md"}

# (label, "bare designation" pattern, "row records a pin" pattern) — guide section 3.7.
# The bare patterns deliberately exclude an immediately-following revision character, so a
# pinned designation (JESD22-B103B.01, JESD22-B104C) does not match at all. Calibrated
# two-sided on the live tree: the bare JESD22-A1xx rows fire, the pinned B103/B104 rows
# do not.
UNPINNED_STANDARD_PATTERNS = [
    # JEDEC pins the revision as a letter fused to the designation (JESD22-B103B.01), so the
    # bare pattern excludes a following letter and the pin pattern accepts that fused form.
    # A pin is a VALUE, never the word — "issue letter still unpinned" and "no edition is
    # pinned" must NOT read as pins. Matched case-sensitively on purpose: under re.I a
    # `[A-Z]` revision letter also matches lowercase prose, which silently pinned every row.
    ("a JEDEC standard", r"JESD\d+-[A-Z]\d+(?![A-Za-z0-9.])",
     r"(?:JESD\d+-[A-Z]\d+[A-Z](?:\.\d+)?|Issue\s*\d|[Rr]ev(?:ision)?\s*\**[A-Z]\b)"),
    ("a Telcordia standard", r"\bGR-\d+\b", r"Issue\s*\d"),
    ("an IEC standard", r"\bIEC\s?\d{4,5}\b", r"(?:Ed(?:ition)?\.?\s*\**\d|:\s*20\d\d)"),
    ("a MIL standard", r"\bMIL-STD-\d+\b",
     r"(?:[Rr]ev(?:ision)?\s*\**[A-Z]\b|:\s*20\d\d|-\d{4}\b)"),
]


def ledger_rows(seg):
    """Body rows of the Source Ledger table proper.

    A ledger section can hold further tables (provenance/correction logs); their rows are
    not citation rows and must not be judged as if they were."""
    rows, in_table = [], False
    for line in seg.splitlines():
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0].lower() == "key":
            in_table = True
            continue
        if in_table and not set("".join(cells)) <= set("-: "):
            rows.append(line)
    return rows


OVERLAP_SECTION = "## Known keyword overlaps"
OVERLAP_ROW = re.compile(
    r"^\|\s*`([^`]+\.md)`\s*\|\s*`([^`]+\.md)`\s*\|\s*`([^`]+)`\s*\|", re.M
)


def parse_overlap_register(routing_text):
    """Return {(fileA, fileB, keyword)} declared in _routing.md's exception register.

    Scoped to that one section on purpose: the manifest and the disambiguation tables
    also contain backticked file names, and a register that quietly absorbed them would
    exempt everything (see the section's own note on why the disambiguation tables are
    NOT the source of truth here)."""
    text = strip_comments(routing_text)
    i = text.find(OVERLAP_SECTION)
    if i < 0:
        return set()
    nxt = re.search(r"^## ", text[i + len(OVERLAP_SECTION):], re.M)
    seg = text[i: i + len(OVERLAP_SECTION) + (nxt.start() if nxt else len(text))]
    return {(m.group(1), m.group(2), m.group(3)) for m in OVERLAP_ROW.finditer(seg)}


def overlap_candidates(rows):
    """Every exemption key a real cross-domain overlap could consume: (pair, folded kw).

    Computed BEFORE exemption and BEFORE the reachability filter, so a register row is
    judged dead only when the two keywords genuinely do not overlap — the one thing that
    is unarguable. A row whose overlap exists but is also suppressed for another reason
    is redundant, not wrong, and is left alone.
    """
    keys = set()
    for a, ra in rows.items():
        for b, rb in rows.items():
            if a == b or domain_of(a, ra) == domain_of(b, rb):
                continue
            for ka in ra["keywords"]:
                for kb in rb["keywords"]:
                    if token_bounded(fold(ka), fold(kb)):
                        keys.add((frozenset((a, b)), fold(ka)))
    return keys


def check_keyword_overlaps(rows, register, findings):
    """KEYWORD-OVERLAP + WEAK-ANCHOR + REDUNDANT-VARIANT over the manifest's keywords.

    Every comparison runs on `fold()`ed keywords, the same space `load_set()` matches in.
    Comparing raw strings here would report collisions the matcher does not have, and miss
    the ones it does (`TiO2 cladding` vs `TiO₂ cladding` are one keyword to the matcher).
    """
    exempt = {(frozenset((a, b)), fold(kw)) for a, b, kw in register}

    seen = set()
    for a, ra in rows.items():
        for b, rb in rows.items():
            if a == b or domain_of(a, ra) == domain_of(b, rb):
                continue
            for ka in ra["keywords"]:
                for kb in rb["keywords"]:
                    fa, fb = fold(ka), fold(kb)
                    if not token_bounded(fa, fb):
                        continue
                    # Folded key: an identical pair is reported from both directions
                    # otherwise, and a variant pair from both spellings.
                    key = (frozenset((a, b)), fa, fb)
                    if key in seen or (frozenset((a, b)), fa) in exempt:
                        continue
                    seen.add(key)
                    # Can a prompt whose only relevant hit is `kb` reach row `a` at all?
                    # None = the manifest cannot say -> report (see module docstring).
                    if rung1_reachability(rows, a, ra, kb) is False:
                        continue
                    how = ("identical" if fa == fb
                           else f"'{ka}' is contained in '{kb}'")
                    if fa == fb and ka != kb:
                        how = f"identical after Unicode folding ('{ka}' / '{kb}')"
                    findings.append((
                        "WARN", "_routing.md",
                        f"KEYWORD-OVERLAP: {a} and {b} are different domains but their "
                        f"triggers overlap ({how}) — a prompt matching '{kb}' loads both. "
                        f"Narrow one keyword, or declare the pair in § Known keyword overlaps",
                    ))

    for a, ra in rows.items():
        for k in ra["keywords"]:
            fk = fold(k)
            if len(fk) > 3 or not fk.isascii() or not fk.isalnum():
                continue
            for b, rb in rows.items():
                if a == b or domain_of(a, ra) == domain_of(b, rb):
                    continue
                infix = next((kb for kb in rb["keywords"]
                              if fk in fold(kb) and not token_bounded(fk, fold(kb))), None)
                if infix:
                    findings.append((
                        "WARN", "_routing.md",
                        f"WEAK-ANCHOR: {a}'s trigger '{k}' matches inside ordinary words "
                        f"(it occurs as a bare infix in {b}'s '{infix}'). Safe today only "
                        f"because the Step-0 scan is case-sensitive — do not lower-case it, "
                        f"and prefer a longer anchor if one exists",
                    ))
                    break

    for a, ra in rows.items():
        by_fold = {}
        for k in ra["keywords"]:
            by_fold.setdefault(fold(k), []).append(k)
        for canonical, spellings in by_fold.items():
            if len(spellings) > 1:
                findings.append((
                    "WARN", "_routing.md",
                    f"REDUNDANT-VARIANT: {a} lists {' and '.join(repr(s) for s in spellings)}, "
                    f"which are one keyword ('{canonical}') to the matcher — matching is "
                    f"variant-insensitive, so keep one spelling and delete the rest",
                ))


def table_headers_in(seg):
    """Return header-cell lists for every markdown table in a text segment."""
    headers = []
    lines = seg.splitlines()
    for i, ln in enumerate(lines):
        if re.match(r"^\|[\s:-]+\|", ln.replace("-", "-")) and i > 0 and lines[i - 1].startswith("|"):
            # separator row -> previous line is a header row
            cells = [c.strip() for c in lines[i - 1].strip().strip("|").split("|")]
            headers.append(cells)
    return headers


def tables_under_node(text, node_num):
    """Yield header-cell lists for every table between a node heading and the next H2.

    Node headings tolerated: '## 4.', '## Node 4.', '## 4. Branch-Specific ...'."""
    pat = re.compile(r"^##+\s*(?:Node\s*)?" + node_num + r"\.", re.M)
    m = pat.search(text)
    if not m:
        return None  # node absent
    nxt = re.search(r"^## ", text[m.end():], re.M)
    seg = text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]
    return table_headers_in(seg)


def check_profile(path, text, kind, findings):
    rel = path.as_posix()

    if CHECKLIST in text:
        findings.append(("FAIL", rel, "abolished 'AI Decision-Trigger Checklist' section/reference present (guide section 3.6)"))
    # Opaque markers are forbidden only where they would be USED as citations: Nodes 1-6.
    # A ledger/provenance log legitimately QUOTES the packet's original [^N] indices as the
    # audited defect (guide section 3.4 scopes its command the same way).
    m1 = re.search(r"^##+\s*(?:Node\s*)?1\.", text, re.M)
    m7 = re.search(r"^##+ .*(?:Literature Anchors|Source Ledger|Evidence Anchors)", text, re.M)
    start = m1.start() if m1 else 0
    end = m7.start() if (m7 and m7.start() > start) else len(text)
    body = text[start:end]
    for m in OPAQUE.finditer(body):
        findings.append(("FAIL", rel, f"opaque citation marker {m.group(0)} inside Nodes 1-6 (guide section 3.2/3.4)"))

    if kind == "base":
        for n in ["1", "2", "3", "4", "5", "6"]:
            if not re.search(r"^##+\s*(?:Node\s*)?" + n + r"\.", text, re.M):
                findings.append(("FAIL", rel, f"missing required Node {n} heading"))
        if not re.search(r"^##+ .*Literature Anchors", text, re.M):
            findings.append(("FAIL", rel, "missing Node 7a (Literature Anchors) heading"))
        if not re.search(r"^##+ .*Source Ledger", text, re.M):
            findings.append(("FAIL", rel, "missing Node 7b (Source Ledger) heading"))
        if DECISION_POINT not in text:
            findings.append(("FAIL", rel, "missing canonical 'Decision point (mandatory Tier 0 confirmation)' block"))
        # Guide section 3.7: ledger rows carry a per-citation currency date. WARN, not FAIL —
        # profiles predating the column are recorded debt, remediated at each file's next
        # content touch; this keeps the remaining list re-derived every run instead of
        # trusted from STATUS.md prose.
        mledg = re.search(r"^##+ .*Source Ledger", text, re.M)
        if mledg:
            nxt = re.search(r"^## ", text[mledg.end():], re.M)
            seg = text[mledg.end(): mledg.end() + nxt.start()] if nxt else text[mledg.end():]
            lheaders = table_headers_in(seg)
            if lheaders and not any(
                any("Verified (date)" in cell for cell in cells) for cells in lheaders
            ):
                findings.append(("WARN", rel, "Source Ledger table lacks 'Verified (date)' column (guide section 3.7 — pre-3.7 debt, add at next content touch)"))
            # Guide section 3.7 version pinning: a versioned source must name the exact
            # issue/edition consulted. A bare standard designation is the versioned-source
            # equivalent of an undated verification — without it, "review-when: the next
            # revision" is undecidable. Property of the asset, checked per ledger row.
            for row in ledger_rows(seg):
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                # Look for the designation only where the row *identifies its source*
                # (Full citation, Identifier). A status cell that merely mentions a standard
                # in prose is not this row's source. Accept a pin recorded anywhere in the row.
                where = " | ".join(cells[1:3])
                for label, pat, pinned in UNPINNED_STANDARD_PATTERNS:
                    m = re.search(pat, where)
                    if m and not re.search(pinned, row):
                        findings.append((
                            "WARN", rel,
                            f"Source Ledger row '{cells[0]}' cites {label} '{m.group(0)}' with no "
                            f"issue/edition/revision recorded (guide section 3.7 version pinning)",
                        ))

    sev = "FAIL" if kind == "base" else "WARN"
    for n, core in NODE_CORE.items():
        headers = tables_under_node(text, n)
        if headers is None:
            continue  # sub-profiles legitimately omit nodes; base absence caught above
        if not headers:
            findings.append((sev, rel, f"Node {n}: no table found under the node heading"))
            continue
        for cells in headers:
            missing = [c for c in core if not any(c in cell for cell in cells)]
            if kind == "base" and not any(SOURCE_COL in cell for cell in cells):
                missing.append("Source [Key]")
            if missing:
                findings.append((sev, rel, f"Node {n} table missing core column(s): {', '.join(missing)} (header: {' | '.join(cells)})"))

    if kind == "sub-profile":
        if not re.search(r"^##+\s*(?:Node\s*)?6\.", text, re.M):
            findings.append(("FAIL", rel, "sub-profile without its own Node 6 (branch pitfalls) — that is what makes it a sub-profile (guide section 8)"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="skill root (default: parent of this script's directory)")
    args = ap.parse_args()
    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    domains = root / "domains"
    if not domains.is_dir():
        print(f"no domains/ under {root}", file=sys.stderr)
        return 2

    findings = []

    routing = domains / "_routing.md"
    manifest = {}
    if routing.exists():
        routing_text = routing.read_text(encoding="utf-8")
        manifest = parse_manifest(routing_text)
        for relf in manifest:
            if not (domains / relf).exists():
                findings.append(("FAIL", "_routing.md", f"manifest row points at missing file: {relf}"))
        register = parse_overlap_register(routing_text)
        candidates = overlap_candidates(manifest)
        # Register closure, FAIL: an exception row naming a file with no manifest row
        # silently exempts nothing (or worse, keeps exempting a pair after a rename).
        # This is the hole that scraping the disambiguation tables opened -- that scan
        # harvests `cpo.md`, a file declared never to exist.
        for a, b, kw in sorted(register):
            named = [f for f in (a, b) if f not in manifest]
            for f in named:
                findings.append((
                    "FAIL", "_routing.md",
                    f"§ Known keyword overlaps row '{kw}' names {f}, which has no "
                    f"manifest row",
                ))
            # Dead-row closure, FAIL: the column holds the SHORT (contained) keyword, and
            # this row's whole effect is to consume one exemption key. If that pair has no
            # such overlap at all, the row silences nothing while reading as a ruling that
            # was made and is still holding -- worse than a missing row. The live example
            # that motivated it: a second row naming `microring thermal crosstalk`, the
            # CONTAINING spelling, which is a real keyword of a real row and still exempts
            # nothing. A keyword-membership test passes that row; only asking whether an
            # overlap exists catches it. Determinable, so FAIL like the closure above.
            if not named and (frozenset((a, b)), fold(kw)) not in candidates:
                findings.append((
                    "FAIL", "_routing.md",
                    f"§ Known keyword overlaps row '{kw}' suppresses nothing — {a} and {b} "
                    f"have no overlap on that keyword. The column holds the SHORT "
                    f"(contained) keyword, never the containing one",
                ))
        check_keyword_overlaps(manifest, register, findings)
    else:
        findings.append(("FAIL", "domains/", "_routing.md missing"))

    for path in sorted(domains.rglob("*.md")):
        rel = path.relative_to(domains).as_posix()
        if path.name in EXCLUDED:
            if path.name == "domain-expansion-guide.md":
                continue
            if path.name == "_template.md":
                continue  # carries the forbidden examples on purpose
            continue
        text = path.read_text(encoding="utf-8")

        if AUTHORING_NOTES.search(text):
            findings.append(("FAIL", rel, "template '### Authoring notes' scaffolding present (guide section 6)"))

        in_manifest = rel in manifest
        if not in_manifest:
            findings.append(("FAIL", rel, "file exists but has no _routing.md manifest row"))
        kind = (manifest[rel]["type"] if in_manifest
                else ("base" if "/" not in rel else "reference"))
        if kind in ("reference", "boundary"):
            for m in OPAQUE.finditer(text):
                findings.append(("FAIL", rel, f"opaque citation marker {m.group(0)}"))
            continue
        check_profile(Path(rel), text, kind, findings)

    # FM-CLOSURE: generated front-matter card <-> manifest row agreement (see docstring).
    if manifest:
        findings.extend(fm_check_tree(domains, manifest))

    fails = [f for f in findings if f[0] == "FAIL"]
    warns = [f for f in findings if f[0] == "WARN"]
    for sev, rel, msg in fails + warns:
        print(f"{sev}  {rel}: {msg}")
    print(f"\nprofile-lint: {len(fails)} FAIL, {len(warns)} WARN "
          f"({len(manifest)} manifest rows checked under {domains})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
