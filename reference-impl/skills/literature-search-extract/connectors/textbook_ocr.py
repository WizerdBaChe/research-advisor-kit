#!/usr/bin/env python3
r"""OCR sidecar for scanned textbooks in the local textbook library, with a
per-page quality gate that EXCLUDES pages rather than guessing at them.

WHY THIS EXISTS. 7 of the 32 books in <TEXTBOOKS> (measured 2026-09-13) carry
no text layer, so the literature skill could not open them at all — a scanned
book was "may not read, report honestly" (PDF-GUIDE). This tool gives each
such book a sidecar folder `<book>.ocr/` holding one text file per ACCEPTED
page plus a manifest that says, per page, whether the text was accepted and
why not otherwise. The original PDF is never modified.

THE RULE THE GATE ENFORCES (user ruling 2026-09-13): a page that is visibly
skewed or whose recognition failed is marked NOT INCLUDED and gets no text
file — "wrong data is worse than no data". The gate rules only on what it can
determine (token plausibility, detected text angle, sparsity); it never
rewrites text and never fills a gap.

ENGINE. Windows built-in OCR (`Windows.Media.Ocr`, WinRT), driven through one
PowerShell process per batch. Zero install; languages on this machine:
en-US, ja, zh-Hans-CN, zh-Hant-TW (probe recorded in ops/environment.md
§Local toolchain). It returns no confidence score, so the gate is built from
what it DOES return: the text itself and `TextAngle` (detected skew).

PAGE STATUS VOCABULARY (manifest `pages[].status`):
    ok       accepted, text file written
    sparse   fewer than SPARSE_TOKENS tokens — cover, blank, figure-only page;
             text file written (may be empty) but the page carries no claim
    skew     |TextAngle| still above SKEW_DEG after the deskew retry → EXCLUDED
    garbage  enough tokens but too few plausible words → EXCLUDED
    error    engine raised / no result → EXCLUDED

Exclusion is a status, not a deletion: the page number stays in the manifest
so a reader knows the hole is there and why.

Usage:
    python textbook_ocr.py --pdf <file.pdf> [--lang auto|en-US|zh-Hans-CN|zh-Hant-TW] [--dpi 150]
    python textbook_ocr.py --scan <root>        list PDFs without a text layer (dry)
    python textbook_ocr.py --report <root>      summarise every <book>.ocr manifest under root
    python textbook_ocr.py --selftest           two-sided gate calibration (see below)

SELFTEST — the controls must FIRE, not merely pass: a clean rasterised page
from a text-layer PDF must come out `ok`; the same page rotated 12° must be
DETECTED as skewed (angle > SKEW_DEG before the retry); the same page mirrored
must come out `garbage`. A gate that returns `ok` for all three is broken.

Exit: 0 ok, 1 nothing done / a control did not fire, 2 bad usage.
review-when: Windows.Media.Ocr changes its language list (re-run the probe in
ops/environment.md); the library root moves; a book is renamed (the manifest
carries the source sha256 so the sidecar can be re-linked, but the folder name
is the PDF stem and will not follow the rename by itself).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
import sys as _hksys  # machine roots at run time (platform/codemod_roots.py, build plan H-1)
from pathlib import Path as _HKPath
_hksys.path.insert(0, str(_HKPath(__file__).resolve().parents[3] / "hooks" / "_lib"))
import roots as hkroots  # noqa: E402

try:
    import fitz  # pymupdf
except ImportError:  # pragma: no cover
    print("pymupdf (fitz) is required", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
SCHEMA = "textbook-ocr/manifest@1"
DEFAULT_ROOT = hkroots.path("TEXTBOOKS")

# --- gate thresholds: the single edit point ------------------------------
SPARSE_TOKENS = 30      # below this a page is 'sparse', never 'garbage'
SKEW_DEG = 1.5          # |TextAngle| above this after retry -> 'skew'
DESKEW_TRY_DEG = 1.0    # |TextAngle| above this triggers the deskew retry
QUALITY_MIN = 0.55      # plausible-word share below this (with >= SPARSE_TOKENS) -> 'garbage'
TEXT_LAYER_MIN_CHARS = 200  # per sampled page; below on all samples -> "no text layer"
# ---------------------------------------------------------------------------

LANGS = ("en-US", "zh-Hans-CN", "zh-Hant-TW")
LATIN_WORD = re.compile(r"^(?:[A-Za-z][a-z]{1,}|[A-Z]{2,}|[A-Za-z]\.?)$")
CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
NUMBER = re.compile(r"^[\d.,%°()\-–—+=×/]+$")

PS_SCRIPT = r'''
param([string]$ListFile, [string]$OutFile, [string]$Lang)
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $t) { $m = $asTaskGeneric.MakeGenericMethod($t); $task = $m.Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
# Pick the engine from the INSTALLED list rather than constructing a Language:
# (a) it proves the language is really installed; (b) a variable named $lang
# collides case-insensitively with the $Lang parameter and produced a string
# where an object was expected (measured 2026-09-13).
$langObj = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Where-Object { $_.LanguageTag -eq $Lang } | Select-Object -First 1
if ($null -eq $langObj) { [Console]::Error.WriteLine("language not installed: $Lang"); exit 3 }
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($langObj)
if ($null -eq $engine) { [Console]::Error.WriteLine("engine null for $Lang"); exit 3 }
$enc = New-Object System.Text.UTF8Encoding($false)
$sb = New-Object System.Text.StringBuilder
foreach ($line in [IO.File]::ReadAllLines($ListFile, [Text.Encoding]::UTF8)) {
  if ($line.Trim().Length -eq 0) { continue }
  $parts = $line -split "`t"
  $page = [int]$parts[0]; $path = $parts[1]
  try {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bmp = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
    $angle = $null
    if ($null -ne $res.TextAngle) { $angle = [double]$res.TextAngle }
    $txt = (($res.Lines | ForEach-Object { $_.Text }) -join "`n")
    $obj = @{ page = $page; angle = $angle; lines = $res.Lines.Count; text = $txt; err = $null }
    $bmp.Dispose(); $stream.Dispose()
  } catch {
    $obj = @{ page = $page; angle = $null; lines = 0; text = ""; err = $_.Exception.Message }
  }
  [void]$sb.AppendLine((ConvertTo-Json $obj -Compress -Depth 3))
}
[IO.File]::WriteAllText($OutFile, $sb.ToString(), $enc)
'''


# ---------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def has_text_layer(doc: fitz.Document, samples: int = 5) -> bool:
    n = doc.page_count
    idx = sorted({min(n - 1, int(n * f)) for f in (0.2, 0.35, 0.5, 0.65, 0.8)})[:samples]
    return any(len(doc[i].get_text()) >= TEXT_LAYER_MIN_CHARS for i in idx)


def quality(text: str) -> tuple[int, float, float]:
    """Return (tokens, plausible share, cjk share of non-space chars).

    Plausible = a Latin word shape, a number, or a CJK run. Punctuation-only
    tokens are ignored. This is a plausibility ruler, not a dictionary — it
    catches mirrored/garbled output, not a wrong word."""
    toks = [t for t in re.split(r"\s+", text) if t]
    toks = [t.strip(".,;:!?()[]{}\"'«»“”‘’") for t in toks]
    toks = [t for t in toks if t]
    if not toks:
        return 0, 0.0, 0.0
    good = 0
    for t in toks:
        if CJK.search(t):
            good += 1
        elif LATIN_WORD.match(t) or NUMBER.match(t):
            good += 1
    nonspace = re.sub(r"\s+", "", text)
    cjk_share = (len(CJK.findall(nonspace)) / len(nonspace)) if nonspace else 0.0
    return len(toks), good / len(toks), cjk_share


CJK_GAP = re.compile(r"(?<=[㐀-鿿豈-﫿　-〿＀-￯])[ \t]+(?=[㐀-鿿豈-﫿　-〿＀-￯])")


def normalize_cjk_spacing(text: str) -> str:
    """The Windows Chinese engines emit one 'word' per character ('固 体 物 理 学',
    measured 2026-09-13). Removing the spaces BETWEEN two CJK characters (or CJK
    punctuation) restores searchable text without touching any character; Latin
    tokens, digits and mixed runs keep their spacing. Recorded in the manifest as
    `normalization`, so a reader knows the text file is not the engine's raw output."""
    return CJK_GAP.sub("", text)


