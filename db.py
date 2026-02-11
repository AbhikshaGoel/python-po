"""
SQLite database manager.
Zero config. File-based. Portable.
Just copy posts.db to move all your data.
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

import config


def _now() -> str:
    """Current UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection():
    """Get a database connection with auto-commit/rollback."""
    conn = sqlite3.connect(str(config.DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""

        -- Main posts table
        CREATE TABLE IF NOT EXISTS posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            topic           TEXT NOT NULL,
            summary         TEXT NOT NULL,
            full_content    TEXT,
            link            TEXT,
            image_url       TEXT,
            video_url       TEXT,

            -- Processing state
            status          TEXT NOT NULL DEFAULT 'pending',
            -- pending → approved → posting → completed
            -- pending → rejected
            -- pending → auto_approved → posting → completed
            -- posting → partial_failure
            -- posting → failed

            priority        TEXT NOT NULL DEFAULT 'normal',
            -- normal, high, low

            -- Approval tracking
            approved_by     TEXT,
            approved_at     TEXT,
            approval_type   TEXT,
            -- manual, auto, timeout
            rejection_reason TEXT,

            -- Metadata
            source          TEXT DEFAULT 'webhook',
            -- webhook, manual, scheduled
            tags            TEXT,
            -- JSON array: ["tech", "news"]

            -- Timestamps
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            scheduled_for   TEXT,
            -- If set, don't post before this time
            completed_at    TEXT,

            -- Error tracking
            error_message   TEXT,
            retry_count     INTEGER DEFAULT 0
        );

        -- Per-platform posting status
        CREATE TABLE IF NOT EXISTS platform_posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id         INTEGER NOT NULL,
            platform        TEXT NOT NULL,
            -- facebook, instagram, twitter, youtube, linkedin

            status          TEXT NOT NULL DEFAULT 'pending',
            -- pending, posting, published, failed, skipped

            platform_post_id TEXT,
            -- The ID returned by the platform after posting
            platform_url    TEXT,
            -- Direct link to the published post

            posted_at       TEXT,
            error_message   TEXT,
            retry_count     INTEGER DEFAULT 0,
            
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,

            FOREIGN KEY (post_id) REFERENCES posts(id)
        );

        -- Audit log for everything that happens
        CREATE TABLE IF NOT EXISTS audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id         INTEGER,
            action          TEXT NOT NULL,
            -- created, approved, rejected, posted, failed, retried
            details         TEXT,
            -- JSON with extra context
            timestamp       TEXT NOT NULL,

            FOREIGN KEY (post_id) REFERENCES posts(id)
        );

        -- Indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_posts_status
            ON posts(status);
        CREATE INDEX IF NOT EXISTS idx_posts_created
            ON posts(created_at);
        CREATE INDEX IF NOT EXISTS idx_posts_scheduled
            ON posts(scheduled_for);
        CREATE INDEX IF NOT EXISTS idx_platform_posts_post_id
            ON platform_posts(post_id);
        CREATE INDEX IF NOT EXISTS idx_platform_posts_status
            ON platform_posts(status);
        CREATE INDEX IF NOT EXISTS idx_audit_post_id
            ON audit_log(post_id);

        """)


# ── Post CRUD ──────────────────────────────────────────


def create_post(
    topic: str,
    summary: str,
    full_content: str = "",
    link: str = "",
    image_url: str = "",
    video_url: str = "",
    priority: str = "normal",
    source: str = "webhook",
    tags: list[str] | None = None,
    scheduled_for: str | None = None,
) -> int:
    """Create a new post. Returns the post ID."""
    now = _now()
    tags_json = json.dumps(tags or [])

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO posts
                (topic, summary, full_content, link, image_url, video_url,
                 status, priority, source, tags, scheduled_for,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
            """,
            (
                topic, summary, full_content, link, image_url, video_url,
                priority, source, tags_json, scheduled_for, now, now,
            ),
        )
        post_id = cursor.lastrowid

        # Create platform_posts entries for each enabled platform
        for platform in config.ENABLED_PLATFORMS:
            conn.execute(
                """
                INSERT INTO platform_posts
                    (post_id, platform, status, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?)
                """,
                (post_id, platform, now, now),
            )

        # Audit log
        conn.execute(
            """
            INSERT INTO audit_log (post_id, action, details, timestamp)
            VALUES (?, 'created', ?, ?)
            """,
            (
                post_id,
                json.dumps({
                    "source": source,
                    "platforms": config.ENABLED_PLATFORMS,
                    "priority": priority,
                }),
                now,
            ),
        )

    return post_id


