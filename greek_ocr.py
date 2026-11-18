#!/usr/bin/env python3
"""
greek_ocr.py — Re-OCR PDFs so that polytonic Ancient Greek can be copied and searched.
古典ギリシャ語（多調式）を含むPDFを再OCRし、ギリシャ語を正しくコピー・検索できるようにする。

Copyright (c) 2026 Masahiro Kitano
Released under the MIT License (see LICENSE).
Developed with the help of Claude (Anthropic).

Usage / 使い方:
  python3 greek_ocr.py FOLDER [--dry-run] [--force] [--fast] [--out DIR] [--jobs N]

  Run it with the Python that comes with OCRmyPDF (Homebrew):
  OCRmyPDF に付属の Python で実行する:
    "$(brew --prefix ocrmypdf)/libexec/bin/python3" greek_ocr.py FOLDER

  --dry-run   only show how each PDF would be handled / 判定を表示するだけ（何も書き換えない）
  --force     re-render and re-OCR every page / 種類に関係なく焼き直してOCRする
  --fast      use the standard (fast) data even if the "best" data is installed
              best版データがあっても通常版（速い）を使う

  Output goes to FOLDER_OCR (English) or FOLDER_OCR済み (Japanese), next to FOLDER,
  with the same subfolder structure. Originals are never modified.
  Files already in the output folder are skipped, so an interrupted run can be resumed.
  保存先は対象フォルダの隣の「フォルダ名_OCR済み」。元のファイルは書き換えない。
  処理済みのファイルは次回飛ばすので、途中で止めても続きから再開できる。
"""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import warnings
import zlib
from pathlib import Path

__version__ = "1.1.0"

warnings.filterwarnings("ignore", category=DeprecationWarning)


# ---------------------------------------------------------------- messages / 表示言語

def _ui_is_japanese():
    forced = os.environ.get("GREEK_OCR_LANG", "").lower()
    if forced in ("ja", "en"):
        return forced == "ja"
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "")
        if val:
            return val.lower().startswith("ja")
    return False


JA = _ui_is_japanese()


def T(ja, en):
    """Return the message in the user's language. 表示言語に合わせて文を選ぶ"""
    return ja if JA else en


try:
    import pikepdf
    from pikepdf import Name, Array, PdfImage
except ImportError:
    sys.exit(T(
        "pikepdf が見つかりません。OCRmyPDF に付属の Python で実行してください:\n"
        '  "$(brew --prefix ocrmypdf)/libexec/bin/python3" greek_ocr.py フォルダ',
        "pikepdf was not found. Run this script with the Python that comes with OCRmyPDF:\n"
        '  "$(brew --prefix ocrmypdf)/libexec/bin/python3" greek_ocr.py FOLDER'))


# Languages of the main text: English, German, French, Italian, Spanish, Latin.
# 本文の言語: 英・独・仏・伊・西・ラテン語
SAMPLE_LANGS = "eng+deu+fra+ita+spa+lat"
ALL_LANGS = SAMPLE_LANGS + "+grc"
BEST_DIR = Path.home() / "GreekOCR" / "tessdata_best"
NEEDED = ["grc", "eng", "deu", "fra", "ita", "osd"]   # needed to use the best data at all
OPTIONAL = ["spa", "lat"]                             # used from the best data when present

# Frequent words, chosen so that the languages share as few as possible.
# よく出る単語（言語どうしでなるべく重ならないものを選んである）
STOPWORDS = {
    "eng": set("the and of to is that which with this are was for not".split()),
    "deu": set("der die und das ist nicht mit den zu sich des ein eine auch".split()),
    "fra": set("le les et des est une dans du pas qui sur au".split()),
    "ita": set("il che di della sono gli nel anche delle questo".split()),
    "spa": set("el los las y por para con es lo como pero sus".split()),
    "lat": set("est ad cum quod ut sed quae enim autem sunt atque etiam".split()),
}

