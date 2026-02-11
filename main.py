"""
ENTRY POINT - Run this to start everything.

Usage:
    python main.py              # Start the service
    python main.py --test       # Run tests
    python main.py --status     # Show current status
    python main.py --dry-run    # Process without actually posting
"""

import sys
import time
import signal
import hmac
import hashlib
import threading
from flask import Flask, request, jsonify

import config
import db
from poster import Poster
from scheduler import Scheduler
from logger import get_logger, setup_logging

setup_logging()
log = get_logger("main")

# Flask app for webhook
app = Flask(__name__)
poster: Poster = None


# ── Webhook API ────────────────────────────────────────


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify HMAC signature of incoming webhook."""
    expected = hmac.new(
        config.WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    stats = db.get_stats()
    return jsonify({
        "status": "ok",
        "platforms": config.ENABLED_PLATFORMS,
        "stats": stats,
    })


@app.route("/v1/content", methods=["POST"])
def receive_content():
    """
    Webhook endpoint to receive new content.
    
    Headers:
        X-Signature: HMAC-SHA256 signature of request body
    
    Body (JSON):
        topic: str (required)
        summary: str (required)
        full_content: str (optional)
        link: str (optional)
        image_url: str (optional)
        video_url: str (optional)
        priority: str (optional, default: normal)
        tags: list[str] (optional)
    """
    # Verify signature
    signature = request.headers.get("X-Signature", "")
    if not verify_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 401

    # Parse body
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    # Validate required fields
    if not data.get("topic") or not data.get("summary"):
        return jsonify({"error": "topic and summary are required"}), 400

    # Process
    try:
        post_id = poster.process_incoming(
            topic=data["topic"],
            summary=data["summary"],
            full_content=data.get("full_content", ""),
            link=data.get("link", ""),
            image_url=data.get("image_url", ""),
            video_url=data.get("video_url", ""),
            priority=data.get("priority", "normal"),
            source="webhook",
            tags=data.get("tags"),
        )

        return jsonify({
            "status": "accepted",
            "post_id": post_id,
            "message": "Post created and sent for approval",
        }), 202

    except Exception as e:
        log.error(f"Webhook processing error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/v1/posts", methods=["GET"])
def list_posts():
    """List recent posts and their statuses."""
    signature = request.headers.get("X-Signature", "")
    if not verify_signature(b"GET /v1/posts", signature):
        return jsonify({"error": "Invalid signature"}), 401

    posts = db.get_recent_posts(limit=20)
    return jsonify({"posts": posts})


@app.route("/v1/stats", methods=["GET"])
def get_stats():
    """Get posting statistics."""
    stats = db.get_stats()
    return jsonify(stats)


# ── Main Entry Point ──────────────────────────────────


def run_service():
    """Start all services."""
    global poster

    config.print_status()

    problems = config.validate()
    if problems:
        for p in problems:
            log.error(f"Config problem: {p}")
        if any("missing" in p.lower() for p in problems):
            log.error("Fix configuration issues before starting")
            sys.exit(1)

    # Initialize database
    db.init_db()
    log.info("Database initialized")

    # Create poster
    poster = Poster()
    if not poster.start():
        log.error("Failed to start poster service")
        sys.exit(1)

    # Create and start scheduler
    sched = Scheduler(poster)
    sched.start()

    # Handle shutdown
    def shutdown(sig, frame):
        log.info("Shutting down...")
        sched.stop()
        poster.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start webhook server in a thread
    log.info(f"Starting webhook server on port {config.WEBHOOK_PORT}")
    server_thread = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=config.WEBHOOK_PORT,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    )
    server_thread.start()

    log.info("=" * 50)
    log.info("Social Poster is running!")
    log.info(f"Webhook: http://localhost:{config.WEBHOOK_PORT}/v1/content")
    log.info(f"Health:  http://localhost:{config.WEBHOOK_PORT}/health")
    log.info("=" * 50)

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown(None, None)


def show_status():
    """Show current system status."""
    db.init_db()
    config.print_status()

    print("\n📊 Database Stats:")
    stats = db.get_stats()
    print(f"  Total posts: {stats['total_posts']}")

    for status, count in stats.get("by_status", {}).items():
        print(f"  {status}: {count}")

    print("\n📡 Platform Stats:")
    for platform, statuses in stats.get("by_platform", {}).items():
        print(f"  {platform}:")
        for status, count in statuses.items():
            print(f"    {status}: {count}")

    print("\n📋 Recent Posts:")
    recent = db.get_recent_posts(limit=5)
    for post in recent:
        print(
            f"  #{post['id']} [{post['status']}] "
            f"{post['topic'][:50]} "
            f"({post['created_at'][:16]})"
        )
        for p in post.get("platforms", []):
            emoji = "✅" if p["status"] == "published" else "⏳" if p["status"] == "pending" else "❌"
            print(f"    {emoji} {p['platform']}: {p['status']}")


if __name__ == "__main__":
    if "--test" in sys.argv:
        # Run tests
        import pytest
        sys.exit(pytest.main(["-v", "tests/"]))

    elif "--status" in sys.argv:
        show_status()

    elif "--dry-run" in sys.argv:
        config.DRY_RUN = True
        log.info("DRY RUN MODE - no actual posting will occur")
        run_service()

    else:
        run_service()
