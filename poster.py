"""
Main posting orchestrator.
Takes a post from the DB, processes it, gets approval, posts to all platforms.
This is the brain of the system.
"""

import time
from typing import Optional

import config
import db
import platforms
from media.processor import process_for_all_platforms, cleanup_cache
from approval.telegram_bot import TelegramBot
from approval.slack_bot import SlackBot
from notifier.alerts import (
    alert_post_failed,
    alert_all_platforms_failed,
    send_alert,
)
from logger import get_logger

log = get_logger("poster")


class Poster:
    """Orchestrates the entire post lifecycle."""

    def __init__(self):
        self.telegram = TelegramBot()
        self.slack = SlackBot()
        self._posting_in_progress = set()

    def start(self):
        """Initialize and start the poster service."""
        log.info("Starting Poster service...")

        # Initialize DB
        db.init_db()

        # Validate Telegram
        if not self.telegram.validate():
            log.error("Telegram bot validation failed!")
            return False

        # Validate Slack (optional)
        if self.slack.enabled:
            self.slack.validate()

        # Validate platforms
        platform_status = platforms.validate_all()
        for name, valid in platform_status.items():
            status = "✓" if valid else "✗"
            log.info(f"  Platform {name}: {status}")

        # Start Telegram polling for approval responses
        self.telegram.start_polling()

        log.info("Poster service started successfully")
        return True

    def process_incoming(
        self,
        topic: str,
        summary: str,
        full_content: str = "",
        link: str = "",
        image_url: str = "",
        video_url: str = "",
        priority: str = "normal",
        source: str = "webhook",
        tags: list[str] = None,
    ) -> int:
        """
        Process a new incoming post.
        Creates DB record → Sends for approval → Returns post_id.
        """
        # Create post in DB
        post_id = db.create_post(
            topic=topic,
            summary=summary,
            full_content=full_content,
            link=link,
            image_url=image_url,
            video_url=video_url,
            priority=priority,
            source=source,
            tags=tags,
        )

        log.info(f"Created post #{post_id}: {topic}")

        # Send for approval
        self.telegram.send_approval_request(
            post_id=post_id,
            on_approved=self._on_approved,
            on_rejected=self._on_rejected,
        )

        # Also notify Slack
        post = db.get_post(post_id)
        if post:
            self.slack.send_notification(post, "pending")

        return post_id

    def _on_approved(self, post_id: int):
        """Called when a post is approved (manually or auto)."""
        log.info(f"Post #{post_id} approved, starting posting...")
        self._do_post(post_id)

    def _on_rejected(self, post_id: int):
        """Called when a post is rejected."""
        log.info(f"Post #{post_id} rejected")
        post = db.get_post(post_id)
        if post:
            self.slack.send_notification(post, "rejected")

    def _do_post(self, post_id: int):
        """Execute posting to all platforms."""
        if post_id in self._posting_in_progress:
            log.warning(f"Post #{post_id} already being processed, skipping")
            return

        self._posting_in_progress.add(post_id)

        try:
            post = db.get_post(post_id)
            if not post:
                log.error(f"Post #{post_id} not found")
                return

            db.update_post_status(post_id, "posting")

            # Process media if image URL provided
            processed_images = {}
            if post.get("image_url"):
                log.info(f"Processing media for post #{post_id}")
                processed_images = process_for_all_platforms(post["image_url"])

            # Post to each platform
            results = []
            success_count = 0
            total_count = 0

            for name, platform in platforms.get_all_enabled().items():
                total_count += 1

                # Build the post text
                text = self._build_post_text(post, name)

                # Get processed image path (or use original URL)
                image_path = None
                if name in processed_images and processed_images[name]:
                    image_path = str(processed_images[name])
                elif post.get("image_url"):
                    # For platforms that accept URLs (like Instagram)
                    image_path = post["image_url"]

                # Post
                log.info(f"Posting to {name}...")
                db.update_platform_status(post_id, name, "posting")

                result = platform.post(
                    text=text,
                    image_path=image_path,
                    link=post.get("link", ""),
                )

                if result.success:
                    success_count += 1
                    db.update_platform_status(
                        post_id,
                        name,
                        "published",
                        platform_post_id=result.platform_post_id,
                        platform_url=result.platform_url,
                    )
                    log.info(
                        f"  ✓ {name}: {result.platform_url or result.platform_post_id}"
                    )
                else:
                    db.update_platform_status(
                        post_id,
                        name,
                        "failed",
                        error_message=result.error_message,
                    )
                    log.error(f"  ✗ {name}: {result.error_message}")
                    alert_post_failed(post_id, name, result.error_message)

                results.append({
                    "platform": name,
                    "status": "published" if result.success else "failed",
                    "platform_url": result.platform_url,
                    "error_message": result.error_message,
                })

                # Small delay between platforms to be nice to APIs
                time.sleep(2)

            # Update overall status
            if success_count == total_count:
                db.update_post_status(post_id, "completed")
                log.info(
                    f"Post #{post_id} completed: {success_count}/{total_count} platforms"
                )
            elif success_count > 0:
                db.update_post_status(post_id, "partial_failure")
                log.warning(
                    f"Post #{post_id} partial: {success_count}/{total_count} platforms"
                )
            else:
                db.update_post_status(post_id, "failed")
                log.error(f"Post #{post_id} FAILED on all platforms")
                alert_all_platforms_failed(post_id)

            # Send results to Slack
            post = db.get_post(post_id)
            if post:
                self.slack.send_result(post, results)

            # Send summary to Telegram
            summary_lines = [f"📊 Post #{post_id} Results:\n"]
            for r in results:
                emoji = "✅" if r["status"] == "published" else "❌"
                summary_lines.append(f"{emoji} {r['platform'].capitalize()}")
                if r.get("platform_url"):
                    summary_lines.append(f"   {r['platform_url']}")
            self.telegram.send_message("\n".join(summary_lines))

        except Exception as e:
            log.error(f"Error posting #{post_id}: {e}", exc_info=True)
            db.update_post_status(
                post_id, "failed", error_message=str(e)
            )
            send_alert(
                f"Post #{post_id} Crashed",
                str(e),
                level="critical",
            )
        finally:
            self._posting_in_progress.discard(post_id)

    def _build_post_text(self, post: dict, platform: str) -> str:
        """
        Build platform-appropriate post text.
        Different platforms have different character limits and styles.
        """
        topic = post["topic"]
        summary = post["summary"]
        link = post.get("link", "")

        if platform == "twitter":
            # 280 chars max, link counts as 23
            max_text = 253 if link else 280
            text = f"{topic}\n\n{summary}"
            if len(text) > max_text:
                text = f"{topic}\n\n{summary[:max_text - len(topic) - 5]}..."
            return text

        elif platform == "instagram":
            # 2200 chars max, no clickable links in caption
            text = f"{topic}\n\n{summary}"
            if post.get("full_content"):
                text += f"\n\n{post['full_content']}"
            if link:
                text += "\n\n🔗 Link in bio"
            return text[:2200]

        elif platform == "linkedin":
            # 3000 chars max
            text = f"{topic}\n\n{summary}"
            if post.get("full_content"):
                text += f"\n\n{post['full_content']}"
            return text[:3000]

        else:
            # Facebook, YouTube, default
            text = f"{topic}\n\n{summary}"
            if post.get("full_content"):
                text += f"\n\n{post['full_content']}"
            if link:
                text += f"\n\n🔗 {link}"
            return text[:5000]

    def process_pending(self):
        """
        Check for any approved posts that haven't been posted yet.
        Called by the scheduler.
        """
        pending = db.get_pending_posts()
        if pending:
            log.info(f"Found {len(pending)} pending posts to process")
        for post in pending:
            self._do_post(post["id"])

    def stop(self):
        """Graceful shutdown."""
        self.telegram.stop_polling()
        cleanup_cache()
        log.info("Poster service stopped")
