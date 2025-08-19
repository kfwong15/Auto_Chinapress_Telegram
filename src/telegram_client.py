(cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF'
diff --git a/src/telegram_client.py b/src/telegram_client.py
--- a/src/telegram_client.py
+++ b/src/telegram_client.py
@@ -0,0 +1,30 @@
+import logging
+import os
+from typing import Optional
+
+import requests
+
+
+class TelegramClient:
+    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
+        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
+        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
+        if not self.bot_token:
+            raise ValueError("Missing TELEGRAM_BOT_TOKEN")
+        if not self.chat_id:
+            raise ValueError("Missing TELEGRAM_CHAT_ID")
+        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
+
+    def send_message(self, text: str, disable_web_page_preview: bool = False) -> None:
+        payload = {
+            "chat_id": self.chat_id,
+            "text": text,
+            "parse_mode": "HTML",
+            "disable_web_page_preview": disable_web_page_preview,
+        }
+        resp = requests.post(f"{self.base_url}/sendMessage", json=payload, timeout=20)
+        if not resp.ok:
+            logging.error("Telegram sendMessage failed: %s %s", resp.status_code, resp.text)
+            resp.raise_for_status()
+
+
EOF
)