def classify(text: str, angle: float | None, err: str | None) -> tuple[str, dict]:
    tokens, q, cjk = quality(text)
    metrics = {"chars": len(text), "tokens": tokens, "quality": round(q, 3), "cjk_share": round(cjk, 3),
               "angle": None if angle is None else round(angle, 2)}
    if err:
        return "error", metrics
    if angle is not None and abs(angle) > SKEW_DEG:
        return "skew", metrics
    if tokens < SPARSE_TOKENS:
        return "sparse", metrics
    if q < QUALITY_MIN:
        return "garbage", metrics
    return "ok", metrics


def render_page(doc: fitz.Document, i: int, dpi: int, out: Path, rotate_deg: float = 0.0,
                mirror: bool = False) -> None:
    pix = doc[i].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    if rotate_deg == 0.0 and not mirror:
        pix.save(str(out))
        return
    from PIL import Image, ImageOps
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    if mirror:
        img = ImageOps.mirror(img)
    if rotate_deg:
        img = img.rotate(rotate_deg, expand=True, fillcolor=255)
    img.save(str(out))


def run_engine(pairs: list[tuple[int, Path]], lang: str, work: Path) -> dict[int, dict]:
    """OCR a list of (page, png) in ONE PowerShell process; returns page -> row."""
    if not pairs:
        return {}
    script = work / "ocr.ps1"
    script.write_text(PS_SCRIPT, encoding="utf-8")
    lst = work / f"list_{int(time.time()*1000)}.txt"
    outp = work / f"out_{int(time.time()*1000)}.jsonl"
    lst.write_text("".join(f"{p}\t{png}\n" for p, png in pairs), encoding="utf-8")
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
           "-ListFile", str(lst), "-OutFile", str(outp), "-Lang", lang]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not outp.exists():
        raise RuntimeError(f"OCR engine failed rc={r.returncode}: {r.stderr[-500:]}")
    rows: dict[int, dict] = {}
    for line in outp.read_text(encoding="utf-8").splitlines():
        if line.strip():
            o = json.loads(line)
            rows[int(o["page"])] = o
    return rows


