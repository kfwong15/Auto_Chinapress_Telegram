import logging
import os
from typing import Optional

import requests


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class TelegramClient:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.dry_run = _env_truthy("TELEGRAM_DRY_RUN", default=False)

        if not self.bot_token or not self.chat_id:
            if self.dry_run:
                logging.warning("Telegram is in DRY_RUN mode (missing token/chat). Messages will not be sent.")
                self.base_url = None
                return
            if not self.bot_token:
                raise ValueError("Missing TELEGRAM_BOT_TOKEN")
            if not self.chat_id:
                raise ValueError("Missing TELEGRAM_CHAT_ID")

        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, text: str, disable_web_page_preview: bool = False) -> None:
        if self.dry_run or not self.base_url or not self.chat_id:
            logging.info("[DRY_RUN] Would send Telegram message: %s", text)
            return
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_web_page_preview,
        }
        resp = requests.post(f"{self.base_url}/sendMessage", json=payload, timeout=20)
        if not resp.ok:
            logging.error("Telegram sendMessage failed: %s %s", resp.status_code, resp.text)
            resp.raise_for_status()
