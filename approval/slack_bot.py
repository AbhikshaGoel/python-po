# slack_bot.py
"""
Slack notification bot (optional).
Sends approval requests to Slack channel.
Simpler than Telegram - just notifications, approve via Telegram.
"""

import json
import requests
from typing import Optional

import config
from logger import get_logger

log = get_logger("slack")


class SlackBot:
    """Simple Slack notification sender."""

    API_BASE = "https://slack.com/api"

    def __init__(self):
        self.token = config.SLACK_BOT_TOKEN
        self.channel = config.SLACK_CHANNEL_ID
        self.enabled = bool(self.token and self.channel)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def validate(self) -> bool:
        """Check Slack credentials."""
        if not self.enabled:
            log.info("Slack not configured, skipping")
            return False

        try:
            resp = requests.post(
                f"{self.API_BASE}/auth.test",
                headers=self._headers(),
                timeout=10,
            )
            data = resp.json()
            if data.get("ok"):
                log.info(f"Slack authenticated as: {data.get('user')}")
                return True
            log.error(f"Slack auth failed: {data.get('error')}")
            return False
        except requests.RequestException as e:
            log.error(f"Slack connection error: {e}")
            return False

    def send_notification(self, post: dict, status: str = "pending") -> bool:
        """Send a notification to Slack about a post."""
        if not self.enabled:
            return False

        try:
            blocks = self._build_blocks(post, status)

            resp = requests.post(
                f"{self.API_BASE}/chat.postMessage",
                headers=self._headers(),
                json={
                    "channel": self.channel,
                    "text": f"New post: {post['topic']}",
                    "blocks": blocks,
                },
                timeout=15,
            )
            data = resp.json()
            if data.get("ok"):
                log.info("Slack notification sent")
                return True
            log.error(f"Slack send failed: {data.get('error')}")
            return False

        except requests.RequestException as e:
            log.error(f"Slack send error: {e}")
            return False

    def _build_blocks(self, post: dict, status: str) -> list:
        """Build Slack Block Kit message."""
        status_emoji = {
            "pending": "🟡",
            "approved": "🟢",
            "rejected": "🔴",
            "completed": "✅",
            "failed": "❌",
        }.get(status, "⚪")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} Post #{post['id']}: {post['topic'][:60]}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Summary:*\n{post['summary'][:300]}\n\n"
                        f"*Status:* {status.upper()}\n"
                        f"*Priority:* {post['priority']}\n"
                        f"*Platforms:* {', '.join(config.ENABLED_PLATFORMS)}"
                    ),
                },
            },
        ]

        if post.get("link"):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Link:* {post['link']}",
                },
            })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"_Approve/reject via Telegram_ | "
                        f"Auto-approval in {config.APPROVAL_TIMEOUT_MINUTES}min"
                    ),
                }
            ],
        })

        return blocks

    def send_result(self, post: dict, results: list[dict]) -> bool:
        """Send posting results to Slack."""
        if not self.enabled:
            return False

        lines = [f"📊 *Results for Post #{post['id']}:* {post['topic']}"]
        for r in results:
            emoji = "✅" if r["status"] == "published" else "❌"
            url_text = f" - <{r['platform_url']}|View>" if r.get("platform_url") else ""
            error_text = f" ({r['error_message']})" if r.get("error_message") else ""
            lines.append(
                f"  {emoji} {r['platform'].capitalize()}{url_text}{error_text}"
            )

        return self.send_notification(
            {**post, "summary": "\n".join(lines)},
            status="completed",
        )
