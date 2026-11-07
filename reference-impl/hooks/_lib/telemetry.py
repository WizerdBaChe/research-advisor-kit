"""hooks/_lib/telemetry -- one locked append for every telemetry row.

WHY. Windows emulates O_APPEND as seek-to-end + write, which is not atomic
across processes: measured 2026-09-14 (instructions_loaded_logger docstring),
8 processes x 60 events with plain `open(path, "a")` kept 410/480 small rows
and 362/480 large ones -- rows are OVERWRITTEN, not merely interleaved. Until
2026-10-25 only that one hook locked; the other 47 appenders, deny_receipt's
receipt rows included, wrote unlocked. Live loss is small (53,246 rows, 2
torn, counted 2026-10-25) because hooks rarely collide, but a torn deny
receipt is a nonce the reader cannot find, which reads as a forged deny.

HOW. Each row is one `os.write` under a byte-range lock placed far past EOF
(LOCK_OFFSET), so readers of the log are never blocked and the lock never
covers data. If the lock is not obtained within `wait_s` the row is written
anyway: fail-open beats a lost row, and a hook must never stall on logging.
The lock is held for one write, microseconds; the wait is only ever reached
when another process is stalled holding it (a dead holder's lock is released
by the OS).

API (stdlib only, importable from hooks/ -- hooks/ is sys.path[0] when a hook
runs -- and from anywhere else by path):
  append_line(path, text, wait_s=LOCK_WAIT_S) -> bool   text, utf-8, trailing
      newline ensured, parent dir created; True when the lock was held.
  append_bytes(path, data, wait_s=LOCK_WAIT_S) -> bool  the raw form.
Both raise OSError on an unwritable path: the CALLER decides fail-open
(every hook wraps its logging in try/except already).

Proof-of-life: `python hooks/tests/test_lib_telemetry.py` (two-sided: the
unlocked writer must lose rows under contention before the locked writer is
believed for keeping them; an uncontended run is reported undetermined).
"""
import os
import time

try:
    import msvcrt
except ImportError:  # non-Windows
    msvcrt = None
    import fcntl

# One byte far past any real EOF (logs rotate at a few MB); below 2**31 for the
# CRT's 32-bit lock offset.
LOCK_OFFSET = 0x7FFFFFF0
# A hook appends up to three rows (receipt, log, notice budget) inside a 5 s timeout, so the
# per-call wait is 0.5 s: three stalled waits still leave the deny delivered. The OS releases a
# dead holder's byte-range lock, so only a STALLED holder (suspended, blocked in a scanner)
# ever makes a caller wait this long.
LOCK_WAIT_S = 0.5
_POLL_S = 0.005


def _lock(fd, wait_s):
    """Try to take the writer lock until wait_s; -> True if held."""
    deadline = time.monotonic() + wait_s
    while True:
        try:
            if msvcrt:
                os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, LOCK_OFFSET, os.SEEK_SET)
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(_POLL_S)


def _unlock(fd):
    try:
        if msvcrt:
            os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.lockf(fd, fcntl.LOCK_UN, 1, LOCK_OFFSET, os.SEEK_SET)
    except OSError:
        pass  # closing the descriptor releases it anyway


def append_bytes(path, data, wait_s=LOCK_WAIT_S):
    """Append `data` (one whole row) as a single write under the writer lock.

    -> True if the lock was held for the write, False if it was written after
    the wait expired (fail-open). Raises OSError if the file cannot be opened.
    """
    path = os.fspath(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    try:
        locked = _lock(fd, wait_s)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            if locked:
                _unlock(fd)
    finally:
        os.close(fd)
    return locked


def append_line(path, text, wait_s=LOCK_WAIT_S):
    """Append one text row (utf-8, trailing newline ensured). See append_bytes."""
    if not text.endswith("\n"):
        text += "\n"
    return append_bytes(path, text.encode("utf-8"), wait_s)
