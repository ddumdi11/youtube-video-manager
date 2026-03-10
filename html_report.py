#!/usr/bin/env python3
"""
HTML Report Generator for YouTube Video Manager.

Generates a visual HTML report with thumbnails and video metadata.
"""

import html
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# Import from main module
from yt_extractor import VideoData

# Allowed URL schemes for href/src attributes
_SAFE_SCHEMES = frozenset({"http", "https", "data"})


def _sanitize_url(url: str, fallback: str = "#") -> str:
    """Sanitize a URL to only allow safe schemes (http, https, data)."""
    if not url:
        return fallback
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in _SAFE_SCHEMES:
            return fallback
    except Exception:
        return fallback
    return html.escape(url, quote=True)


def generate_html_report(
    videos: list[VideoData],
    output_path: Path,
    title: str = "YouTube Video Report",
    thumbnail_dir: Optional[Path] = None
) -> Path:
    """
    Generate an HTML report with video thumbnails and metadata.

    Args:
        videos: List of VideoData objects
        output_path: Path for the HTML output file
        title: Report title
        thumbnail_dir: Directory containing downloaded thumbnails (optional)

    Returns:
        Path to the generated HTML file
    """
    # Determine thumbnail base path relative to HTML file
    if thumbnail_dir:
        try:
            thumb_base = thumbnail_dir.relative_to(output_path.parent) if thumbnail_dir.is_absolute() else thumbnail_dir
        except ValueError:
            thumb_base = thumbnail_dir
    else:
        thumb_base = Path("thumbnails")

    html_content = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>
        :root {{
            --bg-color: #0f0f0f;
            --card-bg: #1a1a1a;
            --text-color: #f1f1f1;
            --text-secondary: #aaa;
            --accent-color: #ff0000;
            --border-color: #333;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Roboto', 'Segoe UI', Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.5;
            padding: 20px;
        }}

        .header {{
            text-align: center;
            padding: 20px 0 30px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 30px;
        }}

        .header h1 {{
            font-size: 24px;
            font-weight: 500;
            margin-bottom: 10px;
        }}

        .header .stats {{
            color: var(--text-secondary);
            font-size: 14px;
        }}

        .filter-bar {{
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: center;
        }}

        .filter-bar input {{
            flex: 1;
            min-width: 200px;
            padding: 10px 15px;
            border: 1px solid var(--border-color);
            border-radius: 20px;
            background: var(--card-bg);
            color: var(--text-color);
            font-size: 14px;
        }}

        .filter-bar input:focus {{
            outline: none;
            border-color: var(--accent-color);
        }}

        .filter-bar select {{
            padding: 10px 15px;
            border: 1px solid var(--border-color);
            border-radius: 20px;
            background: var(--card-bg);
            color: var(--text-color);
            font-size: 14px;
            cursor: pointer;
        }}

        .video-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 20px;
        }}

        .video-card {{
            background: var(--card-bg);
            border-radius: 12px;
            overflow: hidden;
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .video-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.4);
        }}

        .thumbnail-container {{
            position: relative;
            width: 100%;
            padding-top: 56.25%; /* 16:9 aspect ratio */
            background: #000;
        }}

        .thumbnail-container img {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}

        .thumbnail-container .duration {{
            position: absolute;
            bottom: 8px;
            right: 8px;
            background: rgba(0,0,0,0.8);
            color: #fff;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }}

        .thumbnail-container .video-type {{
            position: absolute;
            top: 8px;
            left: 8px;
            background: var(--accent-color);
            color: #fff;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
            text-transform: uppercase;
        }}

        .thumbnail-container .live-badge {{
            position: absolute;
            top: 8px;
            right: 8px;
            color: #fff;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
        }}

        .live-badge.live {{
            background: #ff0000;
            animation: pulse 2s infinite;
        }}

        .live-badge.premiere {{
            background: #065fd4;
        }}

        .live-badge.upcoming {{
            background: #606060;
        }}

        .live-badge.unknown {{
            background: #606060;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}

        .video-info {{
            padding: 12px;
        }}

        .video-title {{
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 8px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            line-height: 1.4;
        }}

        .video-title a {{
            color: var(--text-color);
            text-decoration: none;
        }}

        .video-title a:hover {{
            color: var(--accent-color);
        }}

        .video-meta {{
            font-size: 12px;
            color: var(--text-secondary);
        }}

        .video-meta .channel {{
            color: var(--text-color);
            margin-bottom: 4px;
        }}

        .video-meta .stats {{
            display: flex;
            gap: 8px;
        }}

        .no-results {{
            text-align: center;
            padding: 60px 20px;
            color: var(--text-secondary);
        }}

        @media (max-width: 768px) {{
            .video-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{html.escape(title)}</h1>
        <div class="stats">
            {len(videos)} Videos | Generiert am {datetime.now().strftime('%d.%m.%Y um %H:%M')}
        </div>
    </div>

    <div class="filter-bar">
        <input type="text" id="searchInput" placeholder="Videos durchsuchen..." onkeyup="filterVideos()">
        <select id="typeFilter" onchange="filterVideos()">
            <option value="all">Alle Typen</option>
            <option value="video">Nur Videos</option>
            <option value="short">Nur Shorts</option>
        </select>
        <select id="liveFilter" onchange="filterVideos()">
            <option value="all">Alle Status</option>
            <option value="live">🔴 Live</option>
            <option value="premiere">🎬 Premiere</option>
            <option value="upcoming">⏳ Geplant</option>
            <option value="unknown">? Unbekannt</option>
            <option value="normal">Normale Videos</option>
        </select>
        <select id="sortOrder" onchange="sortVideos()">
            <option value="default">Standard-Reihenfolge</option>
            <option value="date-desc">Datum (neueste zuerst)</option>
            <option value="date-asc">Datum (älteste zuerst)</option>
            <option value="views-desc">Aufrufe (absteigend)</option>
            <option value="views-asc">Aufrufe (aufsteigend)</option>
            <option value="title-asc">Titel (A-Z)</option>
            <option value="title-desc">Titel (Z-A)</option>
        </select>
    </div>

    <div class="video-grid" id="videoGrid">
"""

    # Generate video cards
    for video in videos:
        # Determine thumbnail source (sanitize URLs)
        video_id_escaped = html.escape(video.video_id, quote=True)
        fallback_thumb = f"https://i.ytimg.com/vi/{video_id_escaped}/mqdefault.jpg"
        if video.thumbnail_local:
            thumb_src = html.escape(str(thumb_base / f"{video.video_id}.jpg"), quote=True)
        elif video.thumbnail_url:
            thumb_src = _sanitize_url(video.thumbnail_url, fallback=fallback_thumb)
        else:
            thumb_src = fallback_thumb

        # Sanitize video URL
        video_url = _sanitize_url(video.url, fallback=f"https://youtube.com/watch?v={video_id_escaped}")

        # Escape HTML in text fields
        title_escaped = html.escape(video.title or "Unbekannter Titel")
        channel_escaped = html.escape(video.channel or "")
        views_escaped = html.escape(video.views or "")
        published_escaped = html.escape(video.published or "")

        # Build meta info
        meta_parts = []
        if video.views:
            meta_parts.append(views_escaped)
        if video.published_date:
            meta_parts.append(html.escape(video.published_date))
        elif video.published:
            meta_parts.append(published_escaped)
        meta_text = " • ".join(meta_parts) if meta_parts else ""

        # Get published_date for sorting (use source_date as fallback for display)
        published_date = video.published_date or ""

        # Derive canonical live state from booleans and live_badge
        live_state = ""
        live_badge_html = ""
        if video.is_live:
            live_state = "LIVE"
            live_badge_html = '<span class="live-badge live">🔴 LIVE</span>'
        elif video.is_premiere:
            live_state = "PREMIERE"
            live_badge_html = '<span class="live-badge premiere">🎬 PREMIERE</span>'
        elif video.is_upcoming:
            live_state = "UPCOMING"
            live_badge_html = '<span class="live-badge upcoming">⏳ GEPLANT</span>'
        elif video.live_badge == "UNKNOWN":
            live_state = "UNKNOWN"
            live_badge_html = '<span class="live-badge unknown">?</span>'

        html_content += f"""
        <div class="video-card" data-type="{html.escape(video.video_type, quote=True)}" data-views="{video.views_count or 0}" data-title="{title_escaped.lower()}" data-date="{published_date}" data-live="{live_state}">
            <div class="thumbnail-container">
                <a href="{video_url}" target="_blank">
                    <img src="{thumb_src}" alt="{title_escaped}" loading="lazy"
                         onerror="this.src='{fallback_thumb}'">
                </a>
                {f'<span class="duration">{html.escape(video.duration)}</span>' if video.duration else ''}
                {f'<span class="video-type">Short</span>' if video.video_type == "short" else ''}
                {live_badge_html}
            </div>
            <div class="video-info">
                <div class="video-title">
                    <a href="{video_url}" target="_blank">{title_escaped}</a>
                </div>
                <div class="video-meta">
                    {f'<div class="channel">{channel_escaped}</div>' if channel_escaped else ''}
                    <div class="stats">{meta_text}</div>
                </div>
            </div>
        </div>
"""

    html_content += """
    </div>

    <div class="no-results" id="noResults" style="display: none;">
        Keine Videos gefunden.
    </div>

    <script>
        function filterVideos() {
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const typeFilter = document.getElementById('typeFilter').value;
            const liveFilter = document.getElementById('liveFilter').value;
            const cards = document.querySelectorAll('.video-card');
            let visibleCount = 0;

            cards.forEach(card => {
                const title = card.dataset.title;
                const type = card.dataset.type;
                const liveStatus = (card.dataset.live || '').toUpperCase();

                const matchesSearch = title.includes(searchTerm);
                const matchesType = typeFilter === 'all' || type === typeFilter;

                let matchesLive = true;
                if (liveFilter === 'live') {
                    matchesLive = liveStatus === 'LIVE';
                } else if (liveFilter === 'premiere') {
                    matchesLive = liveStatus === 'PREMIERE';
                } else if (liveFilter === 'upcoming') {
                    matchesLive = liveStatus === 'UPCOMING';
                } else if (liveFilter === 'unknown') {
                    matchesLive = liveStatus === 'UNKNOWN';
                } else if (liveFilter === 'normal') {
                    matchesLive = liveStatus === '';
                }

                if (matchesSearch && matchesType && matchesLive) {
                    card.style.display = '';
                    visibleCount++;
                } else {
                    card.style.display = 'none';
                }
            });

            document.getElementById('noResults').style.display = visibleCount === 0 ? '' : 'none';
        }

        function sortVideos() {
            const grid = document.getElementById('videoGrid');
            const cards = Array.from(grid.querySelectorAll('.video-card'));
            const sortOrder = document.getElementById('sortOrder').value;

            cards.sort((a, b) => {
                switch(sortOrder) {
                    case 'date-desc':
                        return (b.dataset.date || '').localeCompare(a.dataset.date || '');
                    case 'date-asc':
                        return (a.dataset.date || '').localeCompare(b.dataset.date || '');
                    case 'views-desc':
                        return parseInt(b.dataset.views) - parseInt(a.dataset.views);
                    case 'views-asc':
                        return parseInt(a.dataset.views) - parseInt(b.dataset.views);
                    case 'title-asc':
                        return a.dataset.title.localeCompare(b.dataset.title);
                    case 'title-desc':
                        return b.dataset.title.localeCompare(a.dataset.title);
                    default:
                        return 0;
                }
            });

            cards.forEach(card => grid.appendChild(card));
        }
    </script>
</body>
</html>
"""

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding='utf-8')

    return output_path


if __name__ == '__main__':
    # Test with sample data
    sample_videos = [
        VideoData(
            video_id="dQw4w9WgXcQ",
            title="Rick Astley - Never Gonna Give You Up",
            channel="Rick Astley",
            views="1.5 Mio. Aufrufe",
            views_count=1500000,
            published="vor 15 Jahren",
            duration="3:33",
            video_type="video",
            thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hq720.jpg"
        ),
        VideoData(
            video_id="abc123",
            title="Test Short Video",
            views="50.000 Aufrufe",
            views_count=50000,
            video_type="short",
            thumbnail_url="https://i.ytimg.com/vi/abc123/hq720.jpg"
        ),
    ]

    output = generate_html_report(sample_videos, Path("test_report.html"))
    print(f"Report generated: {output}")