CATEGORY = {
    "redo": ("検索可能な画像 → redo", "searchable image → redo"),
    "clearscan": ("ClearScan → force", "ClearScan → force"),
    "scan": ("文字層なし → 通常OCR", "no text layer → OCR"),
    "digital": ("電子版(元から文字) → 処理せずコピー", "born-digital text → copied as is"),
    "forced": ("強制OCR（焼き直し）", "forced re-OCR"),
    "japanese": ("日本語中心 → 処理せずコピー", "mainly Japanese → copied as is"),
    "finereader": ("FineReaderでOCR済み・ギリシャ語あり → force",
                   "OCRed by FineReader, contains Greek → force"),
    "monotonic": ("ギリシャ語が現代ギリシャ語として認識済み → force",
                  "Greek read as monotonic (modern) Greek → force"),
}


def cat_name(cat):
    ja, en = CATEGORY[cat]
    return T(ja, en)


# ---------------------------------------------------------------- external tools / 外部プログラム

def find_tool(*names):
    """Find the first of `names` on PATH or in the usual Homebrew folders."""
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
        for n in names:
            p = Path(prefix) / n
            if p.exists():
                return str(p)
    return names[0]


GS = find_tool("gs", "gswin64c", "gswin32c")
TESSERACT = find_tool("tesseract")


def find_std_tessdata():
    """The folder of Tesseract's standard language data, as Tesseract itself reports it.
    通常版の言語データの場所を Tesseract 自身に尋ねる"""
    try:
        r = subprocess.run([TESSERACT, "--list-langs"], capture_output=True, text=True, timeout=60)
        m = re.search(r'"([^"]+)"', r.stdout + r.stderr)
        if m and Path(m.group(1)).is_dir():
            return Path(m.group(1))
    except Exception:
        pass
    for p in ("/opt/homebrew/share/tessdata", "/usr/local/share/tessdata",
              "/usr/share/tesseract-ocr/5/tessdata", "/usr/share/tessdata"):
        if Path(p).is_dir():
            return Path(p)
    return None


STD_TESSDATA = find_std_tessdata()


BEST_ON = False


def setup_tessdata(use_fast):
    """Use the "best" data if it is complete. Returns a description for display.
    best版データがそろっていればそれを使う。戻り値は表示用の説明"""
    global BEST_ON
    BEST_ON = False
    if use_fast:
        return T("通常版（--fast 指定）", "standard (--fast)")
    missing = [l for l in NEEDED if not (BEST_DIR / f"{l}.traineddata").exists()]
    if missing:
        return T(f"通常版（best版に不足: {', '.join(missing)}）",
                 f"standard (best data missing: {', '.join(missing)})")
    # Tesseract also reads its config files (configs, tessconfigs) from the data folder.
    # The best-data folder has none, so point to (or copy) the standard ones.
    # Tesseract は設定ファイルも言語データと同じ場所から読む。best版フォルダには無いので補う。
    if STD_TESSDATA:
        for sub in ("configs", "tessconfigs"):
            target = BEST_DIR / sub
            source = STD_TESSDATA / sub
            if not target.exists() and source.exists():
                try:
                    target.symlink_to(source)
                except OSError:
                    try:
                        shutil.copytree(source, target)
                    except OSError:
                        pass
    if not (BEST_DIR / "configs" / "hocr").exists():
        return T("通常版（best版フォルダに設定ファイル configs がありません）",
                 "standard (no 'configs' folder in the best-data folder)")
    BEST_ON = True
    lacking = [l for l in OPTIONAL if not (BEST_DIR / f"{l}.traineddata").exists()]
    note = T(f"。{'・'.join(lacking)} は通常版", f"; {', '.join(lacking)} from the standard data") if lacking else ""
    return T(f"best版（{BEST_DIR}{note}）", f"best ({BEST_DIR}{note})")


def uses_best(lang):
    """True if every language of `lang` can be read from the best data."""
    return BEST_ON and all((BEST_DIR / f"{l}.traineddata").exists()
                           for l in lang.split("+") + ["osd"])


