"""由 colab/ 的核心腳本產生按鈕模式筆記本「啟動私人AI.ipynb」。

核心腳本只維護 colab/ 一份；修改後重新執行：
    python tools/build_notebook.py
筆記本把腳本內嵌進去，所以不需要 git clone，也能直接從雲端硬碟開啟。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = ROOT / "colab"
NOTEBOOK = ROOT / "啟動私人AI.ipynb"
CORE_FILES = ["setup_strata.sh", "setup_opencode.sh", "setup_tools.sh", "selfcheck_tools.py", "portal.py", "viewer.py"]


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text, form=True):
    meta = {"cellView": "form"} if form else {}
    return {"cell_type": "code", "metadata": meta, "execution_count": None,
            "outputs": [], "source": text.strip("\n")}


def embed_core():
    lines = [
        "#@title ② 準備核心腳本（自動產生，請勿修改）",
        "import os",
        "os.makedirs('/content/core', exist_ok=True)",
        "FILES = {}",
    ]
    for name in CORE_FILES:
        content = (CORE_DIR / name).read_text(encoding="utf-8")
        if "'''" in content or content.endswith("\\"):
            raise ValueError(f"{name} 含有無法內嵌的字元")
        lines.append(f"FILES[{name!r}] = r'''{content}'''")
    lines += [
        "for name, content in FILES.items():",
        "    with open(f'/content/core/{name}', 'w', encoding='utf-8') as f:",
        "        f.write(content)",
        "print('✅ 核心腳本已就緒：', ', '.join(FILES))",
    ]
    return "\n".join(lines)


CELLS = [
    md("""
# 🔒 啟動私人 AI（教師隱私資料處理）

這個筆記本會在**你自己 Google 帳號的私人 Colab 主機**上，安裝本地 AI（Strata＋Qwen 模型）與 OpenCode 網頁介面。
資料只在這台主機內處理，**不會送到任何 AI 公司**；用完刪除執行階段，主機就會銷毀。

### 使用步驟
1. 確認右上角登入的是**有付費 Colab 運算單元**的 Google 帳號。
2. 選單「執行階段 → 變更執行階段類型」，確認硬體加速器是 **G4**（本筆記本已預設）。
3. 選單「執行階段 → 全部執行」。若跳出「這個筆記本不是由 Google 編寫的」，按「仍要執行」。
4. 等待約 10–15 分鐘，第 ⑤ 格下方就會出現對話框，直接打字即可。
5. 用完請執行最後一格「清理」，再按「執行階段 → 中斷連線並刪除執行階段」。

### ⚠️ 隱私提醒
- **不要使用 Colab 裡的 Gemini 功能**處理學生資料（Gemini 的對話可能被人工審閱）。
- 建議上傳前先把學生姓名等資料換成代號。
- 使用期間請保持這個分頁開著。
"""),
    code("""
#@title ① 檢查主機（GPU、記憶體、磁碟）
import shutil, subprocess

gpu = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                     capture_output=True, text=True)
if gpu.returncode != 0:
    raise SystemExit('❌ 沒有偵測到 GPU。請到「執行階段 → 變更執行階段類型」選擇 G4 後重新執行。')
gpu_name, vram_mib = [s.strip() for s in gpu.stdout.strip().splitlines()[0].split(',')]
vram_gb = int(vram_mib) / 1024
ram_gb = int(open('/proc/meminfo').readline().split()[1]) / 1024 / 1024
disk_gb = shutil.disk_usage('/content').free / 1024**3

print(f'GPU：{gpu_name}（{vram_gb:.0f} GB）')
print(f'系統記憶體：{ram_gb:.0f} GB')
print(f'可用磁碟：{disk_gb:.0f} GB')

# Qwen3.8 IQ3_S 需要約 55 GB（顯示卡＋系統記憶體合計）
MODEL = 'iq3_s' if vram_gb + ram_gb >= 70 else 'iq2_xs'
print(f'➡ 使用模型：Qwen3.8-Flash-Next {MODEL.upper()}')
if disk_gb < 90:
    print('⚠️ 可用磁碟少於 90 GB，模型可能下載不完。')
"""),
    code(embed_core()),
    code("""
#@title ③ 安裝 Strata 並下載、載入模型（約 10 分鐘；同時在背景安裝文件工具）
!bash /content/core/setup_tools.sh --background
!bash /content/core/setup_strata.sh {MODEL}
"""),
    code("""