def pick_language(doc: fitz.Document, dpi: int, work: Path) -> tuple[str, dict]:
    """Try every installed language on six mid-book pages; keep the best
    plausible-word share. Two-sided by construction: a Chinese book scores
    low under en-US and vice versa, so the pick is measured, not guessed."""
    n = doc.page_count
    idx = sorted({min(n - 1, int(n * f)) for f in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)})
    pairs = []
    for i in idx:
        png = work / f"lang_{i:04d}.png"
        render_page(doc, i, dpi, png)
        pairs.append((i + 1, png))
    scores = {}
    for lang in LANGS:
        rows = run_engine(pairs, lang, work)
        qs = [quality(r.get("text", ""))[1] for r in rows.values() if r.get("text")]
        toks = sum(quality(r.get("text", ""))[0] for r in rows.values())
        scores[lang] = {"mean_quality": round(sum(qs) / len(qs), 3) if qs else 0.0, "tokens": toks}
    best = max(scores, key=lambda k: (scores[k]["mean_quality"], scores[k]["tokens"]))
    return best, scores


# ---------------------------------------------------------------- main ops
def ocr_book(pdf: Path, lang: str, dpi: int, batch: int = 200, force: bool = False) -> Path:
    doc = fitz.open(pdf)
    if has_text_layer(doc) and not force:
        print(f"SKIP (has text layer): {pdf.name}")
        return pdf
    side = pdf.with_name(pdf.stem + ".ocr")
    textdir = side / "text"
    side.mkdir(exist_ok=True)
    textdir.mkdir(exist_ok=True)
    manifest_path = side / "manifest.json"
    if manifest_path.exists() and not force:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        if m.get("complete"):
            print(f"SKIP (manifest complete): {pdf.name}")
            return side
    t0 = time.time()
    src_sha = sha256_file(pdf)
    work = Path(tempfile.mkdtemp(prefix="tbocr_"))
    lang_scores = None
    if lang == "auto":
        lang, lang_scores = pick_language(doc, dpi, work)
        print(f"lang auto -> {lang} {lang_scores}")
    n = doc.page_count
    pages: list[dict] = []
    for start in range(0, n, batch):
        idx = list(range(start, min(n, start + batch)))
        pairs = []
        for i in idx:
            png = work / f"p{i+1:04d}.png"
            render_page(doc, i, dpi, png)
            pairs.append((i + 1, png))
        rows = run_engine(pairs, lang, work)
        # deskew retry for pages the engine saw as tilted
        retry = [(p, rows[p]["angle"]) for p in rows
                 if rows[p].get("angle") is not None and abs(rows[p]["angle"]) > DESKEW_TRY_DEG]
        retried: dict[int, dict] = {}
        if retry:
            # A retry is accepted ONLY if the residual |angle| got smaller — measured
            # 2026-09-13 on Neamen p.23: rotating the wrong way took -1.5 to -3.0 with
            # equal text quality, and a quality-only rule kept the worse page.
            # PIL rotates counter-clockwise for positive degrees; TextAngle's sign
            # convention is not documented, so both directions are tried, +ang first.
            for sign in (1.0, -1.0):
                pairs2 = []
                for p, ang in retry:
                    if p in retried and retried[p]["angle"] is not None and abs(retried[p]["angle"]) <= DESKEW_TRY_DEG:
                        continue
                    png = work / f"r{p:04d}_{'m' if sign < 0 else 'p'}.png"
                    render_page(doc, p - 1, dpi, png, rotate_deg=sign * ang)
                    pairs2.append((p, png))
                if not pairs2:
                    break
                rows2 = run_engine(pairs2, lang, work)
                for p, r2 in rows2.items():
                    old = retried.get(p) or rows[p]
                    old_ang = abs(old.get("angle") or 0.0)
                    new_ang = abs(r2.get("angle") or 0.0) if r2.get("angle") is not None else 0.0
                    if r2.get("err") or not r2.get("text"):
                        continue
                    if new_ang < old_ang and quality(r2.get("text", ""))[1] >= quality(old.get("text", ""))[1] - 0.05:
                        r2["deskewed"] = True
                        r2["angle_before"] = rows[p]["angle"]
                        retried[p] = r2
        for p in sorted(rows):
            r = retried.get(p, rows[p])
            status, metrics = classify(r.get("text", ""), r.get("angle"), r.get("err"))
            row = {"page": p, "status": status, **metrics,
                   "deskewed": bool(r.get("deskewed", False)),
                   "angle_before": r.get("angle_before"), "error": r.get("err")}
            pages.append(row)
            tf = textdir / f"{p:04d}.txt"
            if status in ("ok", "sparse"):
                out_text = r.get("text", "")
                if lang.startswith("zh") or lang == "ja":
                    out_text = normalize_cjk_spacing(out_text)
                tf.write_text(out_text, encoding="utf-8")
            elif tf.exists():
                tf.unlink()
        for _, png in pairs:
            png.unlink(missing_ok=True)
        for f in work.glob("r*.png"):
            f.unlink(missing_ok=True)
        done = min(n, start + batch)
        print(f"  {pdf.name[:50]}: {done}/{n} pages, {time.time()-t0:.0f}s", flush=True)
    counts = {}
    for row in pages:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    manifest = {
        "schema": SCHEMA,
        "source": {"path": str(pdf), "sha256": src_sha, "size_bytes": pdf.stat().st_size, "pages": n},
        "engine": {"name": "Windows.Media.Ocr", "language": lang, "language_scores": lang_scores,
                   "dpi": dpi, "os": sys.getwindowsversion().build if hasattr(sys, "getwindowsversion") else None},
        "normalization": ("cjk-space-collapse (spaces between adjacent CJK characters removed; no character changed)"
                          if (lang.startswith("zh") or lang == "ja") else None),
        "gate": {"SPARSE_TOKENS": SPARSE_TOKENS, "SKEW_DEG": SKEW_DEG, "DESKEW_TRY_DEG": DESKEW_TRY_DEG,
                 "QUALITY_MIN": QUALITY_MIN,
                 "rule": "skew/garbage/error pages are EXCLUDED: no text file, listed here by page (user ruling 2026-09-13)"},
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - t0, 1),
        "summary": counts,
        "excluded_pages": [r["page"] for r in pages if r["status"] in ("skew", "garbage", "error")],
        "complete": True,
        "pages": pages,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"DONE {pdf.name[:60]}: {counts} in {time.time()-t0:.0f}s -> {side}")
    for f in work.glob("*"):
        f.unlink(missing_ok=True)
    work.rmdir()
    return side


