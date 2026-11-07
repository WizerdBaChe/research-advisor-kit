#!/usr/bin/env python3
r"""access_policy — the skill's read-only view of hooks/literature-host-policy.json.

WHY. `rules/literature-access.md` (2026-09-10) says which surface an agent may use on
which host and that an anti-bot challenge is a routing signal, never an obstacle. Until
this file, that was prose the executor had to remember — and the skill's own
search-sources.md still told it to render "anti-bot" pages with a headless browser.
This module turns the routing table into ONE function every retrieval path consults
BEFORE it fetches: `decide(host, surface)`.

WHERE THE POLICY LIVES. `~/.claude/hooks/literature-host-policy.json` — rule tier, so
that the machine-wide hook (`hooks/literature_host_guard.py`) and this skill read the
same rows. The skill never writes it; editing a row is a reviewed act by the user.

WHAT THIS RULES ON, and only this:
  * the host's row (exact or suffix match), or the file's `unlisted_default`;
  * whether `surface` is in the row's `agent_surfaces`;
  * a per-run count, when the caller passes one (max_per_run / distinct unlisted cap).
It does not know whether a page is paywalled, whether the user is entitled, or whether
a challenge will fire — those are outcomes fetchsrc.py records after the fact.

FAIL-CLOSED WITHOUT THE FILE. If the policy is missing or unreadable, `decide` refuses
every browser surface everywhere and allows script/webfetch only on OPEN_CORE (public
scholarly APIs). A missing file must never read as "everything allowed".

THE PER-RUN COUNT IS SHARED ACROSS SURFACES (2026-11-03, G10). `max_per_run` used to be counted
only from `sources/manifest.json`, i.e. only for requests `verify/fetchsrc.py` itself made; a plain
`python -c` / curl call to the same host never reached it (evidence run 20261103_identify-retrieve-
and-extract-the-10-bi2: ~11 OpenAlex calls under an unlisted cap of 1). `run_usage(run)` now adds the
run's own call log `<run>/sources/host-calls.jsonl`, which any script surface appends to with
`--check --run <run> --record` (or `gate()`), and fetchsrc reads the same sum before it fetches. A
caller must pass the run: a script has no other way to be attributed to one (the PreToolUse hook
`hooks/literature_host_guard.py` attributes by SESSION instead and only warns on unlisted hosts).

Usage:
    python access_policy.py --host ieeexplore.ieee.org [--surface webfetch]
    python access_policy.py --url https://link.springer.com/article/10.1007/x --surface browser_headless --check
    python access_policy.py --url https://api.openalex.org/works?search=x --surface script --check --run <run dir> --record
    python access_policy.py --selftest
Exit: 0 allowed / usage ok · 1 refused (with --check) · 2 bad usage · 3 policy unreadable.
review-when: the policy schema changes ("schema" field) or a new surface name appears; the manifest
             entry fields fetchsrc counts on (route / status / host / policy_row) change.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

SURFACES = ("script", "webfetch", "browser_headless", "browser_user")
NON_AGENT_ROUTES = ("local_pdf", "user_provided", "hand_to_user")   # not surfaces: never judged here
OPEN_CORE = {"arxiv.org", "export.arxiv.org", "api.crossref.org", "doi.org", "api.semanticscholar.org",
             "eutils.ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov",
             "zenodo.org", "ntrs.nasa.gov", "osti.gov"}


def policy_path() -> Path:
    env = os.environ.get("LSE_HOST_POLICY")
    if env:
        return Path(env)
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
    return home / "hooks" / "literature-host-policy.json"


def load(path: Path | None = None) -> dict | None:
    p = path or policy_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                   # noqa: BLE001 — unreadable = absent
        return None
    if not isinstance(data, dict) or not isinstance(data.get("hosts"), list):
        return None
    return data


def canon_host(host: str) -> str:
    """Lower-case, no leading dot, no trailing dot: `ieeexplore.ieee.org.` (the absolute-FQDN form,
    which DNS resolves identically) is the same host as `ieeexplore.ieee.org` (QA 2026-09-11 F-1)."""
    return (host or "").strip().lower().strip(".")


def host_of(url_or_host: str) -> str:
    raw = (url_or_host or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        if "/" in raw or ":" in raw:
            raw = "https://" + raw
        else:
            return canon_host(raw)
    try:
        return canon_host(urlsplit(raw).hostname or "")
    except Exception:                                   # noqa: BLE001
        return ""


def row_for(host: str, policy: dict | None) -> dict:
    """The matching row, or the unlisted default marked `class: unlisted`."""
    host = canon_host(host)
    if policy:
        best = None
        for row in policy["hosts"]:
            listed = canon_host(str(row.get("host", "")))
            if listed and (host == listed or host.endswith("." + listed)):
                if best is None or len(listed) > len(best.get("host", "")):
                    best = row
        if best:
            return dict(best)
        d = dict(policy.get("unlisted_default") or {})
        d.setdefault("class", "unlisted")
        d.setdefault("agent_surfaces", ["script", "webfetch"])
        d.setdefault("max_per_run", 1)
        d.setdefault("retention", "excerpt")
        d["host"] = host
        d["unlisted"] = True
        if host in OPEN_CORE:
            d.update({"class": "open", "agent_surfaces": ["script", "webfetch"], "max_per_run": 100,
                      "retention": "full", "unlisted": False, "note": "OPEN_CORE built-in"})
        return d
    # policy unreadable: fail closed except the built-in public-API core
    if host in OPEN_CORE:
        return {"host": host, "class": "open", "agent_surfaces": ["script", "webfetch"], "max_per_run": 100,
                "retention": "full", "unlisted": False, "policy_unreadable": True}
    return {"host": host, "class": "policy_unreadable", "agent_surfaces": [], "max_per_run": 0,
            "retention": "excerpt", "unlisted": True, "policy_unreadable": True}


def decide(host: str, surface: str, policy: dict | None = None, *, used_on_host: int = 0,
           distinct_unlisted: int = 0) -> tuple[bool, str, dict]:
    """(allowed, reason, row). `surface` may also be a non-agent route, which is allowed by definition."""
    if surface in NON_AGENT_ROUTES:
        return True, f"{surface} is not an agent surface (the user's or the file system's act)", {"host": host, "class": "n/a"}
    if surface not in SURFACES:
        return False, f"unknown surface {surface!r}; known: {', '.join(SURFACES)}", {"host": host, "class": "n/a"}
    if policy is None:
        policy = load()
    row = row_for(host, policy)
    cls = row.get("class")
    if row.get("policy_unreadable") and cls != "open":
        return False, ("policy file unreadable — refusing everything outside the built-in public-API core "
                       f"({policy_path()})"), row
    if cls in ("agent_banned", "institutional_only"):
        return False, (f"{host}: {cls} — {row.get('licence_basis', '')[:160]}. Hand the named document to the "
                       "user (DOI + URL); their reading is licensed, a program's is not"), row
    if surface not in (row.get("agent_surfaces") or []):
        if row.get("unlisted"):
            return False, (f"{host} is not listed in the policy; an unlisted host permits one script/webfetch of a "
                           f"named URL and NO browser surface until a row lists it ({policy_path().name})"), row
        return False, (f"{host}: surface {surface} is not in agent_surfaces {row.get('agent_surfaces')} "
                       f"({row.get('note') or row.get('licence_basis', '')[:120]})"), row
    cap = int(row.get("max_per_run", 0) or 0)
    if used_on_host >= cap:
        return False, (f"{host}: max_per_run {cap} reached ({used_on_host} already this run) — the shape of a run "
                       "that wants more is a bulk download; name the remaining targets for the user"), row
    if row.get("unlisted"):
        run_cap = int((policy or {}).get("unlisted_default", {}).get("run_cap_distinct_unlisted_hosts", 3))
        if distinct_unlisted >= run_cap:
            return False, (f"run-level cap: {run_cap} distinct unlisted hosts already in this run — add rows to "
                           f"{policy_path().name} before touching a {run_cap + 1}th"), row
    return True, f"{host}: {cls} — {surface} permitted for a named document (max_per_run {cap})", row


# ---------------------------------------------------------------- the per-run count, shared
RUN_LOG_REL = Path("sources") / "host-calls.jsonl"


def manifest_counts(entries: dict) -> tuple[dict, set]:
    """Per-host count of what fetchsrc retrieved (route script/webfetch, status written/scratch) and the
    set of distinct unlisted hosts among them. The one definition: fetchsrc.run_counts delegates here."""
    per_host: dict = {}
    unlisted: set = set()
    for e in (entries or {}).values():
        if e.get("route") not in ("script", "webfetch"):
            continue
        if e.get("status") in ("written", "scratch"):
            per_host[e.get("host", "")] = per_host.get(e.get("host", ""), 0) + 1
            if e.get("policy_row") == "unlisted":
                unlisted.add(e.get("host", ""))
    return per_host, unlisted


def run_log_rows(run: Path | str) -> list[dict]:
    p = Path(run) / RUN_LOG_REL
    out: list[dict] = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("host"):
            out.append(row)
    return out


def run_usage(run: Path | str) -> tuple[dict, set]:
    """(per_host, distinct_unlisted) for one run = fetchsrc's manifest entries + the run's own call log.
    The two sources are disjoint by construction (fetchsrc never writes the log; a script surface never
    writes the manifest), so the sum is the number of allowed calls the run has made to the host."""
    try:
        man = json.loads((Path(run) / "sources" / "manifest.json").read_text(encoding="utf-8"))
        entries = man.get("entries", {}) if isinstance(man, dict) else {}
    except (OSError, json.JSONDecodeError):
        entries = {}
    per_host, unlisted = manifest_counts(entries)
    for row in run_log_rows(run):
        h = canon_host(str(row["host"]))
        per_host[h] = per_host.get(h, 0) + 1
        if row.get("unlisted"):
            unlisted.add(h)
    return per_host, unlisted


def record_call(run: Path | str, host: str, surface: str, row: dict, caller: str = "access_policy") -> None:
    """Append one allowed call to the run's log (the shared counter's script-surface side)."""
    p = Path(run) / RUN_LOG_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "host": canon_host(host),
             "surface": surface, "class": row.get("class"), "unlisted": bool(row.get("unlisted")), "caller": caller}
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def gate(url_or_host: str, run: Path | str, surface: str = "script", policy: dict | None = None, *,
         record: bool = False, caller: str = "access_policy") -> tuple[bool, str, dict]:
    """decide() with the run's shared count. With record=True an ALLOWED call is appended to the run's
    log before the caller makes the request (a refused call is never recorded: it consumes nothing)."""
    host = host_of(url_or_host)
    if policy is None:
        policy = load()
    per_host, unlisted = run_usage(run)
    allowed, reason, row = decide(host, surface, policy, used_on_host=per_host.get(host, 0),
                                  distinct_unlisted=len(unlisted - {host}))
    if allowed and record and surface not in NON_AGENT_ROUTES:
        record_call(run, host, surface, row, caller)
    return allowed, reason, row


# ---------------------------------------------------------------- selftest (two-sided)
def selftest() -> int:
    import tempfile
    pol = {"schema": "literature-host-policy@1",
           "unlisted_default": {"class": "unlisted", "agent_surfaces": ["script", "webfetch"], "max_per_run": 1,
                                "retention": "excerpt", "run_cap_distinct_unlisted_hosts": 3},
           "hosts": [
               {"host": "open.example", "class": "open", "agent_surfaces": ["script", "webfetch", "browser_headless"],
                "max_per_run": 5, "retention": "full"},
               {"host": "landing.example", "class": "landing_page", "agent_surfaces": ["webfetch"], "max_per_run": 1,
                "retention": "excerpt"},
               {"host": "banned.example", "class": "agent_banned", "agent_surfaces": [], "max_per_run": 0,
                "retention": "excerpt", "licence_basis": "ToU forbids intelligent agents"},
               {"host": "inst.example", "class": "institutional_only", "agent_surfaces": [], "max_per_run": 0}]}
    cases = [  # (label, host, surface, kwargs, want_allowed)
        ("must-REFUSE banned + browser_user", "banned.example", "browser_user", {}, False),
        ("must-REFUSE banned + webfetch", "banned.example", "webfetch", {}, False),
        ("must-REFUSE banned + script", "banned.example", "script", {}, False),
        ("must-REFUSE institutional_only + webfetch", "inst.example", "webfetch", {}, False),
        ("must-ALLOW open + script", "open.example", "script", {}, True),
        ("must-ALLOW open subdomain + browser_headless", "www.open.example", "browser_headless", {}, True),
        ("must-REFUSE landing + browser_headless (surface not listed)", "landing.example", "browser_headless", {}, False),
        ("must-ALLOW landing + webfetch first document", "landing.example", "webfetch", {"used_on_host": 0}, True),
        ("must-REFUSE landing + webfetch second document (max_per_run 1)", "landing.example", "webfetch", {"used_on_host": 1}, False),
        ("must-ALLOW unlisted + webfetch", "nobody.example", "webfetch", {}, True),
        ("must-REFUSE unlisted + browser_headless", "nobody.example", "browser_headless", {}, False),
        ("must-REFUSE unlisted + browser_user", "nobody.example", "browser_user", {}, False),
        ("must-REFUSE 4th distinct unlisted host", "fourth.example", "webfetch", {"distinct_unlisted": 3}, False),
        ("must-ALLOW non-agent route local_pdf", "banned.example", "local_pdf", {}, True),
        ("must-REFUSE unknown surface", "open.example", "carrier-pigeon", {}, False),
        ("must-REFUSE banned host in absolute-FQDN form (trailing dot; QA F-1)", "banned.example.", "webfetch", {}, False),
        ("must-REFUSE banned host via a URL with a trailing dot", host_of("https://www.banned.example./doc/1"), "webfetch", {}, False),
    ]
    bad = 0
    print(f"{'verdict':9} case")
    print("-" * 72)
    for label, host, surface, kw, want in cases:
        ok_, reason, _ = decide(host, surface, pol, **kw)
        good = ok_ == want
        bad += 0 if good else 1
        print(f"{'ok' if good else 'BROKEN':9} {label}")
        if not good:
            print(f"{'':9}   got allowed={ok_}: {reason[:100]}")
    # policy unreadable: fail closed, except OPEN_CORE script/webfetch
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "nope.json"
        prev_env = os.environ.get("LSE_HOST_POLICY")   # restored, not dropped: the live check below reads it
        os.environ["LSE_HOST_POLICY"] = str(missing)
        try:
            a1 = decide("link.springer.com", "webfetch", load())[0]
            a2 = decide("api.crossref.org", "script", load())[0]
            a3 = decide("api.crossref.org", "browser_headless", load())[0]
        finally:
            if prev_env is None:
                os.environ.pop("LSE_HOST_POLICY", None)
            else:
                os.environ["LSE_HOST_POLICY"] = prev_env
    for label, got, want in [("must-REFUSE any non-core host when the policy is unreadable", a1, False),
                             ("must-ALLOW OPEN_CORE script when the policy is unreadable", a2, True),
                             ("must-REFUSE OPEN_CORE browser when the policy is unreadable", a3, False)]:
        good = got == want
        bad += 0 if good else 1
        print(f"{'ok' if good else 'BROKEN':9} {label}")
    # shared per-run count (G10): the script surface and fetchsrc's manifest meet in run_usage()
    shared = [  # (label, got, want)
    ]
    with tempfile.TemporaryDirectory() as tmp:
        runa, runb = Path(tmp) / "20261103_a", Path(tmp) / "20261103_b"
        for r_ in (runa, runb):
            (r_ / "sources").mkdir(parents=True)
        g1 = gate("https://landing.example/doc/1", runa, "webfetch", pol, record=True)[0]
        g2 = gate("https://landing.example/doc/2", runa, "webfetch", pol, record=True)[0]
        g3 = gate("https://landing.example/doc/1", runb, "webfetch", pol, record=True)[0]
        n_rows = len(run_log_rows(runa))
        shared += [("must-ALLOW the 1st recorded call to a max_per_run 1 host in run A", g1, True),
                   ("must-REFUSE the 2nd call to it in the SAME run (positive control: the cap fires)", g2, False),
                   ("must-ALLOW the same host in a DIFFERENT run (negative control: runs are independent)", g3, True),
                   ("must-RECORD exactly one row in run A (a refused call consumes nothing)", n_rows == 1, True)]
        # a request fetchsrc already made (manifest entry) counts against a later script-surface call
        (runb / "sources" / "manifest.json").write_text(json.dumps({"entries": {
            "f1": {"route": "script", "status": "scratch", "host": "open.example", "policy_row": "open.example"}}}),
            encoding="utf-8")
        shared.append(("must-COUNT fetchsrc's manifest entries toward the shared cap (open.example cap 5, 4 more fit)",
                       [gate("https://open.example/p", runb, "script", pol, record=True)[0] for _ in range(5)],
                       [True, True, True, True, False]))
        # a hand_to_user stub is not a retrieval: it must not count
        runc = Path(tmp) / "20261103_c"
        (runc / "sources").mkdir(parents=True)
        (runc / "sources" / "manifest.json").write_text(json.dumps({"entries": {
            "w": {"route": "hand_to_user", "status": "refused", "host": "landing.example"}}}), encoding="utf-8")
        shared.append(("must-NOT count a refused hand_to_user stub (negative control)",
                       gate("https://landing.example/x", runc, "webfetch", pol)[0], True))
        # an unlisted host the script surface used counts toward the distinct-unlisted run cap
        rund = Path(tmp) / "20261103_d"
        (rund / "sources").mkdir(parents=True)
        for h_ in ("n1.example", "n2.example", "n3.example"):
            gate(f"https://{h_}/p", rund, "script", pol, record=True)
        shared.append(("must-REFUSE a 4th distinct unlisted host once 3 were logged by the script surface",
                       gate("https://n4.example/p", rund, "script", pol)[0], False))
    for label, got, want in shared:
        good = got == want
        bad += 0 if good else 1
        print(f"{'ok' if good else 'BROKEN':9} {label}" + ("" if good else f"   got {got!r}"))
    n = len(cases) + 3 + len(shared)
    n_allow = sum(1 for c in cases if c[4]) + 1 + sum(1 for s in shared if s[2] is True)
    print("-" * 72)
    print(f"{n} cases ({n_allow} must-allow / {n - n_allow} must-refuse), {bad} broken — "
          f"{'calibrated' if not bad else 'NOT TRUSTWORTHY'}")
    # the live file must parse and cover the hosts ops/environment.md measured
    live = load()
    if live is None:
        print(f"WARN live policy unreadable at {policy_path()} — decide() is failing closed")
        return 1 if bad else 0
    listed = {r["host"] for r in live["hosts"]}
    need = {"ieeexplore.ieee.org", "www.sciencedirect.com", "onlinelibrary.wiley.com", "www.mdpi.com",
            "eprints.soton.ac.uk", "opg.optica.org", "iopscience.iop.org", "arxiv.org", "osti.gov"}
    miss = sorted(need - listed)
    print(f"live policy: {len(listed)} rows; measured hosts missing: {miss or 'none'}")
    # a host listed by a row is outside the distinct-unlisted run cap and carries its own max_per_run
    # (rows added 2026-10-04 so a grey-literature run stops tripping the unlisted cap — FUTURE-WORK B9(3))
    cap_ok = decide("sebokwiki.org", "webfetch", live, distinct_unlisted=3, used_on_host=4)[0]
    cap_ctl = decide("unlisted.example", "webfetch", live, distinct_unlisted=3)[0]
    print(f"{'ok' if cap_ok else 'BROKEN':9} live: listed sebokwiki.org passes with 3 unlisted hosts + 4 documents already")
    print(f"{'ok' if not cap_ctl else 'BROKEN':9} live: an unlisted host is still refused at the same count (control)")
    return 1 if (bad or miss or not cap_ok or cap_ctl) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host")
    ap.add_argument("--url")
    ap.add_argument("--surface", default="webfetch")
    ap.add_argument("--check", action="store_true", help="exit 1 when refused")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--run", help="evidence run folder: judge against the run's SHARED count "
                                  "(fetchsrc manifest + sources/host-calls.jsonl)")
    ap.add_argument("--record", action="store_true",
                    help="with --run: append an ALLOWED call to the run's log so fetchsrc and every other "
                         "script surface count it (call this immediately before the request)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    host = host_of(a.url) if a.url else host_of(a.host or "")
    if not host:
        ap.print_help()
        return 2
    if a.record and not a.run:
        print("--record needs --run <run folder>: a script can only be attributed to a run by naming it")
        return 2
    pol = load()
    if a.run:
        allowed, reason, row = gate(host, a.run, a.surface, pol, record=a.record)
    else:
        allowed, reason, row = decide(host, a.surface, pol)
    if a.json:
        print(json.dumps({"host": host, "surface": a.surface, "allowed": allowed, "reason": reason, "row": row},
                         ensure_ascii=False, indent=1))
    else:
        print(f"{'ALLOW' if allowed else 'REFUSE'} {host} via {a.surface}: {reason}")
        print(f"  class={row.get('class')} surfaces={row.get('agent_surfaces')} max_per_run={row.get('max_per_run')} "
              f"retention={row.get('retention')} verified={row.get('verified', '-')}")
        if a.run:
            used = run_usage(a.run)[0].get(host, 0)
            print(f"  run {Path(a.run).name}: {used} allowed call(s) to {host} counted"
                  + (" (this one recorded)" if allowed and a.record else ""))
    if pol is None:
        print(f"  (policy unreadable: {policy_path()})")
        return 3 if a.check else 0
    return (0 if allowed else 1) if a.check else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