#@title ④ 安裝 OpenCode，確認文件工具已就緒並自我檢查
!bash /content/core/setup_opencode.sh
!bash /content/core/setup_tools.sh --wait
"""),
    code("""
#@title ⑤ 開啟私人 AI 入口
import sys, importlib
sys.path.insert(0, '/content/core')
import portal
importlib.reload(portal)  # 重跑時讀到最新的核心腳本
from google.colab import output

model_id = portal.write_config()
portal.start()
print(f'模型：{model_id}')
print(portal.reasoning_check())
print('👇 對話框就在下方，直接打字即可（檔案用輸入框左下的「＋」附加；思考強度可在入口切換 off／low／medium／high）。')
print('（入口內嵌在這本筆記本裡，只有你這個瀏覽器、這個 Google 帳號看得到；另開分頁或換瀏覽器會是 404）')
# 內嵌顯示：另開視窗的方式會被瀏覽器擋（彈出視窗／不同分頁沒有 Colab 的存取權）
# path 直接開到工作區的新對話，老師不必自己新增專案
output.serve_kernel_port_as_iframe(portal.PORTAL_PORT, path=portal.entry_path(), height=850)
"""),
    code("""
#@title ⏹ 啟動完成（「全部執行」會停在這一格，這是正常的）
# 用例外讓「全部執行」停在這裡，下方的檢視／下載／清理格就不會被自動執行。
# 不用核取方塊：Colab 會把勾選狀態存進筆記本，下次「全部執行」就會誤觸清理（實測發生過）。
class 啟動完成(Exception):
    def _render_traceback_(self):
        return []

print('✅ 啟動完成。下方的「檢視」「下載」「清理」格，需要時再各自按左邊的 ▶。')
raise 啟動完成()
"""),
    md("""
## 📁 檢視、下載與清理

「全部執行」會在上一格停下，以下三格**只有你按 ▶ 才會執行**。

- 檔案請用對話框左下的「＋」附加。你附加的、AI 產出的檔案都在主機的「工作區」資料夾。
- 「檢視」可以直接在這裡看 Word、Excel、PowerPoint、PDF、圖片等，不必下載。
- 這本筆記本設定為**不儲存輸出**：檢視的內容只顯示在你的瀏覽器，不會存回雲端硬碟。
"""),
    code("""
#@title 👀 檢視工作區檔案（按 ▶，選檔案後按「顯示」）
import sys, importlib
sys.path.insert(0, '/content/core')
import viewer
importlib.reload(viewer)
viewer.show()
"""),
    code("""
#@title ⬇️ 下載結果（按 ▶ 把工作區打包成 zip）
import os, zipfile
from google.colab import files
ws = '/content/工作區'
names = [n for n in sorted(os.listdir(ws)) if n != 'AGENTS.md'] if os.path.isdir(ws) else []
if not names:
    print('工作區是空的，還沒有檔案可以下載。')
else:
    zip_path = '/content/處理結果.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, fnames in os.walk(ws):
            for fn in fnames:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, ws)
                if rel != 'AGENTS.md':
                    z.write(full, rel)
    print(f'✅ 已打包 {len(names)} 個項目，開始下載…')
    files.download(zip_path)
"""),
    code("""
#@title 🧹 清理（用完按 ▶：關閉 AI、刪除所有上傳檔案與對話紀錄）
import sys, os
sys.path.insert(0, '/content/core')
import portal
portal.cleanup()
if os.path.exists('/content/處理結果.zip'):
    os.remove('/content/處理結果.zip')
print('✅ 已關閉 AI、刪除工作區、對話紀錄與日誌。')
print('👉 最後請按選單「執行階段 → 中斷連線並刪除執行階段」，主機才會銷毀並停止扣運算單元。')
"""),
]


def main():
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            # private_outputs：儲存時不保存輸出，檢視的學生資料不會寫回雲端硬碟
            "colab": {"provenance": [], "gpuType": "G4", "machine_shape": "hm", "private_outputs": True},
            "accelerator": "GPU",
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
        },
        "cells": CELLS,
    }
    # 固定 LF 換行：在 Windows 產生也不會變成 CRLF
    NOTEBOOK.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"已產生 {NOTEBOOK.name}（{len(CELLS)} 格）")


if __name__ == "__main__":
    main()