def tess_env(lang):
    """Environment for Tesseract: the best data if it has all the languages, else the standard data."""
    env = dict(os.environ)
    if uses_best(lang):
        env["TESSDATA_PREFIX"] = str(BEST_DIR)
    else:
        env.pop("TESSDATA_PREFIX", None)
    return env


# ---------------------------------------------------------------- classification / 分類

def page_images(page):
    """Images of a page, including those nested in form XObjects."""
    try:
        return list(page.get_images().values())
    except AttributeError:
        return list(page.images.values())


def count_text(obj, resources, tr, depth, counts):
    """Count visible and invisible text-showing operators, looking inside form XObjects.
    見える文字と透明な文字の命令を数える（フォームの中も調べる）"""
    if depth > 6:
        return
    try:
        ops = pikepdf.parse_content_stream(obj)
    except Exception:
        return
    stack = []
    for operands, op in ops:
        o = str(op)
        if o == "q":
            stack.append(tr)
        elif o == "Q":
            tr = stack.pop() if stack else 0
        elif o == "Tr" and operands:
            try:
                tr = int(operands[0])
            except Exception:
                pass
        elif o in ("Tj", "TJ", "'", '"'):
            counts["invisible" if tr == 3 else "visible"] += 1
        elif o == "Do" and operands and resources is not None:
            try:
                xobj = resources.XObject[operands[0]]
            except Exception:
                continue
            if xobj.get(Name.Subtype) == Name.Form:
                sub_res = xobj.get(Name.Resources, resources)
                count_text(xobj, sub_res, tr, depth + 1, counts)


def classify(pdf, sample_pages=24):
    """First classification of a PDF by its text layer and images."""
    n = len(pdf.pages)
    bits = set()
    pages_with_bilevel = 0
    has_images = False
    for page in pdf.pages:
        page_has_bilevel = False
        for img in page_images(page):
            has_images = True
            b = 1 if img.get(Name.ImageMask, False) else int(img.get(Name.BitsPerComponent, 8))
            bits.add(b)
            if b == 1:
                page_has_bilevel = True
        if page_has_bilevel:
            pages_with_bilevel += 1

    # Look at pages spread over the whole book, not only the front matter.
    # 本全体から等間隔にページを選んで調べる
    if n <= sample_pages:
        idx = list(range(n))
    else:
        idx = sorted({int(i * (n - 1) / (sample_pages - 1)) for i in range(sample_pages)})
    counts = {"visible": 0, "invisible": 0}
    for i in idx:
        page = pdf.pages[i]
        count_text(page.obj, page.obj.get(Name.Resources), 0, 0, counts)

    visible, invisible = counts["visible"], counts["invisible"]
    total = visible + invisible
    if total == 0:
        cat = "scan"
    elif visible > total * 0.2:
        # ClearScan leaves bilevel image fragments on most pages; born-digital PDFs do not.
        cat = "clearscan" if pages_with_bilevel >= n * 0.5 else "digital"
    else:
        cat = "redo"
    producer = str(pdf.docinfo.get("/Producer", "")) if pdf.docinfo else ""
    creator = str(pdf.docinfo.get("/Creator", "")) if pdf.docinfo else ""
    return {
        "cat": cat,
        "all_bilevel": has_images and bits <= {1},
        "has_images": has_images,
        "visible": visible,
        "invisible": invisible,
        "producer": producer,
        "creator": creator,
    }


# ---------------------------------------------------------------- text and language / 文字と言語

def judge_lang(text, min_hits=20):
    """Guess the main language(s) from common words. None if unsure."""
    words = re.findall(r"[a-zà-öø-ÿß]+", text.lower())
    counts = {lang: sum(1 for w in words if w in sw) for lang, sw in STOPWORDS.items()}
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    (l1, c1), (l2, c2) = ranked[0], ranked[1]
    if c1 < min_hits:
        return None
    if c2 >= c1 * 0.5:
        return f"{l1}+{l2}+grc"
    return f"{l1}+grc"


