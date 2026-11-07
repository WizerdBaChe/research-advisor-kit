#!/usr/bin/env python3
r"""staleclaim - catch a measured number that stopped being true.

THE BUG THIS EXISTS FOR (real, 2026-08-27). The backlog file — then named
FUTURE-WORK.md, renamed owner-first the same day — said SKILL.md was
"261 lines". That was true on 2026-07-12 and false from 2026-07-19, when the
file was trimmed to 250. It sat wrong for five weeks, and then a later session
took it as a BASELINE and did arithmetic on it, producing a second wrong number
in a new document. Nobody lied; nobody re-measured either.

The skill's P4.5 gate exists to stop exactly this - an unverified number
propagating - and the skill's own backlog was doing it. A convention in a file
header does not fix that, because the convention is only as good as the reader's
memory of it. This checker is the part that does not need to remember.

WHAT IT RULES ON, and only this (gate-severity-by-consumer, 2026-08-26):

  FAIL - determinable and closed: a document claims "<file> ... N lines" and
         the file does not have N lines. Re-measuring is one wc -l; there is
         no judgement involved, so there is no excuse for a WARN.
  WARN - undeterminable here: a section carries a measured-looking quantity
         with no date anywhere near it. Cannot tell intent from text, so it
         reports and forwards. PROMOTION TRIGGER, named: if a WARN here is
         ever confirmed as a real stale number, that pattern graduates to FAIL.
  IGNORED on purpose: numbers next to a budget/cap word (upper bound, not a
         measurement), and years inside citations or identifiers.

SCOPE - deliberately local. Pilot on this skill only. It widens to ~/.claude
when it has caught something real that a human agreed was worth catching, and
not before: a doc-hygiene checker that cries wolf across the whole environment
gets muted, and a muted checker is worse than none.

Usage:
    python staleclaim.py                    check this skill
    python staleclaim.py --path <dir|file>  check elsewhere
    python staleclaim.py --selftest         two-sided calibration
Exit: 0 = no FAIL, 1 = at least one FAIL, 2 = bad usage.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent

# --- CONFIG: single edit point --------------------------------------------
FILE_REF = re.compile(r"([\w./-]+\.(?:md|py|json|txt|yaml|yml))")
# "291 lines" / "291 行" / "291-line", with optional markdown emphasis.
LINE_CLAIM = re.compile(r"(?<![\d.])(\d{2,5})\s*\**\s*(?:行|lines?|-line)\b", re.I)
# A number that is an upper bound, not a measurement, is not this tool's business.
BUDGET_NEAR = re.compile(r"(上限|上界|預算|budget|cap\b|limit|至多|最多|max\b)", re.I)
# Any of these makes a quantity look measured rather than referential.
QUANTITY_WORD = re.compile(r"(\d[\d,]*)\s*\**\s*(行|lines?|篇|files?|entries|"
                           r"cases?|筆|個檔|connectors?|PDFs?|MB|KB)\b", re.I)
DATE_NEAR = re.compile(r"(20\d{2}-\d{2}-\d{2}|20\d{2}/\d{1,2}/\d{1,2})")
# Sections that are explicitly historical are supposed to hold old numbers.
HISTORICAL = re.compile(r"(更正|correction|was true|封存|archive|tombstone|"
                        r"retired|歷史|previously|量測（|實證|baseline)", re.I)
# ---------------------------------------------------------------------------


def sections(text: str) -> list[tuple[int, str]]:
    """Split on markdown headings. Returns (start_line_no, section_text)."""
    lines = text.splitlines()
    out, start, buf = [], 1, []
    for i, ln in enumerate(lines, 1):
        if ln.startswith("#") and buf:
            out.append((start, "\n".join(buf)))
            start, buf = i, [ln]
        else:
            buf.append(ln)
    if buf:
        out.append((start, "\n".join(buf)))
    return out


def is_bound(sec: str, start: int, end: int) -> bool:
    """Is THIS number an upper bound rather than a measurement?

    Scope the question to the span between this number and its neighbours, not
    a fixed character window. The fixed window was the first version and it was
    wrong on the very case this tool was written for: "現 261 行，超過 250 行軟
    上限" puts a bound word five characters from a measurement, so a +/-40
    window let 250's 上限 vouch for 261 and the real bug walked straight past a
    green self-test. A keyword only speaks for the number it is adjacent to.
    """
    after = sec[end:]
    nxt = re.search(r"\d", after)
    if BUDGET_NEAR.search(after[:nxt.start()] if nxt else after):
        return True
    before = sec[:start]
    prev = None
    for m in re.finditer(r"\d", before):
        prev = m
    return bool(BUDGET_NEAR.search(before[prev.end():] if prev else before))


def measure_lines(name: str, base: Path) -> int | None:
    for cand in (base / name, SKILL_ROOT / name, base.parent / name):
        try:
            if cand.is_file():
                return len(cand.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    return None


def check_text(text: str, doc: Path, base: Path) -> list[tuple[str, str, str]]:
    findings: list[tuple[str, str, str]] = []
    for start, sec in sections(text):
        if HISTORICAL.search(sec):
            continue                      # a correction record must quote old numbers
        files = FILE_REF.findall(sec)
        for m in LINE_CLAIM.finditer(sec):
            if is_bound(sec, m.start(), m.end()):
                continue
            claimed = int(m.group(1))
            for fname in dict.fromkeys(files):
                actual = measure_lines(fname, base)
                if actual is None:
                    continue
                if actual == claimed:
                    break
            else:
                targets = [f for f in dict.fromkeys(files)
                           if measure_lines(f, base) is not None]
                if targets:
                    real = ", ".join(f"{f}={measure_lines(f, base)}" for f in targets)
                    findings.append((
                        f"{doc.name}:~{start}", "FAIL",
                        f"claims {claimed} lines, but nothing in this section has "
                        f"that many ({real}). Re-measure or delete the number."))
        # heuristic half
        for q in QUANTITY_WORD.finditer(sec):
            window = sec[max(0, q.start() - 120):q.end() + 120]
            if BUDGET_NEAR.search(window) or DATE_NEAR.search(window):
                continue
            findings.append((
                f"{doc.name}:~{start}", "WARN",
                f"quantity {q.group(0).strip()!r} with no measurement date within "
                f"120 chars. Undeterminable here - if it is a measured value it "
                f"needs a date and a re-take command; if it is a reference or a "
                f"bound, it is fine as is."))
            break                          # one WARN per section is enough
    return findings


# A saved run is a snapshot of what was true when it ran. Re-measuring it is
# meaningless, and warning about it every time is how a checker gets muted.
FROZEN_DIRS = {"evals", "archive", "outputs"}


def run(target: Path) -> list[tuple[str, str, str]]:
    docs = sorted(target.rglob("*.md")) if target.is_dir() else [target]
    docs = [d for d in docs if not FROZEN_DIRS & set(p.name for p in d.parents)]
    out = []
    for d in docs:
        try:
            out.extend(check_text(d.read_text(encoding="utf-8", errors="replace"),
                                  d, d.parent))
        except OSError:
            continue
    return out


def selftest() -> int:
    import tempfile
    bad = 0
    print(f"{'verdict':9} case")
    print("-" * 76)
    with tempfile.TemporaryDirectory(prefix="staleclaim-") as tmp:
        base = Path(tmp)
        (base / "target.md").write_text("\n".join(f"line {i}" for i in range(1, 11)),
                                        encoding="utf-8")
        cases = [
            ("must-FAIL: wrong line count for a real file",
             "## A\ntarget.md is 250 lines today.\n", True),
            ("must-PASS: correct line count",
             "## A\ntarget.md is 10 lines today.\n", False),
            ("must-PASS: number is a budget, not a measurement",
             "## A\ntarget.md must stay under the 300 line cap.\n", False),
            ("must-PASS: a correction record may quote the old number",
             "## A\n更正：target.md 曾寫 250 行，實測 10 行。\n", False),
            ("must-PASS: no file named, nothing to measure against",
             "## A\nThe report ran to 250 lines.\n", False),
            # REGRESSION FIXTURE - the actual 2026-07 bug, verbatim in shape.
            # Version 1 of this checker passed every synthetic case above and
            # MISSED this one, because a bound word five characters from a
            # measurement vouched for it. Never delete these two.
            ("must-FAIL: measurement and bound in one sentence (the real bug)",
             "### A2. target.md 精簡\n現 261 行，超過 250 行軟上限（hook 會持續提示）。\n",
             True),
            ("must-PASS: same shape, but the measurement is correct",
             "### A2. target.md 精簡\n現 10 行，超過 250 行軟上限（hook 會持續提示）。\n",
             False),
            ("must-FAIL: English form of the same trap",
             "## A\ntarget.md is 250 lines, under the 300 line cap.\n", True),
        ]
        for label, body, want_fail in cases:
            got = check_text(body, base / "doc.md", base)
            failed = any(v == "FAIL" for _, v, _ in got)
            ok = failed == want_fail
            bad += 0 if ok else 1
            print(f"{'ok' if ok else 'BROKEN':9} {label}")
            if not ok:
                for w, v, d in got:
                    print(f"{'':9}   {v} {d[:80]}")
    n_fail = sum(1 for _, _, w in cases if w)
    print("-" * 76)
    print(f"{len(cases)} cases ({len(cases) - n_fail} must-pass / {n_fail} must-fail), "
          f"{bad} broken — "
          f"{'checker is calibrated' if not bad else 'CHECKER IS NOT TRUSTWORTHY'}")
    if not n_fail or n_fail == len(cases):
        print("ONE-SIDED: both sides must be populated for this to mean anything.")
        return 1
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--path", default=str(SKILL_ROOT))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    target = Path(args.path)
    if not target.exists():
        print(f"not found: {target}")
        return 2
    findings = run(target)
    for where, verdict, detail in findings:
        print(f"{verdict:5} {where:34} {detail}")
    fails = sum(1 for f in findings if f[1] == "FAIL")
    warns = len(findings) - fails
    print(f"\n{fails} FAIL, {warns} WARN over {target}")
    if not findings:
        print("No stale line-count claim found. That is a real result only if the "
              "checker can fail — run --selftest to confirm it still can.")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
