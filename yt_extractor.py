#!/usr/bin/env python3
"""
YT Overview Extractor - Extracts video metadata from saved YouTube HTML pages.

Supports:
- Channel Shorts pages (/@channel/shorts)
- Algorithm recommendations (YouTube homepage)
"""

import argparse
import csv
import json
import logging
import re
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("BeautifulSoup4 not available. DOM parsing will be disabled.")


@dataclass
class VideoData:
    """Represents extracted video metadata."""
    video_id: str
    title: str
    channel: Optional[str] = None
    views: Optional[str] = None
    views_count: Optional[int] = None  # Numeric value for sorting
    published: Optional[str] = None
    published_date: Optional[str] = None  # Calculated: "2025-12-16" (ISO-Format)
    duration: Optional[str] = None
    url: str = ""
    video_type: str = "video"  # "video" or "short"
    thumbnail_url: Optional[str] = None
    thumbnail_local: Optional[str] = None  # Path to downloaded thumbnail
    source_file: Optional[str] = None  # Source HTML filename
    source_date: Optional[str] = None  # ISO-Format: "2025-12-18T15:59:24"
    # Live-Video-Felder
    is_live: bool = False  # Aktiver Live-Stream
    is_premiere: bool = False  # Premiere (geplante Erstausstrahlung)
    is_upcoming: bool = False  # Geplanter Stream (noch nicht gestartet)
    live_badge: Optional[str] = None  # "LIVE", "PREMIERE", "UPCOMING", "UNKNOWN"

    def __post_init__(self):
        """Generate URL based on video type."""
        if not self.url:
            if self.video_type == "short":
                self.url = f"https://youtube.com/shorts/{self.video_id}"
            else:
                self.url = f"https://youtube.com/watch?v={self.video_id}"


def extract_source_timestamp(html_content: str) -> Optional[datetime]:
    """
    Extract the YouTube page load timestamp from HTML.

    Searches for: "timestamp":{"seconds":"1765802483"...}
    Returns datetime or None if not found.
    """
    pattern = r'"timestamp":\s*\{\s*"seconds":\s*"(\d+)"'
    match = re.search(pattern, html_content)

    if match:
        unix_timestamp = int(match.group(1))
        try:
            return datetime.fromtimestamp(unix_timestamp)
        except (ValueError, OSError) as e:
            logger.debug(f"Invalid timestamp {unix_timestamp}: {e}")
            return None

    return None


def get_source_date(html_content: str, filepath: Path) -> Optional[datetime]:
    """
    Determine the source date with fallback strategies.

    1. YouTube timestamp embedded in HTML
    2. SingleFile filename format: "(54) YouTube (16.12.2025 00：42：51).html"
    3. File modification time
    """
    # Strategy 1: YouTube timestamp
    source_date = extract_source_timestamp(html_content)
    if source_date:
        logger.debug(f"Source date from YouTube timestamp: {source_date}")
        return source_date

    # Strategy 2: SingleFile filename pattern
    # Format: "(54) YouTube (16.12.2025 00：42：51).html" (note: fullwidth colons ：)
    filename = filepath.name
    # Match both regular colons and fullwidth colons
    pattern = r'\((\d{2})\.(\d{2})\.(\d{4})\s+(\d{2})[:：](\d{2})[:：](\d{2})\)'
    match = re.search(pattern, filename)
    if match:
        day, month, year, hour, minute, second = map(int, match.groups())
        try:
            source_date = datetime(year, month, day, hour, minute, second)
            logger.debug(f"Source date from filename: {source_date}")
            return source_date
        except ValueError as e:
            logger.debug(f"Invalid date in filename: {e}")

    # Strategy 3: File modification time
    try:
        mtime = filepath.stat().st_mtime
        source_date = datetime.fromtimestamp(mtime)
        logger.debug(f"Source date from file mtime: {source_date}")
        return source_date
    except (OSError, ValueError) as e:
        logger.debug(f"Could not get file mtime: {e}")

    return None


