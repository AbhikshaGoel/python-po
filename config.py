"""
All configuration loaded from .env file.
Single source of truth for every setting.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")


def _get(key: str, default: str = "") -> str:
    """Get env var or return default."""
    return os.getenv(key, default).strip()


def _get_bool(key: str, default: bool = False) -> bool:
    """Get boolean env var."""
    val = _get(key, str(default)).lower()
    return val in ("true", "1", "yes")


def _get_int(key: str, default: int = 0) -> int:
    """Get integer env var."""
    try:
        return int(_get(key, str(default)))
    except ValueError:
        return default


def _get_list(key: str, default: str = "") -> list[str]:
    """Get comma-separated list from env var."""
    raw = _get(key, default)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


# ── Paths ──────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data"
MEDIA_CACHE_DIR = DATA_DIR / "media_cache"
LOG_DIR = PROJECT_ROOT / "logs"
DB_PATH = DATA_DIR / "posts.db"

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
MEDIA_CACHE_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# ── Telegram ───────────────────────────────────────────
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID")

# ── Slack (optional) ──────────────────────────────────
SLACK_BOT_TOKEN = _get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = _get("SLACK_CHANNEL_ID")

# ── Facebook ───────────────────────────────────────────
FACEBOOK_PAGE_ID = _get("FACEBOOK_PAGE_ID")
FACEBOOK_ACCESS_TOKEN = _get("FACEBOOK_ACCESS_TOKEN")

# ── Instagram ──────────────────────────────────────────
INSTAGRAM_BUSINESS_ACCOUNT_ID = _get("INSTAGRAM_BUSINESS_ACCOUNT_ID")
INSTAGRAM_ACCESS_TOKEN = _get("INSTAGRAM_ACCESS_TOKEN")

# ── Twitter/X ──────────────────────────────────────────
TWITTER_API_KEY = _get("TWITTER_API_KEY")
TWITTER_API_SECRET = _get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = _get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = _get("TWITTER_ACCESS_SECRET")

# ── YouTube ────────────────────────────────────────────
YOUTUBE_CLIENT_ID = _get("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = _get("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = _get("YOUTUBE_REFRESH_TOKEN")

# ── LinkedIn ───────────────────────────────────────────
LINKEDIN_ACCESS_TOKEN = _get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = _get("LINKEDIN_PERSON_ID")

# ── Webhook ────────────────────────────────────────────
WEBHOOK_SECRET = _get("WEBHOOK_SECRET", "change-me-please")
WEBHOOK_PORT = _get_int("WEBHOOK_PORT", 5123)

# ── Schedule ───────────────────────────────────────────
POST_TIMES = _get_list("POST_TIMES", "09:00,13:00,18:00")

# ── Approval ──────────────────────────────────────────
APPROVAL_TIMEOUT_MINUTES = _get_int("APPROVAL_TIMEOUT_MINUTES", 5)
AUTO_APPROVE = _get_bool("AUTO_APPROVE", True)

# ── General ────────────────────────────────────────────
LOG_LEVEL = _get("LOG_LEVEL", "INFO")
DRY_RUN = _get_bool("DRY_RUN", False)

# ── Platform enable/disable (auto-detect from tokens) ─
ENABLED_PLATFORMS: list[str] = []

if FACEBOOK_ACCESS_TOKEN and FACEBOOK_PAGE_ID:
    ENABLED_PLATFORMS.append("facebook")
if INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID:
    ENABLED_PLATFORMS.append("instagram")
if TWITTER_API_KEY and TWITTER_ACCESS_TOKEN:
    ENABLED_PLATFORMS.append("twitter")
if YOUTUBE_REFRESH_TOKEN:
    ENABLED_PLATFORMS.append("youtube")
if LINKEDIN_ACCESS_TOKEN:
    ENABLED_PLATFORMS.append("linkedin")


def validate() -> list[str]:
    """Check config and return list of problems."""
    problems = []

    if not TELEGRAM_BOT_TOKEN:
        problems.append("TELEGRAM_BOT_TOKEN is missing")
    if not TELEGRAM_CHAT_ID:
        problems.append("TELEGRAM_CHAT_ID is missing")
    if WEBHOOK_SECRET == "change-me-please":
        problems.append("WEBHOOK_SECRET is still the default value")
    if not ENABLED_PLATFORMS:
        problems.append("No platforms configured (all tokens missing)")
    if not POST_TIMES:
        problems.append("No POST_TIMES configured")

    return problems


def print_status():
    """Print current configuration status."""
    print("\n╔══════════════════════════════════════╗")
    print("║     Social Poster Configuration      ║")
    print("╠══════════════════════════════════════╣")
    print(f"║ Platforms: {', '.join(ENABLED_PLATFORMS) or 'NONE':<24} ║")
    print(f"║ Post times: {', '.join(POST_TIMES):<23} ║")
    print(f"║ Approval timeout: {APPROVAL_TIMEOUT_MINUTES} min{' ' * 14} ║")
    print(f"║ Auto-approve: {str(AUTO_APPROVE):<21} ║")
    print(f"║ Dry run: {str(DRY_RUN):<26} ║")
    print(f"║ Telegram: {'✓' if TELEGRAM_BOT_TOKEN else '✗':<25} ║")
    print(f"║ Slack: {'✓' if SLACK_BOT_TOKEN else '✗ (disabled)':<28} ║")
    print(f"║ DB: {str(DB_PATH.name):<31} ║")
    print("╚══════════════════════════════════════╝")

    problems = validate()
    if problems:
        print("\n⚠️  WARNINGS:")
        for p in problems:
            print(f"   • {p}")
        print()
