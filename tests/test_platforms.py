# test_platforms.py
"""
Platform connectivity tests.
Tests that credentials work and APIs are reachable.
Doesn't actually post anything.
"""

import pytest
from unittest.mock import patch, MagicMock

import config


class TestFacebookPlatform:
    def test_init(self):
        from platforms.facebook import FacebookPlatform
        fb = FacebookPlatform()
        assert fb.name == "facebook"

    @patch("platforms.facebook.requests.get")
    def test_validate_success(self, mock_get):
        mock_get.return_value = MagicMock(
            json=lambda: {"name": "Test Page", "id": "123"}
        )
        from platforms.facebook import FacebookPlatform
        fb = FacebookPlatform()
        assert fb.validate_credentials() is True

    @patch("platforms.facebook.requests.get")
    def test_validate_failure(self, mock_get):
        mock_get.return_value = MagicMock(
            json=lambda: {"error": {"message": "Invalid token"}}
        )
        from platforms.facebook import FacebookPlatform
        fb = FacebookPlatform()
        assert fb.validate_credentials() is False

    @patch("platforms.facebook.requests.post")
    def test_post_text_dry_run(self, mock_post):
        with patch.object(config, "DRY_RUN", True):
            from platforms.facebook import FacebookPlatform
            fb = FacebookPlatform()
            result = fb.post_text("Hello world")
            assert result.success is True
            assert result.platform_post_id == "dry_run"
            mock_post.assert_not_called()

    @patch("platforms.facebook.requests.post")
    def test_post_text_success(self, mock_post):
        mock_post.return_value = MagicMock(
            json=lambda: {"id": "123_456"}
        )
        with patch.object(config, "DRY_RUN", False):
            from platforms.facebook import FacebookPlatform
            fb = FacebookPlatform()
            result = fb.post_text("Test post")
            assert result.success is True
            assert result.platform_post_id == "123_456"

    @patch("platforms.facebook.requests.post")
    def test_post_text_api_error(self, mock_post):
        mock_post.return_value = MagicMock(
            json=lambda: {"error": {"message": "Rate limited"}}
        )
        with patch.object(config, "DRY_RUN", False):
            from platforms.facebook import FacebookPlatform
            fb = FacebookPlatform()
            result = fb.post_text("Test post")
            assert result.success is False
            assert "Rate limited" in result.error_message


class TestTwitterPlatform:
    def test_init(self):
        with patch("platforms.twitter.tweepy.Client"):
            with patch("platforms.twitter.tweepy.OAuth1UserHandler"):
                with patch("platforms.twitter.tweepy.API"):
                    from platforms.twitter import TwitterPlatform
                    tw = TwitterPlatform()
                    assert tw.name == "twitter"

    def test_truncate_short_text(self):
        with patch("platforms.twitter.tweepy.Client"):
            with patch("platforms.twitter.tweepy.OAuth1UserHandler"):
                with patch("platforms.twitter.tweepy.API"):
                    from platforms.twitter import TwitterPlatform
                    tw = TwitterPlatform()
                    result = tw._truncate("Short text")
                    assert result == "Short text"

    def test_truncate_long_text(self):
        with patch("platforms.twitter.tweepy.Client"):
            with patch("platforms.twitter.tweepy.OAuth1UserHandler"):
                with patch("platforms.twitter.tweepy.API"):
                    from platforms.twitter import TwitterPlatform
                    tw = TwitterPlatform()
                    long_text = "a" * 300
                    result = tw._truncate(long_text)
                    assert len(result) <= 280
                    assert result.endswith("...")

    def test_truncate_with_link(self):
        with patch("platforms.twitter.tweepy.Client"):
            with patch("platforms.twitter.tweepy.OAuth1UserHandler"):
                with patch("platforms.twitter.tweepy.API"):
                    from platforms.twitter import TwitterPlatform
                    tw = TwitterPlatform()
                    result = tw._truncate("Test", "https://example.com")
                    assert "https://example.com" in result


class TestInstagramPlatform:
    def test_text_only_fails(self):
        from platforms.instagram import InstagramPlatform
        ig = InstagramPlatform()
        result = ig.post_text("No images on Instagram")
        assert result.success is False

    def test_local_file_rejected(self):
        with patch.object(config, "DRY_RUN", False):
            from platforms.instagram import InstagramPlatform
            ig = InstagramPlatform()
            result = ig.post_image("Caption", "/local/path/img.jpg")
            assert result.success is False
            assert "public URL" in result.error_message


class TestLinkedInPlatform:
    @patch("platforms.linkedin.requests.get")
    def test_validate_success(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "localizedFirstName": "John",
                "localizedLastName": "Doe",
            },
        )
        from platforms.linkedin import LinkedInPlatform
        li = LinkedInPlatform()
        assert li.validate_credentials() is True

    @patch("platforms.linkedin.requests.get")
    def test_validate_failure(self, mock_get):
        mock_get.return_value = MagicMock(status_code=401)
        from platforms.linkedin import LinkedInPlatform
        li = LinkedInPlatform()
        assert li.validate_credentials() is False


class TestPlatformRegistry:
    def test_get_enabled_platforms(self):
        with patch.object(config, "ENABLED_PLATFORMS", ["facebook", "twitter"]):
            import platforms