def parse_relative_time(time_str: str, reference_date: datetime) -> Optional[datetime]:
    """
    Convert relative time strings to actual datetime.

    Supported German formats:
    - vor 6 Minuten / vor 1 Minute
    - vor 2 Stunden / vor 1 Stunde
    - vor 3 Tagen / vor 1 Tag
    - vor 2 Wochen / vor 1 Woche
    - vor 5 Monaten / vor 1 Monat
    - vor 1 Jahr / vor 2 Jahren

    English formats:
    - 6 minutes ago / 1 minute ago
    - 2 hours ago / 1 hour ago
    - 3 days ago / 1 day ago
    - 2 weeks ago / 1 week ago
    - 5 months ago / 1 month ago
    - 1 year ago / 2 years ago
    """
    if not time_str:
        return None

    time_str = time_str.lower().strip()

    # German pattern: "vor X einheit"
    de_match = re.match(r'vor\s+(\d+)\s+(\w+)', time_str)
    # English pattern: "X unit ago"
    en_match = re.match(r'(\d+)\s+(\w+)\s+ago', time_str)

    if de_match:
        amount = int(de_match.group(1))
        unit = de_match.group(2)
    elif en_match:
        amount = int(en_match.group(1))
        unit = en_match.group(2)
    else:
        return None

    # Map units to timedelta (handle both singular and plural forms)
    if unit.startswith('minute'):
        delta = timedelta(minutes=amount)
    elif unit.startswith('stunde') or unit.startswith('hour'):
        delta = timedelta(hours=amount)
    elif unit.startswith('tag') or unit.startswith('day'):
        delta = timedelta(days=amount)
    elif unit.startswith('woche') or unit.startswith('week'):
        delta = timedelta(weeks=amount)
    elif unit.startswith('monat') or unit.startswith('month'):
        delta = timedelta(days=amount * 30)  # Approximation
    elif unit.startswith('jahr') or unit.startswith('year'):
        delta = timedelta(days=amount * 365)  # Approximation
    else:
        logger.debug(f"Unknown time unit: {unit}")
        return None

    return reference_date - delta


