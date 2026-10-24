"""產生 OpenCode 設定、啟動網頁入口、關閉與清理。

筆記本與 agent 都只呼叫這裡的函式，確保兩種模式行為一致。
本檔不會讀取或列出工作區裡的檔案內容（學生資料）。
"""
import base64
import json
import os
import secrets
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request

# Colab 自己的服務佔用 8080，Strata 改用 8181（與 setup_strata.sh 一致）
STRATA_URL = f"http://127.0.0.1:{os.environ.get('STRATA_PORT', '8181')}"
PORTAL_PORT = 4096
# 老師的所有檔案（上傳的、AI 產出的）都放在這一個資料夾，也是入口預設開啟的專案
WORKSPACE = "/content/工作區"
LOG_DIR = "/content/logs"
CONFIG_PATH = os.path.expanduser("~/.config/opencode/opencode.json")
OPENCODE_DATA = os.path.expanduser("~/.local/share/opencode")
PID_FILE = os.path.join(LOG_DIR, "opencode.pid")
COMPACT_AT = 0.8  # 用到上下文 80% 就自動壓縮，避免爆掉
# 思考強度：Strata 接受 app 的 reasoning effort（off／low／medium／high），
# OpenCode 的 variants 讓老師在介面切換；off 最快，high 適合難題
REASONING_LEVELS = ["off", "low", "medium", "high"]

AGENT_RULES = """# 工作規則

你是協助老師處理教學資料的助理，在一台私人主機上執行。

- 所有檔案都在目前這個資料夾：老師上傳的檔案在這裡，你產出的檔案也一律存在這裡（不要另建子資料夾，除非老師要求）。
- 檔案可能含學生個資：不得連網、不得把內容傳到任何外部服務。
- 已預先安裝好的工具，直接使用，**不要再安裝其他套件或下載任何東西**；缺少工具時告訴老師：
  - OCR：`tesseract`（含繁中 chi_tra、簡中 chi_sim、英文 eng），Python `pytesseract`
  - PDF：`pdftotext`／`pdftoppm`（poppler），Python `pdfplumber`、`pymupdf`（PyMuPDF）
  - Word／Excel／PowerPoint：Python `docx`、`openpyxl`、`pptx`；轉檔用 `pandoc`、`soffice --headless --convert-to`（LibreOffice）
  - 表格資料分析：Python `pandas`、`numpy`（可直接讀寫 Excel）
  - 圖片處理：Python `PIL`（Pillow）、`cv2`（OpenCV）；你也可以直接看圖（模型支援圖片輸入）
- 表格與圖表的做法（中文字型都已設定好）：
  - Word 表格：`docx` 的 `add_table`（可設 `style = "Table Grid"`）；Word 裡的圖表：先用 matplotlib 存成 PNG，再 `add_picture`
  - Excel 表格與圖表：`openpyxl.chart` 或 `xlsxwriter`，做成 Excel 原生圖表，老師之後還能在 Excel 裡改
  - PowerPoint 圖表：`pptx` 的 `shapes.add_chart`（原生圖表，可再編輯）
  - 統計圖存成圖片：`matplotlib`（不必指定字型）；用 `seaborn` 時要寫 `sns.set_theme(font=plt.rcParams["font.sans-serif"][0])`（沿用已設定的中文字型），否則中文會變方塊
  - 互動圖表：`plotly` 存成 HTML，一定要用 `write_html(..., include_plotlyjs=True)`，才能離線打開
  - 流程圖、組織圖：`graphviz`，節點與圖都要設 `fontname="Noto Sans CJK TC"`
  - 在對話中顯示表格：用 Markdown 表格，或 `pandas` 的 `to_markdown()`
- 老師常見的文書工作：
  - 合併列印（每位學生一份通知單、成績單、IEP）：`docxtpl` 用 Word 範本（`{{ 姓名 }}`）逐一產生；要合成一個檔用 `docxcompose`
  - PDF 合併、分割、加密碼：`pypdf`；要加密壓縮整批檔案用 `pyzipper`（AES）。密碼由老師提供，不要自己設定或寫進檔名
  - 學校寄來有密碼的 Excel／Word：`msoffcrypto-tool`（要先請老師提供密碼）
  - 舊版 `.xls` 用 `pandas.read_excel`（已裝 xlrd）；舊版 `.doc`／`.ppt` 先用 `soffice --headless --convert-to docx`（或 pptx）轉檔再處理
  - 掃描的 PDF：`ocrmypdf -l chi_tra+eng 輸入.pdf 輸出.pdf` 轉成可搜尋、可複製文字；手寫或表格很複雜時，直接看圖通常比 OCR 準
  - 文件指定標楷體／新細明體／微軟正黑體時照常寫進檔案；轉 PDF 會自動用楷書／明體／黑體代替
  - 簡體轉繁體（台灣用語）：`opencc`（`OpenCC("s2twp")`）；所有產出一律用繁體中文
  - 輔導紀錄、問卷開放題的關鍵字與斷詞：`jieba`
  - 去識別化：先用代號取代姓名，身分證字號（如 `[A-Z][12]\\d{8}`）、電話、生日、地址用正規表示式找出來遮蔽，完成後列出替換了哪些欄位讓老師確認
- 用繁體中文回答；產出 IEP 等正式文件時保持專業、具體、可評量。
- 不確定的地方標註「待老師確認」，不要自行編造學生資料。
"""


