"""
SQLite database module for YouTube video metadata management.

Provides persistent storage for extracted video data with support for:
- User comments and ratings
- Custom tags for organization
- Import tracking from HTML extractions
"""

import sqlite3
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class VideoRecord:
    """Database record for a video with user annotations."""
    # Core video data (from extraction)
    video_id: str
    title: str
    channel: Optional[str] = None
    views: Optional[str] = None
    views_count: Optional[int] = None
    published: Optional[str] = None
    published_date: Optional[str] = None
    duration: Optional[str] = None
    url: str = ""
    video_type: str = "video"
    thumbnail_url: Optional[str] = None
    thumbnail_local: Optional[str] = None

    # Live status (None = unspecified, for merge semantics)
    is_live: Optional[bool] = False
    is_premiere: Optional[bool] = False
    is_upcoming: Optional[bool] = False
    live_badge: Optional[str] = None

    # User annotations
    user_comment: Optional[str] = None
    user_rating: Optional[int] = None  # 1-5 stars
    user_tags: List[str] = None  # Stored as JSON in DB

    # Analysis data (from youtube_analyzer merge)
    transcript_text: Optional[str] = None
    transcript_language: Optional[str] = None
    summary: Optional[str] = None
    themes: Optional[str] = None  # JSON array of theme tags
    claims: Optional[str] = None  # JSON array of extracted claims
    analysis_status: str = "none"  # none / transcript / analyzed / error
    import_group: Optional[str] = None  # OneTab group name

    # Metadata
    source_file: Optional[str] = None
    source_date: Optional[str] = None
    first_seen: Optional[str] = None  # When first imported
    last_updated: Optional[str] = None  # Last modification

    # Database ID
    id: Optional[int] = None

    def __post_init__(self):
        if self.user_tags is None:
            self.user_tags = []
        if not self.url and self.video_id:
            if self.video_type == "short":
                self.url = f"https://youtube.com/shorts/{self.video_id}"
            else:
                self.url = f"https://youtube.com/watch?v={self.video_id}"


