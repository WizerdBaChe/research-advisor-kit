#!/usr/bin/env python3
r"""zotero_local - real bibliographic metadata for the local PDF library.

WHAT IT ADDS OVER pdf_index.py. That one reads FILENAMES, so it can tell you a
paper is in the library and nothing more: no DOI, no journal, no abstract, no
full author list. Every local hit therefore still needed an identifier
resolution round-trip before it could enter a deliverable. This reads Zotero's
own database, where those fields already exist — measured on this library
(2026-08-27): 126 DOIs, 99 abstracts, 92 journal titles across 150 real items.

READ-ONLY, AND COPY FIRST. Zotero holds a write lock on zotero.sqlite while it
runs, and a reader that trips over a mid-write page gets a corrupt answer, not
an error. So this copies the database to a temp file and reads the copy — it
never opens the live file, never writes, and works whether or not Zotero is
running. That is also why it does not use the local HTTP API on port 23119:
the API needs the app open, the file does not.

WHAT IT IS NOT. Not a citation authority. Zotero's fields are whatever the
import put there, and a wrong DOI in Zotero is a wrong DOI here. It removes the
LOOKUP, not the VERIFICATION: anything load-bearing still goes through P2
identifier resolution and the P4.5 support-span check. The difference is that
those now start from a real DOI instead of a guess from a filename.

MARKS, AND WHO MADE THEM (added 2026-09-14, researcher.tw review B-8, user
ruling R4). `--annotations` lists the highlights, underlines, notes and child
notes already on an item's PDFs, each tagged with an ORIGIN: owner (made in
Zotero, no author name), named (made in Zotero under a name), tool (the name
is declared in `invoke.annotation_tool_authors` or `--tool-author`), external
(embedded in the PDF file itself — any reader or program), unattributed (child
notes: Zotero records no author, and plugins write notes too). The user expects
an AI-assisted library to pre-annotate papers, so the split is the contract:
only owner marks may be read as the user's own attention, and even those are
confirmed; every other origin is a pointer to look, never the user's pick and
never evidence. Measured 2026-09-14: this library holds 0 annotations and 114
child notes, so the origin logic is calibrated on an in-memory fixture built
with Zotero 9.0.6's real column names.

Usage:
    python zotero_local.py --search perovskite hysteresis
    python zotero_local.py --resolve <ITEMKEY>     full record + attachment path
    python zotero_local.py --stats                 coverage of the metadata itself
    python zotero_local.py --annotations <KEY> [--json] [--tool-author NAME]
                                                   marks on the item's PDFs + child notes, origin-tagged
    python zotero_local.py --selftest              two-sided calibration
Exit: 0 ok, 1 no match / no library, 2 bad usage.
review-when: Zotero changes its schema (a major version bump), or the library
moves — `invoke.db` on the zotero_local entry in registry.json is the one edit.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "registry.json"
sys.path.insert(0, str(HERE))
import regload  # noqa: E402  (registry loader: expands ${ROOT} path fields)

# Fields worth lifting. Zotero stores everything as (item, field, value) rows;
# these are the ones a citation actually needs.
WANTED = ("title", "DOI", "abstractNote", "publicationTitle", "date", "url",
          "volume", "issue", "pages", "ISSN", "journalAbbreviation", "extra",
          "archiveID")   # Zotero 7 preprint field ('arXiv:2405.00208'); older imports keep it in `extra`

# Zotero.Annotations.ANNOTATION_TYPE_* (zotero/zotero chrome/content/zotero/xpcom/annotations.js,
# read 2026-09-14). An integer outside this map prints as type-N, never guessed.
ANNOT_TYPES = {1: "highlight", 2: "note", 3: "image", 4: "ink", 5: "underline", 6: "text"}
PROVENANCE_RULE = (
    "origin: owner = made in Zotero with no author name (presumed the library owner) | "
    "named = made in Zotero under an author name | tool = author name declared as a tool | "
    "external = embedded in the PDF file (any reader or program) | unattributed = child note. "
    "Only owner marks may be read as the user's own picks, and those are confirmed, not assumed; "
    "no mark is evidence until its text is found in the paper.")


def registered() -> dict:
    try:
        reg = regload.load(REGISTRY)
    except Exception:                                       # noqa: BLE001
        return {}
    for c in reg.get("connectors", []):
        if c.get("id") == "zotero_local":
            return (c.get("invoke") or {})
    return {}


def open_snapshot(db_path: Path) -> tuple[sqlite3.Connection, Path] | None:
    """Copy, then read the copy. Never touch the live file."""
    if not db_path.is_file():
        return None
    tmp = Path(tempfile.mkdtemp(prefix="zotero-ro-")) / "zot.sqlite"
    try:
        shutil.copy2(db_path, tmp)
    except OSError:
        return None
    return sqlite3.connect(f"file:{tmp}?mode=ro", uri=True), tmp


def load_items(con: sqlite3.Connection) -> list[dict]:
    """Every non-trashed, non-attachment, non-note item with its fields."""
    rows: dict[int, dict] = {}
    q = """
        SELECT i.itemID, i."key", t.typeName
          FROM items i
          JOIN itemTypes t ON t.itemTypeID = i.itemTypeID
         WHERE t.typeName NOT IN ('attachment','note','annotation')
           AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
    """
    for item_id, item_key, type_name in con.execute(q):
        rows[item_id] = {"item_key": item_key, "type": type_name,
                         "creators": [], "attachments": []}

    qf = """
        SELECT d.itemID, f.fieldName, v.value
          FROM itemData d
          JOIN fields f ON f.fieldID = d.fieldID
          JOIN itemDataValues v ON v.valueID = d.valueID
    """
    for item_id, field, value in con.execute(qf):
        if item_id in rows and field in WANTED:
            rows[item_id][field] = value

    qc = """
        SELECT ic.itemID, c.lastName, c.firstName
          FROM itemCreators ic
          JOIN creators c ON c.creatorID = ic.creatorID
         ORDER BY ic.orderIndex
    """
    for item_id, last, first in con.execute(qc):
        if item_id in rows:
            rows[item_id]["creators"].append((last or "").strip())

    # storage:<filename> lives under storage/<attachment item key>/<filename>
    qa = """
        SELECT a.parentItemID, ai."key", a.path, a.contentType
          FROM itemAttachments a
          JOIN items ai ON ai.itemID = a.itemID
         WHERE a.path IS NOT NULL AND a.parentItemID IS NOT NULL
    """
    for parent, att_key, path, ctype in con.execute(qa):
        if parent in rows and str(path).startswith("storage:"):
            rows[parent]["attachments"].append(
                {"key": att_key, "file": str(path)[len("storage:"):],
                 "content_type": ctype})
    return list(rows.values())


def attachment_path(root: Path, att: dict) -> Path:
    return root / att["key"] / att["file"]


def cite_of(it: dict) -> str:
    who = it["creators"][0] if it["creators"] else "?"
    if len(it["creators"]) > 1:
        who += " et al."
    year = (it.get("date") or "")[:4] or "n.d."
    return f"{who} {year}"


def render(it: dict, root: Path, full: bool = False) -> None:
    print(f"  {cite_of(it):24} {it.get('title', '(untitled)')[:66]}")
    bits = []
    if it.get("DOI"):
        bits.append(f"DOI {it['DOI']}")
    if it.get("publicationTitle"):
        bits.append(it["publicationTitle"][:40])
    bits.append(it["type"])
    print(f"        {' | '.join(bits)}")
    pdfs = [a for a in it["attachments"] if a["file"].lower().endswith(".pdf")]
    for a in pdfs:
        p = attachment_path(root, a)
        print(f"        PDF {'[on disk]' if p.is_file() else '[MISSING]'} {p}")
    if not pdfs:
        print("        no PDF attached -> metadata only, cannot reach [full]")
    if full and it.get("abstractNote"):
        print(f"        abstract: {it['abstractNote'][:400]}")
    print(f"        item_key: {it['item_key']}")


def annotation_origin(is_external, author_name, tool_authors) -> str:
    """Who put the mark there, as far as the database can say. A declared tool name wins even
    on an embedded mark; an embedded mark's author field is whatever the PDF claimed, so it
    never promotes the mark to a named person."""
    name = (author_name or "").strip().casefold()
    if name and name in {t.strip().casefold() for t in tool_authors}:
        return "tool"
    if is_external:
        return "external"
    return "named" if name else "owner"


def note_text(body: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", body or "")).split())


def load_marks(con: sqlite3.Connection, item_key: str, tool_authors=()) -> dict | None:
    """Annotations on the item's attachments (or on the attachment itself) + its child notes."""
    row = con.execute(
        'SELECT i.itemID, t.typeName FROM items i JOIN itemTypes t ON t.itemTypeID = i.itemTypeID '
        'WHERE upper(i."key") = upper(?)', (item_key,)).fetchone()
    trashed = {r[0] for r in con.execute("SELECT itemID FROM deletedItems")}
    if not row or row[0] in trashed:
        return None
    item_id, type_name = row
    notes_of = item_id
    if type_name == "attachment":
        # this PDF's own marks only, but the paper's child notes: a note is about the paper, not the file
        att_ids = [item_id]
        par = con.execute("SELECT parentItemID FROM itemAttachments WHERE itemID = ?", (item_id,)).fetchone()
        notes_of = par[0] if par and par[0] is not None else None
    else:
        att_ids = [r[0] for r in con.execute(
            "SELECT itemID FROM itemAttachments WHERE parentItemID = ?", (item_id,)) if r[0] not in trashed]
    marks = []
    if att_ids:
        q = f"""
            SELECT a.itemID, ai."key", a.type, a.authorName, a.text, a.comment,
                   a.color, a.pageLabel, a.isExternal
              FROM itemAnnotations a
              JOIN items ai ON ai.itemID = a.itemID
             WHERE a.parentItemID IN ({",".join("?" * len(att_ids))})
             ORDER BY a.parentItemID, a.sortIndex
        """
        for aid, akey, typ, author, text, comment, color, page, ext in con.execute(q, att_ids).fetchall():
            if aid in trashed:
                continue
            tags = [t for (t,) in con.execute(
                "SELECT tg.name FROM itemTags it JOIN tags tg ON tg.tagID = it.tagID WHERE it.itemID = ?", (aid,))]
            marks.append({"key": akey, "origin": annotation_origin(ext, author, tool_authors),
                          "kind": ANNOT_TYPES.get(typ, f"type-{typ}"), "text": text or "",
                          "comment": comment or "", "locator": f"p.{page}" if page else "",
                          "author": author or "", "color": color or "", "tags": tags})
    notes = []
    if notes_of is not None:
        qn = ('SELECT n.itemID, i."key", n.title, n.note FROM itemNotes n '
              'JOIN items i ON i.itemID = n.itemID WHERE n.parentItemID = ?')
        for nid, nkey, title, body in con.execute(qn, (notes_of,)).fetchall():
            if nid not in trashed:
                notes.append({"key": nkey, "origin": "unattributed", "kind": "child-note",
                              "title": title or "", "text": note_text(body)})
    return {"item_key": item_key.upper(), "item_type": type_name, "attachments": len(att_ids),
            "annotations": marks, "notes": notes, "provenance_rule": PROVENANCE_RULE}


