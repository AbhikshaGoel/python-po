# base.py
"""
Base class for all platform workers.
Every platform must implement these methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from logger import get_logger


@dataclass
class PostResult:
    """Result of a platform posting attempt."""
    success: bool
    platform: str
    platform_post_id: Optional[str] = None
    platform_url: Optional[str] = None
    error_message: Optional[str] = None


class BasePlatform(ABC):
    """
    Base class for all social media platforms.
    
    To add a new platform:
    1. Create a new file in platforms/
    2. Extend this class
    3. Implement post_text() and post_image()
    4. Add credentials to config.py
    5. Register in platforms/__init__.py
    """

    def __init__(self, name: str):
        self.name = name
        self.log = get_logger(f"platform.{name}")

    @abstractmethod
    def validate_credentials(self) -> bool:
        """Check if credentials are valid. Returns True/False."""
        pass

    @abstractmethod
    def post_text(self, text: str, link: str = "") -> PostResult:
        """Post text-only content. Returns PostResult."""
        pass

    @abstractmethod
    def post_image(
        self,
        text: str,
        image_path: str,
        link: str = "",
    ) -> PostResult:
        """Post text with an image. Returns PostResult."""
        pass

    def post(
        self,
        text: str,
        image_path: str = None,
        link: str = "",
    ) -> PostResult:
        """
        Post content. Automatically chooses text or image posting.
        This is the main method callers should use.
        """
        try:
            if image_path:
                return self.post_image(text, image_path, link)
            else:
                return self.post_text(text, link)
        except Exception as e:
            self.log.error(f"Unexpected error posting to {self.name}: {e}")
            return PostResult(
                success=False,
                platform=self.name,
                error_message=str(e),
            )
