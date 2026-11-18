"""zotero_ris_export.py gap fills. Rung 0 (example tests), offline: the registry calls are injected.
Cases are the four records `inbox.py bib --ris --check` failed on 2026-11-09 (Moran chapter with no
year anywhere but the ledger; three arXiv items whose ledgers carried no authors). The negative
controls: a record that already has author+year is returned unchanged, and an unavailable registry
adds nothing (the record stays BAD rather than getting an invented value)."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
import zotero_ris_export as zx  # noqa: E402

MORAN_DOI = "10.1007/1-4020-2307-3_12"
MORAN_RIS = [("TY", "GENERIC"), ("DO", MORAN_DOI), ("TI", "Group Theory in Radar and Signal Processing"),
             ("AU", "Moran, William"), ("AU", "Manton, Jonathan H.")]


def tags(rec):
    return [t for t, _ in rec]


class FillYear(unittest.TestCase):
    def test_crossref_year_first(self):
        rec, how = zx.fill_year(list(MORAN_RIS), {"doi": MORAN_DOI, "year": 2004},
                                crossref=lambda d: [("TY", "CHAP"), ("PY", "2004")])
        self.assertEqual(dict(rec)["PY"], "2004")
        self.assertEqual(how, "year from Crossref")

    def test_ledger_year_when_registries_have_none(self):
        rec, how = zx.fill_year(list(MORAN_RIS), {"doi": MORAN_DOI, "year": 2004},
                                crossref=lambda d: [("TY", "CHAP")])
        self.assertEqual(dict(rec)["PY"], "2004")
        self.assertIn("ledger", dict(rec)["N1"])
        self.assertEqual(how, "year from run ledger")

    def test_springer_book_record_year_when_chapter_has_none(self):
        book_doi = "10.1007/1-4020-2307-3"
        table = {MORAN_DOI: [("TY", "CHAP"), ("T2", "NATO Science Series II: Mathematics, Physics and Chemistry"),
                             ("T3", "Computational Noncommutative Algebra and Applications")],
                 book_doi: [("TY", "BOOK"), ("TI", "Computational Noncommutative Algebra and Applications"),
                            ("PY", "2005")]}
        rec, how = zx.fill_year(list(MORAN_RIS), {"doi": MORAN_DOI, "year": 2004}, crossref=table.get)
        self.assertEqual(dict(rec)["PY"], "2005")
        self.assertIn("needs manual check", dict(rec)["N1"])     # ledger disagrees
        self.assertEqual(how, "year from Crossref book record")

    def test_book_record_with_other_title_is_not_used(self):
        table = {MORAN_DOI: [("TY", "CHAP"), ("T2", "Some Other Book")],
                 "10.1007/1-4020-2307-3": [("TY", "BOOK"), ("TI", "Computational Noncommutative Algebra"),
                                           ("PY", "2005")]}
        rec, how = zx.fill_year(list(MORAN_RIS), {"doi": MORAN_DOI}, crossref=table.get)
        self.assertNotIn("PY", tags(rec))

    def test_no_year_anywhere_stays_missing(self):
        rec, how = zx.fill_year(list(MORAN_RIS), {"doi": MORAN_DOI}, crossref=lambda d: None)
        self.assertNotIn("PY", tags(rec))
        self.assertEqual(how, "")

    def test_record_with_year_untouched(self):
        rec0 = MORAN_RIS + [("PY", "2004")]
        rec, how = zx.fill_year(list(rec0), {"doi": MORAN_DOI, "year": 1999},
                                crossref=lambda d: self.fail("must not fetch"))
        self.assertEqual(rec, rec0)


ARX_ITEM = {"manual": {"type": "JOUR", "title": "Cryogenic packaging", "authors": [], "year": None,
                       "url": "https://arxiv.org/abs/2306.09894"}}


def arx_meta(aid):
    return {"ok": True, "year": 2023, "authors": [
        {"family": "Zeng", "given": "Bicheng", "inferred": True},
        {"family": "De-Eknamkul", "given": "Chawina", "inferred": True},
        {"org": "Collaboration"}]}


class FillArxiv(unittest.TestCase):
    def test_authors_and_year_from_arxiv_in_order(self):
        rec0 = zx.ris_from_manual(ARX_ITEM["manual"])
        rec, how = zx.fill_arxiv(rec0, ARX_ITEM, meta=arx_meta)
        d = [v for t, v in rec if t == "AU"]
        self.assertEqual(d, ["Zeng, Bicheng", "De-Eknamkul, Chawina", "Collaboration"])
        self.assertEqual(dict(rec)["PY"], "2023")
        self.assertEqual(tags(rec)[0], "TY")
        self.assertIn("inferred", dict(rec)["N1"])
        self.assertTrue(how)

    def test_registry_unavailable_adds_nothing(self):
        rec0 = zx.ris_from_manual(ARX_ITEM["manual"])
        rec, how = zx.fill_arxiv(list(rec0), ARX_ITEM, meta=lambda a: {"ok": False, "status": 0, "body": "x"})
        self.assertEqual(rec, rec0)
        self.assertEqual(how, "")

    def test_complete_manual_item_not_fetched(self):
        item = {"manual": dict(ARX_ITEM["manual"], authors=["Zeng, B."], year=2023)}
        rec0 = zx.ris_from_manual(item["manual"])
        rec, _ = zx.fill_arxiv(list(rec0), item, meta=lambda a: self.fail("must not fetch"))
        self.assertEqual(rec, rec0)

    def test_versioned_url_strips_version(self):
        seen = []
        item = {"manual": dict(ARX_ITEM["manual"], url="https://arxiv.org/abs/2508.06079v2")}
        zx.fill_arxiv(zx.ris_from_manual(item["manual"]), item, meta=lambda a: seen.append(a) or {"ok": False})
        self.assertEqual(seen, ["2508.06079"])


sys.path.insert(0, str(HERE.parent))
import inbox  # noqa: E402


def src(key, cite):
    return {"key": key, "cite_as": cite, "authors": ["Mu, J."], "year": 2019, "title": cite, "venue": "",
            "publisher": "ieee", "runs": {"r1"}, "rows_full": 1, "rows_partial": 0, "rows_abstract": 0}


class BibIds(unittest.TestCase):
    def test_colliding_cite_ids_are_suffixed_not_dropped(self):
        agg = {"sources": {"a": src("doi:10.1109/group4.2019.8925686", "Mu 2019"),
                           "b": src("doi:10.1109/icocn.2019.8934126", "Mu 2019")}}
        import os, tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"LSE_RUN_HOME": td}):
            ids = [i["id"] for i in inbox.build_bib(agg, [])["items"]]
        self.assertEqual(len(set(ids)), 2, ids)          # old build: ['Mu2019', 'Mu2019']
        self.assertEqual(ids[0], "Mu2019")


if __name__ == "__main__":
    unittest.main()
