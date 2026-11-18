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

ENGINES (`--engine`, recorded in the manifest's `engine.name`):
    winrt     DEFAULT. Windows built-in OCR (`Windows.Media.Ocr`), one PowerShell
              process per batch. Zero install; languages on this machine: en-US,
              ja, zh-Hans-CN, zh-Hant-TW (ops/environment.md §Local toolchain).
              Returns no confidence; the gate uses the text and `TextAngle`.
    rapidocr  PP-OCR ONNX models on CPU (`pip install rapidocr onnxruntime`).
              Reads contents pages (dot leaders) and two-column layouts far
              better than winrt; angle is estimated from the detected line boxes.
    vlm       A vision-language OCR model behind a llama.cpp `llama-server`
              that the caller started with the model AND its mmproj
              (`--vlm-url`, default http://127.0.0.1:8091; measured with the
              official PaddleOCR-VL-1.5 GGUF). Best on formulas and Chinese, but
              it reports no angle, emits LaTeX/markdown, and can loop on dot
              leaders — the repetition rule below catches the loop. Local only:
              no page image leaves the machine.
The per-class choice is measured, not assumed: ocr_bench.py scores every engine
by character error rate on fixed regions (ocr_bench_gt.json).

TEXT LAYER, PER PAGE. A book whose sampled pages all carry text is skipped as
before. A book with SOME pages lacking a text layer (a handbook with scanned
inserts) is OCRed on those pages only; the others are copied from the layer
with status `text-layer`, so the sidecar holds the whole book and says, per
page, where each text came from.

PAGE STATUS VOCABULARY (manifest `pages[].status`):
    ok       accepted, text file written
    sparse   fewer than SPARSE_TOKENS tokens — cover, blank, figure-only page;
             text file written (may be empty) but the page carries no claim
    skew     |TextAngle| still above SKEW_DEG after the deskew retry → EXCLUDED
    garbage  enough tokens but too few plausible words → EXCLUDED
    error    engine raised / no result → EXCLUDED
    text-layer  (mixed books only) copied from the PDF's own text layer, not OCRed
A page whose output repeats one short unit REPEAT_RUN times in a row (a VLM
stuck on a dot leader) is `garbage`, with `repeat_run` in its metrics.

Exclusion is a status, not a deletion: the page number stays in the manifest
so a reader knows the hole is there and why.

Usage:
    python textbook_ocr.py --pdf <file.pdf> [--lang auto|en-US|zh-Hans-CN|zh-Hant-TW] [--dpi 150]
                           [--engine winrt|rapidocr|vlm] [--vlm-url http://127.0.0.1:8091]
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
PAGE_TEXT_MIN_CHARS = 20    # per page: below this the page has no usable text layer (mixed books)
REPEAT_RUN = 80             # one 1-4 char unit repeated this many times in a row -> 'garbage' (VLM loop)
MIRROR_MIN = 5              # reversed common words ('eht','ot') >= this and > 2x forward -> 'garbage'
# ---------------------------------------------------------------------------

ENGINES = ("winrt", "rapidocr", "vlm")
VLM_URL = "http://127.0.0.1:8091"
VLM_PROMPT = "OCR:"  # PaddleOCR-VL task prompt (model card)
REPEAT = re.compile(r"(.{1,4}?)\1{%d,}" % (REPEAT_RUN - 1), re.S)

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
    # A CJK run counts one token PER CHARACTER: winrt spaces every character
    # ('固 体 物 理'), rapidocr and VLMs do not ('固体物理'), and a whitespace
    # count ruled a full VLM page of Chinese 'sparse' (measured 2026-11-16).
    good = total = 0
    for t in toks:
        k = len(CJK.findall(t))
        if k:
            good += k
            total += k
        else:
            total += 1
            good += bool(LATIN_WORD.match(t) or NUMBER.match(t))
    nonspace = re.sub(r"\s+", "", text)
    cjk_share = (len(CJK.findall(nonspace)) / len(nonspace)) if nonspace else 0.0
    return total, good / total, cjk_share


CJK_GAP = re.compile(r"(?<=[㐀-鿿豈-﫿　-〿＀-￯])[ \t]+(?=[㐀-鿿豈-﫿　-〿＀-￯])")


def normalize_cjk_spacing(text: str) -> str:
    """The Windows Chinese engines emit one 'word' per character ('固 体 物 理 学',
    measured 2026-09-13). Removing the spaces BETWEEN two CJK characters (or CJK
    punctuation) restores searchable text without touching any character; Latin
    tokens, digits and mixed runs keep their spacing. Recorded in the manifest as
    `normalization`, so a reader knows the text file is not the engine's raw output."""
    return CJK_GAP.sub("", text)


FWD_WORDS = {"the", "of", "and", "to", "in", "is", "at"}
REV_WORDS = {"eht", "fo", "dna", "ot", "ni", "si", "ta"}  # the same words read backwards


def mirror_counts(text: str) -> tuple[int, int]:
    """(forward, reversed) counts of seven common English words. A mirrored page
    read by an engine that still recognises the glyphs comes out as reversed
    words ('eht', 'ot', 'ta') that pass the word-SHAPE test (measured 2026-11-16:
    rapidocr on a mirrored Sze page scored quality 0.744 -> 'ok')."""
    toks = [t.strip(".,;:!?()[]{}\"'").lower() for t in text.split()]
    return sum(t in FWD_WORDS for t in toks), sum(t in REV_WORDS for t in toks)


def repeat_run(text: str) -> int:
    """Longest run of one 1-4 char unit repeated back to back, spaces ignored."""
    m = REPEAT.search(re.sub(r"\s+", "", text))
    if not m:
        return 0
    unit, span = m.group(1), m.group(0)
    return len(span) // len(unit)


def classify(text: str, angle: float | None, err: str | None) -> tuple[str, dict]:
    tokens, q, cjk = quality(text)
    metrics = {"chars": len(text), "tokens": tokens, "quality": round(q, 3), "cjk_share": round(cjk, 3),
               "angle": None if angle is None else round(angle, 2)}
    if err:
        return "error", metrics
    rr = repeat_run(text)
    if rr:
        metrics["repeat_run"] = rr
        return "garbage", metrics
    if angle is not None and abs(angle) > SKEW_DEG:
        return "skew", metrics
    if tokens < SPARSE_TOKENS:
        return "sparse", metrics
    if q < QUALITY_MIN:
        return "garbage", metrics
    fwd, rev = mirror_counts(text)
    if cjk < 0.2 and rev >= MIRROR_MIN and rev > 2 * fwd:
        metrics["mirror_words"] = [fwd, rev]
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


def rapid_lines(boxes, txts) -> str:
    """Group RapidOCR boxes into lines by vertical overlap, then left to right."""
    if boxes is None or txts is None:
        return ""
    items = []
    for b, t in zip(boxes, txts):
        ys = [p[1] for p in b]
        xs = [p[0] for p in b]
        items.append((min(ys), max(ys), min(xs), t))
    items.sort(key=lambda x: (x[0], x[2]))
    lines: list[list] = []
    for it in items:
        if lines:
            y0, y1 = lines[-1][0], lines[-1][1]
            h = min(y1 - y0, it[1] - it[0]) or 1
            if min(y1, it[1]) - max(y0, it[0]) > 0.5 * h:
                lines[-1][2].append(it)
                lines[-1][0], lines[-1][1] = min(y0, it[0]), max(y1, it[1])
                continue
        lines.append([it[0], it[1], [it]])
    return "\n".join(" ".join(t for *_, t in sorted(ln[2], key=lambda x: x[2])) for ln in lines)


def rapid_angle(boxes) -> float | None:
    """Median slope (degrees) of the top edge of wide line boxes; None if no line
    box is wide enough to measure. Sign follows image y-down: positive = the line
    falls to the right."""
    import math
    if boxes is None:
        return None
    angs = []
    for b in boxes:
        (x0, y0), (x1, y1) = b[0], b[1]
        h = abs(b[3][1] - b[0][1]) or 1
        if abs(x1 - x0) > 4 * h:
            angs.append(math.degrees(math.atan2(y1 - y0, x1 - x0)))
    if not angs:
        return None
    angs.sort()
    return angs[len(angs) // 2]


_RAPID = None


def _rapid_version() -> str | None:
    try:
        from importlib.metadata import version
        return "rapidocr " + version("rapidocr")
    except Exception:  # noqa: BLE001
        return None


def run_rapidocr(pairs: list[tuple[int, Path]]) -> dict[int, dict]:
    global _RAPID
    if _RAPID is None:
        from rapidocr import RapidOCR
        _RAPID = RapidOCR()
    rows = {}
    for p, png in pairs:
        try:
            res = _RAPID(str(png))
            rows[p] = {"page": p, "text": rapid_lines(res.boxes, res.txts), "angle": rapid_angle(res.boxes),
                       "err": None}
        except Exception as e:  # noqa: BLE001 — recorded as status 'error'
            rows[p] = {"page": p, "text": "", "angle": None, "err": f"{type(e).__name__}: {e}"[:300]}
    return rows


def run_vlm(pairs: list[tuple[int, Path]], url: str) -> dict[int, dict]:
    import base64
    import urllib.request
    rows = {}
    for p, png in pairs:
        body = json.dumps({
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," +
                                                    base64.b64encode(png.read_bytes()).decode()}},
                {"type": "text", "text": VLM_PROMPT}]}],
            "temperature": 0, "max_tokens": 4096, "stream": False}).encode()
        try:
            req = urllib.request.Request(f"{url}/v1/chat/completions", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as r:
                text = json.loads(r.read())["choices"][0]["message"]["content"]
            rows[p] = {"page": p, "text": text, "angle": None, "err": None}
        except Exception as e:  # noqa: BLE001
            rows[p] = {"page": p, "text": "", "angle": None, "err": f"{type(e).__name__}: {e}"[:300]}
    return rows


def vlm_model(url: str) -> str | None:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{url}/v1/models", timeout=10) as r:
            return json.loads(r.read())["data"][0]["id"]
    except Exception:  # noqa: BLE001
        return None


def run_pages(engine: str, pairs: list[tuple[int, Path]], lang: str, work: Path,
              vlm_url: str = VLM_URL) -> dict[int, dict]:
    if engine == "winrt":
        return run_engine(pairs, lang, work)
    if engine == "rapidocr":
        return run_rapidocr(pairs)
    if engine == "vlm":
        return run_vlm(pairs, vlm_url)
    raise ValueError(f"unknown engine {engine}")


def pages_without_text(doc: fitz.Document) -> list[int]:
    """1-based pages whose text layer is below PAGE_TEXT_MIN_CHARS."""
    return [i + 1 for i in range(doc.page_count) if len(doc[i].get_text().strip()) < PAGE_TEXT_MIN_CHARS]


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
ENGINE_NAMES = {"winrt": "Windows.Media.Ocr", "rapidocr": "RapidOCR (PP-OCR ONNX)",
                "vlm": "llama.cpp llama-server VLM"}


def ocr_book(pdf: Path, lang: str, dpi: int, batch: int = 200, force: bool = False,
             engine: str = "winrt", vlm_url: str = VLM_URL) -> Path:
    doc = fitz.open(pdf)
    n = doc.page_count
    layer_pages: set[int] = set()  # pages copied from the PDF's own text layer
    if has_text_layer(doc) and not force:
        missing = pages_without_text(doc)
        if not missing:
            print(f"SKIP (has text layer): {pdf.name}")
            return pdf
        layer_pages = set(range(1, n + 1)) - set(missing)
        print(f"MIXED: {len(missing)}/{n} pages lack a text layer -> OCR those only: {pdf.name}")
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
    if engine == "vlm" and vlm_model(vlm_url) is None:
        raise RuntimeError(f"--engine vlm: no llama-server answering at {vlm_url}")
    pages: list[dict] = []
    for p in sorted(layer_pages):
        text = doc[p - 1].get_text()
        status, metrics = classify(text, None, None)
        pages.append({"page": p, "status": "text-layer", **metrics, "deskewed": False,
                      "angle_before": None, "error": None})
        (textdir / f"{p:04d}.txt").write_text(text, encoding="utf-8")
    todo = [i for i in range(n) if i + 1 not in layer_pages]
    for start in range(0, len(todo), batch):
        idx = todo[start:start + batch]
        pairs = []
        for i in idx:
            png = work / f"p{i+1:04d}.png"
            render_page(doc, i, dpi, png)
            pairs.append((i + 1, png))
        rows = run_pages(engine, pairs, lang, work, vlm_url)
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
                rows2 = run_pages(engine, pairs2, lang, work, vlm_url)
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
        done = min(len(todo), start + batch)
        print(f"  {pdf.name[:50]}: {done}/{len(todo)} OCR pages, {time.time()-t0:.0f}s", flush=True)
    pages.sort(key=lambda r: r["page"])
    counts = {}
    for row in pages:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    manifest = {
        "schema": SCHEMA,
        "source": {"path": str(pdf), "sha256": src_sha, "size_bytes": pdf.stat().st_size, "pages": n},
        "engine": {"name": ENGINE_NAMES[engine], "id": engine, "language": lang, "language_scores": lang_scores,
                   "dpi": dpi, "os": sys.getwindowsversion().build if hasattr(sys, "getwindowsversion") else None,
                   "model": vlm_model(vlm_url) if engine == "vlm" else (_rapid_version() if engine == "rapidocr" else None)},
        "text_source": ("mixed: text-layer pages copied, the rest OCRed" if layer_pages else "ocr"),
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
    # rapidocr engine: same three images, same gate
    try:
        import rapidocr  # noqa: F401
        have_rapid = True
    except ImportError:
        have_rapid = False
        print("  rapidocr not installed: its controls are SKIPPED (not passed)")
    if have_rapid:
        rr = run_rapidocr([(1, a), (2, b), (3, c)])
        rv = {name: classify(rr[p].get("text", ""), rr[p].get("angle"), rr[p].get("err"))
              for p, name in ((1, "clean"), (2, "rotated12"), (3, "mirrored"))}
        for name, (st, met) in rv.items():
            print(f"  rapidocr {name:10s} -> {st:8s} {met}")
        if rv["clean"][0] != "ok":
            print("FAIL rapidocr positive control: clean page not 'ok'"); ok = False
        if rv["rotated12"][0] != "skew":
            print("FAIL rapidocr negative control: 12-degree rotation not 'skew'"); ok = False
        if rv["mirrored"][0] != "garbage":
            print("FAIL rapidocr negative control: mirrored page not 'garbage'"); ok = False
    # repetition rule: a VLM stuck on a dot leader vs a real contents page
    loop = "PREFACE: ON PROCESS " + ". " * 300
    toc = "\n".join(f"{k}. CHAPTER TITLE NUMBER {k} " + ". " * 40 + str(10 * k) for k in range(1, 12))
    st_loop, met_loop = classify(loop + " words " * 40, None, None)
    st_toc, _ = classify(toc, None, None)
    print(f"  repetition: loop -> {st_loop} (repeat_run={met_loop.get('repeat_run')}), real contents page -> {st_toc}")
    if st_loop != "garbage":
        print("FAIL negative control: dot-leader loop not 'garbage'"); ok = False
    if st_toc == "garbage":
        print("FAIL positive control: a real contents page (40-dot leaders) ruled 'garbage'"); ok = False
    # CJK token count must not depend on whether the engine spaces characters
    zh = "選擇緊挨著你已經繪畫過顏色旁邊的下一個色塊進行繪製那樣你就可以對比你實際看到的顏色關係"
    st_tight, met_tight = classify(zh, None, None)
    st_spaced, met_spaced = classify(" ".join(zh), None, None)
    print(f"  cjk tokens: unspaced -> {st_tight} ({met_tight['tokens']}), spaced -> {st_spaced} ({met_spaced['tokens']})")
    if st_tight != "ok" or met_tight["tokens"] != met_spaced["tokens"]:
        print("FAIL control: unspaced Chinese counted differently from spaced Chinese"); ok = False
    # per-page text layer: 2 text pages + 1 blank page -> only page 3 lacks text
    mix = fitz.open()
    for k in range(3):
        pg = mix.new_page()
        if k < 2:
            pg.insert_text((72, 72), "This page carries a real text layer of some length. " * 2)
    miss = pages_without_text(mix)
    print(f"  per-page text layer: pages without text = {miss} (want [3])")
    if miss != [3]:
        print("FAIL per-page text-layer control"); ok = False
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
    ap.add_argument("--engine", default="winrt", choices=ENGINES)
    ap.add_argument("--vlm-url", default=VLM_URL, help="llama-server base URL for --engine vlm")
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
        ocr_book(pdf, a.lang, a.dpi, a.batch, a.force, a.engine, a.vlm_url)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
