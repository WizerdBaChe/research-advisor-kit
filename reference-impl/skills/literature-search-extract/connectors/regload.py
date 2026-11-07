#!/usr/bin/env python3
r"""The one loader for connectors/registry.json.

Path fields in the registry are written as `${NAME}/rest` (NAME = a machine root such as HOME,
WORK_ROOT, TEXTBOOKS) and resolved here, at read time, through hooks/_lib/roots.py. A field whose
root is unset on this machine (or whose host.toml is absent) is DROPPED from its object, so callers
see the same thing as "this connector has no such path": their existing `.get(...)` / "not
readable" branches apply and nothing crashes.

review-when: the registry gains a path field that is not a plain string value.
"""
from __future__ import annotations

import json
import sys as _hksys  # machine roots at run time (platform/codemod_roots.py, build plan H-1)
from pathlib import Path as _HKPath
_hksys.path.insert(0, str(_HKPath(__file__).resolve().parents[3] / "hooks" / "_lib"))
import roots as hkroots  # noqa: E402


def _resolve(node):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            r = _resolve(v)
            if r is not _UNSET:
                out[k] = r
        return out
    if isinstance(node, list):
        return [r for r in (_resolve(v) for v in node) if r is not _UNSET]
    if isinstance(node, str) and "${" in node:
        try:
            e = hkroots.expand(node)
        except hkroots.HostFileMissing:
            e = None
        return _UNSET if e is None else e
    return node


_UNSET = object()


def load(path: _HKPath) -> dict:
    """Parse the registry and expand every `${NAME}` string; unresolved fields are dropped."""
    return _resolve(json.loads(_HKPath(path).read_text(encoding="utf-8")))
