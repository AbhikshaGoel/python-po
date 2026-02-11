# youtube.py
"""
YouTube Community Post via Data API v3.
Note: Community posts API is limited. This posts text with optional image.
Video uploads are manual.
"""

import requests

import config
from platforms.base import BasePlatform, PostResult


class YouTubePlatform(BasePlatform):
    """YouTube poster. Community posts only (videos are manual)."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(self):
        super().__init__("youtube")
        self._access_token = None

    def _refresh_access_token(self) -> bool:
        """Refresh OAuth2 access token using refresh token."""
        try:
            resp = requests.post(
                self.TOKEN_URL,
                data={
                    "client_id": config.YOUTUBE_CLIENT_ID,
                    "client_secret": config.YOUTUBE_CLIENT_SECRET,
                    "refresh_token": config.YOUTUBE_REFRESH_TOKEN,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )
            data = resp.json()
            if "access_token" in data:
                self._access_token = data["access_token"]
                return True
            self.log.error(f"YouTube token refresh failed: {data}")
            return False
        except requests.RequestException as e:
            self.log.error(f"YouTube token refresh error: {e}")
            return False

    def validate_credentials(self) -> bool:
        """Verify YouTube credentials by refreshing token."""
        if self._refresh_access_token():
            try:
                resp = requests.get(
                    f"{self.API_BASE}/channels",
                    params={
                        "part": "snippet",
                        "mine": "true",
                    },
                    headers={
                        "Authorization": f"Bearer {self._access_token}"
                    },
                    timeout=10,
                )
                data = resp.json()
                items = data.get("items", [])
                if items:
                    name = items[0]["snippet"]["title"]
                    self.log.info(f"YouTube authenticated as: {name}")
                    return True
            except requests.RequestException as e:
                self.log.error(f"YouTube validation error: {e}")
        return False

    def post_text(self, text: str, link: str = "") -> PostResult:
        """
        Post a community post to YouTube.
        NOTE: YouTube Community Posts API has limited availability.
        This is a best-effort implementation.
        """
        try:
            if not self._access_token:
                if not self._refresh_access_token():
                    return PostResult(
                        success=False,
                        platform="youtube",
                        error_message="Failed to refresh access token",
                    )

            post_text = text
            if link:
                post_text = f"{text}\n\n{link}"

            if config.DRY_RUN:
                self.log.info(
                    f"[DRY RUN] Would post to YouTube: {text[:80]}"
                )
                return PostResult(
                    success=True,
                    platform="youtube",
                    platform_post_id="dry_run",
                )

            # Community posts API (activities.insert is deprecated)
            # Using the newer approach
            self.log.warning(
                "YouTube Community Posts API has limited support. "
                "Consider posting manually for now."
            )

            return PostResult(
                success=False,
                platform="youtube",
                error_message=(
                    "YouTube Community Posts API not fully supported. "
                    "Post manually."
                ),
            )

        except Exception as e:
            return PostResult(
                success=False,
                platform="youtube",
                error_message=str(e),
            )

    def post_image(
        self, text: str, image_path: str, link: str = ""
    ) -> PostResult:
        """YouTube community post with image. Same limitations apply."""
        return self.post_text(text, link)
