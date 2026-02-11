# instagram.py
"""
Instagram posting via Facebook Graph API.
Requires an Instagram Business Account connected to a Facebook Page.
Supports single image posts.
Reels/Stories are manual.
"""

import time
import requests

import config
from platforms.base import BasePlatform, PostResult


class InstagramPlatform(BasePlatform):
    """Instagram poster using Facebook Graph API (Content Publishing API)."""

    API_BASE = "https://graph.facebook.com/v19.0"

    def __init__(self):
        super().__init__("instagram")
        self.account_id = config.INSTAGRAM_BUSINESS_ACCOUNT_ID
        self.access_token = config.INSTAGRAM_ACCESS_TOKEN

    def validate_credentials(self) -> bool:
        """Verify Instagram Business credentials."""
        try:
            resp = requests.get(
                f"{self.API_BASE}/{self.account_id}",
                params={
                    "fields": "username,name",
                    "access_token": self.access_token,
                },
                timeout=10,
            )
            data = resp.json()
            if "error" in data:
                self.log.error(
                    f"Instagram auth error: {data['error']['message']}"
                )
                return False
            self.log.info(
                f"Instagram authenticated as: @{data.get('username')}"
            )
            return True
        except requests.RequestException as e:
            self.log.error(f"Instagram connection error: {e}")
            return False

    def post_text(self, text: str, link: str = "") -> PostResult:
        """
        Instagram doesn't support text-only posts.
        Return skipped result.
        """
        self.log.info("Instagram requires an image, skipping text-only post")
        return PostResult(
            success=False,
            platform="instagram",
            error_message="Instagram requires an image for posting",
        )

    def post_image(
        self, text: str, image_path: str, link: str = ""
    ) -> PostResult:
        """
        Post image to Instagram.
        Uses the 2-step Container approach:
        1. Create media container with image URL
        2. Publish the container
        
        NOTE: Image must be accessible via public URL.
              Local files need to be uploaded to a CDN first.
        """
        try:
            caption = text
            if link:
                caption = f"{text}\n\n🔗 Link in bio"

            if config.DRY_RUN:
                self.log.info(
                    f"[DRY RUN] Would post to Instagram: {text[:80]}"
                )
                return PostResult(
                    success=True,
                    platform="instagram",
                    platform_post_id="dry_run",
                )

            # Instagram requires a PUBLIC image URL
            # If image_path is a local file, you need to upload it first
            # For now, we assume image_url is passed or image is hosted
            image_url = image_path  # This should be a URL
            if image_url.startswith("/") or image_url.startswith("C:"):
                self.log.error(
                    "Instagram requires a public URL, not a local file path. "
                    "Upload image to CDN first."
                )
                return PostResult(
                    success=False,
                    platform="instagram",
                    error_message="Local file not supported, need public URL",
                )

            # Step 1: Create container
            resp = requests.post(
                f"{self.API_BASE}/{self.account_id}/media",
                data={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": self.access_token,
                },
                timeout=30,
            )
            data = resp.json()

            if "error" in data:
                return PostResult(
                    success=False,
                    platform="instagram",
                    error_message=data["error"]["message"],
                )

            container_id = data["id"]
            self.log.info(f"Instagram container created: {container_id}")

            # Step 2: Wait for processing (poll status)
            for attempt in range(10):
                time.sleep(3)
                status_resp = requests.get(
                    f"{self.API_BASE}/{container_id}",
                    params={
                        "fields": "status_code",
                        "access_token": self.access_token,
                    },
                    timeout=10,
                )
                status_data = status_resp.json()
                status_code = status_data.get("status_code")

                if status_code == "FINISHED":
                    break
                elif status_code == "ERROR":
                    return PostResult(
                        success=False,
                        platform="instagram",
                        error_message=f"Container processing failed: {status_data}",
                    )
                self.log.debug(
                    f"Instagram processing... attempt {attempt + 1}"
                )

            # Step 3: Publish
            publish_resp = requests.post(
                f"{self.API_BASE}/{self.account_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": self.access_token,
                },
                timeout=30,
            )
            publish_data = publish_resp.json()

            if "error" in publish_data:
                return PostResult(
                    success=False,
                    platform="instagram",
                    error_message=publish_data["error"]["message"],
                )

            post_id = publish_data.get("id", "")
            self.log.info(f"Posted to Instagram: {post_id}")

            return PostResult(
                success=True,
                platform="instagram",
                platform_post_id=post_id,
                platform_url=f"https://instagram.com/p/{post_id}",
            )

        except requests.RequestException as e:
            return PostResult(
                success=False,
                platform="instagram",
                error_message=str(e),
            )

