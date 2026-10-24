#!/usr/bin/env bash
# 安裝 Strata 並在背景啟動模型，等到模型載入完成才結束。
# 用法：bash setup_strata.sh [模型代號，預設 iq3_s] [最長等待分鐘數，預設 120]
set -euo pipefail

MODEL="${1:-iq3_s}"
MAX_WAIT_MIN="${2:-120}"
# 上下文長度：模型上限 256K；G4（96GB 顯卡＋177GB 記憶體）以 --plan 確認可行
CONTEXT="${STRATA_CONTEXT:-256k}"
# Colab 自己的服務佔用 8080，Strata 改用 8181
STRATA_PORT="${STRATA_PORT:-8181}"
LOG_DIR=/content/logs
HEALTH_URL="http://127.0.0.1:${STRATA_PORT}/health"
mkdir -p "$LOG_DIR"
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

is_loaded() {
  curl -fs --max-time 5 "$HEALTH_URL" 2>/dev/null | grep -Eq '"loaded"[[:space:]]*:[[:space:]]*true'
}

if is_loaded; then
  echo "✅ Strata 已在執行，模型已載入。"
  exit 0
fi

if ! command -v strata >/dev/null 2>&1; then
  echo "▶ 安裝 Strata…"
  curl -fsSL https://github.com/Niko1221/Strata/releases/latest/download/install.sh -o /tmp/strata_install.sh
  sh /tmp/strata_install.sh
  # 安裝程式會把 strata 放進 PATH，但 Colab 的非互動 shell 不一定讀得到，補建一個連結
  if ! command -v strata >/dev/null 2>&1; then
    found=$(find "$HOME/.local" -maxdepth 5 -type f -name strata -perm -u+x 2>/dev/null | head -n1 || true)
    if [ -z "$found" ]; then
      echo "❌ 找不到 strata 執行檔，安裝可能失敗。" >&2
      exit 1
    fi
    ln -sf "$found" /usr/local/bin/strata
  fi
fi
# Python 核心（portal.py）的 PATH 沒有 ~/.local/bin，統一連到 /usr/local/bin
ln -sf "$(command -v strata)" /usr/local/bin/strata 2>/dev/null || true
strata --version

echo "▶ 啟動 Strata（模型 $MODEL，上下文 $CONTEXT）。第一次會下載約 55–76 GB，請耐心等候…"
nohup strata launch --model "$MODEL" --context "$CONTEXT" --port "$STRATA_PORT" --yes --no-tui > "$LOG_DIR/strata.log" 2>&1 &

start=$(date +%s)
while ! is_loaded; do
  elapsed=$(( ($(date +%s) - start) / 60 ))
  if [ "$elapsed" -ge "$MAX_WAIT_MIN" ]; then
    echo "❌ 等待超過 $MAX_WAIT_MIN 分鐘仍未載入，最後幾行紀錄：" >&2
    tail -n 20 "$LOG_DIR/strata.log" >&2
    exit 1
  fi
  last=$(tail -n 1 "$LOG_DIR/strata.log" 2>/dev/null | tr -d '\r' | cut -c1-120)
  echo "  ⏳ 已等待 ${elapsed} 分鐘｜${last}"
  sleep 30
done

echo "✅ 模型載入完成，總共 $(( ($(date +%s) - start) / 60 )) 分鐘。"
