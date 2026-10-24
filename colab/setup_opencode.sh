#!/usr/bin/env bash
# 安裝 OpenCode（agent 與網頁介面）。
set -euo pipefail
# 固定實測過的版本：入口網址格式（/<目錄>/session）依版本而異
OPENCODE_VERSION="${OPENCODE_VERSION:-1.19.4}"
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:/usr/local/bin:$PATH"

if ! command -v opencode >/dev/null 2>&1; then
  echo "▶ 安裝 OpenCode $OPENCODE_VERSION…"
  curl -fsSL https://opencode.ai/install -o /tmp/opencode_install.sh
  bash /tmp/opencode_install.sh --version "$OPENCODE_VERSION"
  for candidate in "$HOME/.opencode/bin/opencode" "$HOME/.local/bin/opencode"; do
    if [ -x "$candidate" ]; then
      ln -sf "$candidate" /usr/local/bin/opencode
      break
    fi
  done
fi

if ! command -v opencode >/dev/null 2>&1; then
  echo "❌ 找不到 opencode 執行檔，安裝可能失敗。" >&2
  exit 1
fi
echo "✅ OpenCode $(opencode --version)"