def extract_text(path, npages, span=20):
    """Text of up to `span` pages (from page 3), or of the whole PDF if span >= npages."""
    first = 1 if span >= npages else (3 if npages >= 6 else 1)
    last = min(npages, first + span - 1)
    cmd = [GS, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER",
           "-sDEVICE=txtwrite", f"-dFirstPage={first}", f"-dLastPage={last}",
           "-sOutputFile=-", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=1800)
        return r.stdout.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def greek_counts(path, npages, whole=False):
    """(Greek letters, of which with breathings etc.) in the text layer.
    Text read as modern Greek has almost no letters with breathings."""
    text = unicodedata.normalize("NFC", extract_text(path, npages, span=npages if whole else 20))
    total = sum(1 for ch in text if "Ͱ" <= ch <= "Ͽ" or "ἀ" <= ch <= "῿")
    poly = sum(1 for ch in text if "ἀ" <= ch <= "῿")
    return total, poly


def greek_desc(total, poly):
    return T(f"ギリシャ文字 {total}字（うち気息記号などの付いた文字 {poly}字）",
             f"{total} Greek letters ({poly} with breathings etc.)")


def refine_digital(info, path, npages):
    """Split PDFs with visible text by the software that made them. Returns (category, note)."""
    meta = (info["producer"] + " " + info["creator"]).lower()
    # Acrobat OCR ("Paper Capture") with visible text = ClearScan on gray or colour images.
    # Acrobat does not record Greek as Greek letters, so counting them would tell nothing.
    if "paper capture" in meta:
        return "clearscan", ""
    total, poly = greek_counts(path, npages, whole=True)
    desc = greek_desc(total, poly)
    if total >= 20 and ("finereader" in meta or "abbyy" in meta):
        return "finereader", desc
    if total >= 50 and poly <= total * 0.02:
        return "monotonic", desc
    return "digital", desc


def detect_lang(path, npages):
    """Language from the existing text layer. None if unsure."""
    return judge_lang(extract_text(path, npages))


def ocr_sample(path, npages, lang, fractions=(0.3, 0.5, 0.7), std_data=False):
    """OCR a few pages from the middle of the book and return the text."""
    if npages <= len(fractions):
        pages = list(range(1, npages + 1))
    else:
        pages = [max(1, int(npages * f)) for f in fractions]
    text = ""
    tmp = Path(tempfile.mkdtemp(prefix="greeklang_"))
    try:
        for p in pages:
            png = tmp / f"p{p}.png"
            subprocess.run([GS, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER",
                            "-sDEVICE=pnggray", "-r200",
                            f"-dFirstPage={p}", f"-dLastPage={p}",
                            f"-sOutputFile={png}", str(path)],
                           capture_output=True, timeout=120)
            if not png.exists():
                continue
            cmd = [TESSERACT, str(png), "stdout", "-l", lang]
            env = tess_env(lang)
            if std_data and STD_TESSDATA:
                cmd[1:1] = ["--tessdata-dir", str(STD_TESSDATA)]
                env.pop("TESSDATA_PREFIX", None)
            r = subprocess.run(cmd, capture_output=True, timeout=300, env=env)
            text += r.stdout.decode("utf-8", errors="ignore") + "\n"
    except Exception:
        pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return text


def detect_lang_by_sampling(path, npages):
    """Language of a PDF without a text layer, from a trial OCR of three pages."""
    text = ocr_sample(path, npages, SAMPLE_LANGS)
    return judge_lang(text, min_hits=10) if text else None


def is_japanese(text):
    """True if the text is mainly Japanese (kana and kanji)."""
    jp = sum(1 for ch in text if "぀" <= ch <= "ヿ" or "一" <= ch <= "鿿")
    latin = sum(1 for ch in text if ("a" <= ch <= "z") or ("A" <= ch <= "Z"))
    return jp >= 150 and jp > latin * 0.5


def japanese_check(cat, path, npages):
    """True for a mainly Japanese book: by its text layer, or by a trial OCR if it has none."""
    if cat == "scan":
        if not (STD_TESSDATA and (STD_TESSDATA / "jpn.traineddata").exists()):
            return False
        return is_japanese(ocr_sample(path, npages, "jpn", fractions=(0.4, 0.6), std_data=True))
    return is_japanese(extract_text(path, npages))


