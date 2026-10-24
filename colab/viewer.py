"""在 Colab 裡直接預覽工作區的檔案，不必下載。

筆記本的「👀 檢視工作區檔案」格呼叫 show()：選檔案 → 顯示在格子下方。
- Word／PowerPoint 等：LibreOffice 轉 PDF 後逐頁顯示成圖片（版面最接近原檔）
- Excel／CSV：表格；PDF：逐頁圖片；圖片、Markdown、文字檔：直接顯示；HTML（互動圖表）：內嵌
內容只顯示在老師自己的瀏覽器；筆記本設為「不儲存輸出」，不會寫回雲端硬碟。
"""
import glob
import html
import io
import os
import shutil
import subprocess
import tempfile

WORKSPACE = "/content/工作區"
HIDDEN = {"AGENTS.md"}
MAX_PAGES = 20          # 超過的頁數不顯示，避免畫面太長
MAX_TEXT = 200_000      # 文字檔最多顯示的字數
PAGE_DPI = "80"

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
OFFICE_EXT = {".docx", ".doc", ".odt", ".rtf", ".pptx", ".ppt", ".odp"}
TABLE_EXT = {".xlsx", ".xls", ".ods", ".csv"}
TEXT_EXT = {".txt", ".json", ".py", ".log", ".tsv", ".xml", ".yaml", ".yml"}


def list_files():
    """工作區的檔案（含子資料夾），最新修改的排最前面。"""
    found = []
    for root, dirs, files in os.walk(WORKSPACE):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), WORKSPACE)
            if rel not in HIDDEN and not name.startswith((".", "~$")):
                found.append(rel)
    return sorted(found, key=lambda r: os.path.getmtime(os.path.join(WORKSPACE, r)), reverse=True)


def _show_pdf_pages(pdf):
    from IPython.display import Image, display
    tmp = tempfile.mkdtemp(prefix="viewer_")
    try:
        subprocess.run(["pdftoppm", "-png", "-r", PAGE_DPI, "-l", str(MAX_PAGES), pdf, os.path.join(tmp, "p")],
                       check=True, capture_output=True, timeout=180)
        pages = sorted(glob.glob(os.path.join(tmp, "p*.png")))
        for page in pages:
            display(Image(filename=page))
        if len(pages) == MAX_PAGES:
            print(f"（只顯示前 {MAX_PAGES} 頁，完整內容請下載）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _show_office(path):
    tmp = tempfile.mkdtemp(prefix="viewer_")
    try:
        # 獨立的 LibreOffice 設定檔，避免和 AI 同時轉檔時互搶
        subprocess.run(["soffice", f"-env:UserInstallation=file://{tmp}/profile", "--headless",
                        "--convert-to", "pdf", "--outdir", tmp, path],
                       check=True, capture_output=True, timeout=240)
        pdfs = glob.glob(os.path.join(tmp, "*.pdf"))
        if not pdfs:
            raise RuntimeError("LibreOffice 沒有轉出 PDF")
        _show_pdf_pages(pdfs[0])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _show_table(path, ext):
    import pandas as pd
    from IPython.display import Markdown, display
    if ext == ".csv":
        sheets = {"": pd.read_csv(path)}
    else:
        sheets = pd.read_excel(path, sheet_name=None)
    for name, df in sheets.items():
        if name:
            display(Markdown(f"**工作表：{name}**（{len(df)} 列）"))
        display(df)


def _show_image(path):
    from IPython.display import Image, display
    from PIL import Image as PILImage
    if os.path.splitext(path)[1].lower() in {".png", ".jpg", ".jpeg", ".gif"}:
        display(Image(filename=path))
        return
    buf = io.BytesIO()
    PILImage.open(path).convert("RGB").save(buf, format="PNG")
    display(Image(data=buf.getvalue()))


def _show_text(path, markdown=False):
    from IPython.display import HTML, Markdown, display
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read(MAX_TEXT + 1)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT]
        print(f"（只顯示前 {MAX_TEXT} 字）")
    if markdown:
        display(Markdown(text))
    else:
        display(HTML(f"<pre style='white-space:pre-wrap'>{html.escape(text)}</pre>"))


def preview(rel):
    """顯示一個工作區檔案；rel 為相對於工作區的路徑。"""
    from IPython.display import HTML, display
    path = os.path.join(WORKSPACE, rel)
    ext = os.path.splitext(rel)[1].lower()
    print(f"📄 {rel}")
    if ext == ".pdf":
        _show_pdf_pages(path)
    elif ext in OFFICE_EXT:
        _show_office(path)
    elif ext in TABLE_EXT:
        _show_table(path, ext)
    elif ext in IMAGE_EXT:
        _show_image(path)
    elif ext in {".md", ".markdown"}:
        _show_text(path, markdown=True)
    elif ext in {".html", ".htm"}:
        with open(path, encoding="utf-8", errors="replace") as f:
            display(HTML(f.read()))
    elif ext in TEXT_EXT:
        _show_text(path)
    else:
        print("這種檔案無法在這裡預覽，請按「下載這個檔案」。")


def show():
    """顯示檔案選單與按鈕。"""
    import ipywidgets as widgets
    from IPython.display import display

    picker = widgets.Dropdown(description="檔案", layout=widgets.Layout(width="70%"))
    view_btn = widgets.Button(description="👀 顯示", button_style="primary")
    refresh_btn = widgets.Button(description="🔄 重新整理清單")
    download_btn = widgets.Button(description="⬇️ 下載這個檔案")
    out = widgets.Output()

    def refresh(_=None):
        files = list_files()
        picker.options = files
        if not files:
            with out:
                out.clear_output()
                print("工作區還沒有檔案。用對話框左下的「＋」附加檔案，或請 AI 產出後再按「重新整理清單」。")

    def view(_):
        with out:
            out.clear_output()
            if not picker.value:
                print("請先選一個檔案。")
                return
            try:
                preview(picker.value)
            except Exception as e:  # 預覽失敗只提示，不影響其他功能
                print(f"⚠️ 無法預覽（{type(e).__name__}: {e}），請改用下載。")

    def download(_):
        from google.colab import files
        with out:
            if picker.value:
                files.download(os.path.join(WORKSPACE, picker.value))

    view_btn.on_click(view)
    refresh_btn.on_click(refresh)
    download_btn.on_click(download)
    refresh()
    display(widgets.VBox([picker, widgets.HBox([view_btn, refresh_btn, download_btn]), out]))