def _get_json(path):
    with urllib.request.urlopen(STRATA_URL + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def strata_model():
    """回傳 Strata 目前提供的 (模型 ID, 上下文長度)。"""
    models = _get_json("/v1/models").get("data", [])
    if not models:
        raise RuntimeError("Strata 沒有回報任何模型，請確認模型已載入。")
    # 以 Strata 實際載入的上下文為準（setup_strata.sh 預設要 256K）；讀不到時保守用 65536
    return models[0]["id"], models[0].get("meta", {}).get("n_ctx", 65536)


def write_config(context=None, output=16384):
    """寫入 OpenCode 全域設定：只連本機 Strata、禁止分享與連網；上下文長度跟 Strata 一致。

    自動壓縮：OpenCode 1.19.4（session/overflow.ts）在 已用 token ≥ limit.input − compaction.reserved
    時壓縮，所以 input 設滿、reserved 設 20%，就是用到 80% 時壓縮。
    """
    model_id, n_ctx = strata_model()
    context = context or n_ctx
    config = {
        "$schema": "https://opencode.ai/config.json",
        "share": "disabled",
        "autoupdate": False,
        "model": f"strata/{model_id}",
        "small_model": f"strata/{model_id}",
        "provider": {
            "strata": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Strata（私人主機上的 AI）",
                "options": {"baseURL": STRATA_URL + "/v1", "apiKey": "local"},
                "models": {
                    model_id: {
                        "name": model_id,
                        "limit": {"context": context, "input": context, "output": output},
                        "modalities": {"input": ["text", "image"], "output": ["text"]},
                        # @ai-sdk/openai-compatible 會把 reasoningEffort 送成 reasoning_effort
                        "variants": {level: {"reasoningEffort": level} for level in REASONING_LEVELS},
                    }
                },
            }
        },
        "compaction": {"auto": True, "prune": True, "reserved": int(context * (1 - COMPACT_AT))},
        "permission": {"webfetch": "deny"},
    }
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return model_id


def reasoning_check():
    """用一題簡單算術確認 Strata 真的依思考強度調整：off 不該有思考內容，high 應該有。"""
    def thinks(level):
        body = {"model": "local", "max_tokens": 300, "reasoning_effort": level,
                "messages": [{"role": "user", "content": "1+1 等於多少？只回答數字。"}]}
        req = urllib.request.Request(STRATA_URL + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            msg = json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]
        thought = msg.get("reasoning_content") or msg.get("reasoning") or ""
        return bool(thought.strip()) or "<think>" in (msg.get("content") or "")

    try:
        off, high = thinks("off"), thinks("high")
    except Exception as e:  # 檢查失敗不影響入口
        return f"⚠️ 無法確認思考強度（{type(e).__name__}: {e}）"
    if high and not off:
        return "✅ 思考強度可切換：off 不思考、high 會思考（入口可選 " + "／".join(REASONING_LEVELS) + "）"
    return f"⚠️ 思考強度可能沒有生效（off 有思考：{off}，high 有思考：{high}）"


def entry_path(directory=WORKSPACE):
    """入口直接開到「工作區」的新對話，省掉「新增專案」步驟。

    OpenCode 1.19.4 網頁版路由 `/:dir/session/:id?`，dir 為目錄的 URL-safe base64（去掉 =），
    見 packages/app/src/utils/session-route.ts 的 legacySessionHref。
    """
    encoded = base64.urlsafe_b64encode(directory.encode("utf-8")).decode("ascii").rstrip("=")
    return f"/{encoded}/session"


def _port_open(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3)
        return True
    except urllib.error.HTTPError:
        return True  # 401 等回應代表服務已經起來
    except OSError:
        return False


def start(port=PORTAL_PORT, wait_seconds=120, use_password=False):
    """啟動 OpenCode 網頁介面，回傳 (使用者名稱, 本次密碼)；不設密碼時回傳 (None, None)。

    預設不設密碼：入口內嵌在 Colab 筆記本裡，只有開著這本筆記本、登入同一個
    Google 帳號的瀏覽器連得到（換瀏覽器實測為 404）；內嵌畫面也無法跳出帳密框。
    """
    os.makedirs(WORKSPACE, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    rules = os.path.join(WORKSPACE, "AGENTS.md")
    if not os.path.exists(rules):
        with open(rules, "w", encoding="utf-8") as f:
            f.write(AGENT_RULES)

    stop_portal()
    env = dict(os.environ)
    env.pop("OPENCODE_SERVER_PASSWORD", None)
    password = secrets.token_urlsafe(9) if use_password else None
    if password:
        env["OPENCODE_SERVER_PASSWORD"] = password
    log = open(os.path.join(LOG_DIR, "opencode.log"), "w")
    # Colab 的連接埠代理是從主機內網位址連進來，只綁 127.0.0.1 會 404；
    # 綁 0.0.0.0 仍只能經 Google 驗證的代理到達，另有密碼保護。Strata 維持只綁 127.0.0.1。
    proc = subprocess.Popen(
        ["opencode", "web", "--hostname", "0.0.0.0", "--port", str(port)],
        cwd=WORKSPACE, env=env, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("OpenCode 啟動失敗，請查看 /content/logs/opencode.log")
        if _port_open(port):
            return ("opencode" if password else None), password
        time.sleep(2)
    raise RuntimeError("OpenCode 在時間內沒有回應，請查看 /content/logs/opencode.log")


def stop_portal():
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            pid = int(f.read().strip() or 0)
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        os.remove(PID_FILE)


def cleanup():
    """關閉入口與 Strata，刪除工作區、對話紀錄與日誌。"""
    stop_portal()
    strata = shutil.which("strata") or os.path.expanduser("~/.local/bin/strata")
    try:
        subprocess.run([strata, "launch", "--stop"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass  # 找不到 strata 就略過；刪除執行階段時主機會一併銷毀
    for path in (WORKSPACE, OPENCODE_DATA, LOG_DIR):
        shutil.rmtree(path, ignore_errors=True)
