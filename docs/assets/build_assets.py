"""Regenerate every README image from the shipped tools' real output (no hand-made picture).

Usage (from the repo root):  python -X utf8 docs/assets/build_assets.py

What it does: copies reference-impl/ into a temp dir, RUNS the shipped tools there (citecheck, the host-access
hook, profile-lint; same drive as controls K5, K6, K9 of verify/run_controls.py), pastes their stdout (temp path
scrubbed to <scratch>) into the pages under docs/assets/src/, and screenshots the pages with playwright chromium.
Offline: nothing touches the network.

Outputs (docs/assets/): hero.png, panel-citecheck.png, panel-hostguard.png, panel-lint.png (all 960 px wide;
the height follows the content and is printed).
Needs: Python 3.11+, playwright + chromium (python -m playwright install chromium). The pages use local fonts
only; without a CJK serif font installed the type differs, the content does not.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "docs" / "assets"
SRC = ASSETS / "src"
WIDTH = 960


FIT_JS = """() => {
  const box = (e) => e.getBoundingClientRect(), bad = [];
  for (const t of document.querySelectorAll('[data-name],[data-role]')) {
    const id = t.dataset.name || t.dataset.role, n = document.querySelector(`[data-node="${id}"]`);
    const a = box(t), b = box(n);
    // a diamond narrows away from its centre line: the half-width left at the text's farthest edge
    const dia = n.tagName === 'path', cx = (b.left + b.right) / 2, cy = (b.top + b.bottom) / 2;
    const dy = Math.max(Math.abs(a.top - cy), Math.abs(a.bottom - cy));
    const half = dia ? (b.width / 2) * (1 - dy / (b.height / 2)) : b.width / 2;
    const l = cx - half, r = cx + half;
    if (a.left < l + 4 || a.right > r - 4 || a.top < b.top || a.bottom > b.bottom) bad.push(`text of ${id} outside its node`);
  }
  for (const g of document.querySelectorAll('[data-chip]')) {
    const r = box(g.querySelector('rect'));
    for (const t of g.querySelectorAll('text')) { const a = box(t);
      if (a.left < r.left || a.right > r.right + 0.5) bad.push(`chip ${g.dataset.chip} text overflows`); }
  }
  for (const g of document.querySelectorAll('[data-label]')) {
    const a = box(g), r = box(document.querySelector(`[data-group="${g.dataset.label}"]`));
    if (a.right > r.right - 8) bad.push(`group label ${g.dataset.label} overflows`);
  }
  return bad;
}"""


def build_flow() -> int:
    """Render flow.<lang>.svg (from flow.build.mjs) to PNG @2x; the in-browser text-fit check must be quiet on the
    real SVG and must fire on a known-bad copy whose one node is shrunk to 40 px wide."""
    st = subprocess.run(["node", str(ASSETS / "flow.build.mjs"), "--selftest"], capture_output=True, text=True, encoding="utf-8")
    print(st.stdout.strip())
    if st.returncode:
        sys.exit("flow.build.mjs --selftest failed")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        for lang in ("zh-TW", "en"):
            b = subprocess.run(["node", str(ASSETS / "flow.build.mjs"), "--lang", lang], capture_output=True, text=True, encoding="utf-8")
            print(b.stdout.strip())
            if b.returncode:
                sys.exit(f"flow {lang}: model asserts failed")
            svg = (ASSETS / f"flow.{lang}.svg").read_text(encoding="utf-8")
            w, h = (int(float(x)) for x in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups())
            page.set_viewport_size({"width": w, "height": h})
            page.set_content(f"<html><body style='margin:0'>{svg}</body></html>")
            bad = page.evaluate(FIT_JS)
            shrunk = re.sub(r'(<rect data-node="LOC" x=")([\d.]+)(" y="[\d.]+" width=")([\d.]+)',
                            lambda m: f"{m[1]}{float(m[2]) + float(m[4]) / 2 - 20}{m[3]}40", svg, count=1)
            page.set_content(f"<html><body style='margin:0'>{shrunk}</body></html>")
            ctl = page.evaluate(FIT_JS)
            print(f"text-fit {lang}: real {len(bad)} problem(s); known-bad (LOC shrunk to 40 px) {len(ctl)} problem(s)"
                  f" -> {'ok' if not bad and ctl else 'FAIL'}")
            if bad or not ctl:
                sys.exit(f"flow {lang}: text-fit {bad or 'control silent'}")
            page.set_content(f"<html><body style='margin:0'>{svg}</body></html>")
            out = ASSETS / f"flow.{lang}.png"
            page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h})
            print(f"wrote docs/assets/flow.{lang}.png ({w}x{h} css px, @2x)")
        browser.close()
    return 0


def main() -> int:
    if "--only" in sys.argv and sys.argv[sys.argv.index("--only") + 1] == "flow":
        return build_flow()
    build_flow()
    work = Path(tempfile.mkdtemp(prefix="rak-assets-"))
    try:
        slots = capture(work)
        pages = work / "_pages"
        pages.mkdir()
        shutil.copyfile(SRC / "base.css", pages / "base.css")
        shots = [("hero", slots["hero"]), ("panel-citecheck", slots["citecheck"]),
                 ("panel-hostguard", slots["hostguard"]), ("panel-lint", slots["lint"])]
        for name, fill in shots:
            text = (SRC / f"{name}.html").read_text(encoding="utf-8")
            for k, v in fill.items():
                text = text.replace("{{" + k + "}}", v)
            left = re.findall(r"\{\{(\w+)\}\}", text)
            if left:
                sys.exit(f"{name}: unfilled slots {left}")
            (pages / f"{name}.html").write_text(text, encoding="utf-8")
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": WIDTH, "height": 1200}, device_scale_factor=2)
            for name, _ in shots:
                page.goto((pages / f"{name}.html").as_uri())
                page.wait_for_load_state("networkidle")
                geo = page.evaluate("""() => { const b = document.body.getBoundingClientRect();
                  const over = [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > b.right + 0.5
                    || e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflow !== 'visible').map(e => e.tagName + '.' + e.className);
                  return {h: Math.ceil(document.body.getBoundingClientRect().height), over}; }""")
                if geo["over"]:
                    sys.exit(f"{name}: elements overflow the canvas: {geo['over'][:5]}")
                out = ASSETS / f"{name}.png"
                page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": WIDTH, "height": geo["h"]})
                print(f"wrote docs/assets/{name}.png ({WIDTH}x{geo['h']} css px, @2x)")
            browser.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


# ---------------------------------------------------------------- capture of real tool output

def capture(work: Path) -> dict:
    ri = work / "reference-impl"
    shutil.copytree(REPO / "reference-impl", ri)
    lse = ri / "skills" / "literature-search-extract"
    srg = ri / "skills" / "scientific-research-guide"
    env = dict(os.environ, HK_HOST_TOML=str(REPO / "verify" / "host.toml"), PYTHONIOENCODING="utf-8",
               CLAUDE_TELEMETRY_DIR=str(work / "telemetry"), LSE_RUN_HOME=str(work / "runs"),
               LSE_INBOX=str(work / "inbox"), LSE_BIB_HOME=str(work / "bib"))
    env.pop("LSE_ARXIV_CONTACT", None)

    def scrub(s: str) -> str:
        for form in (str(work), work.as_posix(), str(work).replace("\\", "\\\\")):
            s = s.replace(form, "<scratch>")
        for form in (str(REPO), REPO.as_posix()):
            s = s.replace(form, "<repo>")
        return s

    def assert_no_path(label: str, s: str) -> None:
        m = re.search(r".{0,60}(?:\b[A-Za-z]:[\\/]|Users[\\/]).{0,60}", s, re.S)
        if m:
            sys.exit(f"{label}: a private path survived the scrub: {m[0]!r}")

    def run(args: list[str], stdin: str | None = None) -> tuple[int, str]:
        p = subprocess.run([sys.executable, "-X", "utf8", *args], cwd=work, env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", input=stdin, timeout=300)
        return p.returncode, scrub((p.stdout + p.stderr).replace("\r\n", "\n"))

    esc = html.escape

    def colour(text: str, mark: str | None = None) -> str:
        """HTML-escape tool output; colour the verdict words; wrap the line matching `mark` in a highlight."""
        rows = []
        for line in text.rstrip("\n").split("\n"):
            e = esc(line)
            e = re.sub(r"^(\s+)(OK|WARN|FAIL)(\s)", lambda m: f"{m[1]}<span class=\"{m[2]}\">{m[2]}</span>{m[3]}", e)
            e = re.sub(r"^(FAIL)(\s)", r'<span class="FAIL">\1</span>\2', e)
            if mark and re.search(mark, line):
                e = f'<span class="hl">{e}</span>'
            rows.append(e)
        return "\n".join(rows)

    # ---- citecheck (control K5): shipped span vs one number changed in span and claim
    run_dir = work / "run"
    shutil.copytree(lse / "loop" / "tests" / "fixtures" / "good-run", run_dir)
    cc = [str(lse / "verify" / "citecheck.py"), "run/ledger.jsonl", "--offline"]
    cmd_cc = "python verify/citecheck.py run/ledger.jsonl --offline"
    _, ok_out = run(cc)
    row = json.loads((run_dir / "ledger.jsonl").read_text(encoding="utf-8"))
    row["support_span"] = row["support_span"].replace("22 um", "48 um")
    row["claim"] = row["claim"].replace("22 ±", "48 ±")
    (run_dir / "ledger.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    _, bad_out = run(cc)
    sup = lambda o: re.search(r"^\s*(OK|WARN|FAIL)\s+support\b", o, re.M)[1]
    if (sup(ok_out), sup(bad_out)) != ("OK", "FAIL"):
        sys.exit(f"citecheck control K5 did not reproduce: {sup(ok_out)} / {sup(bad_out)}")
    pick = lambda o: "\n".join(l for l in o.split("\n") if re.match(r"\[C1\]|\s+(OK|FAIL)\s+support", l))

    # ---- host guard (control K6): the hook fed a JSON payload on stdin
    hook = str(ri / "hooks" / "literature_host_guard.py")
    banned = "https://" + "ieeexplore.ieee.org" + "/document/1"  # split: a live copy of the hook reads command text
    open_url = "https://arxiv.org/abs/2101.00001"

    def decide(url: str) -> tuple[str, str]:
        payload = json.dumps({"session_id": "assets", "tool_name": "WebFetch", "tool_input": {"url": url, "prompt": "x"}})
        rc, out = run([hook], stdin=payload)
        if rc == 0 and not out.strip():
            return payload, "(no output, exit 0: allowed silently)"
        j = json.loads(out)["hookSpecificOutput"]
        return payload, f"permissionDecision: {j['permissionDecision']}\npermissionDecisionReason:\n{j['permissionDecisionReason']}"

    p0, o0 = decide(open_url)
    p1, o1 = decide(banned)
    if "silently" not in o0 or "permissionDecision: deny" not in o1:
        sys.exit("host guard control K6 did not reproduce")
    hcmd = lambda p: "echo '" + p + "' | python hooks/literature_host_guard.py"

    # ---- profile-lint (control K9): a manifest row with no file vs that row with an unfilled template copy
    lint = [str(srg / "tools" / "profile-lint.py"), "--root", str(srg)]
    routing = srg / "domains" / "_routing.md"
    routing.write_text(routing.read_text(encoding="utf-8").replace(
        "|---|---|---|---|---|---|\n",
        "|---|---|---|---|---|---|\n| base | `demo_domain.md` | — | demo widget | Demo domain profile | yes (Node 6) |\n", 1),
        encoding="utf-8")
    _, l1 = run(lint)
    shutil.copy(srg / "domains" / "_template.md", srg / "domains" / "demo_domain.md")
    _, l2 = run(lint)
    count = lambda o: int(re.search(r"profile-lint: (\d+) FAIL", o)[1])
    n1, n2 = count(l1), count(l2)
    if not (n1 == 1 and "missing file: demo_domain.md" in l1 and n2 > 1 and "missing file" not in l2):
        sys.exit(f"profile-lint control K9 did not reproduce: {n1} / {n2}")
    lcmd = "python tools/profile-lint.py --root ."

    evals = json.loads((srg / "evals" / "evals.json").read_text(encoding="utf-8"))["evals"]
    prompt = next(e["prompt"] for e in evals if e["id"] == 2)

    for label, text in (("ok", ok_out), ("bad", bad_out), ("allow", o0), ("deny", o1), ("lint1", l1), ("lint2", l2)):
        assert_no_path(label, text)
    return {
        "hero": {"PROMPT": esc(prompt), "OK": colour(pick(ok_out), r"\s+(OK|FAIL)\s+support"),
                 "FAIL": colour(pick(bad_out), r"\s+(OK|FAIL)\s+support")},
        "citecheck": {"CMD0": esc("$ " + cmd_cc), "OUT0": colour(ok_out, r"\s+(OK|FAIL)\s+support"),
                      "CMD1": esc("$ " + cmd_cc + "    # after changing 22 um to 48 um in the span and the claim"),
                      "OUT1": colour(bad_out, r"\s+(OK|FAIL)\s+support")},
        "hostguard": {"CMD0": esc("$ " + hcmd(p0)), "OUT0": esc(o0), "CMD1": esc("$ " + hcmd(p1)), "OUT1": esc(o1)},
        "lint": {"N0": str(n1), "N1": str(n2), "CMD0": esc("$ " + lcmd + "    # after adding the row for demo_domain.md"),
                 "OUT0": colour(l1), "CMD1": esc("$ " + lcmd + "    # after cp domains/_template.md domains/demo_domain.md"),
                 "OUT1": colour(l2)},
    }


if __name__ == "__main__":
    sys.exit(main())
