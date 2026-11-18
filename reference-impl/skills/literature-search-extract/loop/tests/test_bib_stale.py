"""BB12 (R20): registering a run tells the user when the central bibliography is behind. Offline, temp library only.
Both sides: a fresh library is STALE after register (positive control: the notice fires), and is current once
`inbox.py bib` has written the JSON (negative control: the notice goes silent)."""
import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import inbox  # noqa: E402
import runs  # noqa: E402

GOOD = HERE / "fixtures" / "good-run"


class BibStale(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lse-bibstale-"))
        self.env = {"LSE_RUN_HOME": self.tmp / "lit" / "EvidenceRuns", "LSE_BIB_HOME": self.tmp / "lit" / "Bibliography",
                    "LSE_RUN_UNFILED": self.tmp / "unf", "LSE_BRIDGE_PATH": self.tmp / "bridge.md",
                    "LSE_REGISTRY_PATH": self.tmp / "registry.json"}
        self._saved = {k: os.environ.get(k) for k in self.env}
        for k, v in self.env.items():
            os.environ[k] = str(v)
        shutil.copy(runs.SKILL_DIR / "consumers" / "registry.json", self.tmp / "registry.json")
        with contextlib.redirect_stdout(io.StringIO()):
            runs.cmd_init(argparse.Namespace())
        self.d = self.env["LSE_RUN_HOME"] / "20260903_good-copy"
        shutil.copytree(GOOD, self.d)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        for k, old in self._saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old

    def register(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = runs.cmd_register(argparse.Namespace(run_dir=str(self.d)))
        self.assertEqual(rc, 0)
        return out.getvalue(), err.getvalue()

    def test_register_notices_then_goes_silent_after_bib_export(self):
        out, err = self.register()
        self.assertIn("central bibliography is stale", err)
        self.assertIn("bib --ris", err)                       # names the command
        self.assertEqual(json.loads(out)["registered"], "20260903_ag-lspp-633nm-fixture")   # stdout stays one JSON line
        s = inbox.bib_staleness("20260903_good-copy")
        self.assertEqual(s["missing"], ["doi:10.0000/fake.2022.234"])
        with contextlib.redirect_stdout(io.StringIO()):
            inbox.cmd_bib(argparse.Namespace(out=None, ris=False))
        self.assertEqual(inbox.stale_notice("20260903_good-copy"), "")
        _, err2 = self.register()
        self.assertNotIn("stale", err2)

    def test_changed_access_level_is_stale(self):
        self.register()
        with contextlib.redirect_stdout(io.StringIO()):
            inbox.cmd_bib(argparse.Namespace(out=None, ris=False))
        f = self.env["LSE_BIB_HOME"] / "evidence-runs-bib.json"
        j = json.loads(f.read_text(encoding="utf-8"))
        j["items"][0]["_access"] = "abstract"                 # the file says abstract; the ledger says full
        f.write_text(json.dumps(j), encoding="utf-8")
        s = inbox.bib_staleness()
        self.assertEqual(s["changed"], ["doi:10.0000/fake.2022.234"])


if __name__ == "__main__":
    unittest.main()
