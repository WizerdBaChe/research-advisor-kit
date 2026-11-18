r"""Notice budget: one injected notice per hook per session (library, not a registered hook).

STATUS: LIVE since 2026-10-12 (WC-11b, user ruling R-17 = budget B, at the recommended
value; replay in reports/harness-healthcheck-2026-10-12/notice-budget-replay.md).

WHY. 28 days of transcripts showed 2,272 hook notices over 385 main sessions: mean 5.90
per session, p90 16, max 37, 126 sessions above 6, each notice carrying a fixed ~320 B of
self-identification and receipt on top of its content. A notice is read by an agent that
cannot tell it from injected text, so every repeat inside one session is cost without a
new fact. Budget B, ruled 2026-10-12: each notice-emitting hook injects ONCE per session;
the moc-regen note is written to telemetry only (narrowed 2026-10-24, D-072: delivered once
per session once the MOC is overdue, see TELEMETRY-ONLY CLASS); the [canary] and [probe]
calibration instruments are always delivered and never budgeted (narrowed 2026-10-21, see
INSTRUMENT CLASS).

CONTRACT.
  allow(hook_name, session_id, text="") -> bool
      True  = the caller may print its additionalContext / systemMessage now;
      False = the caller must NOT print it (it still writes its own telemetry row, so
              before/after rates stay comparable). Every call also appends one row to
              telemetry/notice-budget.jsonl {ts, hook, session, delivered, reason} so a
              delivered notice and a suppressed one can be told apart afterwards.
  The NOTICE surface only (rules/hook-deny-message.md): never call it before a deny or
  block reason. A refusal is not a notice and has no budget.

KEYS. The budget key is the hook name. A hook whose per-call notice is load-bearing passes
a finer key, `<hook>:<discriminator>` (feedback_notice is once per target by design:
`feedback_notice:<target>`; handoff_snapshot re-arms every 40k tokens of context growth:
`handoff_snapshot:<band>`; subagent_retrieval_brief is delivered into a fresh context per
subagent: `subagent_retrieval_brief:<agent_id>`; dev_mod_notice is once per mod folder:
`dev_mod_notice:<normcased mod root>`; home_uncommitted_notice is once per distinct set of
uncommitted home paths, since a changed set at close-out is a new fact:
`home_uncommitted_notice:<set hash>`), so the count is still centralised here
and the replay can read it. The part before the first ":" is the hook; the budget is
per (session, full key).

TELEMETRY-ONLY CLASS (never True, whatever the session, except the exact keys below):
  * by hook name  -- TELEMETRY_ONLY_HOOKS: moc_closeout_notice (the moc-regen note; the
    ops-health watchdog is its backstop, ruling R-17), EXCEPT the exact keys in
    BUDGETED_EXCEPTIONS, which are budgeted like any other notice (once per session).
    `moc_closeout_notice:overdue` is the one exception: the hook passes it only when the
    MOC is past MOC_OVERDUE_HOURS (tools/graph-snapshot/gs_watchdog.py), so inside the
    window the note stays telemetry-only. User ruling 2026-10-24 (D-072, narrows R-17's
    moc clause): from 10-12 to 10-24 the note fired 211 times, was delivered 0 times, and
    MOC regeneration fell from 3-31 a day to 10 in 13 days. Any other finer key of a
    telemetry-only hook (`moc_closeout_notice:x`) stays telemetry-only.

INSTRUMENT CLASS (always True, never budgeted, one row per call):
  * by text marker -- INSTRUMENT_MARKERS, matched at the START of the text the caller
    passes: "[canary]" (context_runway_shadow's planted keep canary) and "[probe]" (the
    drop canary, delivered by context_runway_shadow and unattended_run). They are the
    compaction-summarizer's calibration controls (references/long-run-probe-design.md
    §2), read back by tools/process-ledger/ledger.py and tools/compact-loss-audit; a
    control that is never delivered cannot fail, so suppressing one is not a saving but
    a blind instrument. R-17 (2026-10-12) listed them as telemetry-only; that clause was
    never wired (the emitters print without allow(), WC-11b fork) and was narrowed by
    user ruling 2026-10-21 (G-3 of the hook-spine audit: "technical question, take the
    system-stable choice"). An instrument call does not consume the hook's own budget.
    Excuse answered: "it is still a notice, so it costs context" -- ~40 tokens once per
    session per band; the cost is the instrument's price, measured in the R-17 replay.

STATE. One small JSON file per session under <state dir>/<session>.json holding
{"keys": {key: first-delivery ts}}. State dir: CLAUDE_NOTICE_BUDGET_DIR, else
<claude dir>/cache/notice-budget (cache/ is gitignored). Files older than STATE_TTL_DAYS
are pruned when a new session file is created, so the directory stays bounded.
Concurrent hooks of one session may race on the file (read-modify-write, atomic replace);
the failure mode is one extra notice, never a lost one.

SUITE MODE. The hooks' own suites drive a hook many times with a fixed session id, and
the state would persist across runs and make a green suite red on its second run. Every
such suite already redirects the hook's telemetry or state with one of the calibration-
only variables in SUITE_ENV_VARS (the hooks' docstrings: "Claude Code never sets them").
While one of them is set and CLAUDE_NOTICE_BUDGET_DIR is not, allow() is a pass-through:
True, no state, no row -- so a hook suite keeps testing detection, composition and rows
exactly as before, and the budget is tested where it can be told apart: test_notice_budget.py
and test_notice_budget_wiring.py set CLAUDE_NOTICE_BUDGET_DIR to opt in. A new hook
suite that redirects through a new variable must add it to SUITE_ENV_VARS; forgetting it
shows up as that suite failing on its second run, not as a silent pass.

FAIL TOWARD TELLING. An unreadable state dir, a missing or non-string session id, any
exception: allow() returns True. An undetermined case is told, never silenced -- the
budget may only suppress what it can DETERMINE is a repeat (global CLAUDE.md, gate
authority). The one exception is the telemetry-only class above, decided by the hook
name alone with no state. Precedence: telemetry-only (by hook) is checked before the
instrument class (by text), so a telemetry-only hook stays silent whatever its text.

Proof-of-life: `python hooks/tests/test_notice_budget.py`.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from _lib.telemetry import append_line  # hooks/ is sys.path[0] when run as a hook
except Exception:  # imported by path from outside hooks/ (a tool, a test)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from _lib.telemetry import append_line
    except Exception:  # the library is broken or absent: a hook must not stop at import over logging
        def append_line(path, text):
            with open(path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(text if text.endswith("\n") else text + "\n")

CLAUDE_DIR =Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
STATE_TTL_DAYS = 14

TELEMETRY_ONLY_HOOKS = frozenset({"moc_closeout_notice"})
BUDGETED_EXCEPTIONS = frozenset({"moc_closeout_notice:overdue"})   # D-072, exact keys only
INSTRUMENT_MARKERS = ("[canary]", "[probe]")
# Calibration-only redirects the hook suites set (each is documented in its hook as
# never set by Claude Code); see SUITE MODE in the module docstring.
SUITE_ENV_VARS = ("CLAUDE_TELEMETRY_DIR", "BCN_STATE_DIR", "CSN_STATE_DIR", "DCN_STATE_DIR",
                  "FBN_STATE_DIR", "DBN_LOG", "MOC_NOTICE_HOME", "GOLIVE_HOME",
                  "PS_ERRORPREF_LOG", "PS_PIPECLOSE_LOG")


def _telemetry_dir() -> Path:
    return Path(os.environ.get("CLAUDE_TELEMETRY_DIR") or (CLAUDE_DIR / "telemetry"))


def _state_dir() -> Path:
    explicit = os.environ.get("CLAUDE_NOTICE_BUDGET_DIR")
    if explicit:
        return Path(explicit)
    return CLAUDE_DIR / "cache" / "notice-budget"


def suite_mode() -> bool:
    """True while a hook suite has redirected the hook and has not opted in (see docstring)."""
    return (not os.environ.get("CLAUDE_NOTICE_BUDGET_DIR")
            and any(os.environ.get(v) for v in SUITE_ENV_VARS))


def hook_of(key: str) -> str:
    """The hook part of a (possibly finer) budget key."""
    return str(key).split(":", 1)[0]


def telemetry_only(key: str, text: str = "") -> str:
    """'' when the notice may be budgeted; else the reason it is telemetry-only. Pure."""
    if hook_of(key) in TELEMETRY_ONLY_HOOKS and str(key) not in BUDGETED_EXCEPTIONS:
        return "telemetry-only:hook"
    return ""


def instrument(text: str = "") -> str:
    """'' unless the text is a calibration instrument; else 'instrument:marker <m>'. Pure."""
    head = str(text or "").lstrip()
    for marker in INSTRUMENT_MARKERS:
        if head.startswith(marker):
            return "instrument:marker " + marker
    return ""


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(name))[:96]


def _log(key: str, session, delivered: bool, reason: str) -> None:
    try:
        d = _telemetry_dir()
        d.mkdir(parents=True, exist_ok=True)
        append_line(d / "notice-budget.jsonl",
                    json.dumps({"ts": int(time.time()), "hook": str(key)[:160],
                                "session": session if isinstance(session, str) else None,
                                "delivered": delivered, "reason": reason},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


def _prune(state: Path) -> None:
    cutoff = time.time() - STATE_TTL_DAYS * 86400
    try:
        for p in [*state.glob("*.json"), *state.glob("*.tmp*")]:   # *.tmp<pid> = orphaned atomic-write temps
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                pass
    except Exception:
        pass


def allow(hook_name: str, session_id, text: str = "") -> bool:
    """May this hook inject its notice now? See the module docstring for the contract."""
    try:
        if suite_mode():
            return True
        why = telemetry_only(hook_name, text)
        if why:
            _log(hook_name, session_id, False, why)
            return False
        inst = instrument(text)
        if inst:
            _log(hook_name, session_id, True, inst)
            return True
        if not isinstance(session_id, str) or not session_id:
            _log(hook_name, session_id, True, "no-session-id")
            return True
        state = _state_dir()
        path = state / (_safe(session_id) + ".json")
        keys = {}
        try:
            keys = json.loads(path.read_text(encoding="utf-8")).get("keys", {})
            if not isinstance(keys, dict):
                keys = {}
        except FileNotFoundError:
            state.mkdir(parents=True, exist_ok=True)
            _prune(state)
        except Exception:
            keys = {}
        if hook_name in keys:
            _log(hook_name, session_id, False, "repeat")
            return False
        keys[hook_name] = int(time.time())
        tmp = path.with_suffix(".tmp%d" % os.getpid())
        tmp.write_text(json.dumps({"keys": keys}), encoding="utf-8")
        os.replace(tmp, path)
        _log(hook_name, session_id, True, "first")
        return True
    except Exception:
        return True
