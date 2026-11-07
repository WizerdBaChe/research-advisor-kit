#!/usr/bin/env python3
r"""Generated front-matter card on domain profiles (notes-vault design v0.2, C-3 / D-6).

WHY
---
The Obsidian vault `<NOTES_VAULT>` mounts this skill's `domains/` as a wing, and the
cross-index union query reaches a file only through a card. Each manifest-registered
profile therefore carries a LEADING YAML block that is (a) an Obsidian properties block,
(b) a cross-index card, and (c) DERIVED from `_routing.md` — never hand-edited. The
block is a §3.8 category-1 structural retrofit: every value already exists in the
manifest row or the file itself, nothing is invented. Measured before adoption
(2026-09-02 probe): profile-lint output identical with and without the block
(0 FAIL / 25 WARN), xi_cards accepts 21/21.

WHAT THE BLOCK CONTAINS
-----------------------
    xi: 1
    what: "<H1 minus 'Domain Profile:'> — <Covers/role cell>"
    tags: [srg-domain, 領域框架, <type>]      # 領域框架 = the CJK half of the bilingual card
    aliases: ["<every Load-trigger keyword of the row>"]
    date: <'Last updated:' date in the file, else the existing card's date, else today>
    status: live
    profile_type: <type>
    parent: "<parent | ->"

No Chinese translation of a domain name is generated (LexiconVault D2: no invented
translations); the CJK requirement of the card grammar is met by the fixed tag.
Keywords are the row's own words, so Obsidian's property panel and the union query see
exactly what routing sees.

CLOSURE (imported by profile-lint.py as FM-CLOSURE, FAIL)
--------------------------------------------------------
Adoption is detected from the tree: if at least one manifest file carries a card, every
manifest file must, and each card's aliases (NFKC-folded set), profile_type and parent
must equal the manifest row. A tree with no cards at all (the seeded fixtures) is not
judged — the rule cannot fire there, which keeps the documented fixture counts intact.
Positive control: evals/fixtures/frontmatter-drift (one drifted alias + one missing
card = exactly 2 FAIL).

Usage:
  python tools/profile_frontmatter.py --check          # exit 1 on any drift
  python tools/profile_frontmatter.py --sync           # rewrite the leading block only
  python tools/profile_frontmatter.py --strip          # remove the block (rollback)
  add --root <skill-root> to target another tree.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from routing_sim import fold, parse_manifest  # noqa: E402

H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)
LAST_UPDATED = re.compile(r"Last updated(?: \([^)]*\))?:\s*(\d{4}-\d{2}-\d{2})")
FIXED_TAGS = ("srg-domain", "領域框架")


def split_card(text: str):
    """(card_lines | None, body). A card is a leading '---' block."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[: i + 1], "".join(lines[i + 1:])
    return None, text


def parse_card(card_lines):
    """Flat key -> str | list, same grammar subset xi_cards reads."""
    out = {}
    for ln in card_lines[1:-1]:
        if ": " not in ln:
            continue
        k, v = ln.split(": ", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            items = [i.strip().strip("'\"") for i in v[1:-1].split(",")]
            out[k.strip()] = [i for i in items if i]
        else:
            out[k.strip()] = v.strip("'\"")
    return out


def _q(s: str) -> str:
    return '"' + s.replace('"', "'") + '"'


def expected_card(rel: str, row: dict, body: str, prior: dict | None) -> str:
    m = H1.search(body)
    title = re.sub(r"^Domain Profile:\s*", "", m.group(1)) if m else rel
    covers = " ".join(row["covers"].split())
    dm = LAST_UPDATED.search(body)
    if dm:
        date = dm.group(1)
    elif prior and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(prior.get("date", ""))):
        date = prior["date"]
    else:
        date = _dt.date.today().isoformat()
    parent = row["parent"] if row["parent"] and row["parent"] not in ("-", "—") else "-"
    aliases = ", ".join(_q(k) for k in row["keywords"])
    return (
        "---\n"
        "xi: 1\n"
        f"what: {_q(title + ' — ' + covers)}\n"
        f"tags: [{', '.join(FIXED_TAGS)}, {row['type']}]\n"
        f"aliases: [{aliases}]\n"
        f"date: {date}\n"
        "status: live\n"
        f"profile_type: {row['type']}\n"
        f"parent: {_q(parent)}\n"
        "---\n"
    )


def check_tree(domains: Path, manifest: dict):
    """FM-CLOSURE findings as (sev, rel, msg). Silent when no manifest file has a card."""
    findings = []
    cards = {}
    for rel in manifest:
        p = domains / rel
        if not p.exists():
            continue  # manifest closure is profile-lint's own FAIL
        card, _ = split_card(p.read_text(encoding="utf-8"))
        cards[rel] = parse_card(card) if card else None
    if not any(cards.values()):
        return findings
    for rel, card in cards.items():
        row = manifest[rel]
        if card is None:
            findings.append(("FAIL", rel, "FM-CLOSURE: no generated card while sibling profiles carry one — run tools/profile_frontmatter.py --sync"))
            continue
        want = {fold(k) for k in row["keywords"]}
        have = {fold(a) for a in (card.get("aliases") or [])}
        if want != have:
            missing = sorted(want - have)
            extra = sorted(have - want)
            findings.append(("FAIL", rel, f"FM-CLOSURE: aliases drift from the manifest row (missing {missing}, extra {extra}) — never hand-edit; run --sync"))
        if card.get("profile_type") != row["type"]:
            findings.append(("FAIL", rel, f"FM-CLOSURE: profile_type `{card.get('profile_type')}` != manifest type `{row['type']}`"))
        parent = row["parent"] if row["parent"] and row["parent"] not in ("-", "—") else "-"
        if (card.get("parent") or "-") != parent:
            findings.append(("FAIL", rel, f"FM-CLOSURE: parent `{card.get('parent')}` != manifest parent `{parent}`"))
        if str(card.get("xi")) != "1":
            findings.append(("FAIL", rel, "FM-CLOSURE: card lacks `xi: 1`"))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--sync", action="store_true")
    g.add_argument("--strip", action="store_true")
    args = ap.parse_args()
    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    domains = root / "domains"
    manifest = parse_manifest((domains / "_routing.md").read_text(encoding="utf-8"))

    if args.check:
        f = check_tree(domains, manifest)
        for sev, rel, msg in f:
            print(f"{sev}  {rel}: {msg}")
        print(f"profile_frontmatter --check: {len(f)} FAIL over {len(manifest)} manifest rows")
        return 1 if f else 0

    changed = 0
    for rel, row in manifest.items():
        p = domains / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        card, body = split_card(text)
        if args.strip:
            if card:
                p.write_text(body, encoding="utf-8")
                changed += 1
            continue
        prior = parse_card(card) if card else None
        new = expected_card(rel, row, body, prior)
        if (card and "".join(card) == new):
            continue
        p.write_text(new + body, encoding="utf-8")
        changed += 1
    print(f"profile_frontmatter --{'strip' if args.strip else 'sync'}: {changed} file(s) changed of {len(manifest)}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
