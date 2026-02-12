"""
Platform registry.
Automatically loads only the platforms that have credentials configured.
"""

from typing import Optional
import config
from platforms.base import BasePlatform

# Import all platform classes
from platforms.facebook import FacebookPlatform
from platforms.twitter import TwitterPlatform
from platforms.instagram import InstagramPlatform
from platforms.youtube import YouTubePlatform


# Registry mapping name → class
_REGISTRY: dict[str, type[BasePlatform]] = {
    "facebook": FacebookPlatform,
    "twitter": TwitterPlatform,
    "instagram": InstagramPlatform,
    "youtube": YouTubePlatform,

}

# Cached instances
_instances: dict[str, BasePlatform] = {}


def get_platform(name: str) -> Optional[BasePlatform]:
    """Get a platform instance by name. Returns None if not enabled."""
    if name not in config.ENABLED_PLATFORMS:
        return None

    if name not in _instances:
        cls = _REGISTRY.get(name)
        if cls:
            _instances[name] = cls()

    return _instances.get(name)


def get_all_enabled() -> dict[str, BasePlatform]:
    """Get all enabled platform instances."""
    result = {}
    for name in config.ENABLED_PLATFORMS:
        platform = get_platform(name)
        if platform:
            result[name] = platform
    return result


def validate_all() -> dict[str, bool]:
    """Validate credentials for all enabled platforms."""
    results = {}
    for name, platform in get_all_enabled().items():
        results[name] = platform.validate_credentials()
    return results
