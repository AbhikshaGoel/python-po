"""
Twitter/X posting via API v2.
Posts text and images (media upload v1.1 + tweet v2).
"""

import requests
import tweepy
from typing import Optional

import config
from platforms.base import BasePlatform, PostResult


class TwitterPlatform(BasePlatform):
    """Twitter/X poster using API v2 + tweepy."""

    def __init__(self):
        super().__init__("twitter")
        self.client = None
        self.auth = None
        self._init_client()

    def _init_client(self):
        """Initialize tweepy client."""
        try:
            self.client = tweepy.Client(
                consumer_key=config.TWITTER_API_KEY,
                consumer_secret=config.TWITTER_API_SECRET,
                access_token=config.TWITTER_ACCESS_TOKEN,
                access_token_secret=config.TWITTER_ACCESS_SECRET,
            )
            # v1.1 API needed for media uploads
            self.auth = tweepy.OAuth1UserHandler(
                config.TWITTER_API_KEY,
                config.TWITTER_API_SECRET,
                config.TWITTER_ACCESS_TOKEN,
                config.TWITTER_ACCESS_SECRET,
            )
            self.api_v1 = tweepy.API(self.auth)
        except Exception as e:
            self.log.error(f"Failed to init Twitter client: {e}")

    def validate_credentials(self) -> bool:
        """Verify Twitter credentials."""
        try:
            me = self.client.get_me()
            if me and me.data:
                self.log.info(
                    f"Twitter authenticated as: @{me.data.username}"
                )
                return True
            return False
        except Exception as e:
            self.log.error(f"Twitter auth error: {e}")
            return False

    def _truncate(self, text: str, link: str = "", max_len: int = 280) -> str:
        """Truncate text to fit Twitter's character limit."""
        if link:
            # Twitter counts URLs as 23 chars
            available = max_len - 24  # 23 for URL + 1 for newline
            if len(text) > available:
                text = text[: available - 3] + "..."
            return f"{text}\n{link}"

        if len(text) > max_len:
            return text[: max_len - 3] + "..."
        return text

    def post_text(self, text: str, link: str = "") -> PostResult:
        """Post a tweet (text only)."""
        try:
            tweet_text = self._truncate(text, link)

            if config.DRY_RUN:
                self.log.info(
                    f"[DRY RUN] Would tweet: {tweet_text[:80]}"
                )
                return PostResult(
                    success=True,
                    platform="twitter",
                    platform_post_id="dry_run",
                )

            response = self.client.create_tweet(text=tweet_text)

            if response and response.data:
                tweet_id = response.data["id"]
                self.log.info(f"Tweeted: {tweet_id}")
                return PostResult(
                    success=True,
                    platform="twitter",
                    platform_post_id=tweet_id,
                    platform_url=f"https://twitter.com/i/status/{tweet_id}",
                )

            return PostResult(
                success=False,
                platform="twitter",
                error_message="No response data from Twitter",
            )

        except tweepy.TweepyException as e:
            return PostResult(
                success=False,
                platform="twitter",
                error_message=str(e),
            )

    def post_image(
        self, text: str, image_path: str, link: str = ""
    ) -> PostResult:
        """Post a tweet with an image."""
        try:
            if config.DRY_RUN:
                self.log.info(
                    f"[DRY RUN] Would tweet with image: {text[:80]}"
                )
                return PostResult(
                    success=True,
                    platform="twitter",
                    platform_post_id="dry_run",
                )

            # Upload media via v1.1 API
            media = self.api_v1.media_upload(filename=image_path)
            media_id = media.media_id_string

            tweet_text = self._truncate(text, link)

            # Create tweet with media via v2
            response = self.client.create_tweet(
                text=tweet_text,
                media_ids=[media_id],
            )

            if response and response.data:
                tweet_id = response.data["id"]
                self.log.info(f"Tweeted with image: {tweet_id}")
                return PostResult(
                    success=True,
                    platform="twitter",
                    platform_post_id=tweet_id,
                    platform_url=f"https://twitter.com/i/status/{tweet_id}",
                )

            return PostResult(
                success=False,
                platform="twitter",
                error_message="No response data from Twitter",
            )

        except tweepy.TweepyException as e:
            return PostResult(
                success=False,
                platform="twitter",
                error_message=str(e),
            )