def extract_yt_initial_data(html_content: str) -> Optional[dict]:
    """Extract ytInitialData JSON from HTML content."""
    patterns = [
        r'var\s+ytInitialData\s*=\s*({.*?});</script>',
        r'ytInitialData\s*=\s*({.*?});</script>',
        r'window\["ytInitialData"\]\s*=\s*({.*?});',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html_content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON with pattern: {e}")
                continue
    
    logger.debug("No ytInitialData found in HTML (expected for SingleFile exports)")
    return None


def detect_page_type(data: dict) -> str:
    """Detect the type of YouTube page from ytInitialData."""
    try:
        params = data.get("responseContext", {}).get("serviceTrackingParams", [])
        for service in params:
            for param in service.get("params", []):
                if param.get("key") == "route" and param.get("value") == "channel.shorts":
                    return "shorts"
                if param.get("key") == "browse_id" and param.get("value") == "FEwhat_to_watch":
                    return "algorithm"
    except Exception:
        pass

    # Check for search page structure
    content_str = json.dumps(data)
    if "twoColumnSearchResultsRenderer" in content_str:
        return "search"

    # Fallback: check for shorts indicators in content
    if "shortsLockupViewModel" in content_str:
        return "shorts"
    if "videoRenderer" in content_str or "lockupViewModel" in content_str:
        return "algorithm"

    return "unknown"


def parse_views_count(views_text: str) -> Optional[int]:
    """
    Parse view count string to integer.

    Supports German formats:
    - "1.234 Aufrufe" → 1234
    - "5,6 Mio. Aufrufe" → 5600000
    - "1,2 Tsd. Aufrufe" → 1200

    And English formats:
    - "1.2M views" → 1200000
    - "1.2K views" → 1200
    """
    if not views_text:
        return None

    text = views_text.lower()

    # Handle German "Mio." (Millionen) format
    mio_match = re.search(r'([\d.,]+)\s*mio\.?', text)
    if mio_match:
        num_str = mio_match.group(1).replace('.', '').replace(',', '.')
        try:
            return int(float(num_str) * 1_000_000)
        except ValueError:
            pass

    # Handle German "Tsd." (Tausend) format
    tsd_match = re.search(r'([\d.,]+)\s*tsd\.?', text)
    if tsd_match:
        num_str = tsd_match.group(1).replace('.', '').replace(',', '.')
        try:
            return int(float(num_str) * 1_000)
        except ValueError:
            pass

    # Handle English "M" (Million) format
    m_match = re.search(r'([\d.,]+)\s*m\b', text)
    if m_match:
        num_str = m_match.group(1).replace(',', '')
        try:
            return int(float(num_str) * 1_000_000)
        except ValueError:
            pass

    # Handle English "K" (Thousand) format
    k_match = re.search(r'([\d.,]+)\s*k\b', text)
    if k_match:
        num_str = k_match.group(1).replace(',', '')
        try:
            return int(float(num_str) * 1_000)
        except ValueError:
            pass

    # Standard format: remove non-numeric characters except dots and commas
    clean = re.sub(r'[^\d.,]', '', views_text)
    # Handle German number format (1.234 = 1234)
    clean = clean.replace('.', '').replace(',', '.')

    try:
        return int(float(clean))
    except ValueError:
        return None


def detect_live_status(renderer: dict) -> dict:
    """
    Erkennt den Live-Status eines Videos aus dem Renderer.

    Prüft mehrere Indikatoren:
    1. Badges in metadataBadgeRenderer (style/label enthält "LIVE")
    2. Thumbnail-Overlays mit style "LIVE" oder "UPCOMING"
    3. viewCountText enthält "zuschauer", "watching", "warten", "waiting"

    Args:
        renderer: videoRenderer oder lockupViewModel Dict

    Returns:
        Dict mit is_live, is_premiere, is_upcoming, live_badge

    Example:
        >>> status = detect_live_status(video_renderer)
        >>> if status["is_live"]:
        ...     print("Video ist live!")
    """
    result = {
        "is_live": False,
        "is_premiere": False,
        "is_upcoming": False,
        "live_badge": None
    }

    # 1. Check: badges (metadataBadgeRenderer)
    badges = renderer.get("badges", [])
    for badge in badges:
        badge_renderer = badge.get("metadataBadgeRenderer", {})
        label = badge_renderer.get("label", "").upper()
        style = badge_renderer.get("style", "").upper()

        if "LIVE" in label or "LIVE" in style:
            result["is_live"] = True
            result["live_badge"] = "LIVE"
        elif "PREMIERE" in label or "PREMIERE" in style:
            result["is_premiere"] = True
            result["live_badge"] = "PREMIERE"
        elif "UPCOMING" in label or "UPCOMING" in style:
            result["is_upcoming"] = True
            result["live_badge"] = "UPCOMING"

    # 2. Check: thumbnailOverlays
    overlays = renderer.get("thumbnailOverlays", [])
    for overlay in overlays:
        time_status = overlay.get("thumbnailOverlayTimeStatusRenderer", {})
        style = time_status.get("style", "").upper()

        if style == "LIVE":
            result["is_live"] = True
            result["live_badge"] = "LIVE"
        elif style == "UPCOMING":
            result["is_upcoming"] = True
            result["live_badge"] = "UPCOMING"

    # 3. Check: viewCountText enthält "warten" / "waiting" / "zuschauer" / "watching"
    view_text = ""
    view_obj = renderer.get("viewCountText", {})
    if isinstance(view_obj, dict):
        view_text = view_obj.get("simpleText", "") or ""
        if not view_text and "runs" in view_obj:
            view_text = "".join(r.get("text", "") for r in view_obj.get("runs", []))

    view_text_lower = view_text.lower()

    if "warten" in view_text_lower or "waiting" in view_text_lower:
        result["is_upcoming"] = True
        if not result["live_badge"]:
            result["live_badge"] = "UPCOMING"
    if "zuschauer" in view_text_lower or "watching" in view_text_lower:
        result["is_live"] = True
        result["live_badge"] = "LIVE"

    return result


def apply_live_fallbacks(video: VideoData, source_date: datetime) -> None:
    """
    Setzt sinnvolle Fallback-Werte für Live-Videos.

    Für erkannte Live/Premiere/Upcoming Videos ohne Metadaten:
    - published_date → source_date (wann die Seite gespeichert wurde)
    - published → "Live am {datum}" / "Premiere am {datum}" etc.
    - views_count → 0
    - views → "Live" / "Premiere" / "Geplant"

    Für Videos ohne jegliche Metadaten (wahrscheinlich Live):
    - live_badge → "UNKNOWN"
    - published → "Gesehen am {source_date}"

    Args:
        video: VideoData-Objekt zum Modifizieren
        source_date: Zeitpunkt der HTML-Speicherung
    """
    date_str = source_date.strftime("%Y-%m-%d") if source_date else None

    if video.is_live or video.is_premiere or video.is_upcoming:
        # Fallback für bekannte Live-Stati
        if not video.published_date and date_str:
            video.published_date = date_str

            if video.is_live:
                video.published = f"Live am {date_str}"
            elif video.is_premiere:
                video.published = f"Premiere am {date_str}"
            elif video.is_upcoming:
                video.published = f"Geplant am {date_str}"

        if video.views_count is None:
            video.views_count = 0

            if video.is_live:
                video.views = "Live"
            elif video.is_premiere:
                video.views = "Premiere"
            elif video.is_upcoming:
                video.views = "Geplant"

    elif not video.published and not video.views:
        # Video ohne Metadaten → wahrscheinlich Live oder spezieller Status
        video.live_badge = "UNKNOWN"

        if date_str:
            video.published_date = date_str
            video.published = f"Gesehen am {date_str}"


def extract_thumbnail_url(video_id: str, data: dict = None, prefer_quality: str = "hq720") -> str:
    """
    Extract thumbnail URL from video data or generate from video_id.

    Args:
        video_id: YouTube video ID
        data: Optional dict containing thumbnail data from ytInitialData
        prefer_quality: Preferred quality (hq720, mqdefault, sddefault, maxresdefault)

    Returns:
        Thumbnail URL string
    """
    # If data provided, try to extract from there
    if data:
        # For lockupViewModel
        if "contentImage" in data:
            sources = data.get("contentImage", {}).get("thumbnailViewModel", {}).get("image", {}).get("sources", [])
            if sources:
                # Return highest resolution available
                return sources[-1].get("url", "")

        # For videoRenderer
        if "thumbnail" in data:
            thumbnails = data.get("thumbnail", {}).get("thumbnails", [])
            if thumbnails:
                return thumbnails[-1].get("url", "")

    # Fallback: generate URL from video_id
    return f"https://i.ytimg.com/vi/{video_id}/{prefer_quality}.jpg"


def extract_shorts(data: dict) -> list[VideoData]:
    """Extract video data from Shorts page."""
    videos = []
    
    try:
        tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
        
        for tab in tabs:
            tab_content = tab.get("tabRenderer", {}).get("content", {})
            grid_contents = tab_content.get("richGridRenderer", {}).get("contents", [])
            
            for item in grid_contents:
                rich_item = item.get("richItemRenderer", {}).get("content", {})
                shorts_vm = rich_item.get("shortsLockupViewModel", {})
                
                if not shorts_vm:
                    continue
                
                # Extract video ID
                video_id = None
                entity_id = shorts_vm.get("entityId", "")
                if "shorts-shelf-item-" in entity_id:
                    video_id = entity_id.replace("shorts-shelf-item-", "")
                
                # Alternative: from onTap command
                if not video_id:
                    on_tap = shorts_vm.get("onTap", {}).get("innertubeCommand", {})
                    video_id = on_tap.get("reelWatchEndpoint", {}).get("videoId")
                
                if not video_id:
                    continue
                
                # Extract title and views from accessibilityText
                acc_text = shorts_vm.get("accessibilityText", "")
                title = ""
                views = ""
                
                # Pattern: "Title, X Aufrufe – Short abspielen"
                match = re.match(r'^(.+?),\s*([\d.,]+)\s*Aufrufe', acc_text)
                if match:
                    title = match.group(1).strip()
                    views = f"{match.group(2)} Aufrufe"
                else:
                    # Fallback: take everything before last comma
                    parts = acc_text.rsplit(',', 1)
                    title = parts[0].strip() if parts else acc_text
                
                # Extract thumbnail
                thumbnail_url = extract_thumbnail_url(video_id, shorts_vm)

                videos.append(VideoData(
                    video_id=video_id,
                    title=title,
                    views=views,
                    views_count=parse_views_count(views),
                    video_type="short",
                    thumbnail_url=thumbnail_url
                ))
                
    except Exception as e:
        logger.error(f"Error extracting shorts: {e}")
    
    return videos


def extract_algorithm_videos(data: dict) -> list[VideoData]:
    """Extract video data from algorithm/homepage."""
    videos = []
    
    def process_video_renderer(renderer: dict) -> Optional[VideoData]:
        """Process a videoRenderer object."""
        video_id = renderer.get("videoId")
        if not video_id:
            return None

        # Title
        title_obj = renderer.get("title", {})
        title = title_obj.get("simpleText") or ""
        if not title and "runs" in title_obj:
            title = "".join(run.get("text", "") for run in title_obj["runs"])

        # Channel
        owner_obj = renderer.get("ownerText", {})
        channel = ""
        if "runs" in owner_obj:
            channel = owner_obj["runs"][0].get("text", "")

        # Views
        views_obj = renderer.get("viewCountText", {})
        views = views_obj.get("simpleText", "")

        # Published time
        published_obj = renderer.get("publishedTimeText", {})
        published = published_obj.get("simpleText", "")

        # Duration
        length_obj = renderer.get("lengthText", {})
        duration = length_obj.get("simpleText", "")

        # Thumbnail
        thumbnail_url = extract_thumbnail_url(video_id, renderer)

        # Live-Status erkennen
        live_status = detect_live_status(renderer)

        return VideoData(
            video_id=video_id,
            title=title,
            channel=channel,
            views=views,
            views_count=parse_views_count(views),
            published=published,
            duration=duration,
            video_type="video",
            thumbnail_url=thumbnail_url,
            is_live=live_status["is_live"],
            is_premiere=live_status["is_premiere"],
            is_upcoming=live_status["is_upcoming"],
            live_badge=live_status["live_badge"]
        )
    
    def process_lockup_view_model(vm: dict) -> Optional[VideoData]:
        """Process a lockupViewModel object (newer format)."""
        # Try to get video ID from various locations
        video_id = None

        # From rendererContext or contentId
        content_id = vm.get("contentId", "")
        if content_id:
            video_id = content_id

        # From onTap command
        on_tap = vm.get("onTap", {}).get("innertubeCommand", {})
        watch_endpoint = on_tap.get("watchEndpoint", {})
        if not video_id:
            video_id = watch_endpoint.get("videoId")

        if not video_id:
            return None

        # Metadata
        metadata = vm.get("metadata", {}).get("lockupMetadataViewModel", {})

        # Title
        title_obj = metadata.get("title", {})
        title = title_obj.get("content", "")

        # Extract other metadata from metadataRows
        channel = ""
        views = ""
        published = ""

        meta_vm = metadata.get("metadata", {}).get("contentMetadataViewModel", {})
        for row in meta_vm.get("metadataRows", []):
            for part in row.get("metadataParts", []):
                text_obj = part.get("text", {})
                text = text_obj.get("content", "")

                if "Aufrufe" in text or "views" in text.lower():
                    views = text
                elif "vor" in text.lower() or "ago" in text.lower():
                    published = text
                elif text and not channel:
                    # First non-view, non-time text is likely channel
                    channel = text

        # Duration from thumbnail overlay
        duration = ""
        content_image = vm.get("contentImage", {}).get("thumbnailViewModel", {})
        for overlay in content_image.get("overlays", []):
            badge_vm = overlay.get("thumbnailOverlayBadgeViewModel", {})
            for badge in badge_vm.get("thumbnailBadges", []):
                text = badge.get("thumbnailBadgeViewModel", {}).get("text", "")
                if re.match(r'\d+:\d+', text):
                    duration = text
                    break

        # Thumbnail
        thumbnail_url = extract_thumbnail_url(video_id, vm)

        # Live-Status erkennen (aus vm, da lockupViewModel andere Struktur hat)
        live_status = detect_live_status(vm)

        return VideoData(
            video_id=video_id,
            title=title,
            channel=channel,
            views=views,
            views_count=parse_views_count(views),
            published=published,
            duration=duration,
            video_type="video",
            thumbnail_url=thumbnail_url,
            is_live=live_status["is_live"],
            is_premiere=live_status["is_premiere"],
            is_upcoming=live_status["is_upcoming"],
            live_badge=live_status["live_badge"]
        )
    
    try:
        tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
        
        for tab in tabs:
            tab_content = tab.get("tabRenderer", {}).get("content", {})
            grid_contents = tab_content.get("richGridRenderer", {}).get("contents", [])
            
            for item in grid_contents:
                rich_item = item.get("richItemRenderer", {}).get("content", {})
                
                # Try videoRenderer (older format)
                video_renderer = rich_item.get("videoRenderer")
                if video_renderer:
                    video = process_video_renderer(video_renderer)
                    if video:
                        videos.append(video)
                    continue
                
                # Try lockupViewModel (newer format)
                lockup_vm = rich_item.get("lockupViewModel")
                if lockup_vm:
                    video = process_lockup_view_model(lockup_vm)
                    if video:
                        videos.append(video)
                    continue
                
                # Check for shorts in algorithm page
                shorts_vm = rich_item.get("shortsLockupViewModel")
                if shorts_vm:
                    # Process as short
                    entity_id = shorts_vm.get("entityId", "")
                    video_id = entity_id.replace("shorts-shelf-item-", "") if "shorts-shelf-item-" in entity_id else None
                    if video_id:
                        acc_text = shorts_vm.get("accessibilityText", "")
                        match = re.match(r'^(.+?),\s*([\d.,]+)\s*Aufrufe', acc_text)
                        title = match.group(1) if match else acc_text.split(',')[0]
                        views = f"{match.group(2)} Aufrufe" if match else ""

                        # Thumbnail
                        thumbnail_url = extract_thumbnail_url(video_id, shorts_vm)

                        videos.append(VideoData(
                            video_id=video_id,
                            title=title,
                            views=views,
                            views_count=parse_views_count(views),
                            video_type="short",
                            thumbnail_url=thumbnail_url
                        ))
                        
    except Exception as e:
        logger.error(f"Error extracting algorithm videos: {e}")

    return videos


def extract_search_results(data: dict) -> list[VideoData]:
    """
    Extract video data from search results page.

    Structure:
    twoColumnSearchResultsRenderer
    └── primaryContents.sectionListRenderer.contents[]
        └── itemSectionRenderer.contents[]
            └── videoRenderer
    """
    videos = []

    try:
        search_contents = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in search_contents:
            item_section = section.get("itemSectionRenderer", {})
            for item in item_section.get("contents", []):
                video_renderer = item.get("videoRenderer")
                if video_renderer:
                    video_id = video_renderer.get("videoId")
                    if not video_id:
                        continue

                    # Title
                    title_obj = video_renderer.get("title", {})
                    title = ""
                    if "runs" in title_obj:
                        title = "".join(run.get("text", "") for run in title_obj["runs"])
                    elif "simpleText" in title_obj:
                        title = title_obj["simpleText"]

                    # Channel
                    owner_obj = video_renderer.get("ownerText", {})
                    channel = ""
                    if "runs" in owner_obj:
                        channel = owner_obj["runs"][0].get("text", "")

                    # Views
                    views_obj = video_renderer.get("viewCountText", {})
                    views = views_obj.get("simpleText", "")

                    # Published time
                    published_obj = video_renderer.get("publishedTimeText", {})
                    published = published_obj.get("simpleText", "")

                    # Duration
                    length_obj = video_renderer.get("lengthText", {})
                    duration = length_obj.get("simpleText", "")

                    # Thumbnail
                    thumbnail_url = extract_thumbnail_url(video_id, video_renderer)

                    videos.append(VideoData(
                        video_id=video_id,
                        title=title,
                        channel=channel,
                        views=views,
                        views_count=parse_views_count(views),
                        published=published,
                        duration=duration,
                        video_type="video",
                        thumbnail_url=thumbnail_url
                    ))

    except Exception as e:
        logger.error(f"Error extracting search results: {e}")

    return videos


def extract_videos_from_dom(html_content: str) -> list[VideoData]:
    """
    Extract videos from rendered DOM (e.g., SingleFile saves).

    This parser works with HTML saved via browser extensions like SingleFile,
    which capture the fully rendered DOM instead of just the source HTML.
    """
    if not BS4_AVAILABLE:
        logger.warning("BeautifulSoup4 not installed. Install with: pip install beautifulsoup4")
        return []

    videos = []
    seen_ids = set()

    try:
        soup = BeautifulSoup(html_content, 'lxml')

        # Find all ytd-rich-item-renderer elements (main video tiles)
        rich_items = soup.find_all('ytd-rich-item-renderer')
        logger.info(f"Found {len(rich_items)} rich item renderers in DOM")

        for item in rich_items:
            try:
                # Find all video links in this item
                links = item.find_all('a', href=re.compile(r'/watch\?v=|/shorts/'))
                if not links:
                    continue

                # Determine video type and find best title link
                video_id = None
                video_type = "video"
                title_link = None

                # First pass: determine video type and ID
                for link in links:
                    href = link.get('href', '')
                    if '/shorts/' in href:
                        shorts_match = re.search(r'/shorts/([a-zA-Z0-9_-]{11})', href)
                        if shorts_match:
                            video_id = shorts_match.group(1)
                            video_type = "short"
                            break
                    elif '/watch?v=' in href:
                        watch_match = re.search(r'/watch\?v=([a-zA-Z0-9_-]{11})', href)
                        if watch_match:
                            video_id = watch_match.group(1)
                            video_type = "video"
                            break

                if not video_id or video_id in seen_ids:
                    continue

                seen_ids.add(video_id)

                # Second pass: find the best link for title extraction
                if video_type == "short":
                    # For shorts: multiple links point to same video
                    # Find the one with actual text content
                    for link in links:
                        if f'/shorts/{video_id}' in link.get('href', ''):
                            link_text = link.get_text(strip=True)
                            if link_text:  # Non-empty text
                                title_link = link
                                break
                    if not title_link:
                        title_link = links[0]
                else:
                    # For videos: prefer link with aria-label
                    for link in links:
                        if f'/watch?v={video_id}' in link.get('href', ''):
                            if link.get('aria-label'):
                                title_link = link
                                break
                    if not title_link:
                        # Fallback to any link with the video ID
                        for link in links:
                            if video_id in link.get('href', ''):
                                title_link = link
                                break

                # Extract title
                title = ""
                if title_link:
                    if video_type == "short":
                        # Shorts: use link text
                        title = title_link.get_text(strip=True)
                    else:
                        # Videos: prefer aria-label, fallback to text
                        title = title_link.get('aria-label', '') or title_link.get_text(strip=True)

                # Extract channel - look for channel link in item
                channel = ""
                channel_links = item.find_all('a', href=re.compile(r'/@'))
                if channel_links:
                    channel = channel_links[0].get_text(strip=True)

                # Extract metadata from item text
                item_text = item.get_text()
                views = ""
                published = ""
                duration = ""

                # Parse views
                views_match = re.search(r'([\d.,]+\s*(?:Aufrufe|views|Mio\.\s*Aufrufe|Tsd\.\s*Aufrufe))', item_text, re.IGNORECASE)
                if views_match:
                    views = views_match.group(1).strip()

                # Parse published time
                published_match = re.search(r'(vor\s+\d+\s+(?:Minute|Stunde|Tag|Woche|Monat|Jahr|Minuten|Stunden|Tagen|Wochen|Monaten|Jahren))', item_text, re.IGNORECASE)
                if published_match:
                    published = published_match.group(1).strip()

                # Parse duration - look for time format
                duration_match = re.search(r'\b(\d+:\d+(?::\d+)?)\b', item_text)
                if duration_match:
                    duration = duration_match.group(1)

                # Create thumbnail URL
                thumbnail_url = extract_thumbnail_url(video_id)

                videos.append(VideoData(
                    video_id=video_id,
                    title=title,
                    channel=channel,
                    views=views,
                    views_count=parse_views_count(views),
                    published=published,
                    duration=duration,
                    video_type=video_type,
                    thumbnail_url=thumbnail_url
                ))

            except Exception as e:
                logger.debug(f"Error parsing rich item: {e}")
                continue

    except Exception as e:
        logger.error(f"Error in DOM parsing: {e}")

    return videos


def download_thumbnail(video_id: str, url: str, output_dir: Path) -> Optional[str]:
    """
    Download thumbnail from URL to output directory with quality fallback.

    Tries multiple quality levels if the preferred one fails:
    1. hq720 (720p) - highest quality
    2. mqdefault (320x180)
    3. sddefault (640x480)
    4. default (120x90) - lowest quality, always available

    Args:
        video_id: YouTube video ID (used for filename)
        url: Thumbnail URL
        output_dir: Directory to save thumbnail

    Returns:
        Relative path to downloaded file, or None if all downloads failed
    """
    if not url:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.jpg"

    # Skip if already downloaded
    if output_path.exists():
        logger.debug(f"Thumbnail already exists: {output_path}")
        return str(output_path)

    # Quality fallback order
    quality_levels = ["hq720", "mqdefault", "sddefault", "default"]
    base_url = f"https://i.ytimg.com/vi/{video_id}/"

    # If URL is from ytInitialData (different format), try it first
    urls_to_try = []
    if url and "ytimg.com" not in url:
        # URL from ytInitialData might be a different CDN
        urls_to_try.append(url)

    # Add standard quality fallbacks
    for quality in quality_levels:
        urls_to_try.append(f"{base_url}{quality}.jpg")

    for try_url in urls_to_try:
        try:
            urllib.request.urlretrieve(try_url, output_path)
            logger.debug(f"Downloaded thumbnail: {output_path}")
            return str(output_path)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Try next quality level
                logger.debug(f"Thumbnail not found at {try_url}, trying next quality")
                continue
            else:
                logger.debug(f"HTTP error {e.code} for {try_url}")
                continue
        except urllib.error.URLError as e:
            logger.debug(f"URL error for {try_url}: {e}")
            continue
        except Exception as e:
            logger.debug(f"Error downloading {try_url}: {e}")
            continue

    logger.warning(f"Failed to download thumbnail for {video_id} (all quality levels failed)")
    return None


def extract_videos(html_content: str, filepath: Optional[Path] = None) -> tuple[list[VideoData], str, str]:
    """
    Extract videos from HTML content.

    Supports formats:
    1. Standard HTML (Ctrl+S) - uses ytInitialData JSON
    2. SingleFile/rendered DOM - uses BeautifulSoup DOM parsing
    3. Search results pages

    Args:
        html_content: The HTML content to parse
        filepath: Optional path to the source file (for source_date calculation)

    Returns:
        Tuple of (videos, page_type, channel_name)
    """
    # Get source date for published_date calculation
    source_date = None
    source_date_str = None
    source_filename = None

    if filepath:
        source_date = get_source_date(html_content, filepath)
        source_date_str = source_date.isoformat() if source_date else None
        source_filename = filepath.name
        if source_date:
            logger.info(f"Source date: {source_date.strftime('%Y-%m-%d %H:%M:%S')}")

    # Try ytInitialData first (standard HTML save)
    data = extract_yt_initial_data(html_content)

    if data:
        # Standard JSON-based extraction
        page_type = detect_page_type(data)
        logger.info(f"Detected page type: {page_type}")

        # Try to get channel name for shorts pages
        channel_name = ""
        try:
            metadata = data.get("metadata", {}).get("channelMetadataRenderer", {})
            channel_name = metadata.get("title", "")
        except Exception:
            pass

        if page_type == "shorts":
            videos = extract_shorts(data)
            # Add channel name to all videos
            for v in videos:
                v.channel = channel_name
        elif page_type == "search":
            videos = extract_search_results(data)
        else:
            videos = extract_algorithm_videos(data)

        # Add source info and calculate published_date for all videos
        for video in videos:
            video.source_file = source_filename
            video.source_date = source_date_str
            if source_date and video.published:
                calc_date = parse_relative_time(video.published, source_date)
                if calc_date:
                    video.published_date = calc_date.strftime("%Y-%m-%d")

            # Live-Fallbacks anwenden
            if source_date:
                apply_live_fallbacks(video, source_date)

        return videos, page_type, channel_name

    # No ytInitialData found - try DOM parsing (SingleFile format)
    logger.info("No ytInitialData found, attempting DOM parsing (SingleFile format)")
    videos = extract_videos_from_dom(html_content)

    if videos:
        page_type = "algorithm"  # Assume algorithm for DOM-parsed content

        # Add source info and calculate published_date
        for video in videos:
            video.source_file = source_filename
            video.source_date = source_date_str
            if source_date and video.published:
                calc_date = parse_relative_time(video.published, source_date)
                if calc_date:
                    video.published_date = calc_date.strftime("%Y-%m-%d")

            # Live-Fallbacks anwenden
            if source_date:
                apply_live_fallbacks(video, source_date)

        return videos, page_type, ""

    return [], "unknown", ""


def output_csv(videos: list[VideoData], output_file=None):
    """Output videos as CSV."""
    fieldnames = ['video_id', 'title', 'channel', 'views', 'views_count',
                  'published', 'published_date', 'duration', 'url', 'video_type',
                  'thumbnail_url', 'thumbnail_local', 'source_file', 'source_date',
                  'is_live', 'is_premiere', 'is_upcoming', 'live_badge']
    
    if output_file:
        f = open(output_file, 'w', newline='', encoding='utf-8')
    else:
        f = sys.stdout
    
    try:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for video in videos:
            writer.writerow(asdict(video))
    finally:
        if output_file:
            f.close()


def output_json(videos: list[VideoData], source_file: str, page_type: str, 
                output_file=None, pretty=False):
    """Output videos as JSON."""
    result = {
        "source_file": source_file,
        "page_type": page_type,
        "extraction_date": datetime.now().isoformat(),
        "video_count": len(videos),
        "videos": [asdict(v) for v in videos]
    }
    
    indent = 2 if pretty else None
    json_str = json.dumps(result, ensure_ascii=False, indent=indent)

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(json_str)
    else:
        # Handle Windows console encoding issues
        try:
            print(json_str)
        except UnicodeEncodeError:
            # Fallback: encode with replacement for console output
            sys.stdout.buffer.write(json_str.encode('utf-8'))
            sys.stdout.buffer.write(b'\n')


def main():
    parser = argparse.ArgumentParser(
        description='Extract video metadata from saved YouTube HTML pages.'
    )
    parser.add_argument('input', type=Path, help='Input HTML file')
    parser.add_argument('-f', '--format', choices=['csv', 'json'], default='csv',
                        help='Output format (default: csv)')
    parser.add_argument('-o', '--output', type=Path, help='Output file (default: stdout)')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--download-thumbnails', action='store_true',
                        help='Download thumbnails to local directory')
    parser.add_argument('--thumbnail-dir', type=Path, default=Path('thumbnails'),
                        help='Directory for downloaded thumbnails (default: thumbnails)')
    parser.add_argument('--html-report', type=Path, metavar='FILE',
                        help='Generate HTML report with thumbnails')
    parser.add_argument('--open-report', action='store_true',
                        help='Open HTML report in browser after generation')

    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Read input file
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)
    
    logger.info(f"Processing: {args.input}")
    html_content = args.input.read_text(encoding='utf-8')

    # Extract videos (pass filepath for source_date calculation)
    videos, page_type, channel = extract_videos(html_content, args.input)

    if not videos:
        logger.warning("No videos found in the HTML file")
        sys.exit(0)

    logger.info(f"Found {len(videos)} videos")

    # Download thumbnails if requested
    if args.download_thumbnails:
        logger.info(f"Downloading thumbnails to {args.thumbnail_dir}")
        for video in videos:
            if video.thumbnail_url:
                local_path = download_thumbnail(video.video_id, video.thumbnail_url, args.thumbnail_dir)
                video.thumbnail_local = local_path
        logger.info("Thumbnail download complete")

    # Generate HTML report if requested
    if args.html_report:
        from html_report import generate_html_report
        thumb_dir = args.thumbnail_dir if args.download_thumbnails else None
        report_title = f"YouTube Report - {channel}" if channel else "YouTube Video Report"
        report_path = generate_html_report(videos, args.html_report, report_title, thumb_dir)
        logger.info(f"HTML report generated: {report_path}")

        if args.open_report:
            import webbrowser
            # Ensure absolute path for URI
            abs_path = report_path.resolve()
            webbrowser.open(abs_path.as_uri())

    # Output CSV/JSON
    output_path = str(args.output) if args.output else None

    if args.format == 'csv':
        output_csv(videos, output_path)
    else:
        output_json(videos, str(args.input), page_type, output_path, args.pretty)

    if output_path:
        logger.info(f"Output written to: {output_path}")


if __name__ == '__main__':
    main()
