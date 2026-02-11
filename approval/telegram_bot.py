# telegram_bot.py
"""
Telegram Bot for post approval.
Sends preview → waits for response → approves/rejects.
Simple polling-based bot (no webhook server needed).
"""

import time
import threading
import json
import requests
from typing import Optional, Callable
from datetime import datetime, timezone

import config
import db
from logger import get_logger

log = get_logger("telegram")


class TelegramBot:
    """Simple Telegram bot for approval notifications."""

    API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base_url = self.API_BASE.format(token=self.token)
        self._last_update_id = 0
        self._pending_approvals: dict[int, dict] = {}
        # Maps message_id → {post_id, timer_thread, callback}
        self._running = False

    def _api(self, method: str, **kwargs) -> dict:
        """Call Telegram Bot API."""
        try:
            resp = requests.post(
                f"{self.base_url}/{method}",
                json=kwargs,
                timeout=30,
            )
            data = resp.json()
            if not data.get("ok"):
                log.error(f"Telegram API error: {data}")
            return data
        except requests.RequestException as e:
            log.error(f"Telegram request failed: {e}")
            return {"ok": False, "error": str(e)}

    def validate(self) -> bool:
        """Check if bot token is valid."""
        data = self._api("getMe")
        if data.get("ok"):
            bot_name = data["result"]["username"]
            log.info(f"Telegram bot validated: @{bot_name}")
            return True
        return False

    def send_message(
        self,
        text: str,
        reply_markup: dict = None,
        parse_mode: str = "HTML",
    ) -> Optional[int]:
        """Send a message. Returns message_id."""
        kwargs = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            kwargs["reply_markup"] = reply_markup

        data = self._api("sendMessage", **kwargs)
        if data.get("ok"):
            return data["result"]["message_id"]
        return None

    def edit_message(self, message_id: int, text: str, reply_markup: dict = None):
        """Edit an existing message."""
        kwargs = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        self._api("editMessageText", **kwargs)

    def send_approval_request(
        self,
        post_id: int,
        on_approved: Callable,
        on_rejected: Callable,
    ) -> bool:
        """
        Send a post for approval with inline buttons.
        Starts a countdown timer for auto-approval.
        """
        post = db.get_post(post_id)
        if not post:
            log.error(f"Post {post_id} not found")
            return False

        # Build preview message
        text = self._build_preview(post)

        # Inline keyboard with approve/reject buttons
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Approve & Post",
                        "callback_data": f"approve:{post_id}",
                    },
                    {
                        "text": "❌ Reject",
                        "callback_data": f"reject:{post_id}",
                    },
                ],
                [
                    {
                        "text": f"⏱ Auto-posts in {config.APPROVAL_TIMEOUT_MINUTES}min",
                        "callback_data": f"info:{post_id}",
                    },
                ],
            ]
        }

        msg_id = self.send_message(text, reply_markup=keyboard)
        if not msg_id:
            log.error("Failed to send approval message")
            return False

        # Store pending approval
        self._pending_approvals[msg_id] = {
            "post_id": post_id,
            "on_approved": on_approved,
            "on_rejected": on_rejected,
            "sent_at": time.time(),
        }

        # Start auto-approval timer
        if config.AUTO_APPROVE:
            timer = threading.Timer(
                config.APPROVAL_TIMEOUT_MINUTES * 60,
                self._auto_approve,
                args=[msg_id, post_id, on_approved],
            )
            timer.daemon = True
            timer.start()
            self._pending_approvals[msg_id]["timer"] = timer

        return True

    def _build_preview(self, post: dict) -> str:
        """Build a nice preview message for Telegram."""
        lines = [
            "🚀 <b>New Post Ready for Approval</b>",
            "",
            f"📝 <b>Topic:</b> {_escape(post['topic'])}",
            "",
            f"📄 <b>Summary:</b>",
            _escape(post["summary"][:500]),
            "",
        ]

        if post.get("link"):
            lines.append(f"🔗 <b>Link:</b> {post['link']}")

        if post.get("image_url"):
            lines.append(f"🖼 <b>Image:</b> {post['image_url'][:80]}...")

        if post.get("video_url"):
            lines.append("🎬 <b>Video:</b> (manual posting required)")

        lines.extend([
            "",
            f"📊 <b>Priority:</b> {post['priority'].upper()}",
            f"📡 <b>Platforms:</b> {', '.join(config.ENABLED_PLATFORMS)}",
            "",
            f"⏱ Auto-approval in <b>{config.APPROVAL_TIMEOUT_MINUTES} minutes</b>",
        ])

        return "\n".join(lines)

    def _auto_approve(self, msg_id: int, post_id: int, callback: Callable):
        """Auto-approve after timeout."""
        if msg_id not in self._pending_approvals:
            return  # Already handled

        log.info(f"Auto-approving post {post_id} (timeout)")

        # Remove from pending
        del self._pending_approvals[msg_id]

        # Update message
        self.edit_message(
            msg_id,
            f"⚠️ <b>Auto-Approved</b> (timeout)\n\nPost #{post_id} is being posted...",
        )

        # Update DB
        db.update_post_status(
            post_id,
            status="auto_approved",
            approval_type="timeout",
            approved_by="system",
        )

        # Trigger posting
        callback(post_id)

    def process_callback(self, callback_data: str, msg_id: int):
        """Handle button press from Telegram."""
        parts = callback_data.split(":")
        action = parts[0]
        post_id = int(parts[1])

        approval = self._pending_approvals.get(msg_id)
        if not approval:
            log.warning(f"No pending approval for message {msg_id}")
            return

        # Cancel timer
        timer = approval.get("timer")
        if timer:
            timer.cancel()

        # Remove from pending
        del self._pending_approvals[msg_id]

        if action == "approve":
            log.info(f"Post {post_id} manually approved")
            self.edit_message(
                msg_id,
                f"✅ <b>Approved!</b>\n\nPost #{post_id} is being posted...",
            )
            db.update_post_status(
                post_id,
                status="approved",
                approval_type="manual",
                approved_by="telegram_user",
            )
            approval["on_approved"](post_id)

        elif action == "reject":
            log.info(f"Post {post_id} rejected")
            self.edit_message(
                msg_id,
                f"❌ <b>Rejected</b>\n\nPost #{post_id} has been rejected.",
            )
            db.update_post_status(
                post_id,
                status="rejected",
                rejection_reason="Manually rejected via Telegram",
            )
            approval["on_rejected"](post_id)

    def poll_updates(self):
        """Long-poll for updates from Telegram."""
        data = self._api(
            "getUpdates",
            offset=self._last_update_id + 1,
            timeout=30,
        )

        if not data.get("ok"):
            return

        for update in data.get("result", []):
            self._last_update_id = update["update_id"]

            # Handle callback queries (button presses)
            if "callback_query" in update:
                callback = update["callback_query"]
                callback_data = callback.get("data", "")
                msg_id = callback["message"]["message_id"]

                # Answer the callback (removes loading spinner)
                self._api(
                    "answerCallbackQuery",
                    callback_query_id=callback["id"],
                )

                self.process_callback(callback_data, msg_id)

    def start_polling(self):
        """Start polling for updates in a background thread."""
        self._running = True

        def _poll_loop():
            log.info("Telegram bot polling started")
            while self._running:
                try:
                    self.poll_updates()
                except Exception as e:
                    log.error(f"Polling error: {e}")
                    time.sleep(5)

        thread = threading.Thread(target=_poll_loop, daemon=True)
        thread.start()
        return thread

    def stop_polling(self):
        """Stop the polling loop."""
        self._running = False


def _escape(text: str) -> str:
    """Escape HTML special chars for Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