def read_marks(item_key: str, db=None, tool_authors=None) -> tuple[dict | None, str]:
    """Snapshot-and-read wrapper for callers outside this file (paper-distill ingest)."""
    inv = registered()
    dbp = Path(db or inv.get("db", ""))
    tools = list(inv.get("annotation_tool_authors", [])) + list(tool_authors or [])
    snap = open_snapshot(dbp)
    if not snap:
        return None, f"Zotero database not readable: {dbp}"
    con, tmp = snap
    try:
        return load_marks(con, item_key, tools), ""
    finally:
        con.close()
        shutil.rmtree(tmp.parent, ignore_errors=True)


def render_marks(res: dict) -> None:
    a, n = res["annotations"], res["notes"]
    print(f"{res['item_key']} ({res['item_type']}): {len(a)} annotation(s) on "
          f"{res['attachments']} attachment(s), {len(n)} child note(s)")
    counts: dict[str, int] = {}
    for m in a:
        counts[m["origin"]] = counts.get(m["origin"], 0) + 1
    if counts:
        print("origins: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    for m in a:
        line = f"  [{m['origin']:8}] {m['kind']:9} {m['locator']:7} \"{m['text'][:120]}\""
        if m["comment"]:
            line += f"  -- {m['comment'][:80]}"
        print(line)
    for x in n:
        print(f"  [unattributed] child-note \"{x['title'][:60]}\": {x['text'][:160]}")
    if not a and not n:
        print("  no marks: Stage 0 runs unseeded. An unmarked PDF is not a finding.")
    print("\n" + PROVENANCE_RULE)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--search", nargs="+")
    ap.add_argument("--resolve")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--annotations", metavar="KEY")
    ap.add_argument("--json", action="store_true", help="with --annotations: one JSON object on stdout")
    ap.add_argument("--tool-author", action="append", default=[],
                    help="author name a pre-annotating tool writes under (repeatable)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--db")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.annotations:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        res, err = read_marks(args.annotations, args.db, args.tool_author)
        if err:
            print(err)
            return 1
        if res is None:
            print(f"no item with key {args.annotations}")
            return 1
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            render_marks(res)
        return 0

    inv = registered()
    db = Path(args.db or inv.get("db", ""))
    root = Path(inv.get("storage", db.parent / "storage" if db.name else ""))
    snap = open_snapshot(db)
    if not snap:
        print(f"Zotero database not readable: {db}\n"
              "Set invoke.db on the zotero_local entry in registry.json, or "
              "pass --db. Nothing else is needed — the app may stay closed.")
        return 1
    con, tmp = snap
    try:
        items = load_items(con)
    finally:
        con.close()
        shutil.rmtree(tmp.parent, ignore_errors=True)

    if args.stats:
        n = len(items)
        with_doi = sum(1 for i in items if i.get("DOI"))
        with_abs = sum(1 for i in items if i.get("abstractNote"))
        with_pdf = sum(1 for i in items
                       if any(a["file"].lower().endswith(".pdf") for a in i["attachments"]))
        print(f"library:   {db}")
        print(f"items:     {n} (attachments and notes excluded)")
        print(f"with DOI:  {with_doi} ({round(100 * with_doi / n) if n else 0}%)"
              " <- these skip the identifier-resolution round-trip")
        print(f"with abstract: {with_abs}")
        print(f"with a PDF on disk: {with_pdf} <- only these can reach [full]")
        print(f"\nThe {n - with_doi} items without a DOI still need P2 resolution, "
              f"and the {n - with_pdf} without a PDF cap at [abstract] no matter "
              f"how complete their metadata looks. Quote both when a claim rests "
              f"only on this library.")
        return 0

    if args.resolve:
        for it in items:
            if it["item_key"].upper() == args.resolve.upper():
                render(it, root, full=True)
                return 0
        print(f"no item with key {args.resolve}")
        return 1

    if args.search:
        needles = [t.casefold() for t in args.search]
        hits = []
        for it in items:
            hay = " ".join([it.get("title", ""), it.get("abstractNote", ""),
                            it.get("publicationTitle", ""),
                            " ".join(it["creators"]), it.get("date", "")]).casefold()
            score = sum(1 for nd in needles if nd in hay)
            if score:
                hits.append((score, it))
        if not hits:
            print(f"no match for {' '.join(args.search)} in {len(items)} items.\n"
                  "An empty local result never means 'literature not found' — go to "
                  "P2 web discovery and record in search_trail that the library "
                  "was checked.")
            return 1
        hits.sort(key=lambda x: (-x[0], -(int((x[1].get("date") or "0")[:4] or 0))))
        print(f"{len(hits)} of {len(items)} library items match "
              f"{' '.join(args.search)!r}:\n")
        for _, it in hits[:20]:
            render(it, root)
        print("\nMetadata is Zotero's, not verified: a wrong DOI in Zotero is "
              "wrong here too. This removes the lookup, not the verification.")
        return 0

    ap.print_help()
    return 2


def _marks_fixture() -> sqlite3.Connection:
    """In-memory library with Zotero 9.0.6's column names (PRAGMA on the real file, 2026-09-14)."""
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE itemTypes(itemTypeID INTEGER PRIMARY KEY, typeName TEXT);
        CREATE TABLE items(itemID INTEGER PRIMARY KEY, itemTypeID INT, "key" TEXT);
        CREATE TABLE deletedItems(itemID INTEGER PRIMARY KEY);
        CREATE TABLE itemAttachments(itemID INTEGER PRIMARY KEY, parentItemID INT, path TEXT, contentType TEXT);
        CREATE TABLE itemAnnotations(itemID INTEGER PRIMARY KEY, parentItemID INT NOT NULL, type INTEGER NOT NULL,
            authorName TEXT, text TEXT, comment TEXT, color TEXT, pageLabel TEXT, sortIndex TEXT NOT NULL,
            position TEXT NOT NULL, isExternal INT NOT NULL);
        CREATE TABLE tags(tagID INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE itemTags(itemID INT, tagID INT, type INT);
        CREATE TABLE itemNotes(itemID INTEGER PRIMARY KEY, parentItemID INT, note TEXT, title TEXT);
        INSERT INTO itemTypes VALUES (1,'journalArticle'),(2,'attachment'),(3,'annotation'),(4,'note');
        INSERT INTO items VALUES (10,1,'PAPERAAA'),(11,2,'ATTAAAAA'),(20,1,'PAPERBBB'),(21,2,'ATTBBBBB'),
            (100,3,'ANN00001'),(101,3,'ANN00002'),(102,3,'ANN00003'),(103,3,'ANN00004'),
            (104,3,'ANN00005'),(105,3,'ANN00006'),(106,3,'ANN00007'),(200,4,'NOTE0001'),(201,4,'NOTE0002');
        INSERT INTO itemAttachments VALUES (11,10,'storage:a.pdf','application/pdf'),(21,20,'storage:b.pdf','application/pdf');
        INSERT INTO itemAnnotations VALUES
            (100,11,1,NULL,'owner highlight','why this matters','#ffd400','3','00002|000100|00050','{}',0),
            (101,11,5,'Reviewer X','named underline',NULL,'#2ea8e5','4','00003|000100|00050','{}',0),
            (102,11,1,'PaperAI','tool highlight',NULL,'#ff6666','5','00004|000100|00050','{}',0),
            (103,11,1,'Someone','embedded highlight',NULL,'#ffd400','6','00005|000100|00050','{}',1),
            (104,11,9,NULL,'unknown type',NULL,NULL,'7','00006|000100|00050','{}',0),
            (105,11,1,NULL,'trashed highlight',NULL,NULL,'8','00007|000100|00050','{}',0),
            (106,21,1,NULL,'another paper',NULL,NULL,'1','00001|000100|00050','{}',0);
        INSERT INTO deletedItems VALUES (105),(201);
        INSERT INTO tags VALUES (1,'ai-suggested');
        INSERT INTO itemTags VALUES (102,1,0);
        INSERT INTO itemNotes VALUES (200,10,'<p>My <b>note</b> &amp; plan</p>','My note'),
                                     (201,10,'<p>trashed</p>','trashed');
    """)
    return con


def selftest() -> int:
    """Calibrate what does not need the real library: citation shaping and mark provenance."""
    cases = [   # (label, got, want)
        ("must-PASS: two authors render as 'et al.'",
         cite_of({"creators": ["Guo", "Li"], "date": "2020-05-01"}), "Guo et al. 2020"),
        ("must-PASS: single author, no et al.",
         cite_of({"creators": ["Zhao"], "date": "2021"}), "Zhao 2021"),
        ("must-PASS: missing date degrades to n.d., never invents one",
         cite_of({"creators": ["Wann"], "date": ""}), "Wann n.d."),
        ("must-PASS: no creators degrades to ?, never invents one",
         cite_of({"creators": [], "date": "1996"}), "? 1996"),
        ("must-FAIL: a year is never taken from the title",
         cite_of({"creators": ["Zhao"], "date": "", "title": "Progress in 2020-2021"}), "Zhao 2021"),
    ]
    con = _marks_fixture()
    res = load_marks(con, "PAPERAAA", ["PaperAI"])
    got = {m["key"]: m for m in res["annotations"]}
    bare = {m["key"]: m for m in load_marks(con, "PAPERAAA", [])["annotations"]}
    via_att = load_marks(con, "attaaaaa", ["PaperAI"])
    cases += [
        ("must-PASS: an unnamed Zotero-native mark reads as owner", got["ANN00001"]["origin"], "owner"),
        ("must-PASS: a mark under an author name reads as named", got["ANN00002"]["origin"], "named"),
        ("must-PASS: a declared tool author reads as tool", got["ANN00003"]["origin"], "tool"),
        ("must-PASS: a mark embedded in the PDF reads as external, name or not", got["ANN00004"]["origin"], "external"),
        ("must-FAIL: an embedded mark is never the owner's", got["ANN00004"]["origin"], "owner"),
        ("must-FAIL: an undeclared tool's signed mark is still never the owner's", bare["ANN00003"]["origin"], "owner"),
        ("must-PASS: only the tool list separates tool from named", bare["ANN00003"]["origin"], "named"),
        ("must-PASS: annotation type 5 is underline", got["ANN00002"]["kind"], "underline"),
        ("must-PASS: an unknown type integer is labelled, never guessed", got["ANN00005"]["kind"], "type-9"),
        ("must-PASS: trashed marks and another paper's marks are dropped",
         ",".join(sorted(got)), "ANN00001,ANN00002,ANN00003,ANN00004,ANN00005"),
        ("must-PASS: a tool's tag travels with its mark", ",".join(got["ANN00003"]["tags"]), "ai-suggested"),
        ("must-PASS: child-note HTML is reduced to text", res["notes"][0]["text"] if res["notes"] else "", "My note & plan"),
        ("must-FAIL: a trashed child note is never listed", str(len(res["notes"])), "2"),
        ("must-PASS: an attachment key (any case) yields the same marks",
         str(len(via_att["annotations"])) if via_att else "none", "5"),
        ("must-PASS: an attachment key still lists its paper's child notes",
         str(len(via_att["notes"])) if via_att else "none", "1"),
    ]
    bad = 0
    print(f"{'verdict':9} case")
    print("-" * 72)
    for label, got, want in cases:
        should_match = not label.startswith("must-FAIL")
        ok = (got == want) if should_match else (got != want)
        bad += 0 if ok else 1
        print(f"{'ok' if ok else 'BROKEN':9} {label}")
        if not ok:
            print(f"{'':9}   got {got!r}, wanted {'==' if should_match else '!='} {want!r}")
    print("-" * 72)
    n_pass = sum(1 for c in cases if not c[0].startswith("must-FAIL"))
    print(f"{len(cases)} cases ({n_pass} must-pass / {len(cases) - n_pass} must-fail), "
          f"{bad} broken — "
          f"{'shaping and provenance are calibrated' if not bad else 'NOT TRUSTWORTHY'}")
    print("NOTE: this calibrates citation SHAPING and mark PROVENANCE on a fixture. Reading "
          "the real database is exercised by --stats and --annotations against the library, "
          "which is the part that would break on a Zotero schema change.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