class VideoDatabase:
    """SQLite database for video metadata storage."""

    SCHEMA_VERSION = 2

    # Allowed columns for ORDER BY (prevents SQL injection)
    ALLOWED_ORDER_COLUMNS = frozenset({
        "id", "video_id", "title", "channel", "views_count",
        "published_date", "duration", "video_type", "is_live",
        "user_rating", "analysis_status", "first_seen", "last_updated",
    })

    def __init__(self, db_path: str | Path = "yt_videos.db"):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._connect()
        self._init_schema()

    def _connect(self):
        """Establish database connection."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")

    def _init_schema(self):
        """Initialize database schema if not exists."""
        cursor = self.conn.cursor()

        # Videos table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                channel TEXT,
                views TEXT,
                views_count INTEGER,
                published TEXT,
                published_date TEXT,
                duration TEXT,
                url TEXT,
                video_type TEXT DEFAULT 'video',
                thumbnail_url TEXT,
                thumbnail_local TEXT,
                is_live INTEGER DEFAULT 0,
                is_premiere INTEGER DEFAULT 0,
                is_upcoming INTEGER DEFAULT 0,
                live_badge TEXT,
                user_comment TEXT,
                user_rating INTEGER CHECK(user_rating IS NULL OR (user_rating >= 1 AND user_rating <= 5)),
                transcript_text TEXT,
                transcript_language TEXT,
                summary TEXT,
                themes TEXT,
                claims TEXT,
                analysis_status TEXT DEFAULT 'none',
                import_group TEXT,
                source_file TEXT,
                source_date TEXT,
                first_seen TEXT NOT NULL,
                last_updated TEXT NOT NULL
            )
        """)

        # Tags table (many-to-many)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)

        # Video-Tags junction table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_tags (
                video_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (video_id, tag_id),
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        """)

        # Import history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS import_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                import_date TEXT NOT NULL,
                video_count INTEGER,
                source_type TEXT
            )
        """)

        # Chat history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Schema version table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)

        # Check current version and migrate BEFORE creating indexes on new columns
        cursor.execute("SELECT MAX(version) as v FROM schema_version")
        row = cursor.fetchone()
        current_version = row["v"] if row and row["v"] else 0

        if current_version < 2:
            self._migrate_to_v2(cursor)

        # Create indexes (after migration so new columns exist)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_published_date ON videos(published_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_video_type ON videos(video_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_user_rating ON videos(user_rating)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_analysis_status ON videos(analysis_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")

        # Insert/update version
        cursor.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                      (self.SCHEMA_VERSION,))

        self.conn.commit()
        logger.info(f"Database initialized: {self.db_path} (schema v{self.SCHEMA_VERSION})")

    def _migrate_to_v2(self, cursor):
        """Migrate schema from v1 to v2: add analysis columns and chat_history."""
        logger.info("Migrating database schema to v2...")

        # Add new columns to videos table (SQLite ALTER TABLE ADD COLUMN)
        new_columns = [
            ("transcript_text", "TEXT"),
            ("transcript_language", "TEXT"),
            ("summary", "TEXT"),
            ("themes", "TEXT"),
            ("claims", "TEXT"),
            ("analysis_status", "TEXT DEFAULT 'none'"),
            ("import_group", "TEXT"),
        ]

        for col_name, col_type in new_columns:
            try:
                cursor.execute(f"ALTER TABLE videos ADD COLUMN {col_name} {col_type}")
                logger.debug(f"Added column: {col_name}")
            except sqlite3.OperationalError:
                # Column already exists
                pass

        logger.info("Schema migration to v2 complete")

    def close(self):
        """Close database connection."""
        with self._lock:
            if self.conn:
                self.conn.close()
                self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # =========================================================================
    # Video CRUD Operations
    # =========================================================================

    def add_video(self, video: VideoRecord) -> int:
        """
        Add a new video or update if exists.

        Args:
            video: VideoRecord to add

        Returns:
            Database ID of the video
        """
        with self._lock:
            return self._add_video_unlocked(video)

    def _add_video_unlocked(self, video: VideoRecord) -> int:
        """Internal add_video without lock (caller must hold self._lock)."""
        now = datetime.now().isoformat()
        cursor = self.conn.cursor()

        # Check if video already exists
        cursor.execute("SELECT id, first_seen FROM videos WHERE video_id = ?",
                      (video.video_id,))
        existing = cursor.fetchone()

        if existing:
            # Update existing video
            video.id = existing["id"]
            video.first_seen = existing["first_seen"]
            video.last_updated = now
            return self._update_video(video)
        else:
            # Insert new video
            video.first_seen = now
            video.last_updated = now

            cursor.execute("""
                INSERT INTO videos (
                    video_id, title, channel, views, views_count,
                    published, published_date, duration, url, video_type,
                    thumbnail_url, thumbnail_local, is_live, is_premiere,
                    is_upcoming, live_badge, user_comment, user_rating,
                    transcript_text, transcript_language, summary, themes,
                    claims, analysis_status, import_group,
                    source_file, source_date, first_seen, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video.video_id, video.title, video.channel, video.views,
                video.views_count, video.published, video.published_date,
                video.duration, video.url, video.video_type, video.thumbnail_url,
                video.thumbnail_local, int(video.is_live or False), int(video.is_premiere or False),
                int(video.is_upcoming or False), video.live_badge, video.user_comment,
                video.user_rating, video.transcript_text, video.transcript_language,
                video.summary, video.themes, video.claims, video.analysis_status,
                video.import_group, video.source_file, video.source_date,
                video.first_seen, video.last_updated
            ))

            video.id = cursor.lastrowid

            # Add tags if any
            if video.user_tags:
                self._set_video_tags(video.id, video.user_tags)

            self.conn.commit()
            logger.debug(f"Added video: {video.video_id}")
            return video.id

    def _update_video(self, video: VideoRecord) -> int:
        """Update existing video record (full overwrite, used by edit dialog)."""
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE videos SET
                title = ?, channel = ?, views = ?, views_count = ?,
                published = ?, published_date = ?, duration = ?, url = ?,
                video_type = ?, thumbnail_url = ?, thumbnail_local = ?,
                is_live = ?, is_premiere = ?, is_upcoming = ?, live_badge = ?,
                user_comment = ?, user_rating = ?,
                transcript_text = ?, transcript_language = ?, summary = ?,
                themes = ?, claims = ?, analysis_status = ?, import_group = ?,
                source_file = ?, source_date = ?, last_updated = ?
            WHERE id = ?
        """, (
            video.title, video.channel, video.views, video.views_count,
            video.published, video.published_date, video.duration, video.url,
            video.video_type, video.thumbnail_url, video.thumbnail_local,
            int(video.is_live or False), int(video.is_premiere or False), int(video.is_upcoming or False),
            video.live_badge, video.user_comment, video.user_rating,
            video.transcript_text, video.transcript_language, video.summary,
            video.themes, video.claims, video.analysis_status, video.import_group,
            video.source_file, video.source_date, video.last_updated, video.id
        ))

        # Update tags
        if video.user_tags is not None:
            self._set_video_tags(video.id, video.user_tags)

        self.conn.commit()
        logger.debug(f"Updated video: {video.video_id}")
        return video.id

    @staticmethod
    def _is_placeholder_title(title: str, video_id: str) -> bool:
        """Check if a title is a placeholder like 'Video abc123'."""
        return title.startswith("Video ") and title[6:] == video_id

    def _merge_video(self, video: VideoRecord) -> int:
        """Merge-update: only update metadata fields, preserve user annotations and analysis data."""
        now = datetime.now().isoformat()

        with self._lock:
            cursor = self.conn.cursor()

            cursor.execute("SELECT id, first_seen FROM videos WHERE video_id = ?",
                          (video.video_id,))
            existing = cursor.fetchone()

            if not existing:
                # New video, just insert
                video.first_seen = now
                video.last_updated = now
                return self._add_video_unlocked(video)

            # Normalize placeholders to None so COALESCE won't overwrite real data
            title = None if self._is_placeholder_title(video.title, video.video_id) else video.title
            video_type = None if video.video_type == "video" else video.video_type

            # Normalize empty strings to None so COALESCE skips them
            def _none_if_empty(val):
                return None if val == "" else val

            channel = _none_if_empty(video.channel)
            views = _none_if_empty(video.views)
            published = _none_if_empty(video.published)
            published_date = _none_if_empty(video.published_date)
            duration = _none_if_empty(video.duration)
            url = _none_if_empty(video.url)
            thumbnail_url = _none_if_empty(video.thumbnail_url)
            thumbnail_local = _none_if_empty(video.thumbnail_local)
            live_badge = _none_if_empty(video.live_badge)
            source_file = _none_if_empty(video.source_file)
            source_date = _none_if_empty(video.source_date)
            import_group = _none_if_empty(video.import_group)

            # Only update metadata fields, preserve everything else
            cursor.execute("""
                UPDATE videos SET
                    title = COALESCE(?, title),
                    channel = COALESCE(?, channel),
                    views = COALESCE(?, views),
                    views_count = COALESCE(?, views_count),
                    published = COALESCE(?, published),
                    published_date = COALESCE(?, published_date),
                    duration = COALESCE(?, duration),
                    url = COALESCE(?, url),
                    video_type = COALESCE(?, video_type),
                    thumbnail_url = COALESCE(?, thumbnail_url),
                    thumbnail_local = COALESCE(?, thumbnail_local),
                    is_live = COALESCE(?, is_live),
                    is_premiere = COALESCE(?, is_premiere),
                    is_upcoming = COALESCE(?, is_upcoming),
                    live_badge = COALESCE(?, live_badge),
                    source_file = COALESCE(?, source_file),
                    source_date = COALESCE(?, source_date),
                    import_group = COALESCE(?, import_group),
                    last_updated = ?
                WHERE video_id = ?
            """, (
                title, channel, views, video.views_count,
                published, published_date, duration, url,
                video_type, thumbnail_url, thumbnail_local,
                int(video.is_live) if video.is_live is not None else None,
                int(video.is_premiere) if video.is_premiere is not None else None,
                int(video.is_upcoming) if video.is_upcoming is not None else None,
                live_badge, source_file, source_date,
                import_group, now, video.video_id,
            ))

            self.conn.commit()
            logger.debug(f"Merge-updated video: {video.video_id}")
            return existing["id"]

    def get_video(self, video_id: str) -> Optional[VideoRecord]:
        """
        Get video by YouTube video ID.

        Args:
            video_id: YouTube video ID

        Returns:
            VideoRecord or None if not found
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_record(row)
            return None

    def get_video_by_id(self, db_id: int) -> Optional[VideoRecord]:
        """Get video by database ID."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE id = ?", (db_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_record(row)
            return None

    def delete_video(self, video_id: str) -> bool:
        """
        Delete video by YouTube video ID.

        Args:
            video_id: YouTube video ID

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
            self.conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"Deleted video: {video_id}")
            return deleted

    def _row_to_record(self, row: sqlite3.Row) -> VideoRecord:
        """Convert database row to VideoRecord."""
        tags = self._get_video_tags(row["id"])

        return VideoRecord(
            id=row["id"],
            video_id=row["video_id"],
            title=row["title"],
            channel=row["channel"],
            views=row["views"],
            views_count=row["views_count"],
            published=row["published"],
            published_date=row["published_date"],
            duration=row["duration"],
            url=row["url"],
            video_type=row["video_type"],
            thumbnail_url=row["thumbnail_url"],
            thumbnail_local=row["thumbnail_local"],
            is_live=bool(row["is_live"]),
            is_premiere=bool(row["is_premiere"]),
            is_upcoming=bool(row["is_upcoming"]),
            live_badge=row["live_badge"],
            user_comment=row["user_comment"],
            user_rating=row["user_rating"],
            user_tags=tags,
            transcript_text=row["transcript_text"],
            transcript_language=row["transcript_language"],
            summary=row["summary"],
            themes=row["themes"],
            claims=row["claims"],
            analysis_status=row["analysis_status"] or "none",
            import_group=row["import_group"],
            source_file=row["source_file"],
            source_date=row["source_date"],
            first_seen=row["first_seen"],
            last_updated=row["last_updated"],
        )

    # =========================================================================
    # Tag Operations
    # =========================================================================

    def _get_or_create_tag(self, tag_name: str) -> int:
        """Get tag ID, creating if necessary."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        row = cursor.fetchone()

        if row:
            return row["id"]

        cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
        return cursor.lastrowid

    def _set_video_tags(self, video_db_id: int, tags: List[str]):
        """Set tags for a video (replaces existing)."""
        cursor = self.conn.cursor()

        # Remove existing tags
        cursor.execute("DELETE FROM video_tags WHERE video_id = ?", (video_db_id,))

        # Add new tags
        for tag in tags:
            tag_id = self._get_or_create_tag(tag.strip().lower())
            cursor.execute(
                "INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)",
                (video_db_id, tag_id)
            )

    def _get_video_tags(self, video_db_id: int) -> List[str]:
        """Get all tags for a video."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT t.name FROM tags t
            JOIN video_tags vt ON t.id = vt.tag_id
            WHERE vt.video_id = ?
            ORDER BY t.name
        """, (video_db_id,))
        return [row["name"] for row in cursor.fetchall()]

    def get_all_tags(self) -> List[str]:
        """Get all unique tags in database."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM tags ORDER BY name")
            return [row["name"] for row in cursor.fetchall()]

    def add_tag_to_video(self, video_id: str, tag: str):
        """Add a single tag to a video."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
            row = cursor.fetchone()
            if row:
                tags = self._get_video_tags(row["id"])
                normalized = tag.strip().lower()
                if normalized not in [t.lower() for t in tags]:
                    tags.append(normalized)
                    self._set_video_tags(row["id"], tags)
                    self.conn.commit()

    def remove_tag_from_video(self, video_id: str, tag: str):
        """Remove a tag from a video."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
            row = cursor.fetchone()
            if row:
                tags = self._get_video_tags(row["id"])
                tags = [t for t in tags if t.lower() != tag.lower()]
                self._set_video_tags(row["id"], tags)
                self.conn.commit()

    # =========================================================================
    # Query / Filter Operations
    # =========================================================================

    def _validate_order_by(self, order_by: str) -> str:
        """Validate order_by column against allowlist to prevent SQL injection."""
        if order_by not in self.ALLOWED_ORDER_COLUMNS:
            raise ValueError(f"Invalid order_by column: {order_by}")
        return order_by

    def get_all_videos(self,
                       order_by: str = "last_updated",
                       descending: bool = True,
                       limit: int = None) -> List[VideoRecord]:
        """
        Get all videos with optional ordering.

        Args:
            order_by: Column to sort by (must be in ALLOWED_ORDER_COLUMNS)
            descending: Sort direction
            limit: Maximum number of results
        """
        order_by = self._validate_order_by(order_by)

        with self._lock:
            cursor = self.conn.cursor()

            order_dir = "DESC" if descending else "ASC"
            query = f"SELECT * FROM videos ORDER BY {order_by} {order_dir}"

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def search_videos(self,
                      search_text: str = None,
                      channel: str = None,
                      tags: List[str] = None,
                      video_type: str = None,
                      min_rating: int = None,
                      is_live: bool = None,
                      has_comment: bool = None,
                      order_by: str = "last_updated",
                      descending: bool = True) -> List[VideoRecord]:
        """
        Search videos with multiple filter criteria.

        Args:
            search_text: Search in title and channel
            channel: Filter by channel name (partial match)
            tags: Filter by tags (videos must have ALL specified tags)
            video_type: Filter by type ("video" or "short")
            min_rating: Minimum user rating
            is_live: Filter by live status
            has_comment: Filter videos with/without comments
            order_by: Sort column
            descending: Sort direction
        """
        conditions = []
        params = []

        if search_text:
            conditions.append("(title LIKE ? OR channel LIKE ?)")
            params.extend([f"%{search_text}%", f"%{search_text}%"])

        if channel:
            conditions.append("channel LIKE ?")
            params.append(f"%{channel}%")

        if video_type:
            conditions.append("video_type = ?")
            params.append(video_type)

        if min_rating is not None:
            conditions.append("user_rating >= ?")
            params.append(min_rating)

        if is_live is not None:
            conditions.append("is_live = ?")
            params.append(int(is_live))

        if has_comment is not None:
            if has_comment:
                conditions.append("user_comment IS NOT NULL AND user_comment != ''")
            else:
                conditions.append("(user_comment IS NULL OR user_comment = '')")

        # Build query
        order_by = self._validate_order_by(order_by)
        order_dir = "DESC" if descending else "ASC"

        if tags:
            # Subquery for tag filtering
            tag_placeholders = ",".join("?" * len(tags))
            query = f"""
                SELECT v.* FROM videos v
                JOIN video_tags vt ON v.id = vt.video_id
                JOIN tags t ON vt.tag_id = t.id
                WHERE t.name IN ({tag_placeholders})
            """
            params = list(tags) + params

            if conditions:
                query += " AND " + " AND ".join(conditions)

            query += f"""
                GROUP BY v.id
                HAVING COUNT(DISTINCT t.name) = ?
                ORDER BY v.{order_by} {order_dir}
            """
            params.append(len(tags))
        else:
            query = f"SELECT * FROM videos"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += f" ORDER BY {order_by} {order_dir}"

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def get_channels(self) -> List[str]:
        """Get all unique channel names."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT DISTINCT channel FROM videos
                WHERE channel IS NOT NULL
                ORDER BY channel
            """)
            return [row["channel"] for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self._lock:
            cursor = self.conn.cursor()

            stats = {}

            cursor.execute("SELECT COUNT(*) as count FROM videos")
            stats["total_videos"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM videos WHERE video_type = 'short'")
            stats["shorts"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM videos WHERE video_type = 'video'")
            stats["videos"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM videos WHERE is_live = 1")
            stats["live"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM videos WHERE user_rating IS NOT NULL")
            stats["rated"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM videos WHERE user_comment IS NOT NULL AND user_comment != ''")
            stats["with_comments"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(DISTINCT channel) as count FROM videos")
            stats["channels"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM tags")
            stats["tags"] = cursor.fetchone()["count"]

            # Analysis stats
            cursor.execute("SELECT COUNT(*) as count FROM videos WHERE transcript_text IS NOT NULL")
            stats["with_transcript"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM videos WHERE summary IS NOT NULL")
            stats["with_summary"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM videos WHERE claims IS NOT NULL AND claims != '[]'")
            stats["with_claims"] = cursor.fetchone()["count"]

            for status in ("none", "transcript", "analyzed", "error"):
                cursor.execute("SELECT COUNT(*) as count FROM videos WHERE analysis_status = ?", (status,))
                stats[f"status_{status}"] = cursor.fetchone()["count"]

            return stats

    # =========================================================================
    # Analysis Operations
    # =========================================================================

    def update_transcript(self, video_id: str, transcript_text: str,
                         transcript_language: str) -> bool:
        """Update transcript for a video."""
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE videos SET
                    transcript_text = ?, transcript_language = ?,
                    analysis_status = CASE
                        WHEN analysis_status IN ('none', 'error') THEN 'transcript'
                        ELSE analysis_status
                    END,
                    last_updated = ?
                WHERE video_id = ?
            """, (transcript_text, transcript_language, now, video_id))
            self.conn.commit()
            return cursor.rowcount > 0

    def update_summary(self, video_id: str, summary: str, themes: str) -> bool:
        """Update summary and themes for a video."""
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE videos SET
                    summary = ?, themes = ?, analysis_status = 'analyzed',
                    last_updated = ?
                WHERE video_id = ?
            """, (summary, themes, now, video_id))
            self.conn.commit()
            return cursor.rowcount > 0

    def update_claims(self, video_id: str, claims_json: str) -> bool:
        """Update extracted claims for a video."""
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE videos SET claims = ?, last_updated = ?
                WHERE video_id = ?
            """, (claims_json, now, video_id))
            self.conn.commit()
            return cursor.rowcount > 0

    def update_analysis_status(self, video_id: str, status: str) -> bool:
        """Update analysis status for a video."""
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE videos SET analysis_status = ?, last_updated = ?
                WHERE video_id = ?
            """, (status, now, video_id))
            self.conn.commit()
            return cursor.rowcount > 0

    def get_videos_by_status(self, status: str) -> List[VideoRecord]:
        """Get all videos with a specific analysis status."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE analysis_status = ? ORDER BY last_updated DESC",
                          (status,))
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def get_analyzed_videos(self) -> List[VideoRecord]:
        """Get all videos that have been analyzed (have summary)."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE summary IS NOT NULL ORDER BY last_updated DESC")
            return [self._row_to_record(row) for row in cursor.fetchall()]

    # =========================================================================
    # Chat History Operations
    # =========================================================================

    def add_chat_message(self, role: str, content: str) -> int:
        """Add a chat message to history."""
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute(
                "INSERT INTO chat_history (role, content, created_at) VALUES (?, ?, ?)",
                (role, content, now),
            )
            self.conn.commit()
            return cursor.lastrowid

    def get_chat_history(self, limit: int = 50) -> List[Dict]:
        """Get recent chat history."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM chat_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            rows.reverse()  # Oldest first
            return rows

    def clear_chat_history(self) -> int:
        """Clear all chat history. Returns number of deleted messages."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM chat_history")
            count = cursor.rowcount
            self.conn.commit()
            return count

    # =========================================================================
    # Import Operations
    # =========================================================================

    def import_from_extraction(self, videos: List[Any], source_file: str = None) -> int:
        """
        Import videos from extraction (VideoData objects).

        Args:
            videos: List of VideoData objects from yt_extractor
            source_file: Source HTML filename

        Returns:
            Number of videos imported/updated
        """
        count = 0
        for video in videos:
            record = VideoRecord(
                video_id=video.video_id,
                title=video.title,
                channel=video.channel,
                views=video.views,
                views_count=video.views_count,
                published=video.published,
                published_date=video.published_date,
                duration=video.duration,
                url=video.url,
                video_type=video.video_type,
                thumbnail_url=video.thumbnail_url,
                thumbnail_local=video.thumbnail_local,
                is_live=video.is_live,
                is_premiere=video.is_premiere,
                is_upcoming=video.is_upcoming,
                live_badge=video.live_badge,
                source_file=source_file or video.source_file,
                source_date=video.source_date
            )
            self._merge_video(record)
            count += 1

        # Record import in history
        if source_file:
            with self._lock:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO import_history (filename, import_date, video_count, source_type)
                    VALUES (?, ?, ?, ?)
                """, (source_file, datetime.now().isoformat(), count, "html"))
                self.conn.commit()

        logger.info(f"Imported {count} videos from {source_file}")
        return count

    def import_from_onetab(self, parsed_videos, source_name: str = "onetab") -> int:
        """
        Import videos from OneTab parser (ParsedVideo objects).

        Args:
            parsed_videos: List of ParsedVideo objects from onetab_parser
            source_name: Source identifier

        Returns:
            Number of videos imported/updated
        """
        count = 0
        for pv in parsed_videos:
            record = VideoRecord(
                video_id=pv.youtube_id,
                title=pv.title or f"Video {pv.youtube_id}",
                url=pv.url,
                is_live=None,
                is_premiere=None,
                is_upcoming=None,
                import_group=pv.group,
                source_file=source_name,
                analysis_status="none",
            )
            self._merge_video(record)
            count += 1

        # Record import in history
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO import_history (filename, import_date, video_count, source_type)
                VALUES (?, ?, ?, ?)
            """, (source_name, datetime.now().isoformat(), count, "onetab"))
            self.conn.commit()

        logger.info(f"Imported {count} videos from OneTab ({source_name})")
        return count

    def get_import_history(self) -> List[Dict]:
        """Get import history."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM import_history ORDER BY import_date DESC
            """)
            return [dict(row) for row in cursor.fetchall()]


# Convenience function for quick database access
def get_database(db_path: str = "yt_videos.db") -> VideoDatabase:
    """Get a database instance."""
    return VideoDatabase(db_path)
