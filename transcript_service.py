"""Service zum Abrufen von YouTube-Transkripten."""

from dataclasses import dataclass
from youtube_transcript_api import YouTubeTranscriptApi

from config import get_logger

logger = get_logger(__name__)


@dataclass
class TranscriptResult:
    """Ergebnis eines Transkript-Abrufs."""
    youtube_id: str
    text: str
    language: str
    is_auto_generated: bool


# Sprachprioritaet: Deutsch vor Englisch
PREFERRED_LANGUAGES = ['de', 'de-DE', 'en']


def get_transcript(youtube_id: str) -> TranscriptResult | None:
    """
    Holt das Transkript fuer ein YouTube-Video.

    Prioritaet:
    1. Manuelles deutsches Transkript
    2. Manuelles englisches Transkript
    3. Auto-generiertes deutsches Transkript
    4. Auto-generiertes englisches Transkript
    5. Irgendein verfuegbares Transkript
    """
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(youtube_id)

        all_transcripts = list(transcript_list)
        manual_transcripts = [t for t in all_transcripts if not t.is_generated]
        auto_transcripts = [t for t in all_transcripts if t.is_generated]

        # Versuch 1: Manuelle Transkripte in bevorzugter Sprache
        for lang in PREFERRED_LANGUAGES:
            for transcript in manual_transcripts:
                if transcript.language_code == lang or transcript.language_code.startswith(lang):
                    fetched = transcript.fetch()
                    text = _fetched_to_text(fetched)
                    logger.debug(f"Manuelles Transkript gefunden: {youtube_id} ({transcript.language_code})")
                    return TranscriptResult(
                        youtube_id=youtube_id,
                        text=text,
                        language=transcript.language_code,
                        is_auto_generated=False,
                    )

        # Versuch 2: Auto-generierte Transkripte in bevorzugter Sprache
        for lang in PREFERRED_LANGUAGES:
            for transcript in auto_transcripts:
                if transcript.language_code == lang or transcript.language_code.startswith(lang):
                    fetched = transcript.fetch()
                    text = _fetched_to_text(fetched)
                    logger.debug(f"Auto-Transkript gefunden: {youtube_id} ({transcript.language_code})")
                    return TranscriptResult(
                        youtube_id=youtube_id,
                        text=text,
                        language=transcript.language_code,
                        is_auto_generated=True,
                    )

        # Versuch 3: Irgendein verfuegbares Transkript
        if all_transcripts:
            transcript = all_transcripts[0]
            fetched = transcript.fetch()
            text = _fetched_to_text(fetched)
            logger.debug(f"Alternatives Transkript: {youtube_id} ({transcript.language_code})")
            return TranscriptResult(
                youtube_id=youtube_id,
                text=text,
                language=transcript.language_code,
                is_auto_generated=transcript.is_generated,
            )

        logger.warning(f"Kein Transkript verfuegbar: {youtube_id}")
        return None

    except Exception as e:
        error_msg = str(e).lower()
        if "disabled" in error_msg:
            logger.warning(f"Transkripte deaktiviert: {youtube_id}")
        elif "unavailable" in error_msg or "not available" in error_msg:
            logger.warning(f"Video nicht verfuegbar: {youtube_id}")
        else:
            logger.error(f"Fehler beim Transkript-Abruf fuer {youtube_id}: {e}")
        return None


def _fetched_to_text(fetched) -> str:
    """Konvertiert ein FetchedTranscript zu einem zusammenhaengenden Text."""
    texts = [snippet.text.strip() for snippet in fetched]
    return ' '.join(texts)


def get_available_languages(youtube_id: str) -> list[str]:
    """Listet alle verfuegbaren Transkript-Sprachen fuer ein Video."""
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(youtube_id)
        languages = []
        for transcript in transcript_list:
            prefix = "[auto] " if transcript.is_generated else ""
            languages.append(f"{prefix}{transcript.language_code}")
        return languages
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Sprachen fuer {youtube_id}: {e}")
        return []