def scan(root: Path) -> list[Path]:
    out = []
    for pdf in sorted(root.rglob("*.pdf")):
        try:
            d = fitz.open(pdf)
        except Exception as e:  # noqa: BLE001
            print(f"ERR {pdf}: {e}")
            continue
        if not has_text_layer(d):
            out.append(pdf)
            print(f"NO TEXT LAYER  {d.page_count:5d}p  {pdf.relative_to(root)}")
    if not out:
        print("every PDF under root has a text layer")
    return out


def report(root: Path) -> int:
    found = 0
    for m in sorted(root.rglob("*.ocr/manifest.json")):
        found += 1
        d = json.loads(m.read_text(encoding="utf-8"))
        s = d["summary"]
        n = d["source"]["pages"]
        exc = len(d["excluded_pages"])
        print(f"{n:5d}p  ok={s.get('ok',0):5d} sparse={s.get('sparse',0):4d} "
              f"EXCLUDED={exc:4d} (skew={s.get('skew',0)} garbage={s.get('garbage',0)} error={s.get('error',0)})  "
              f"lang={d['engine']['language']}  {m.parent.name[:70]}")
    if not found:
        print("no .ocr manifests under root")
        return 1
    return 0


def selftest() -> int:
    """Two-sided calibration on a rasterised page from a text-layer PDF."""
    cand = None
    for pdf in sorted(DEFAULT_ROOT.rglob("*.pdf")) if DEFAULT_ROOT else []:  # TEXTBOOKS unset: no PDF here
        d = fitz.open(pdf)
        if d.page_count > 60 and has_text_layer(d):
            cand = (pdf, d)
            break
    if cand is None:
        print("selftest: no text-layer PDF found under", DEFAULT_ROOT)
        return 1
    pdf, d = cand
    i = 50
    work = Path(tempfile.mkdtemp(prefix="tbocr_self_"))
    a, b, c = work / "clean.png", work / "rot12.png", work / "mirror.png"
    render_page(d, i, 150, a)
    render_page(d, i, 150, b, rotate_deg=12.0)
    render_page(d, i, 150, c, mirror=True)
    rows = run_engine([(1, a), (2, b), (3, c)], "en-US", work)
    verdicts = {}
    for p, name in ((1, "clean"), (2, "rotated12"), (3, "mirrored")):
        r = rows[p]
        status, met = classify(r.get("text", ""), r.get("angle"), r.get("err"))
        verdicts[name] = (status, met)
        print(f"  {name:10s} -> {status:8s} {met}")
    ok = True
    if verdicts["clean"][0] != "ok":
        print("FAIL positive control: clean page not 'ok'"); ok = False
    ang = verdicts["rotated12"][1]["angle"]
    if ang is None or abs(ang) <= SKEW_DEG:
        print("FAIL negative control: 12-degree rotation NOT detected as skew"); ok = False
    if verdicts["mirrored"][0] != "garbage":
        print("FAIL negative control: mirrored page not 'garbage'"); ok = False
    print(f"selftest source: {pdf.name} page {i+1}; {'PASS' if ok else 'FAIL'}")
    for f in work.glob("*"):
        f.unlink(missing_ok=True)
    work.rmdir()
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pdf", action="append", help="PDF to OCR (repeatable)")
    ap.add_argument("--lang", default="auto", choices=("auto",) + LANGS)
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--force", action="store_true", help="redo even if manifest complete / text layer present")
    ap.add_argument("--scan", metavar="ROOT", help="list PDFs without a text layer")
    ap.add_argument("--all", metavar="ROOT", help="OCR every PDF under ROOT that has no text layer")
    ap.add_argument("--report", metavar="ROOT")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.scan:
        return 0 if scan(Path(a.scan)) else 1
    if a.report:
        return report(Path(a.report))
    targets = [Path(p) for p in (a.pdf or [])]
    if a.all:
        targets += scan(Path(a.all))
    if not targets:
        ap.print_usage()
        return 2
    for pdf in targets:
        ocr_book(pdf, a.lang, a.dpi, a.batch, a.force)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
