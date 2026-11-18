#!/bin/bash
# install.sh — set up Greek OCR on a Mac
# ギリシャ語OCR を Mac にセットアップする
#
# Copyright (c) 2026 Masahiro Kitano. MIT License.
#
# Usage / 使い方:
#   bash install.sh            # everything, including the "best" OCR data / best版データも含めてすべて
#   bash install.sh --no-best  # skip the best data (faster, smaller) / best版データを入れない
#
# What it does / すること:
#   1. Installs Tesseract, its language data, OCRmyPDF and pngquant with Homebrew
#   2. Copies greek_ocr.py to ~/GreekOCR and writes the launcher ~/GreekOCR/greek-ocr.sh
#   3. Downloads the "best" data for grc eng deu fra ita spa lat to ~/GreekOCR/tessdata_best
#   4. Builds the app from GreekOCR.applescript with osacompile
#      (built on your own Mac, so macOS does not warn about an unidentified developer)

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/GreekOCR"
BEST="$DEST/tessdata_best"
WANT_BEST=1
if [ "${1:-}" = "--no-best" ]; then WANT_BEST=0; fi

# ---- language of the messages / 表示言語
JA=0
if defaults read -g AppleLocale 2>/dev/null | grep -q '^ja'; then JA=1; fi
case "${LANG:-}" in ja*) JA=1 ;; esac
msg() { if [ "$JA" = 1 ]; then echo "$1"; else echo "$2"; fi; }
die() { msg "$1" "$2" >&2; exit 1; }

# ---- checks / 確認
[ "$(uname)" = "Darwin" ] || die "このスクリプトは macOS 専用です。" "This script is for macOS only."
for f in greek_ocr.py GreekOCR.applescript; do
  [ -f "$HERE/$f" ] || die "$f が見つかりません。install.sh と同じフォルダに置いてください。" \
                           "$f not found. Keep it in the same folder as install.sh."
done

BREW=""
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  if [ -x "$b" ]; then BREW="$b"; break; fi
done
[ -n "$BREW" ] || die "Homebrew が見つかりません。先に https://brew.sh の手順でインストールしてください。" \
                      "Homebrew not found. Install it first, following https://brew.sh"
eval "$("$BREW" shellenv)"

# ---- 1. software / ソフト
msg "== 1/4 Tesseract・OCRmyPDF をインストールします（数分かかります）" \
    "== 1/4 Installing Tesseract and OCRmyPDF (this takes a few minutes)"
brew install tesseract tesseract-lang ocrmypdf pngquant

PY="$(brew --prefix ocrmypdf)/libexec/bin/python3"
[ -x "$PY" ] || die "OCRmyPDF の Python が見つかりません: $PY" "OCRmyPDF's Python not found: $PY"
STD="$(brew --prefix)/share/tessdata"

# ---- 2. script and launcher / スクリプトと起動用ファイル
msg "== 2/4 スクリプトを $DEST に置きます" "== 2/4 Copying the script to $DEST"
mkdir -p "$DEST"
cp "$HERE/greek_ocr.py" "$DEST/greek_ocr.py"
cat > "$DEST/greek-ocr.sh" <<'LAUNCHER'
#!/bin/bash
# Runs greek_ocr.py with the Python that comes with OCRmyPDF.
# OCRmyPDF に付属の Python で greek_ocr.py を動かす。
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  if [ -x "$b" ]; then eval "$("$b" shellenv)"; break; fi
done
exec "$(brew --prefix ocrmypdf)/libexec/bin/python3" "$HOME/GreekOCR/greek_ocr.py" "$@"
LAUNCHER
chmod +x "$DEST/greek-ocr.sh"

# ---- 3. best data / best版データ
if [ "$WANT_BEST" = 1 ]; then
  msg "== 3/4 best版の言語データをダウンロードします" "== 3/4 Downloading the best OCR data"
  mkdir -p "$BEST"
  for l in grc eng deu fra ita spa lat; do
    f="$BEST/$l.traineddata"
    if [ -s "$f" ] && [ "$(wc -c < "$f")" -gt 1000000 ]; then
      msg "   $l: すでにあります" "   $l: already there"
      continue
    fi
    curl -fL --retry 3 -o "$f.part" "https://github.com/tesseract-ocr/tessdata_best/raw/main/$l.traineddata"
    mv "$f.part" "$f"
  done
  cp "$STD/osd.traineddata" "$BEST/"
  for sub in configs tessconfigs; do
    if [ ! -e "$BEST/$sub" ] && [ -e "$STD/$sub" ]; then ln -s "$STD/$sub" "$BEST/$sub"; fi
  done
else
  msg "== 3/4 best版データは入れません（--no-best）" "== 3/4 Skipping the best data (--no-best)"
fi

# ---- 4. app / アプリ
if [ -w /Applications ]; then APPDIR=/Applications; else APPDIR="$HOME/Applications"; mkdir -p "$APPDIR"; fi
if [ "$JA" = 1 ]; then APP="$APPDIR/ギリシャ語OCR.app"; else APP="$APPDIR/Greek OCR.app"; fi
msg "== 4/4 アプリを作ります: $APP" "== 4/4 Building the app: $APP"
rm -rf "$APP"
osacompile -o "$APP" "$HERE/GreekOCR.applescript"

# ---- check / 確認
"$PY" "$DEST/greek_ocr.py" --version >/dev/null
msg "" ""
msg "完了しました。フォルダを「$(basename "$APP" .app)」にドロップして使います。" \
    "Done. Drop a folder on \"$(basename "$APP" .app)\" to use it."
msg "初めて使うときに「ターミナルを制御しようとしています」と出たら「OK」を押してください。" \
    "The first time, macOS asks whether the app may control Terminal: click OK."
