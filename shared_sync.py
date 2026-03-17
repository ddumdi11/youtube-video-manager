"""
Integration with yt-shared-data: sync video/channel data to the shared database.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

try:
    from yt_shared import SharedDatabase, Channel, Video, DataGap
    SHARED_AVAILABLE = True
except ImportError:
    SHARED_AVAILABLE = False

logger = logging.getLogger(__name__)

PROJECT_NAME = "video-manager"


def is_available() -> bool:
    """Check if the shared data layer is installed."""
    return SHARED_AVAILABLE


def sync_videos(videos: Sequence[Any]) -> int:
    """Sync VideoRecord objects to the shared database.

    Args:
        videos: List of VideoRecord objects (from yt_database).

    Returns:
        Number of videos synced.
    """
    if not SHARED_AVAILABLE:
        return 0

    db = SharedDatabase(project_name=PROJECT_NAME)
    count = 0

    with db.connect() as conn:
        for v in videos:
            video_id = getattr(v, "video_id", None)
            if not video_id:
                continue

            db.upsert_video(conn, Video(
                youtube_video_id=video_id,
                title=getattr(v, "title", ""),
                youtube_channel_id=getattr(v, "youtube_channel_id", None),
                published_at=getattr(v, "published_date", None),
                duration=getattr(v, "duration", None),
                view_count=getattr(v, "views_count", None),
                thumbnail_url=getattr(v, "thumbnail_url", None),
                video_type=getattr(v, "video_type", "video"),
            ))
            count += 1

    logger.info(f"Synced {count} videos to shared DB")
    return count


def get_channel_details(channel_name: str) -> Optional[dict[str, Any]]:
    """Look up enriched channel details from the shared DB.

    The video-manager stores channel names, not IDs. This searches
    the shared DB for a matching channel by title and returns
    enriched metadata (subscribers, views, etc.) if available.

    Args:
        channel_name: Channel name as stored in video-manager.

    Returns:
        Dict with channel details or None.
    """
    if not SHARED_AVAILABLE or not channel_name:
        return None

    db = SharedDatabase(project_name=PROJECT_NAME)

    with db.connect() as conn:
        # Search by title (case-insensitive)
        row = conn.execute(
            "SELECT * FROM channels WHERE LOWER(title) = LOWER(?)",
            (channel_name,)
        ).fetchone()

        if not row:
            return None

        return {
            "youtube_channel_id": row["youtube_channel_id"],
            "title": row["title"],
            "subscriber_count": row["subscriber_count"],
            "video_count": row["video_count"],
            "view_count": row["view_count"],
            "custom_url": row["custom_url"],
            "last_fetched_at": row["last_fetched_at"],
        }


def acquire_lock_with_warning() -> bool:
    """Acquire the shared DB lock and log if another project holds it.

    Returns:
        True if lock was acquired, False if another project holds it.
    """
    if not SHARED_AVAILABLE:
        return False

    db = SharedDatabase(project_name=PROJECT_NAME)
    existing = db.acquire_lock()
    if existing:
        logger.warning(
            f"Shared DB wird gerade von '{existing.project_name}' genutzt "
            f"(PID {existing.pid}, seit {existing.started_at})"
        )
        return False
    return True


def release_lock() -> None:
    """Release our lock on the shared DB."""
    if not SHARED_AVAILABLE:
        return
    db = SharedDatabase(project_name=PROJECT_NAME)
    db.release_lock()


def detect_gaps() -> list[Any]:
    """Detect data gaps that other tools could fill.

    Returns:
        List of DataGap objects (or empty list if not available).
    """
    if not SHARED_AVAILABLE:
        return []

    db = SharedDatabase(project_name=PROJECT_NAME)
    with db.connect() as conn:
        return db.detect_gaps(conn)


def get_stats() -> Optional[dict[str, Any]]:
    """Get shared DB statistics.

    Returns:
        Dict with channel/video counts or None.
    """
    if not SHARED_AVAILABLE:
        return None

    db = SharedDatabase(project_name=PROJECT_NAME)
    with db.connect() as conn:
        return db.get_stats(conn)
