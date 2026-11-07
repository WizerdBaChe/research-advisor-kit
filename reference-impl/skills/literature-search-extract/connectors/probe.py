#!/usr/bin/env python3
r"""Capability probe for the literature-search-extract connector layer.

THE BOUNDARY THIS SCRIPT IMPLEMENTS. The agent may RUN a program that holds a
credential; it may never READ the credential. So the trust split is:

    this script          MAY read a connector's .env  (it is the runner)
    whatever reads its   MAY NOT — and must not need to, because everything
    output               it needs is a boolean, a length, and a verdict

Every print statement below is written on the assumption that an LLM will read
it. No branch prints a value, and --selftest proves the leak scanner would
catch it if one ever did.

WHAT IT ANSWERS, in order of what actually goes wrong:
  reachable      is the process up at all?
  contract       do the endpoints registry.json promises still EXIST?
                 (measured 2026-08-26: the running PatentsGrabber server was
                 older than its own source and had no /api/query — the skill
                 would have routed to a 404 and read it as "no results")
  credential     is a key present and non-placeholder? presence only.
  leak           did any response body contain a credential value?

SEVERITY, per the gate-severity-by-consumer ruling (2026-08-26):
  FAIL  leak (security invariant, determinable) and contract drift (the skill
        would make a hard call to an endpoint that is not there)
  WARN  not reachable / no credential — an LLM reads this and degrades the run
        honestly. Promotion trigger, named: a WARN becomes a FAIL the moment a
        deliverable cites this connector as a source.

Usage:
    python probe.py --list                 what is registered, and what is missing
    python probe.py --id patentsgrabber    probe one
    python probe.py --all                  probe every live/available connector
    python probe.py --selftest             two-sided calibration of the scanner
    python probe.py --all --json           machine-readable

    python probe.py --id X --ensure            attach, or start it detached
    python probe.py --id X --ensure --restart  stop and respawn (explicit only)

HOW A NON-HUMAN CALLER GETS A CONNECTOR RUNNING. The registry describes
processes a person started by hand; an agent cannot assume one is there, and
must not assume the one that IS there is correct. `--ensure` covers both: it
attaches to a healthy process, or spawns one detached and waits for readiness.
It never kills anything. A stale process is the case that needs judgement, so
it needs `--restart` typed explicitly — a contract FAIL never escalates to a
kill on its own, and a process whose command line lacks the registry's
identity_marker is never killed at all, because that port may belong to
something else and "my probe went green" is not worth someone else's process.

Exit: 0 = no FAIL. 1 = at least one FAIL. 2 = bad usage.
review-when: registry.json schema_version changes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "registry.json"
sys.path.insert(0, str(HERE))
import regload  # noqa: E402  (registry loader: expands ${ROOT} path fields)
TIMEOUT = 10
MIN_SECRET_LEN = 8          # below this, a "value" is a placeholder, not a key

PLACEHOLDERS = {
    "", "changeme", "<your-key>", "<your-consumer-key>",
    "<your-consumer-secret>", "your-api-key-here", "todo", "xxx",
}


# --------------------------------------------------------------------------
# credential handling — the only code here allowed to touch a secret value
# --------------------------------------------------------------------------
def load_env_values(env_path: str | None) -> tuple[dict[str, str], str]:
    """Parse KEY=VALUE from a .env. Returns (values, status-word).

    The returned dict never leaves this process except through leak scanning
    and length reporting. Nothing downstream formats a value.
    """
    if not env_path or env_path.startswith("<"):
        return {}, "none-declared"
    p = Path(env_path)
    if not p.exists():
        return {}, "file-missing"
    values: dict[str, str] = {}
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as exc:                        # noqa: BLE001
        return {}, f"unreadable ({type(exc).__name__})"
    return values, "ok"


def credential_report(values: dict[str, str], declared: list[str]) -> tuple[str, list[str]]:
    """Presence + length only. Never the value, never a prefix, never a suffix."""
    lines, missing = [], []
    for var in declared:
        raw = values.get(var)
        if raw is None:
            lines.append(f"{var}: absent")
            missing.append(var)
        elif raw.lower() in PLACEHOLDERS or len(raw) < MIN_SECRET_LEN:
            lines.append(f"{var}: placeholder ({len(raw)} chars)")
            missing.append(var)
        else:
            lines.append(f"{var}: present ({len(raw)} chars)")
    return "; ".join(lines) if lines else "none declared", missing


def scan_for_leak(text: str, values: dict[str, str]) -> list[str]:
    """Return the NAMES of any credential whose value appears in `text`."""
    if not text:
        return []
    found = []
    for var, val in values.items():
        if val and len(val) >= MIN_SECRET_LEN and val in text:
            found.append(var)
    return found


# --------------------------------------------------------------------------
# probing
# --------------------------------------------------------------------------
def http_get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "lse-connector-probe/1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(20_000).decode("utf-8", "replace")
    except Exception as exc:                        # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def probe_http_loopback(conn: dict) -> dict:
    inv = conn["invoke"]
    base = inv["base_url"].rstrip("/")
    probe = conn.get("probe") or {}
    result = {"checks": [], "bodies": []}

    status, body = http_get(base + probe.get("path", "/"))
    result["bodies"].append(body)
    if status != probe.get("expect_status", 200):
        start = inv.get("start")
        how = (start.get("human") or " ".join(start.get("argv", []))
               ) if isinstance(start, dict) else (start or "see registry")
        auto = " Or let this tool do it: probe.py --id <id> --ensure." \
            if isinstance(start, dict) and start.get("argv") else ""
        result["checks"].append(
            ("reachable", "WARN",
             f"{probe.get('path')} -> HTTP {status or 'no connection'}. "
             f"Start it: {how}.{auto} "
             f"PROMOTION: this WARN is a FAIL if a deliverable cites this connector."))
        return result
    key = probe.get("expect_json_key")
    if key:
        try:
            if key not in json.loads(body):
                result["checks"].append(
                    ("reachable", "FAIL",
                     f"HTTP 200 but the response has no '{key}' — something else "
                     f"is listening on this port, or the API changed shape."))
                return result
        except Exception:                           # noqa: BLE001
            result["checks"].append(("reachable", "FAIL", "probe response is not JSON"))
            return result
    result["checks"].append(("reachable", "OK", f"{probe.get('path')} -> 200"))

    # contract drift: the running process may be older than its own source.
    spec_path = inv.get("openapi")
    declared = [e["path"] for e in inv.get("endpoints", []) if e.get("required")]
    if spec_path and declared:
        status, spec_body = http_get(base + spec_path)
        result["bodies"].append(spec_body)
        if status == 200:
            try:
                live = set(json.loads(spec_body).get("paths", {}))
                gone = [p for p in declared if p not in live]
                if gone:
                    result["checks"].append(
                        ("contract", "FAIL",
                         f"required endpoint(s) absent from the RUNNING process: "
                         f"{', '.join(gone)}. The process is older than its source "
                         f"or the API moved — restart it before routing here, or a "
                         f"404 will read as 'no results'."))
                else:
                    result["checks"].append(
                        ("contract", "OK", f"{len(declared)} required endpoint(s) present"))
            except Exception:                       # noqa: BLE001
                result["checks"].append(("contract", "WARN", "openapi.json unparseable"))
        else:
            result["checks"].append(
                ("contract", "WARN", f"{spec_path} -> HTTP {status}; drift not checkable"))
    return result


def probe_connector(conn: dict) -> dict:
    cid = conn["id"]
    out = {"id": cid, "status": conn.get("status"), "checks": []}
    kind = (conn.get("invoke") or {}).get("kind")

    if conn.get("status") in ("needs_user", "planned"):
        out["checks"].append(
            ("registered", "WARN",
             f"status={conn['status']} — {conn.get('blocked_on', 'not wired')}. "
             f"USER ACTION: {conn.get('user_action', 'see registry.json')}"))
        return out

    bodies: list[str] = []
    if kind == "http_loopback":
        r = probe_http_loopback(conn)
        out["checks"].extend(r["checks"])
        bodies = r["bodies"]
    elif kind == "mcp":
        out["checks"].append(
            ("registered", "OK",
             "MCP-bound; reachability is the session's tool list, not this probe. "
             f"Primary: {(conn.get('invoke') or {}).get('primary', 'n/a')}"))
    else:
        out["checks"].append(("registered", "WARN", f"no probe for invoke.kind={kind!r}"))

    secrets = conn.get("secrets") or {}
    declared = secrets.get("vars") or []
    values, env_status = load_env_values(secrets.get("env_file"))
    if declared:
        if env_status != "ok":
            out["checks"].append(
                ("credential", "WARN",
                 f"env file {env_status}. The USER creates and fills it; the agent "
                 f"never does. PROMOTION: FAIL if a deliverable cites this connector."))
        else:
            summary, missing = credential_report(values, declared)
            out["checks"].append(
                ("credential", "WARN" if missing else "OK", summary))
    else:
        out["checks"].append(("credential", "OK", "no credential required"))

    if secrets.get("leak_scan") and values:
        leaked = []
        for body in bodies:
            leaked.extend(scan_for_leak(body, values))
        if leaked:
            out["checks"].append(
                ("leak", "FAIL",
                 f"a credential VALUE appeared in a response body: "
                 f"{', '.join(sorted(set(leaked)))}. Stop routing here and fix the "
                 f"connector's redaction before any further call."))
        else:
            out["checks"].append(
                ("leak", "OK", f"{len(bodies)} response(s) scanned, no value echoed"))
    return out


# --------------------------------------------------------------------------
# lifecycle — how a caller that is NOT the human at the keyboard gets a
# connector running
# --------------------------------------------------------------------------
# The registry describes connectors a person started by hand. An agent cannot
# assume that: the process may be absent, or present but stale. Three verbs,
# and the split between them is the whole safety story:
#
#   attach   it is up and the contract matches -> use it, touch nothing
#   spawn    nothing is listening -> start it detached, wait for ready
#   restart  something is listening but WRONG -> kill and respawn, and ONLY
#            on an explicit --restart, never inferred from a FAIL
#
# Never kill a process this tool did not start without --restart, and never
# kill one whose command line does not carry the registry's identity_marker:
# the port may belong to something else entirely, and "my probe went green"
# is not worth someone else's process.

def _port_of(base_url: str) -> int | None:
    try:
        return urllib.parse.urlparse(base_url).port
    except Exception:                               # noqa: BLE001
        return None


def _pid_on_port(port: int) -> int | None:
    """netstat is everywhere; psutil is not, and this must never need installing."""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                             timeout=20).stdout
    except Exception:                               # noqa: BLE001
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and "LISTEN" in parts[3].upper():
            if parts[1].endswith(f":{port}"):
                try:
                    return int(parts[4])
                except ValueError:
                    return None
    return None


def _cmdline_of(pid: int) -> str:
    if sys.platform != "win32":
        try:
            return Path(f"/proc/{pid}/cmdline").read_text(errors="replace").replace("\0", " ")
        except Exception:                           # noqa: BLE001
            return ""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
            capture_output=True, text=True, timeout=25).stdout
        return (out or "").strip()
    except Exception:                               # noqa: BLE001
        return ""


def _spawn(start: dict) -> tuple[int | None, str]:
    cwd = Path(start["cwd"])
    log_path = cwd / start.get("log", "connector-autostart.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    flags = 0
    if sys.platform == "win32":
        # Detached + own process group: the connector must outlive this probe,
        # and must not die when the agent's shell goes away mid-session.
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | \
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    handle = open(log_path, "ab")                   # noqa: SIM115 - outlives this call
    proc = subprocess.Popen(start["argv"], cwd=str(cwd), stdout=handle,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            creationflags=flags, close_fds=True)
    return proc.pid, str(log_path)


def _wait_ready(base: str, probe: dict, timeout: int) -> bool:
    import time
    deadline = time.time() + timeout
    url = base.rstrip("/") + probe.get("path", "/")
    while time.time() < deadline:
        status, _ = http_get(url)
        if status == probe.get("expect_status", 200):
            return True
        time.sleep(1.0)
    return False


def ensure(conn: dict, restart: bool = False) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []
    inv = conn.get("invoke") or {}
    if inv.get("kind") != "http_loopback":
        return [("lifecycle", "WARN",
                 f"invoke.kind={inv.get('kind')!r} has no lifecycle verb; "
                 f"nothing to start")]
    start = inv.get("start")
    if not isinstance(start, dict):
        return [("lifecycle", "WARN",
                 "registry has no structured start block, so this connector can "
                 "only be started by a human. Add invoke.start.{cwd,argv}")]
    if not start.get("cwd"):  # its machine root is unset here (regload drops the field)
        return [("lifecycle", "WARN",
                 "invoke.start.cwd does not resolve on this machine (its root is unset): nothing to start")]

    base = inv["base_url"].rstrip("/")
    port = _port_of(base)
    probe = conn.get("probe") or {}
    marker = start.get("identity_marker", "")
    pid = _pid_on_port(port) if port else None

    if pid and restart:
        cmd = _cmdline_of(pid)
        if marker and marker not in cmd:
            return [("lifecycle", "FAIL",
                     f"port {port} is held by PID {pid} whose command line does "
                     f"not contain {marker!r}. Refusing to kill it — that port "
                     f"belongs to something else. Command: {cmd[:90]!r}")]
        checks.append(("lifecycle", "OK",
                       f"stopping PID {pid} (matched {marker!r}) for restart"))
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True, timeout=25)
            else:
                import signal
                os.kill(pid, signal.SIGTERM)        # noqa: F821 - posix branch
        except Exception as exc:                    # noqa: BLE001
            return checks + [("lifecycle", "FAIL", f"could not stop PID {pid}: {exc}")]
        pid = None

    if pid and not restart:
        checks.append(("lifecycle", "OK", f"attached to existing PID {pid} — not "
                                          f"started by this tool, so not touched"))
        return checks

    new_pid, log_path = _spawn(start)
    ready = _wait_ready(base, probe, int(start.get("ready_timeout_s", 45)))
    checks.append(("lifecycle", "OK" if ready else "FAIL",
                   f"spawned PID {new_pid}, "
                   + (f"ready in <{start.get('ready_timeout_s', 45)}s"
                      if ready else
                      f"NOT ready within {start.get('ready_timeout_s', 45)}s — "
                      f"see {log_path}")
                   + f" | log: {log_path}"))
    return checks


# --------------------------------------------------------------------------
# calibration — a scanner that never fires is not a scanner
# --------------------------------------------------------------------------
def selftest() -> int:
    fake = {"DEMO_KEY": "sk-live-9f3a2b7c1d4e", "SHORT": "abc"}
    cases = [
        ("must-flag: value echoed verbatim",
         "…auth failed for key sk-live-9f3a2b7c1d4e…", ["DEMO_KEY"]),
        ("must-flag: value inside JSON",
         '{"error":"bad key","sent":"sk-live-9f3a2b7c1d4e"}', ["DEMO_KEY"]),
        ("must-pass: clean body", '{"count": 18, "recent": []}', []),
        ("must-pass: variable NAME only, no value",
         '{"error":"DEMO_KEY missing"}', []),
        ("must-pass: short value never treated as a secret", "abc abc abc", []),
    ]
    bad = 0
    print(f"{'verdict':9} case")
    print("-" * 66)
    for label, body, expect in cases:
        got = sorted(scan_for_leak(body, fake))
        ok = got == sorted(expect)
        bad += 0 if ok else 1
        print(f"{'ok' if ok else 'BROKEN':9} {label}")
        if not ok:
            print(f"{'':9}   expected {expect}, got {got}")
    print("-" * 66)
    print(f"{len(cases)} cases, {bad} broken — "
          f"{'scanner is two-sided' if not bad else 'SCANNER IS NOT TRUSTWORTHY'}")
    return 1 if bad else 0


# --------------------------------------------------------------------------
def render(results: list[dict]) -> int:
    worst = 0
    for r in results:
        print(f"\n[{r['id']}]  status={r['status']}")
        for name, verdict, detail in r["checks"]:
            print(f"  {verdict:5} {name:11} {detail}")
            if verdict == "FAIL":
                worst = 1
    print()
    fails = sum(1 for r in results for c in r["checks"] if c[1] == "FAIL")
    warns = sum(1 for r in results for c in r["checks"] if c[1] == "WARN")
    print(f"{len(results)} connector(s): {fails} FAIL, {warns} WARN")
    if fails:
        print("A FAIL means: do not route P2 here until it is fixed.")
    return worst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--id")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--base-url", help="override an http_loopback connector's "
                                       "base_url (probe a second copy on another "
                                       "port without editing the registry)")
    ap.add_argument("--ensure", action="store_true",
                    help="attach if it is already up, otherwise start it "
                         "detached and wait for ready. Never kills anything.")
    ap.add_argument("--restart", action="store_true",
                    help="stop and respawn. Requires --ensure. Only ever "
                         "explicit: a contract FAIL never triggers this on its "
                         "own, and a process whose command line does not match "
                         "the registry's identity_marker is never killed.")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    try:
        reg = regload.load(REGISTRY)
    except Exception as exc:                        # noqa: BLE001
        print(f"cannot read registry.json: {exc}")
        return 2
    conns = reg["connectors"]

    if args.list:
        print(f"{'id':22} {'status':11} {'class':16} answers")
        print("-" * 100)
        for c in conns:
            print(f"{c['id']:22} {c['status']:11} {c.get('source_class', ''):16} "
                  f"{c.get('answers', '')[:52]}")
        need = [c for c in conns if c["status"] in ("needs_user", "planned")]
        if need:
            print(f"\n{len(need)} connector(s) waiting on the user:")
            for c in need:
                print(f"  - {c['id']}: {c.get('user_action', '')}")
        return 0

    if args.id:
        chosen = [c for c in conns if c["id"] == args.id]
        if not chosen:
            print(f"no connector with id={args.id!r}; try --list")
            return 2
    elif args.all:
        chosen = conns
    else:
        ap.print_help()
        return 2

    if args.base_url:
        for c in chosen:
            if (c.get("invoke") or {}).get("kind") == "http_loopback":
                c["invoke"]["base_url"] = args.base_url

    if args.restart and not args.ensure:
        print("--restart requires --ensure (restarting IS a form of ensuring). "
              "Refusing to guess.")
        return 2

    lifecycle: dict[str, list] = {}
    if args.ensure:
        for c in chosen:
            if c.get("status") in ("needs_user", "planned"):
                continue
            lifecycle[c["id"]] = ensure(c, restart=args.restart)

    results = []
    for c in chosen:
        r = probe_connector(c)
        if c["id"] in lifecycle:
            r["checks"] = lifecycle[c["id"]] + r["checks"]
        results.append(r)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 1 if any(c[1] == "FAIL" for r in results for c in r["checks"]) else 0
    return render(results)


if __name__ == "__main__":
    raise SystemExit(main())
