"""Service zum Abrufen von YouTube Video-Metadaten via yt-dlp."""

from dataclasses import dataclass
from datetime import datetime

import yt_dlp

from config import get_logger

logger = get_logger(__name__)


@dataclass
class VideoMetadata:
    """Metadaten eines YouTube-Videos."""
    youtube_id: str
    title: str
    channel: str
    published_date: str | None
    duration_seconds: int
    description: str | None
    view_count: int | None
    thumbnail_url: str | None


# yt-dlp Konfiguration: Nur Metadaten, kein Download
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'skip_download': True,
    'ignoreerrors': True,
}


def get_video_metadata(youtube_id: str) -> VideoMetadata | None:
    """Holt Metadaten fuer ein YouTube-Video."""
    url = f"https://www.youtube.com/watch?v={youtube_id}"

    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

            if info is None:
                logger.warning(f"Keine Metadaten fuer {youtube_id}")
                return None

            # Datum parsen (Format: YYYYMMDD)
            upload_date = info.get('upload_date')
            published_date = None
            if upload_date:
                try:
                    dt = datetime.strptime(upload_date, '%Y%m%d')
                    published_date = dt.strftime('%Y-%m-%d')
                except ValueError:
                    pass

            metadata = VideoMetadata(
                youtube_id=youtube_id,
                title=info.get('title', 'Unbekannt'),
                channel=info.get('channel', info.get('uploader', 'Unbekannt')),
                published_date=published_date,
                duration_seconds=info.get('duration', 0),
                description=info.get('description'),
                view_count=info.get('view_count'),
                thumbnail_url=info.get('thumbnail'),
            )

            logger.debug(f"Metadaten abgerufen: {metadata.title[:50]}...")
            return metadata

    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Metadaten fuer {youtube_id}: {e}")
        return None


def format_duration(seconds: int) -> str:
    """Formatiert Sekunden als lesbaren String (z.B. '1:23:45')."""
    if seconds < 0:
        return "0:00"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"
