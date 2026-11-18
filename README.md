# Greek OCR (GreekOCR-redo)

[日本語](README.ja.md)

For years I have bought books and articles in European languages that contain Greek, scanned them, and read them with FineReader or Acrobat Pro to use them as PDFs. As described below, however, their Ancient Greek is not recognised correctly, and articles downloaded from JSTOR and similar sites have the same problem. Many of these PDFs also carry my notes and sticky notes, which the recent OCR applications that do support Ancient Greek cannot keep when they read the PDFs again.

This tool re-reads PDFs containing Ancient Greek (polytonic Greek, with accents and breathings) with **Tesseract** and **OCRmyPDF**, keeping notes and sticky notes, so that the Greek can be copied and searched correctly. It is meant for fixing PDFs you already use, so it works on whole folders: drop a folder on the app and it processes the PDFs inside, one by one. To OCR newly acquired PDFs, use [EuroOCR](https://github.com/MasahiroKitano/EuroOCR).

## The problem it solves

PDFs OCRed with Adobe Acrobat or ABBYY FineReader read English, German, French and other languages well, but their Ancient Greek comes out garbled:

- Acrobat does not support Ancient Greek, so copied Greek turns into strings such as `'t.�Jov`.
- FineReader reads Greek as modern (monotonic) Greek, so breathings, circumflexes and other diacritics are lost.

After this tool, the same passage copies as `ζῷον`, `καλόν`, `τεταγμένα`.

## Features

- **Keeps sticky notes, comments and highlights.** When pages have to be rebuilt, the annotations are copied back from the original PDF.
- **Recognises what kind of PDF it is**: Acrobat "searchable image", ClearScan, already OCRed by FineReader, scans without a text layer, born-digital text, mainly Japanese books — and handles each accordingly.
- **Detects the main language** (English, German, French, Italian, Spanish or Latin) and OCRs with "that language + Ancient Greek". Books that mix two of them (a German book full of Latin quotations, say) get both.
- **Never modifies the originals.** Results go to a separate folder with the same subfolder structure.
- **Resumable.** Files already done are skipped on the next run.
- **Supports Tesseract's "best" data** when accuracy matters more than speed.

## Requirements

- macOS (Apple Silicon or Intel)
- [Homebrew](https://brew.sh)
- Disk space: a few GB for the software and OCR data, plus the results (from the same size as the originals to a few times larger; see Notes)

The author uses it on a MacBook Air (M1) and has run it on more than 1,000 PDFs. It has not been tested on Windows or Linux.

## Installation

1. Click "Code" → "Download ZIP" on this page and unzip it.
2. Open Terminal, type `cd ` (with a space after it), drag the unzipped folder onto the Terminal window, and press Return.
3. Run:

```
bash install.sh
```

`install.sh` does the following:

1. Installs Tesseract, its language data, OCRmyPDF and pngquant with Homebrew
2. Copies `greek_ocr.py` to `~/GreekOCR`
3. Downloads the "best" data (grc eng deu fra ita spa lat) to `~/GreekOCR/tessdata_best`
4. Builds the "Greek OCR" app in the Applications folder

The app is built on your own Mac, so macOS does not warn about an unidentified developer. To skip the best data, use `bash install.sh --no-best`.

## Usage

1. Drop a folder of PDFs on the "Greek OCR" app (or double-click the app and choose the folder).
2. Choose the OCR data: **Best** (more accurate, slower) or **Standard** (faster).
3. Choose what to do:
   - **Preview only**: shows how each PDF would be handled, and changes nothing. A good first step.
   - **Start OCR**: processes the PDFs.
   - **Forced OCR**: rebuilds and re-OCRs every page, whatever the PDF. For books the automatic handling did not fix.
4. Progress is shown in Terminal, and a notification tells you when it is done. To stop, press `control + C` in that window.

Results are saved next to the folder you dropped, in "FOLDER_OCR", together with `ocr_log.txt`, which records the handling, languages, size change and time for each PDF.

You can also run it from Terminal:

```
~/GreekOCR/greek-ocr.sh FOLDER [--dry-run] [--force] [--fast] [--out DIR] [--jobs 4]
```

Messages follow the system language (Japanese or English). Set `GREEK_OCR_LANG=en` or `GREEK_OCR_LANG=ja` to choose.

## How each kind of PDF is handled

| Kind | How it is recognised | What is done |
| --- | --- | --- |
| Mainly Japanese | Mostly kana and kanji, in the text layer or a trial OCR | Copied as is |
| Searchable image | Mostly invisible text | Only the invisible text layer is replaced: fast, size almost unchanged |
| ClearScan | Visible text with black-and-white image fragments, or made by Acrobat's Paper Capture | Pages rebuilt and re-OCRed, annotations copied back |
| OCRed by FineReader | Made by FineReader and contains Greek letters | As for ClearScan |
| Read as modern Greek | Many Greek letters but almost none with breathings | As for ClearScan |
| No text layer | No text | Normal OCR |
| Born-digital | Text from the start, none of the above | Copied as is |

## Notes

- **OCR is not perfect.** Some errors remain, but the page images look exactly as before. Think of it as a better text layer for copying and searching.
- **File size**: books whose pages are rebuilt (such as ClearScan) grow. In the author's library most grew 1.1–1.4×, a few nearly 3×. "Searchable image" PDFs hardly change.
- **Speed**: about 1–4 seconds per page with the standard data; the best data is slower.
- Acrobat does not store Greek as Greek letters, so ClearScan books are rebuilt whether or not they contain Greek.
- Books OCRed with FineReader without Greek among the recognition languages cannot be recognised automatically: use Forced OCR.
- Do not process the results again: rebuilding twice lowers the image quality. Always process the originals.
- For long runs, keep the Mac on power and a MacBook's lid open (idle sleep is prevented automatically).
- Back up your PDFs before you start.

## Copyright

This tool is meant to make your own PDFs easier to use. If you share processed PDFs, respect the copyright of the books and articles they contain.

## Software used

This tool relies on the following (not bundled; `install.sh` installs them with Homebrew):

- [Tesseract](https://github.com/tesseract-ocr/tesseract) (Apache License 2.0) and [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) (Apache License 2.0)
- [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) (MPL-2.0)
- [pikepdf](https://github.com/pikepdf/pikepdf) (MPL-2.0)
- [Ghostscript](https://www.ghostscript.com) (AGPL)

## Author

Masahiro Kitano

Developed with the help of Claude, Anthropic's AI assistant.

## License

[MIT License](LICENSE). No warranty.