# ---------------------------------------------------------------- PDF parts / 部品

def strip_annots(src, dst):
    """Copy of the PDF without annotations (so highlights are not burnt into the pages)."""
    with pikepdf.open(src) as pdf:
        for page in pdf.pages:
            if Name.Annots in page.obj:
                del page.obj[Name.Annots]
        pdf.save(dst)


def copy_annots(src_path, ocr_path, out_path):
    """Copy notes, highlights and other annotations from the original to the new PDF."""
    src = pikepdf.open(src_path)
    dst = pikepdf.open(ocr_path)
    if len(src.pages) != len(dst.pages):
        raise RuntimeError(T("ページ数が一致しません（注釈の移植を中止）",
                             "page counts differ (annotations not copied)"))
    count = 0
    for sp, dp in zip(src.pages, dst.pages):
        if Name.Annots not in sp.obj:
            continue
        new_annots = Array()
        for a in sp.obj.Annots:
            if not a.is_indirect:
                a = src.make_indirect(a)
            if Name.P in a:
                del a[Name.P]
            na = dst.copy_foreign(a)
            na[Name.P] = dp.obj
            new_annots.append(na)
        if Name.Annots in dp.obj:
            for x in dp.obj.Annots:
                new_annots.append(x)
        dp.obj.Annots = new_annots
        count += len(new_annots)
    dst.save(out_path)
    src.close()
    dst.close()
    return count


def binarize(src, dst, threshold=140):
    """Turn gray page images into black and white, so that JBIG2 can compress them."""
    n = 0
    with pikepdf.open(src) as pdf:
        for page in pdf.pages:
            for raw in page_images(page):
                if raw.get(Name.BitsPerComponent) == 1 or raw.get(Name.ImageMask, False):
                    continue
                pil = PdfImage(raw).as_pil_image().convert("L")
                bw = pil.point(lambda v: 255 if v > threshold else 0).convert("1", dither=0)
                for key in (Name.DecodeParms, Name.Decode, Name.SMask):
                    if key in raw:
                        del raw[key]
                raw.write(zlib.compress(bw.tobytes()), filter=Name.FlateDecode)
                raw.ColorSpace = Name.DeviceGray
                raw.BitsPerComponent = 1
                n += 1
        pdf.save(dst)
    return n


def ocrmypdf(*args, lang=ALL_LANGS):
    r = subprocess.run([sys.executable, "-m", "ocrmypdf", *map(str, args)],
                       capture_output=True, text=True, env=tess_env(lang))
    if r.returncode != 0:
        tail = "\n".join(r.stderr.strip().splitlines()[-5:])
        raise RuntimeError(f"ocrmypdf exit {r.returncode}\n{tail}")


# ---------------------------------------------------------------- one file / 1冊の処理

FORCE_TYPES = ("forced", "finereader", "monotonic", "clearscan")


def decide(src):
    """Decide how to handle a PDF. Returns (category, info, pages, note)."""
    with pikepdf.open(src) as pdf:
        npages = len(pdf.pages)
        info = classify(pdf)
    cat, note = info["cat"], ""
    if japanese_check(cat, src, npages):
        return "japanese", info, npages, ""
    if cat == "digital":
        cat, note = refine_digital(info, src, npages)
    return cat, info, npages, note