def get_post(post_id: int) -> Optional[dict]:
    """Get a single post by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
        if row:
            return dict(row)
    return None


def get_pending_posts() -> list[dict]:
    """Get all posts waiting to be processed."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM posts
            WHERE status IN ('approved', 'auto_approved')
            AND (scheduled_for IS NULL OR scheduled_for <= ?)
            ORDER BY
                CASE priority
                    WHEN 'high' THEN 1
                    WHEN 'normal' THEN 2
                    WHEN 'low' THEN 3
                END,
                created_at ASC
            """,
            (_now(),),
        ).fetchall()
        return [dict(r) for r in rows]


def get_posts_needing_approval() -> list[dict]:
    """Get posts waiting for approval."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM posts
            WHERE status = 'pending'
            ORDER BY created_at ASC
            """,
        ).fetchall()
        return [dict(r) for r in rows]


def update_post_status(
    post_id: int,
    status: str,
    approved_by: str = None,
    approval_type: str = None,
    rejection_reason: str = None,
    error_message: str = None,
):
    """Update post status and related fields."""
    now = _now()
    with get_connection() as conn:
        fields = ["status = ?", "updated_at = ?"]
        values = [status, now]

        if approved_by:
            fields.append("approved_by = ?")
            values.append(approved_by)

        if approval_type:
            fields.append("approval_type = ?")
            values.append(approval_type)
            fields.append("approved_at = ?")
            values.append(now)

        if rejection_reason:
            fields.append("rejection_reason = ?")
            values.append(rejection_reason)

        if error_message:
            fields.append("error_message = ?")
            values.append(error_message)

        if status in ("completed", "partial_failure"):
            fields.append("completed_at = ?")
            values.append(now)

        values.append(post_id)

        conn.execute(
            f"UPDATE posts SET {', '.join(fields)} WHERE id = ?",
            values,
        )

        # Audit
        conn.execute(
            """
            INSERT INTO audit_log (post_id, action, details, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (
                post_id,
                status,
                json.dumps({
                    "approved_by": approved_by,
                    "approval_type": approval_type,
                    "rejection_reason": rejection_reason,
                }),
                now,
            ),
        )


def update_platform_status(
    post_id: int,
    platform: str,
    status: str,
    platform_post_id: str = None,
    platform_url: str = None,
    error_message: str = None,
):
    """Update the posting status for a specific platform."""
    now = _now()
    with get_connection() as conn:
        fields = ["status = ?", "updated_at = ?"]
        values = [status, now]

        if platform_post_id:
            fields.append("platform_post_id = ?")
            values.append(platform_post_id)

        if platform_url:
            fields.append("platform_url = ?")
            values.append(platform_url)

        if status == "published":
            fields.append("posted_at = ?")
            values.append(now)

        if error_message:
            fields.append("error_message = ?")
            values.append(error_message)
            fields.append("retry_count = retry_count + 1")

        values.extend([post_id, platform])

        conn.execute(
            f"""UPDATE platform_posts
                SET {', '.join(fields)}
                WHERE post_id = ? AND platform = ?""",
            values,
        )

        # Audit
        conn.execute(
            """
            INSERT INTO audit_log (post_id, action, details, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (
                post_id,
                f"platform_{status}",
                json.dumps({
                    "platform": platform,
                    "platform_post_id": platform_post_id,
                    "error": error_message,
                }),
                now,
            ),
        )


def get_platform_statuses(post_id: int) -> list[dict]:
    """Get all platform posting statuses for a post."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM platform_posts WHERE post_id = ?",
            (post_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_audit_log(post_id: int) -> list[dict]:
    """Get complete audit trail for a post."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM audit_log
            WHERE post_id = ?
            ORDER BY timestamp ASC
            """,
            (post_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_posts(limit: int = 20) -> list[dict]:
    """Get most recent posts with their platform statuses."""
    with get_connection() as conn:
        posts = conn.execute(
            "SELECT * FROM posts ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        result = []
        for post in posts:
            post_dict = dict(post)
            platforms = conn.execute(
                "SELECT * FROM platform_posts WHERE post_id = ?",
                (post_dict["id"],),
            ).fetchall()
            post_dict["platforms"] = [dict(p) for p in platforms]
            result.append(post_dict)

        return result


def get_stats() -> dict:
    """Get overall statistics."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

        status_counts = {}
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM posts GROUP BY status"
        ).fetchall()
        for row in rows:
            status_counts[row["status"]] = row["cnt"]

        platform_stats = {}
        rows = conn.execute(
            """
            SELECT platform, status, COUNT(*) as cnt
            FROM platform_posts
            GROUP BY platform, status
            """
        ).fetchall()
        for row in rows:
            plat = row["platform"]
            if plat not in platform_stats:
                platform_stats[plat] = {}
            platform_stats[plat][row["status"]] = row["cnt"]

        return {
            "total_posts": total,
            "by_status": status_counts,
            "by_platform": platform_stats,
        }
