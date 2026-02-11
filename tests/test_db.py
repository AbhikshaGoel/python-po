# test_db.py
"""
Database tests.
Tests all CRUD operations and data integrity.
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Override DB path before importing db module
_test_db = tempfile.mktemp(suffix=".db")


@pytest.fixture(autouse=True)
def setup_test_db():
    """Use a temporary database for each test."""
    with patch("config.DB_PATH", Path(_test_db)):
        with patch("config.ENABLED_PLATFORMS", ["facebook", "twitter"]):
            import db
            db.init_db()
            yield db
    # Cleanup
    if os.path.exists(_test_db):
        os.unlink(_test_db)


class TestDatabaseInit:
    def test_tables_created(self, setup_test_db):
        db = setup_test_db
        with db.get_connection() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t["name"] for t in tables]
            assert "posts" in table_names
            assert "platform_posts" in table_names
            assert "audit_log" in table_names

    def test_init_idempotent(self, setup_test_db):
        """Calling init_db multiple times should not fail."""
        db = setup_test_db
        db.init_db()
        db.init_db()
        # Should not raise


class TestPostCRUD:
    def test_create_post(self, setup_test_db):
        db = setup_test_db
        post_id = db.create_post(
            topic="Test Topic",
            summary="Test Summary",
            full_content="Full content here",
            link="https://example.com",
            image_url="https://example.com/img.jpg",
        )
        assert post_id > 0

    def test_create_post_creates_platform_entries(self, setup_test_db):
        db = setup_test_db
        post_id = db.create_post(
            topic="Test",
            summary="Summary",
        )
        statuses = db.get_platform_statuses(post_id)
        assert len(statuses) == 2  # facebook, twitter
        for s in statuses:
            assert s["status"] == "pending"

    def test_get_post(self, setup_test_db):
        db = setup_test_db
        post_id = db.create_post(
            topic="My Topic",
            summary="My Summary",
            link="https://example.com",
        )
        post = db.get_post(post_id)
        assert post is not None
        assert post["topic"] == "My Topic"
        assert post["summary"] == "My Summary"
        assert post["status"] == "pending"

    def test_get_nonexistent_post(self, setup_test_db):
        db = setup_test_db
        post = db.get_post(99999)
        assert post is None

    def test_update_post_status(self, setup_test_db):
        db = setup_test_db
        post_id = db.create_post(topic="Test", summary="Sum")

        db.update_post_status(
            post_id,
            status="approved",
            approved_by="admin",
            approval_type="manual",
        )

        post = db.get_post(post_id)
        assert post["status"] == "approved"
        assert post["approved_by"] == "admin"
        assert post["approval_type"] == "manual"
        assert post["approved_at"] is not None

    def test_update_platform_status(self, setup_test_db):
        db = setup_test_db
        post_id = db.create_post(topic="Test", summary="Sum")

        db.update_platform_status(
            post_id,
            "facebook",
            "published",
            platform_post_id="fb_123",
            platform_url="https://facebook.com/post/123",
        )

        statuses = db.get_platform_statuses(post_id)
        fb = [s for s in statuses if s["platform"] == "facebook"][0]
        assert fb["status"] == "published"
        assert fb["platform_post_id"] == "fb_123"
        assert fb["posted_at"] is not None

    def test_platform_failure_tracking(self, setup_test_db):
        db = setup_test_db
        post_id = db.create_post(topic="Test", summary="Sum")

        db.update_platform_status(
            post_id,
            "twitter",
            "failed",
            error_message="Rate limited",
        )

        statuses = db.get_platform_statuses(post_id)
        tw = [s for s in statuses if s["platform"] == "twitter"][0]
        assert tw["status"] == "failed"
        assert tw["error_message"] == "Rate limited"
        assert tw["retry_count"] == 1


class TestPostQueries:
    def test_get_pending_posts(self, setup_test_db):
        db = setup_test_db

        # Create posts with different statuses
        p1 = db.create_post(topic="Pending", summary="Sum")
        p2 = db.create_post(topic="Approved", summary="Sum")
        p3 = db.create_post(topic="Also Pending", summary="Sum")

        db.update_post_status(p2, "approved", approval_type="manual")

        pending = db.get_pending_posts()
        assert len(pending) == 1
        assert pending[0]["id"] == p2

    def test_priority_ordering(self, setup_test_db):
        db = setup_test_db

        p1 = db.create_post(topic="Low", summary="S", priority="low")
        p2 = db.create_post(topic="High", summary="S", priority="high")
        p3 = db.create_post(topic="Normal", summary="S", priority="normal")

        # Approve all
        for pid in [p1, p2, p3]:
            db.update_post_status(pid, "approved", approval_type="manual")

        pending = db.get_pending_posts()
        assert pending[0]["topic"] == "High"
        assert pending[1]["topic"] == "Normal"
        assert pending[2]["topic"] == "Low"

    def test_get_recent_posts(self, setup_test_db):
        db = setup_test_db

        for i in range(5):
            db.create_post(topic=f"Post {i}", summary=f"Summary {i}")

        recent = db.get_recent_posts(limit=3)
        assert len(recent) == 3
        # Should have platform info
        assert "platforms" in recent[0]

    def test_get_stats(self, setup_test_db):
        db = setup_test_db

        db.create_post(topic="A", summary="S")
        p2 = db.create_post(topic="B", summary="S")
        db.update_post_status(p2, "completed")

        stats = db.get_stats()
        assert stats["total_posts"] == 2
        assert stats["by_status"]["pending"] == 1
        assert stats["by_status"]["completed"] == 1


class TestAuditLog:
    def test_audit_log_on_create(self, setup_test_db):
        db = setup_test_db
        post_id = db.create_post(topic="Test", summary="Sum")

        log = db.get_audit_log(post_id)
        assert len(log) >= 1
        assert log[0]["action"] == "created"

    def test_audit_log_on_approve(self, setup_test_db):
        db = setup_test_db
        post_id = db.create_post(topic="Test", summary="Sum")

        db.update_post_status(
            post_id,
            "approved",
            approved_by="admin",
            approval_type="manual",
        )

        log = db.get_audit_log(post_id)
        assert len(log) >= 2
        actions = [l["action"] for l in log]
        assert "created" in actions
        assert "approved" in actions