def process_file(src, dst, jobs, force=False, decided=None):
    cat, info, npages, note = decided or decide(src)

    dst.parent.mkdir(parents=True, exist_ok=True)

    if cat == "japanese":
        # Mainly Japanese books are never re-OCRed, not even with --force.
        shutil.copy2(src, dst)
        return cat, "-", npages
    if force:
        mode = "forced"
    elif cat == "digital":
        shutil.copy2(src, dst)
        return cat, note, npages
    else:
        mode = cat

    if cat == "scan":
        lang = detect_lang_by_sampling(src, npages) or ALL_LANGS
    else:
        lang = detect_lang(src, npages) or detect_lang_by_sampling(src, npages) or ALL_LANGS
    common = ["--output-type", "pdf", "-l", lang, "--jobs", jobs]

    tmp = Path(tempfile.mkdtemp(prefix="greekocr_"))
    try:
        final = tmp / "final.pdf"
        if mode == "redo":
            ocrmypdf("--mode", "redo", *common, src, final, lang=lang)
        elif mode == "scan":
            ocrmypdf("--mode", "skip", *common, src, final, lang=lang)
        else:  # clearscan / FineReader / monotonic / forced
            clean = tmp / "clean.pdf"
            ocr = tmp / "ocr.pdf"
            strip_annots(src, clean)
            ocrmypdf("--mode", "force", "--optimize", "3", *common, clean, ocr, lang=lang)
            current = ocr
            # Bilevel scans, and born-digital PDFs without images, go back to black and white.
            if info["all_bilevel"] or not info["has_images"]:
                bw = tmp / "bw.pdf"
                if binarize(ocr, bw) > 0:
                    bwopt = tmp / "bwopt.pdf"
                    ocrmypdf("--mode", "skip", "--optimize", "3", *common, bw, bwopt, lang=lang)
                    current = bwopt
            copy_annots(src, current, final)
        shutil.move(str(final), str(dst))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if BEST_ON and not uses_best(lang):
        lang += T("（通常版データ）", " (standard data)")
    return mode, lang, npages


# ---------------------------------------------------------------- main

def mb(p):
    return p.stat().st_size / 1024 / 1024


