# scheduler.py
"""
Simple time-based scheduler.
Runs the poster at configured times each day.
Also handles periodic maintenance tasks.
"""

import time
import schedule
import threading
from datetime import datetime

import config
from poster import Poster
from media.processor import cleanup_cache
from logger import get_logger

log = get_logger("scheduler")


class Scheduler:
    """Run tasks on a schedule."""

    def __init__(self, poster: Poster):
        self.poster = poster
        self._running = False
        self._thread = None

    def setup(self):
        """Configure all scheduled tasks."""
        # Schedule posting at configured times
        for post_time in config.POST_TIMES:
            schedule.every().day.at(post_time).do(self._run_posting_cycle)
            log.info(f"Scheduled posting at {post_time}")

        # Cleanup old media cache daily
        schedule.every().day.at("02:00").do(cleanup_cache)

        # Health check every 30 minutes
        schedule.every(30).minutes.do(self._health_check)

        # Process any pending posts every 5 minutes
        # (catches auto-approved posts between scheduled times)
        schedule.every(5).minutes.do(self.poster.process_pending)

    def _run_posting_cycle(self):
        """Run at each scheduled posting time."""
        log.info(f"=== Posting cycle started at {datetime.now().strftime('%H:%M')} ===")
        try:
            self.poster.process_pending()
        except Exception as e:
            log.error(f"Posting cycle error: {e}", exc_info=True)

    def _health_check(self):
        """Periodic health check."""
        stats = {}
        try:
            import db
            stats = db.get_stats()
            log.info(
                f"Health check OK | "
                f"Total posts: {stats.get('total_posts', 0)} | "
                f"Pending: {stats.get('by_status', {}).get('pending', 0)}"
            )
        except Exception as e:
            log.error(f"Health check failed: {e}")

    def start(self):
        """Start scheduler in background thread."""
        self.setup()
        self._running = True

        def _run():
            log.info("Scheduler started")
            while self._running:
                schedule.run_pending()
                time.sleep(1)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop scheduler."""
        self._running = False
        schedule.clear()
        log.info("Scheduler stopped")
