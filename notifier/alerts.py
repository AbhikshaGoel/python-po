# alerts.py
"""
Alert system for failures and important events.
Uses Telegram (and optionally Slack) to send alerts.
"""

import requests
import config
from logger import get_logger

log = get_logger("alerts")


def send_alert(title: str, message: str, level: str = "warning"):
    """
    Send an alert to configured channels.
    Levels: info, warning, error, critical
    """
    emoji = {
        "info": "ℹ️",
        "warning": "⚠️",
        "error": "❌",
        "critical": "🚨",
    }.get(level, "📢")

    full_message = f"{emoji} <b>{title}</b>\n\n{message}"

    # Always send to Telegram
    _send_telegram_alert(full_message)

    # Also send to Slack if configured
    if config.SLACK_BOT_TOKEN and config.SLACK_CHANNEL_ID:
        _send_slack_alert(f"{emoji} *{title}*\n\n{message}")


def _send_telegram_alert(text: str):
    """Send alert via Telegram."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
    except Exception as e:
        log.error(f"Failed to send Telegram alert: {e}")


def _send_slack_alert(text: str):
    """Send alert via Slack."""
    try:
        requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {config.SLACK_BOT_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "channel": config.SLACK_CHANNEL_ID,
                "text": text,
            },
            timeout=10,
        )
    except Exception as e:
        log.error(f"Failed to send Slack alert: {e}")


def alert_post_failed(post_id: int, platform: str, error: str):
    """Alert when a post fails on a platform."""
    send_alert(
        f"Post #{post_id} Failed on {platform.capitalize()}",
        f"Platform: {platform}\nError: {error}",
        level="error",
    )


def alert_all_platforms_failed(post_id: int):
    """Alert when a post fails on ALL platforms."""
    send_alert(
        f"Post #{post_id} FAILED on ALL Platforms",
        "No platforms were able to publish this post. Check logs.",
        level="critical",
    )


def alert_credentials_expired(platform: str):
    """Alert when platform credentials stop working."""
    send_alert(
        f"{platform.capitalize()} Credentials Expired",
        f"The {platform} API credentials are no longer valid.\n"
        f"Please update them in .env and restart.",
        level="critical",
    )
