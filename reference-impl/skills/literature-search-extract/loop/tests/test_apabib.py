"""apabib.py tests (R20 BB10). Rung 0 (example tests) about: the APA formatter on a FIXED metadata dict
(offline), the fetch path on canned registry answers (offline), and two live registry calls (skipped when
the registry is unreachable). The negative control is the non-existent DOI: it must yield no entry body."""
import json
import socket
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "verify"))
import apabib  # noqa: E402

FRITZSCH_DOI = "10.1007/978-3-030-06019-0_10"
FRITZSCH_META = {
    "ok": True, "via": "crossref", "kind": "book-chapter", "doi": FRITZSCH_DOI, "year": 2019,
    "authors": [{"family": "Fritzsch", "given": "Jonas"}, {"family": "Bogner", "given": "Justus"},
                {"family": "Zimmermann", "given": "Alfred"}, {"family": "Wagner", "given": "Stefan"}],
    "editors": [], "title": "From Monolith to Microservices: A Classification of Refactoring Approaches",
    "containers": ["Lecture Notes in Computer Science",
                   "Software Engineering Aspects of Continuous Development and New Paradigms of Software Production and Deployment"],
    "volume": "", "issue": "", "pages": "128-141", "publisher": "Springer International Publishing", "edition": "",
}


def online() -> bool:
    try:
        socket.create_connection(("api.crossref.org", 443), timeout=5).close()
        return True
    except OSError:
        return False


class Formatter(unittest.TestCase):
    def test_book_chapter_with_series(self):
        self.assertEqual(
            apabib.format_apa(FRITZSCH_META),
            "Fritzsch, J., Bogner, J., Zimmermann, A., & Wagner, S. (2019). From Monolith to Microservices: "
            "A Classification of Refactoring Approaches. In *Software Engineering Aspects of Continuous Development "
            "and New Paradigms of Software Production and Deployment* (Lecture Notes in Computer Science, pp. 128–141). "
            f"Springer International Publishing. https://doi.org/{FRITZSCH_DOI}")

    def test_journal_article(self):
        m = {"kind": "journal-article", "doi": "10.1/x", "year": 2023, "title": "A title",
             "authors": [{"family": "Li", "given": "Chia-Yu"}, {"family": "Silva", "given": "Ivan F. da"}],
             "containers": ["J. of Things"], "volume": "49", "issue": "8", "pages": "4213-4242"}
        self.assertEqual(apabib.format_apa(m),
                         "Li, C.-Y., & Silva, I. F. da. (2023). A title. *J. of Things, 49*(8), 4213–4242. https://doi.org/10.1/x")

    def test_preprint_and_missing_year(self):
        m = {"kind": "preprint", "arxiv_id": "2608.15135", "year": None, "title": "T", "publisher": "arXiv",
             "authors": [{"family": "Nijhara", "given": "G."}]}
        self.assertEqual(apabib.format_apa(m),
                         "Nijhara, G. (n.d.). *T* (arXiv:2608.15135) [Preprint]. arXiv. https://arxiv.org/abs/2608.15135")

    def test_author_list_rules(self):
        a = lambda n: [{"family": f"F{i}", "given": "G"} for i in range(n)]  # noqa: E731
        self.assertEqual(apabib.author_list(a(2)), "F0, G., & F1, G.")
        self.assertTrue(apabib.author_list(a(21)).endswith(", . . . F20, G."))
        self.assertEqual(apabib.author_list([{"org": "Microsoft"}]), "Microsoft")

    def test_no_given_name_is_not_invented(self):
        self.assertEqual(apabib.one_author({"family": "Madonna", "given": ""}), "Madonna")


