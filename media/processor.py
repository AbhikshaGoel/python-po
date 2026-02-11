# processor.py
"""
Simple image processor.
Resize and format images for each platform.
Videos/Reels are posted manually - we just handle images.
"""

import hashlib
import requests
from pathlib import Path
from typing import Optional
from PIL import Image
from io import BytesIO

import config
from logger import get_logger

log = get_logger(__name__)

# Platform image specs
PLATFORM_SPECS = {
    "twitter": {
        "max_width": 1200,
        "max_height": 675,
        "aspect_ratio": (16, 9),
        "max_size_mb": 5,
        "format": "JPEG",
    },
    "facebook": {
        "max_width": 1200,
        "max_height": 630,
        "aspect_ratio": (1.91, 1),
        "max_size_mb": 10,
        "format": "JPEG",
    },
    "instagram": {
        "max_width": 1080,
        "max_height": 1080,
        "aspect_ratio": (1, 1),
        "max_size_mb": 8,
        "format": "JPEG",
    },
    "youtube": {
        "max_width": 1280,
        "max_height": 720,
        "aspect_ratio": (16, 9),
        "max_size_mb": 2,
        "format": "JPEG",
    },
    "linkedin": {
        "max_width": 1200,
        "max_height": 627,
        "aspect_ratio": (1.91, 1),
        "max_size_mb": 5,
        "format": "JPEG",
    },
}


def download_image(url: str) -> Optional[bytes]:
    """Download an image from URL. Returns bytes or None."""
    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        # Check content type
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type:
            log.warning(f"URL is not an image: {content_type}")
            return None

        # Read up to 15MB
        max_bytes = 15 * 1024 * 1024
        data = resp.content
        if len(data) > max_bytes:
            log.warning(f"Image too large: {len(data)} bytes")
            return None

        return data

    except requests.RequestException as e:
        log.error(f"Failed to download image: {e}")
        return None


def process_for_platform(
    image_data: bytes, platform: str
) -> Optional[Path]:
    """
    Resize and format image for a specific platform.
    Returns path to processed file, or None on failure.
    """
    if platform not in PLATFORM_SPECS:
        log.warning(f"Unknown platform: {platform}")
        return None

    spec = PLATFORM_SPECS[platform]

    try:
        img = Image.open(BytesIO(image_data))

        # Convert to RGB if necessary (handles PNG with alpha, etc.)
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Resize maintaining aspect ratio
        max_w = spec["max_width"]
        max_h = spec["max_height"]
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

        # Generate filename based on content hash
        img_hash = hashlib.md5(image_data[:1024]).hexdigest()[:12]
        filename = f"{platform}_{img_hash}.jpg"
        output_path = config.MEDIA_CACHE_DIR / filename

        # Save with quality adjustment to meet size limits
        quality = 90
        max_bytes = spec["max_size_mb"] * 1024 * 1024

        while quality > 30:
            buffer = BytesIO()
            img.save(buffer, format=spec["format"], quality=quality)
            if buffer.tell() <= max_bytes:
                break
            quality -= 10

        img.save(output_path, format=spec["format"], quality=quality)
        log.info(
            f"Processed image for {platform}: "
            f"{img.size[0]}x{img.size[1]}, "
            f"{output_path.stat().st_size // 1024}KB"
        )
        return output_path

    except Exception as e:
        log.error(f"Failed to process image for {platform}: {e}")
        return None


def process_for_all_platforms(
    image_url: str,
) -> dict[str, Optional[Path]]:
    """
    Download and process image for all enabled platforms.
    Returns {platform: file_path} dict.
    """
    results = {}

    image_data = download_image(image_url)
    if not image_data:
        log.error(f"Could not download image: {image_url}")
        return {p: None for p in config.ENABLED_PLATFORMS}

    for platform in config.ENABLED_PLATFORMS:
        results[platform] = process_for_platform(image_data, platform)

    return results


def cleanup_cache(max_age_hours: int = 24):
    """Delete processed images older than max_age_hours."""
    import time

    cutoff = time.time() - (max_age_hours * 3600)
    count = 0

    for file in config.MEDIA_CACHE_DIR.iterdir():
        if file.is_file() and file.stat().st_mtime < cutoff:
            file.unlink()
            count += 1

    if count:
        log.info(f"Cleaned up {count} cached media files")
