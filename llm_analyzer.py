"""LLM-Analyse mit Claude API fuer YouTube-Transkripte und Claim-Extraktion."""

import json
import time
from dataclasses import dataclass

from anthropic import Anthropic

from config import get_api_key, get_logger

logger = get_logger(__name__)

# Claude Modell
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096

# --- System-Prompts ---

SUMMARY_SYSTEM_PROMPT = """Du analysierst YouTube-Video-Transkripte. Erstelle fuer jedes Video:

1. ZUSAMMENFASSUNG (3-5 Saetze): Worum geht es im Video?
2. KERNAUSSAGEN (Bullet Points): Die wichtigsten Punkte/Argumente
3. PERSONEN: Erwaehnte oder interviewte Personen mit Kontext
4. THEMEN-TAGS: 3-5 Schlagworte zur Kategorisierung

Antworte auf Deutsch. Sei praezise und neutral."""

CHAT_SYSTEM_PROMPT_TEMPLATE = """Du bist ein Assistent, der Fragen zu einer Sammlung von YouTube-Videos beantwortet.
Du hast Zugriff auf Transkripte und Zusammenfassungen der folgenden Videos:

{video_context}

Beantworte Fragen basierend auf diesem Wissen. Wenn du Informationen aus
einem bestimmten Video verwendest, nenne den Videotitel.
Wenn die Frage nicht aus den Videos beantwortet werden kann, sage das klar.
Antworte auf Deutsch."""

CLAIM_EXTRACTION_PROMPT = """Du bist ein Fakten-Extraktions-Assistent.

Analysiere das folgende Video-Transkript und extrahiere die wichtigsten Behauptungen/Claims.

Fuer jeden Claim liefere:
- speaker: Name oder Kanal der Person
- topic: Kurze Kategorie (z.B. finances, security, character, religion, timeline, meta, politics, media, society)
- quote_text: Repraesentatives Zitat (max. 40 Woerter)
- stance: Einschaetzung (neutral, supportive, critical, controversial, other)
- context_note: Kurze Erlaeuterung in eigenen Worten (1 Satz)

Extrahiere bis zu {max_claims} Claims. Antworte als reines JSON-Array.
Beispiel:
[
  {{
    "speaker": "Max Mustermann",
    "topic": "politics",
    "quote_text": "Die Situation ist komplexer als dargestellt...",
    "stance": "critical",
    "context_note": "Sprecher kritisiert die vereinfachte Darstellung in den Medien."
  }}
]

Antworte NUR mit dem JSON-Array, kein weiterer Text."""


@dataclass
class SummaryResult:
    """Ergebnis einer Video-Zusammenfassung."""
    summary: str
    themes: list[str]
    raw_response: str


@dataclass
class ClaimResult:
    """Ein extrahierter Claim aus einem Video."""
    speaker: str
    topic: str
    quote_text: str
    stance: str
    context_note: str = ""
    source_url: str = ""


class LLMAnalyzer:
    """Claude-basierte Analyse von Video-Transkripten."""

    def __init__(self):
        api_key = get_api_key()
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY nicht gesetzt! "
                "Bitte in .env-Datei oder Umgebungsvariable setzen."
            )
        self.client = Anthropic(api_key=api_key)
        self._last_request_time = 0.0
        self._min_request_interval = 0.5

    def _rate_limit(self) -> None:
        """Einfaches Rate-Limiting zwischen API-Calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def summarize_transcript(
        self,
        transcript: str,
        title: str | None = None,
        channel: str | None = None,
    ) -> SummaryResult | None:
        """Erstellt eine Zusammenfassung eines Video-Transkripts."""
        self._rate_limit()

        context_parts = []
        if title:
            context_parts.append(f"Titel: {title}")
        if channel:
            context_parts.append(f"Kanal: {channel}")

        context = "\n".join(context_parts) if context_parts else ""

        user_message = f"""Analysiere das folgende Video-Transkript:

{context}

TRANSKRIPT:
{transcript}

