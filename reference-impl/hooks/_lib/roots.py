r"""Machine roots, read at run time from `<config home>/adapt/host.toml`.

Code never spells a machine folder (a share folder, a vault, an install path): it asks
this module. The giver and every member run the same code path; only host.toml
differs (a member's is written by `healthcheck.py bind`, schema `hk-host/1`).

  root("SHARE_ROOT")            -> Path | None   (None = this machine has no such folder)
  path("SHARE_ROOT", "a", "b")  -> Path | None
  expand("${SHARE_ROOT}/x")     -> str | None    (for paths stored in data files)
  tool("codex")                 -> Path | None   (host.toml TOOL_CODEX, else shutil.which("codex"))

Names: CLAUDE_HOME, HOME (always known), WORK_ROOT, SHARE_ROOT, DATA_ROOT, and the
data-folder roles of the packager (`notes-vault`, `research`, ...; key NOTES_VAULT,
RESEARCH, ...), which fall back to DATA_ROOT/<role> when not set on their own.

An unset key is None (the caller decides: skip the feature, or UNDETERMINED in a
test). A MISSING host.toml is different and loud (HostFileMissing): a guard that
silently lost its redlines because the file vanished would fail open. A value of
`none`/empty, or a relative path, counts as unset. `HK_HOST_TOML` overrides the
file location (tests).
"""
from __future__ import annotations

import os
import re
import shutil
import tomllib
from pathlib import Path

CLAUDE_HOME = Path(__file__).resolve().parents[2]
SCHEMA = "hk-host/1"
_VAR = re.compile(r"\$\{([A-Za-z][\w-]*)\}")
_cache: dict | None = None
_cache_key: str | None = None


class HostFileMissing(RuntimeError):
    """adapt/host.toml is absent: roots cannot be known, which is never the same as 'unset'."""


def host_file() -> Path:
    env = os.environ.get("HK_HOST_TOML")
    return Path(env) if env else CLAUDE_HOME / "adapt" / "host.toml"


def _facts() -> dict:
    global _cache, _cache_key
    f = host_file()
    if _cache is not None and _cache_key == str(f):
        return _cache
    if not f.is_file():
        raise HostFileMissing(f"{f} is absent; machine roots unknown (write it, or run healthcheck.py bind)")
    data = tomllib.loads(f.read_text(encoding="utf-8"))
    _cache, _cache_key = {str(k).upper().replace("-", "_"): v for k, v in data.items()}, str(f)
    return _cache


def _key(name: str) -> str:
    return name.upper().replace("-", "_")


def _as_root(value) -> Path | None:
    if not isinstance(value, str) or value.strip().lower() in ("", "none"):
        return None
    p = Path(value.strip())
    return p if p.is_absolute() else None


def root(name: str) -> Path | None:
    key = _key(name)
    if key == "CLAUDE_HOME":
        return CLAUDE_HOME
    if key == "HOME":
        return CLAUDE_HOME.parent
    facts = _facts()
    if key in facts:
        return _as_root(facts[key])
    if key in ("WORK_ROOT", "SHARE_ROOT", "DATA_ROOT"):
        return None
    base = _as_root(facts.get("DATA_ROOT"))  # a data-folder role defaults under DATA_ROOT
    return base / name.lower().replace("_", "-") if base else None


def raw(name: str):
    """The host.toml value of a non-path key as written (a list, a number), or None when unset."""
    return _facts().get(_key(name))


def path(name: str, *parts: str) -> Path | None:
    r = root(name)
    return r.joinpath(*parts) if r else None


def expand(text: str) -> str | None:
    """`${NAME}/rest` -> the resolved path text, or None if any named root is unset."""
    out, missing = text, False
    for m in _VAR.finditer(text):
        r = root(m.group(1))
        if r is None:
            missing = True
            break
        out = out.replace(m.group(0), r.as_posix())
    return None if missing else out


def tool(name: str) -> Path | None:
    # TOOL_ prefix: a data-folder role may share a program's name (role `ollama` vs the ollama binary)
    v = _facts().get("TOOL_" + _key(name))
    if isinstance(v, str) and v.strip() and v.strip().lower() != "none":
        return Path(v.strip())
    found = shutil.which(name.lower())
    return Path(found) if found else None


def selftest() -> list[str]:
    """Problems with this machine's host.toml (empty list = fine)."""
    try:
        facts = _facts()
    except HostFileMissing as e:
        return [str(e)]
    probs = []
    if facts.get("SCHEMA", SCHEMA) != SCHEMA:
        probs.append(f"schema {facts.get('SCHEMA')!r} != {SCHEMA}")
    for k, v in facts.items():
        if isinstance(v, str) and v.strip() and v.strip().lower() != "none" and not Path(v.strip()).is_absolute() \
                and k.endswith(("_ROOT",)):
            probs.append(f"{k} = {v!r} is relative: read as unset")
    return probs


if __name__ == "__main__":
    if {"-h", "--help"} & set(__import__("sys").argv[1:]):  # cli-help-guard: help never runs the tool
        print(__doc__ or "<path>: no module docstring"); raise SystemExit(0)
    import sys
    p = selftest()
    print("\n".join(p) if p else f"roots: ok ({host_file()})")
    sys.exit(1 if p else 0)