class OfflineFetch(unittest.TestCase):
    def setUp(self):
        self._get = apabib.GET

    def tearDown(self):
        apabib.GET = self._get

    def canned(self, table):
        def get(url):
            for k, v in table.items():
                if k in url:
                    return v
            return 404, b"Resource not found.", "text/plain", url
        apabib.GET = get

    def test_fetch_maps_crossref_record_in_registry_order(self):
        msg = {"message": {"type": "book-chapter", "DOI": FRITZSCH_DOI, "title": [FRITZSCH_META["title"]],
                           "issued": {"date-parts": [[2019]]}, "page": "128-141",
                           "author": [{"family": f["family"], "given": f["given"]} for f in FRITZSCH_META["authors"]],
                           "container-title": FRITZSCH_META["containers"], "publisher": "Springer"}}
        self.canned({"api.crossref.org": (200, json.dumps(msg).encode(), "application/json", "")})
        res = apabib.build([(FRITZSCH_DOI, "doi", FRITZSCH_DOI)])
        self.assertEqual([a["family"] for a in res["entries"][0]["meta"]["authors"]],
                         ["Fritzsch", "Bogner", "Zimmermann", "Wagner"])

    def test_record_dates_are_not_a_publication_year(self):
        # Moran & Manton chapter: Crossref carries only created/deposited (2006); the book is 2004.
        msg = {"message": {"type": "book-chapter", "title": ["Group Theory in Radar and Signal Processing"],
                           "issued": {"date-parts": [[None]]}, "created": {"date-parts": [[2006, 6, 23]]},
                           "author": [{"family": "Moran", "given": "William"}]}}
        self.canned({"api.crossref.org": (200, json.dumps(msg).encode(), "application/json", "")})
        meta = apabib.meta_crossref("10.1007/1-4020-2307-3_12", apabib.Guard())
        self.assertIsNone(meta["year"])          # old build: 2006
        self.assertIn("(n.d.)", apabib.format_apa(meta))

    def test_unknown_doi_is_manual_with_no_body(self):
        self.canned({})
        res = apabib.build([("10.9999/x", "doi", "10.9999/x")])
        self.assertEqual(res["entries"], [])
        self.assertEqual(len(res["manual"]), 1)
        self.assertIn(apabib.MANUAL, apabib.render(res))

    def test_diff_flags_author_order(self):
        rows = {"arxiv:1807.10059": {"expect_authors": ["Fritzsch", "Bogner", "Wagner", "Zimmermann"],
                                     "expect_year": 2019, "expect_title": FRITZSCH_META["title"]}}
        d = apabib.diff_entry(FRITZSCH_META, rows, ("doi", FRITZSCH_DOI))   # matched by title
        self.assertEqual(d["status"], "DIFF")
        self.assertIn("authors: ORDER differs", d["problems"])
        ok = dict(rows["arxiv:1807.10059"], expect_authors=["Fritzsch", "Bogner", "Zimmermann", "Wagner"])
        self.assertEqual(apabib.diff_entry(FRITZSCH_META, {"arxiv:1807.10059": ok}, ("doi", FRITZSCH_DOI))["status"], "match")


@unittest.skipUnless(__import__("os").environ.get("LSE_LIVE_TESTS") == "1" and online(),
                     "live registry tests: set LSE_LIVE_TESTS=1 (they send two requests to Crossref)")
class LiveRegistry(unittest.TestCase):
    def test_fritzsch_author_order_live(self):
        res = apabib.build([(FRITZSCH_DOI, "doi", FRITZSCH_DOI)])
        self.assertEqual(res["manual"], [])
        fam = [a["family"] for a in res["entries"][0]["meta"]["authors"]]
        self.assertEqual(fam, ["Fritzsch", "Bogner", "Zimmermann", "Wagner"])
        self.assertTrue(res["entries"][0]["apa"].startswith("Fritzsch, J., Bogner, J., Zimmermann, A., & Wagner, S. (2019)."))

    def test_nonexistent_doi_live_is_needs_manual_check(self):
        res = apabib.build([("10.9999/does-not-exist-r20", "doi", "10.9999/does-not-exist-r20")])
        self.assertEqual(res["entries"], [])
        self.assertEqual(len(res["manual"]), 1)
        out = apabib.render(res)
        self.assertIn(apabib.MANUAL, out)
        self.assertNotIn("https://doi.org/10.9999", out)       # no entry body, no fabricated URL


if __name__ == "__main__":
    unittest.main()