Erstelle eine strukturierte Analyse wie im System-Prompt beschrieben."""

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SUMMARY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            raw_response = response.content[0].text
            themes = self._extract_themes(raw_response)

            logger.debug(f"Zusammenfassung erstellt fuer: {title or 'Unbekannt'}")

            return SummaryResult(
                summary=raw_response,
                themes=themes,
                raw_response=raw_response,
            )

        except Exception as e:
            logger.error(f"Fehler bei der Zusammenfassung: {e}")
            return None

    def extract_claims(
        self,
        transcript: str,
        title: str | None = None,
        channel: str | None = None,
        source_url: str = "",
        max_claims: int = 5,
    ) -> list[ClaimResult]:
        """
        Extrahiert Behauptungen/Claims aus einem Video-Transkript.

        Basiert auf dem Konzept der n8n_youtube_analysen Claim-Extraktion.
        """
        self._rate_limit()

        context_parts = []
        if title:
            context_parts.append(f"Titel: {title}")
        if channel:
            context_parts.append(f"Kanal: {channel}")

        context = "\n".join(context_parts) if context_parts else ""

        system_prompt = CLAIM_EXTRACTION_PROMPT.format(max_claims=max_claims)

        user_message = f"""{context}

TRANSKRIPT:
{transcript}"""

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            raw_text = response.content[0].text.strip()

            # JSON-Array parsen
            claims_data = json.loads(raw_text)

            claims = []
            for item in claims_data:
                claims.append(ClaimResult(
                    speaker=item.get("speaker", "Unbekannt"),
                    topic=item.get("topic", ""),
                    quote_text=item.get("quote_text", ""),
                    stance=item.get("stance", "neutral"),
                    context_note=item.get("context_note", ""),
                    source_url=source_url,
                ))

            logger.debug(f"{len(claims)} Claims extrahiert fuer: {title or 'Unbekannt'}")
            return claims

        except json.JSONDecodeError as e:
            logger.error(f"JSON-Parse-Fehler bei Claim-Extraktion: {e}")
            return []
        except Exception as e:
            logger.error(f"Fehler bei der Claim-Extraktion: {e}")
            return []

    def chat(
        self,
        user_message: str,
        video_context: str,
        chat_history: list[dict] | None = None,
    ) -> str | None:
        """Beantwortet eine Frage basierend auf den Video-Inhalten."""
        self._rate_limit()

        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            video_context=video_context
        )

        messages = []
        if chat_history:
            for msg in chat_history:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=messages,
            )

            answer = response.content[0].text
            logger.debug("Chat-Antwort generiert")
            return answer

        except Exception as e:
            logger.error(f"Fehler beim Chat: {e}")
            return None

    def _extract_themes(self, response: str) -> list[str]:
        """Extrahiert Themen-Tags aus der Claude-Antwort."""
        themes = []
        lines = response.split('\n')
        in_themes_section = False

        for line in lines:
            line_lower = line.lower()
            if 'themen' in line_lower and ('tag' in line_lower or ':' in line):
                in_themes_section = True
                if ':' in line:
                    tags_part = line.split(':', 1)[1]
                    themes.extend(self._parse_tags(tags_part))
                continue

            if in_themes_section:
                if line.strip() == '' or (line.strip() and line.strip()[0].isdigit()):
                    break
                themes.extend(self._parse_tags(line))

        return themes[:5]

    def _parse_tags(self, text: str) -> list[str]:
        """Parst Tags aus einem Text-String."""
        text = text.strip()
        if text.startswith(('-', '*', '\u2022', '\u2013')):
            text = text[1:].strip()

        if ',' in text:
            tags = [t.strip() for t in text.split(',')]
        else:
            tags = [text] if text else []

        cleaned = []
        for tag in tags:
            tag = tag.strip(' -*\u2022#')
            if tag and len(tag) > 1:
                cleaned.append(tag)
        return cleaned


def build_video_context(videos: list[dict]) -> str:
    """
    Baut einen Kontext-String aus einer Liste von Videos fuer den Chat.

    Args:
        videos: Liste von Dicts mit keys: title, channel, summary, transcript_text
    """
    context_parts = []

    for i, video in enumerate(videos, 1):
        title = video.get('title', 'Unbekannt')
        channel = video.get('channel', 'Unbekannt')
        summary = video.get('summary', '')
        transcript = video.get('transcript_text', '')

        part = f"""--- VIDEO {i}: {title} ---
Kanal: {channel}
"""
        if summary:
            part += f"\nZusammenfassung:\n{summary}\n"

        # Transkript kuerzen falls zu lang
        if transcript and not summary:
            max_len = 2000
            if len(transcript) > max_len:
                transcript = transcript[:max_len] + "... [gekuerzt]"
            part += f"\nTranskript-Auszug:\n{transcript}\n"

        context_parts.append(part)

    return "\n".join(context_parts)
