"""inbox.py dashboard embed: source text must not reach the <script> data block raw.

Escaping only "</" leaves "<!-- <script", which puts the HTML parser in its double-escaped
state: the real </script> stops ending the block and the rest of the page is swallowed
(reproduced in headless Chromium 2026-10-27). Paper titles are external text."""
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import inbox  # noqa: E402

HOSTILE = "x <!-- <script> y </script> z"


class TestDashboardEmbed(unittest.TestCase):
    def render(self):
        runs = [{"run_id": "r1", "title": HOSTILE, "rows": [], "stubs": []}]
        agg = {"missing": [], "lifted": [], "sources": {}}
        return inbox.render_dashboard(runs, agg, [], [])

    def test_data_block_holds_no_raw_lt(self):
        page = self.render()
        blob = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1)
        self.assertNotIn("<", blob)

    def test_value_round_trips(self):
        page = self.render()
        blob = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1)
        self.assertEqual(json.loads(blob)["runs"][0]["title"], HOSTILE)


if __name__ == "__main__":
    unittest.main()
