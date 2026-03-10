"""Parser fuer OneTab HTML-Exporte und Clipboard-Text."""

import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from config import get_logger

logger = get_logger(__name__)

# Regex fuer YouTube Video-IDs
YOUTUBE_URL_PATTERNS = [
    r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
]


@dataclass
class ParsedVideo:
    """Ein aus OneTab extrahiertes Video."""
    youtube_id: str
    url: str
    title: str | None
    group: str | None


def extract_youtube_id(url: str) -> str | None:
    """Extrahiert die YouTube Video-ID aus einer URL."""
    for pattern in YOUTUBE_URL_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_youtube_url(url: str) -> bool:
    """Prueft ob eine URL eine YouTube-URL ist."""
    return extract_youtube_id(url) is not None


def parse_onetab_text(text_content: str) -> list[ParsedVideo]:
    """
    Parst OneTab Text-Export (aus Zwischenablage).
    Format: URL | (Zahl) Titel - YouTube
    """
    videos: list[ParsedVideo] = []
    seen_ids: set[str] = set()

    for line in text_content.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        parts = line.split(' | ', 1)
        url = parts[0].strip()

        title = None
        if len(parts) > 1:
            title_part = parts[1].strip()
            title_match = re.match(r'^\(\d+\)\s*(.+?)(?:\s*-\s*YouTube)?$', title_part)
            if title_match:
                title = title_match.group(1).strip()
            else:
                title = re.sub(r'\s*-\s*YouTube$', '', title_part).strip()

        youtube_id = extract_youtube_id(url)

        if youtube_id and youtube_id not in seen_ids:
            seen_ids.add(youtube_id)
            videos.append(ParsedVideo(
                youtube_id=youtube_id,
                url=url,
                title=title if title else None,
                group=None,
            ))

    logger.info(f"Gefunden: {len(videos)} YouTube-Videos ({len(seen_ids)} unique)")
    return videos


def parse_onetab_content(content: str) -> list[ParsedVideo]:
    """Erkennt automatisch das Format und parst OneTab-Export (HTML oder Text)."""
    content_stripped = content.strip()
    if content_stripped.startswith('<') or '<html' in content_stripped.lower():
        return parse_onetab_html(content)
    else:
        return parse_onetab_text(content)


def parse_onetab_html(html_content: str) -> list[ParsedVideo]:
    """Parst OneTab HTML-Export und extrahiert YouTube-Videos."""
    soup = BeautifulSoup(html_content, 'lxml')
    videos: list[ParsedVideo] = []
    seen_ids: set[str] = set()

    tab_groups = soup.find_all('div', class_='tabGroup')

    if tab_groups:
        for group in tab_groups:
            group_label_elem = group.find('div', class_='tabGroupLabel')
            group_name = group_label_elem.get_text(strip=True) if group_label_elem else None

            for link in group.find_all('a', href=True):
                url = link['href']
                youtube_id = extract_youtube_id(url)
                if youtube_id and youtube_id not in seen_ids:
                    seen_ids.add(youtube_id)
                    videos.append(ParsedVideo(
                        youtube_id=youtube_id,
                        url=url,
                        title=link.get_text(strip=True) or None,
                        group=group_name,
                    ))
    else:
        for link in soup.find_all('a', href=True):
            url = link['href']
            youtube_id = extract_youtube_id(url)
            if youtube_id and youtube_id not in seen_ids:
                seen_ids.add(youtube_id)
                videos.append(ParsedVideo(
                    youtube_id=youtube_id,
                    url=url,
                    title=link.get_text(strip=True) or None,
                    group=None,
                ))

    logger.info(f"Gefunden: {len(videos)} YouTube-Videos ({len(seen_ids)} unique)")

    total_youtube_links = sum(
        1 for link in soup.find_all('a', href=True)
        if is_youtube_url(link['href'])
    )
    duplicates = total_youtube_links - len(videos)
    if duplicates > 0:
        logger.info(f"Duplikate uebersprungen: {duplicates}")

    return videos


def parse_onetab_file(file_path: Path | str) -> list[ParsedVideo]:
    """Liest und parst eine OneTab HTML-Datei."""
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")

    if file_path.suffix.lower() not in ['.html', '.htm', '.txt']:
        logger.warning(f"Unerwartete Dateiendung: {file_path.suffix}")

    logger.info(f"Parse OneTab-Export: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    return parse_onetab_content(content)


def get_group_summary(videos: list[ParsedVideo]) -> dict[str | None, int]:
    """Erstellt eine Uebersicht der Videos nach Gruppen."""
    summary: dict[str | None, int] = {}
    for video in videos:
        group = video.group or "(Keine Gruppe)"
        summary[group] = summary.get(group, 0) + 1
    return summary
