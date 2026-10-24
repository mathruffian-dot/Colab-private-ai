#!/usr/bin/env bash
# 預先安裝文件處理工具整合包，避免老師使用時 OpenCode 才要求安裝（例如 OCR 繁中語言包）。
# 用法：bash setup_tools.sh            （前景安裝）
#       bash setup_tools.sh --background（背景安裝，與模型下載同時進行）
#       bash setup_tools.sh --wait      （等待背景安裝完成，再跑 selfcheck_tools.py 確認真的能用）
set -uo pipefail

LOG_DIR=/content/logs
DONE=/content/logs/tools.done
mkdir -p "$LOG_DIR"

APT_PACKAGES=(
  tesseract-ocr tesseract-ocr-chi-tra tesseract-ocr-chi-sim tesseract-ocr-eng  # OCR（含繁中）
  poppler-utils                                                               # pdftotext、pdftoppm
  pandoc                                                                      # Markdown ↔ Word 等轉檔
  libreoffice-writer libreoffice-calc libreoffice-impress                     # docx／xlsx／pptx 轉 PDF
  fonts-noto-cjk                                                              # 中文字型，轉 PDF 不會變方塊
  graphviz                                                                    # 流程圖、組織圖
  ghostscript unpaper pngquant                                                # ocrmypdf 需要的工具（ocrmypdf 本身用 pip 裝）
  fonts-arphic-ukai fonts-arphic-uming                                        # 楷書、明體：代替公文常用的標楷體、新細明體
)
PIP_PACKAGES=(
  python-docx openpyxl python-pptx pdfplumber pymupdf pytesseract pdf2image  # 文件與 OCR
  xlsxwriter tabulate seaborn plotly graphviz                                 # 表格與圖表（已裝的會略過）
  docxtpl docxcompose                                                         # Word 範本合併列印、合併多份 Word
  pypdf pyzipper msoffcrypto-tool xlrd                                        # PDF 合併／加密、AES 加密壓縮、有密碼的 Office 檔、舊版 .xls
  opencc-python-reimplemented jieba                                           # 簡轉繁（台灣用語）、中文斷詞
  ocrmypdf                                                                    # 掃描 PDF 轉可搜尋文字（apt 版是給系統 Python 3.10 的，Colab 的 python3 較新會無法執行）
)
# pandas、numpy、matplotlib、Pillow、OpenCV 是 Colab 內建，不重裝（由 selfcheck_tools.py 確認）

# 學校文件常指定標楷體、新細明體、微軟正黑體（Windows 字型，Linux 沒有），轉 PDF 時改用最接近的字型
configure_fontconfig() {
  cat > /etc/fonts/local.conf <<'EOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <alias><family>標楷體</family><prefer><family>AR PL UKai TW</family></prefer></alias>
  <alias><family>DFKai-SB</family><prefer><family>AR PL UKai TW</family></prefer></alias>
  <alias><family>BiauKai</family><prefer><family>AR PL UKai TW</family></prefer></alias>
  <alias><family>新細明體</family><prefer><family>AR PL UMing TW</family></prefer></alias>
  <alias><family>PMingLiU</family><prefer><family>AR PL UMing TW</family></prefer></alias>
  <alias><family>細明體</family><prefer><family>AR PL UMing TW</family></prefer></alias>
  <alias><family>MingLiU</family><prefer><family>AR PL UMing TW</family></prefer></alias>
  <alias><family>微軟正黑體</family><prefer><family>Noto Sans CJK TC</family></prefer></alias>
  <alias><family>Microsoft JhengHei</family><prefer><family>Noto Sans CJK TC</family></prefer></alias>
</fontconfig>
EOF
  fc-cache -f >/dev/null 2>&1
}

# 圖表中文字型：matplotlib 預設字型沒有中文，會畫成方塊
configure_matplotlib() {
  local cfg cache
  cfg=$(python3 -c 'import matplotlib; print(matplotlib.get_configdir())') || return 1
  cache=$(python3 -c 'import matplotlib; print(matplotlib.get_cachedir())') || return 1
  rm -rf "$cache"/fontlist-*.json  # 讓 matplotlib 重新掃描，找到剛裝的 Noto CJK
  # 用 matplotlib 實際認得的字型名稱（.ttc 只會登記其中一個，常是 JP），避免寫了不存在的名稱一直跳警告
  local family
  family=$(python3 - <<'PY'
from matplotlib import font_manager as fm
names = {f.name for f in fm.fontManager.ttflist if "CJK" in f.name}
print(next((n for n in ("Noto Sans CJK TC", "Noto Sans CJK JP") if n in names), sorted(names)[0] if names else ""))
PY
)
  [ -n "$family" ] || { echo "⚠️ matplotlib 找不到中文字型" >&2; return 1; }
  mkdir -p "$cfg"
  cat > "$cfg/matplotlibrc" <<EOF
font.family: sans-serif
font.sans-serif: $family, DejaVu Sans
axes.unicode_minus: False
EOF
}

install_all() {
  rm -f "$DONE"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends "${APT_PACKAGES[@]}"
  pip install -q "${PIP_PACKAGES[@]}"
  configure_fontconfig
  configure_matplotlib
  tesseract --list-langs 2>/dev/null | grep -q chi_tra && touch "$DONE"
}

case "${1:-}" in
  --background)
    nohup bash "$0" > "$LOG_DIR/tools.log" 2>&1 &
    echo "▶ 文件工具整合包在背景安裝中（OCR 繁中、PDF、Word／Excel／PPT、表格與圖表、合併列印、加密、公文字型）…"
    ;;
  --wait)
    for _ in $(seq 1 120); do
      if [ -f "$DONE" ]; then
        echo "✅ 文件工具整合包已安裝，開始自我檢查（約 30 秒）…"
        python3 "$(dirname "$0")/selfcheck_tools.py" 2>&1 | tee "$LOG_DIR/selfcheck.log"
        exit 0  # 自我檢查沒過只警告，不擋 AI 啟動
      fi
      sleep 5
    done
    echo "⚠️ 文件工具安裝未完成，最後幾行紀錄：" >&2
    tail -n 15 "$LOG_DIR/tools.log" >&2
    exit 1
    ;;
  *)
    install_all
    [ -f "$DONE" ] || { echo "❌ 文件工具安裝失敗" >&2; exit 1; }
    ;;
esac