def main():
    ap = argparse.ArgumentParser(
        description=T("古典ギリシャ語対応 PDF再OCR 一括処理", "Batch re-OCR of PDFs with Ancient Greek"))
    ap.add_argument("input", help=T("処理するフォルダ（サブフォルダも含む）",
                                    "folder to process (subfolders included)"))
    ap.add_argument("--out", help=T("保存先フォルダ", "output folder"))
    ap.add_argument("--dry-run", action="store_true",
                    help=T("判定を表示するだけ", "only show how each PDF would be handled"))
    ap.add_argument("--jobs", default="4", help=T("OCRに使うCPUコア数（既定 4）",
                                                  "CPU cores for OCR (default 4)"))
    ap.add_argument("--fast", action="store_true",
                    help=T("best版データがあっても通常版を使う",
                           "use the standard data even if the best data is installed"))
    ap.add_argument("--force", action="store_true",
                    help=T("種類に関係なく全ページを焼き直してOCRする",
                           "re-render and re-OCR every page, whatever the PDF"))
    ap.add_argument("--version", action="version", version=f"greek_ocr {__version__}")
    a = ap.parse_args()

    in_dir = Path(a.input).expanduser().resolve()
    if not in_dir.is_dir():
        sys.exit(T(f"フォルダが見つかりません: {in_dir}", f"Folder not found: {in_dir}"))
    suffix = T("_OCR済み", "_OCR")
    out_dir = Path(a.out).expanduser().resolve() if a.out else in_dir.parent / f"{in_dir.name}{suffix}"

    files = sorted(p for p in in_dir.rglob("*")
                   if p.is_file() and p.suffix.lower() == ".pdf"
                   and not any(part.startswith(".") for part in p.relative_to(in_dir).parts)
                   and out_dir not in p.parents)
    data_desc = setup_tessdata(a.fast)
    print(T(f"対象: {in_dir}\nPDF: {len(files)} 冊\n認識データ: {data_desc}",
            f"Folder: {in_dir}\nPDFs: {len(files)}\nOCR data: {data_desc}"))

    if a.dry_run:
        for i, f in enumerate(files, 1):
            rel = f.relative_to(in_dir)
            try:
                cat, info, n, note = decide(f)
                unknown = T("判定不可→", "unknown → ") + ALL_LANGS
                if cat == "japanese" or (cat == "digital" and not a.force):
                    lang = "-"
                elif cat == "scan":
                    lang = detect_lang_by_sampling(f, n) or unknown
                else:
                    lang = detect_lang(f, n) or detect_lang_by_sampling(f, n) or unknown
                kind = cat_name("forced") if (a.force and cat != "japanese") else cat_name(cat)
                bilevel = T(" / 白黒2値", " / bilevel") if info["all_bilevel"] else ""
                print(T(f"[{i}/{len(files)}] {rel}\n    {n}ページ / {kind} / 言語 {lang}{bilevel}",
                        f"[{i}/{len(files)}] {rel}\n    {n} page{'' if n == 1 else 's'} / {kind} / languages {lang}{bilevel}"))
                producer = info["producer"] or T("不明", "unknown")
                extra = f" / {note}" if note else ""
                print(T(f"    （詳細: 見える文字 {info['visible']} / 透明な文字 {info['invisible']}"
                        f" / 作成ソフト {producer} / {info['creator'] or '-'}{extra}）",
                        f"    (details: visible text {info['visible']} / invisible text {info['invisible']}"
                        f" / producer {producer} / {info['creator'] or '-'}{extra})"))
            except Exception as e:
                print(T(f"[{i}/{len(files)}] {rel}\n    読み込み失敗: {e}",
                        f"[{i}/{len(files)}] {rel}\n    could not read: {e}"))
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / T("OCR処理ログ.txt", "ocr_log.txt")
    print(T(f"保存先: {out_dir}\nログ: {log_path}\n", f"Output: {out_dir}\nLog: {log_path}\n"))
    done = skipped = failed = 0
    start = time.time()

    with open(log_path, "a", encoding="utf-8") as log:
        log.write(T(f"\n===== 開始 {datetime.datetime.now():%Y-%m-%d %H:%M} / {in_dir} / 認識データ: {data_desc} =====\n",
                    f"\n===== start {datetime.datetime.now():%Y-%m-%d %H:%M} / {in_dir} / OCR data: {data_desc} =====\n"))
        for i, f in enumerate(files, 1):
            rel = f.relative_to(in_dir)
            dst = out_dir / rel
            head = f"[{i}/{len(files)}] {rel}"
            decided = None
            if dst.exists():
                # A file that an earlier version only copied is redone if it now needs OCR.
                # 以前の版でそのままコピーしただけのファイルは、今の判定でOCRが必要なら作り直す
                redo_copy = False
                if dst.stat().st_size == f.stat().st_size:
                    try:
                        decided = decide(f)
                        redo_copy = a.force or decided[0] in FORCE_TYPES
                    except Exception:
                        redo_copy = False
                if not redo_copy:
                    skipped += 1
                    print(head + T("  … 処理済みのため飛ばします", "  … already done, skipped"))
                    continue
                print(head + T("  … 以前は無処理でコピーしたファイル。作り直します",
                               "  … was only copied before; redoing it"), flush=True)
                dst.unlink()
            else:
                print(head + T("  … 処理中", "  … working"), flush=True)
            t0 = time.time()
            try:
                cat, lang, n = process_file(f, dst, a.jobs, a.force, decided)
                minutes = (time.time() - t0) / 60
                line = (f"OK   {rel} | {n}p | {cat_name(cat)} | {lang} | "
                        f"{mb(f):.1f}MB→{mb(dst):.1f}MB | " + T(f"{minutes:.1f}分", f"{minutes:.1f} min"))
                done += 1
            except KeyboardInterrupt:
                log.write(T(f"中断 {rel}\n", f"interrupted {rel}\n"))
                print(T("\n中断しました。次回は続きから再開します。",
                        "\nInterrupted. The next run resumes where this one stopped."))
                break
            except Exception as e:
                line = (T("失敗 ", "FAILED ") + f"{rel} | {e}").replace("\n", " / ")
                failed += 1
            print("    " + line)
            log.write(line + "\n")
            log.flush()
        total = (time.time() - start) / 60
        summary = T(f"===== 終了: 成功 {done} / 失敗 {failed} / 飛ばし {skipped} / {total:.0f}分 =====",
                    f"===== done: {done} OK / {failed} failed / {skipped} skipped / {total:.0f} min =====")
        log.write(summary + "\n")
    print("\n" + summary)


if __name__ == "__main__":
    main()
