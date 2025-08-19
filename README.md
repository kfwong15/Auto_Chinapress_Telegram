(cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF'
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,2 +1,55 @@
-# MyNewsBot
-Malaysia News
+## Telegram 新闻机器人（中国报）
+
+使用 GitHub Actions 定时抓取中国报（China Press）的新闻并发送到 Telegram。
+
+### 功能
+- 优先通过 RSS 抓取（`https://www.chinapress.com.my/feed/`），失败时回退到首页 HTML 解析。
+- 去重：使用仓库中的 `data/seen.json` 持久化，避免重复推送。
+- 支持手动触发与定时（默认每 15 分钟）。
+
+### 快速开始
+1. 创建 Telegram Bot 并获取 Token：
+   - 在 Telegram 搜索 `@BotFather`，创建新 Bot，获取 `TELEGRAM_BOT_TOKEN`。
+2. 获取 Chat ID：
+   - 与你的 Bot 开始聊天并发送任意消息；
+   - 打开 `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates` 查看 `chat.id`；或将 Bot 拉入群并获取群 `chat.id`。
+3. 将本仓库 Fork 到你自己的 GitHub 账号。
+4. 在仓库的 Settings → Secrets and variables → Actions 中添加 Secrets：
+   - `TELEGRAM_BOT_TOKEN`: 你的 Bot Token
+   - `TELEGRAM_CHAT_ID`: 你的聊天/群 ID（整数或以 `-100` 开头的群 ID）
+5. 可选变量（可在 Workflow 中或仓库级 Variables 设置）：
+   - `MAX_ITEMS_PER_RUN`: 每次最多推送多少条，默认 10。
+6. 手动触发一次工作流（Actions → Telegram News Bot → Run workflow），或等待定时任务。
+
+### 本地运行
+```bash
+python -m venv .venv
+source .venv/bin/activate
+pip install -r requirements.txt
+export TELEGRAM_BOT_TOKEN=xxx
+export TELEGRAM_CHAT_ID=xxx
+python -m src.main
+```
+
+### 结构
+```
+.
+├─ src/
+│  ├─ main.py                # 入口
+│  ├─ chinapress.py          # 中国报抓取逻辑（RSS 优先，HTML 备选）
+│  ├─ telegram_client.py     # Telegram 发送
+│  ├─ state_store.py         # 去重状态存储
+│  └─ models.py              # 数据模型
+├─ data/seen.json            # 已推送链接（Actions 会自动维护）
+├─ .github/workflows/telegram-news.yml  # 定时任务
+├─ requirements.txt
+└─ README.md
+```
+
+### 注意
+- GitHub Actions 已开启 `contents: write` 权限，便于自动提交 `data/seen.json` 的更新。
+- 若中国报站点改版导致解析失败，脚本会从 RSS 回退到 HTML；若两者都失败，任务会安全退出并在下次重试。
+
+# MyNewsBot
+Malaysia News
+
EOF
)
