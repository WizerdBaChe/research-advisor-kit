"""Run the kit's machine acceptance controls (docs/BUILD-SPEC.md §7) on a scratch copy.

Usage (from the repo root):  python -X utf8 verify/run_controls.py <new-scratch-dir>

<new-scratch-dir> must not exist or must be empty; reference-impl/ is copied there, mutated and
deleted. Each two-sided control prints BOTH asserted values (shipped vs mutant). Offline: no control
touches the network (citecheck runs with --offline stub resolvers; the hook is fed a payload on stdin).
Evidence rung: 0 (example controls, each two-sided with both asserted values printed).
Needs: Python 3.12+ (tested on 3.12.7), pytest, idutils, jsonschema (verify/requirements.txt). Optional: PyMuPDF —
without it K1k still runs and its tally line says the page-pointer (PDF) cases were skipped; Zotero.
Isolation: every control reads the REPO's files, never an installed ~/.claude (CLAUDE_CONFIG_DIR points at an
empty folder in the scratch dir, LSE_HOST_POLICY at the shipped policy file). A machine that already has the
kit installed therefore gets the same result as a fresh one (review 2026-11-07: K1a/K6 had read ~/.claude).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if len(sys.argv) != 2:
    sys.exit(__doc__)
work = Path(sys.argv[1]).resolve()
if work.exists() and any(work.iterdir()):
    sys.exit(f"refusing: {work} exists and is not empty (it would be deleted)")
if work == REPO or REPO in work.parents or work in REPO.parents:
    sys.exit(f"refusing: {work} overlaps the repo {REPO}")

RI = work / "reference-impl"
LSE = RI / "skills" / "literature-search-extract"
SRG = RI / "skills" / "scientific-research-guide"
ENV = dict(os.environ, HK_HOST_TOML=str(REPO / "verify" / "host.toml"), PYTHONIOENCODING="utf-8",
           CLAUDE_CONFIG_DIR=str(work / "empty-claude-home"),
           LSE_HOST_POLICY=str(RI / "hooks" / "literature-host-policy.json"),
           CLAUDE_TELEMETRY_DIR=str(work / "telemetry"),
           LSE_RUN_HOME=str(work / "runs"), LSE_INBOX=str(work / "inbox"), LSE_BIB_HOME=str(work / "bib"))
ENV.pop("LSE_ARXIV_CONTACT", None)
results: list[tuple[str, bool]] = []
undetermined: list[str] = []


def run(args: list[str], cwd: Path | None = None, stdin: str | None = None) -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-X", "utf8", *args], cwd=cwd or work, env=ENV, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", input=stdin, timeout=600)
    out = p.stdout + p.stderr
    for form in (str(work), work.as_posix()):
        out = out.replace(form, "<scratch>")
    for form in (str(REPO), REPO.as_posix()):
        out = out.replace(form, "<repo>")
    return p.returncode, out


def report(cid: str, ok: bool, line: str) -> None:
    results.append((cid, ok))
    print(f"{cid:<4} {line} -> {'ok' if ok else 'MISMATCH'}")


def last(out: str, pat: str) -> str:
    hits = [l.strip() for l in out.splitlines() if re.search(pat, l)]
    return hits[-1][:110] if hits else "absent"


def lint_counts(out: str) -> tuple[int, int]:
    m = re.search(r"profile-lint: (\d+) FAIL, (\d+) WARN", out)
    return (int(m[1]), int(m[2])) if m else (-1, -1)


def versions() -> str:
    import platform
    from importlib.metadata import PackageNotFoundError, version
    out = [f"python {platform.python_version()}", f"{platform.system()} {platform.release()}"]
    for pkg in ("pytest", "pymupdf", "idutils", "jsonschema"):
        try:
            out.append(f"{pkg} {version(pkg)}")
        except PackageNotFoundError:
            out.append(f"{pkg} absent")
    return ", ".join(out)


def main() -> int:
    print(f"env: {versions()}")
    work.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO / "reference-impl", RI)

    # K1 tool selftests: each carries its own known-good and known-bad inputs and fails on a broken case
    for cid, rel, extra, want in (
        ("K1a", "connectors/access_policy.py", [], r"refused at the same count"),
        ("K1b", "connectors/pdf_index.py", [], r"0 broken"),
        ("K1c", "connectors/probe.py", [], r"0 broken"),
        ("K1d", "connectors/zotero_local.py", [], r"NOTE: this calibrates"),
        ("K1e", "loop/idkey.py", [], r"0 broken"),
        ("K1f", "loop/inbox.py", [], r"selftest: PASS"),
        ("K1g", "loop/reflux.py", [], r"0 broken"),
        ("K1h", "loop/runs.py", [], r"calibrated"),
        ("K1i", "verify/fetchsrc.py", [], r"0 broken"),
        ("K1j", "verify/staleclaim.py", [], r"0 broken"),
        ("K1k", "verify/citecheck.py", ["--offline"], r"0 broken — gate is calibrated"),
    ):
        rc, out = run(["-I", str(LSE / rel), "--selftest", *extra])
        ok = rc == 0 and re.search(want, out) is not None
        report(cid, ok, f"{rel} --selftest {' '.join(extra)}: exit {rc}, '{last(out, want) if ok else last(out, '.')}'")

    # K2 unit suites
    PASSED_RE = r"\d+ (passed|failed)"  # outside the f-string: a backslash there is a SyntaxError before 3.12
    rc, out = run(["-m", "pytest", "-q", "-p", "no:cacheprovider", str(LSE / "loop" / "tests")], cwd=RI)
    report("K2", rc == 0, f"loop/tests pytest: exit {rc}, {last(out, PASSED_RE).strip('= ')}")
    rc, out = run(["-I", str(RI / "hooks" / "tests" / "test_literature_host_guard.py")])
    report("K3", rc == 0 and "ALL TESTS PASSED" in out, f"test_literature_host_guard.py: exit {rc}, '{last(out, '.')}'")
    rc, out = run(["-I", str(RI / "tools" / "secret-guard-test" / "test_secret_file_guard.py")])
    report("K4", rc == 0 and "failures: 0" in out, f"test_secret_file_guard.py: exit {rc}, '{last(out, 'failures')}'")

    # K5 citecheck support check: the shipped span vs one number changed in span and claim
    run_dir = work / "run"
    shutil.copytree(LSE / "loop" / "tests" / "fixtures" / "good-run", run_dir)
    cc = [str(LSE / "verify" / "citecheck.py"), str(run_dir / "ledger.jsonl"), "--offline"]
    sup = lambda o: (re.search(r"^\s*(OK|WARN|FAIL)\s+support\b", o, re.M) or [None, "absent"])[1]
    _, out0 = run(cc)
    row = json.loads((run_dir / "ledger.jsonl").read_text(encoding="utf-8"))
    row["support_span"] = row["support_span"].replace("22 um", "48 um")
    row["claim"] = row["claim"].replace("= 22 μm", "= 48 μm")
    (run_dir / "ledger.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    _, out1 = run(cc)
    report("K5", sup(out0) == "OK" and sup(out1) == "FAIL",
           f"citecheck support: shipped span {sup(out0)} vs span 22->48 um {sup(out1)}")

    # K6 the host-access hook: an agent_banned publisher vs an open-access host, same tool, same session
    hook = RI / "hooks" / "literature_host_guard.py"
    def decide(url: str) -> str:
        rc, out = run([str(hook)], stdin=json.dumps({"session_id": "k6", "tool_name": "WebFetch",
                                                     "tool_input": {"url": url, "prompt": "x"}}))
        m = re.search(r'"permissionDecision":\s*"(\w+)"', out)
        return m[1] if m else ("allow (silent)" if rc == 0 and not out.strip() else f"exit {rc}")
    banned = "https://" + "ieeexplore.ieee.org" + "/document/1"  # split: a live copy of this hook reads command text
    d0, d1 = decide("https://arxiv.org/abs/2101.00001"), decide(banned)
    report("K6", d0 == "allow (silent)" and d1 == "deny", f"literature_host_guard WebFetch: arxiv.org {d0} vs ieeexplore {d1}")

    # K7 profile-lint: the shipped empty manifest vs the two seeded fixtures (counts documented in its docstring)
    lint = [str(SRG / "tools" / "profile-lint.py"), "--root"]
    c0 = lint_counts(run(lint + [str(SRG)])[1])
    c1 = lint_counts(run(lint + [str(SRG / "evals" / "fixtures" / "routing-collision")])[1])
    c2 = lint_counts(run(lint + [str(SRG / "evals" / "fixtures" / "frontmatter-drift")])[1])
    report("K7", c0 == (0, 0) and c1 == (2, 6) and c2 == (2, 0),
           f"profile-lint FAIL/WARN: shipped {c0} vs routing-collision {c1} (want (2, 6)) vs frontmatter-drift {c2} (want (2, 0))")

    # K8 eval-impact selects by declared dependency: a method file vs a deliverables file (shipped manifest)
    ei = [str(SRG / "tools" / "eval-impact.py"), "--files"]
    sel = lambda o: (re.search(r"RE-RUN (\d+) of (\d+) cases", o) or re.search(r"(no) case", o))
    o_m = run(ei + ["references/method-selection.md"], cwd=SRG)[1]
    o_d = run(ei + ["references/deliverables.md"], cwd=SRG)[1]
    n = lambda o: (re.search(r"RE-RUN (\d+) of \d+ cases", o) or [None, "0"])[1]
    report("K8", n(o_m) == "3" and n(o_d) == "0",
           f"eval-impact cases selected: method-selection.md {n(o_m)} (cases 2, 3, 5) vs deliverables.md {n(o_d)}")

    # K9 adding a domain: a manifest row with no file vs that row with an unfilled _template.md copy
    r = SRG / "domains" / "_routing.md"
    r.write_text(r.read_text(encoding="utf-8").replace(
        "|---|---|---|---|---|---|\n",
        "|---|---|---|---|---|---|\n| base | `demo_domain.md` | — | demo widget | Demo domain profile | yes (Node 6) |\n", 1),
        encoding="utf-8")
    o1 = run(lint + [str(SRG)])[1]
    shutil.copy(SRG / "domains" / "_template.md", SRG / "domains" / "demo_domain.md")
    o2 = run(lint + [str(SRG)])[1]
    closure = lambda o: "missing file: demo_domain.md" in o
    report("K9", closure(o1) and lint_counts(o1)[0] == 1 and not closure(o2) and lint_counts(o2)[0] > 0,
           f"profile-lint after adding a row: no file {lint_counts(o1)[0]} FAIL (closure {closure(o1)}) "
           f"vs unfilled template {lint_counts(o2)[0]} FAIL (closure {closure(o2)})")

    # Not counted: tools that need a local library this clean machine does not have
    for rel in ("connectors/local_find.py", "connectors/textbook_ocr.py"):
        rc, out = run(["-I", str(LSE / rel), "--selftest"])
        undetermined.append(f"{rel} --selftest: exit {rc}, '{last(out, '.')}'")
    for u in undetermined:
        print(f"UNDT {u} (needs a textbook library; not counted)")

    shutil.rmtree(work)
    bad = [c for c, ok in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} controls ok, {len(undetermined)} undetermined (not counted)"
          + (f"; MISMATCH: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
