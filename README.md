# YouTube Video Manager

> ### *"Every ripple reveals the pond."*
> ### *„Jede Welle offenbart den Teich."*

---

## Warum dieses Tool?

**EN:** *A single investigation becomes a goldmine—not just through what the subject reveals, but through the entire ecosystem of reactions it triggers. Supporters, critics, bystanders, opportunists: each response adds another layer of data. The obvious questions—"who did it?" and "who's behind it?"—are merely two among thousands that emerge when we refuse to arbitrarily exclude inconvenient subsets and instead examine every stratum of the discourse.*

*This tool extracts the raw material. The refining is up to you.*

**DE:** *Eine einzelne Untersuchung wird zur Goldgrube – nicht nur durch das, was das Subjekt offenbart, sondern durch das gesamte Ökosystem an Reaktionen, das sie auslöst. Unterstützer, Kritiker, Zuschauer, Opportunisten: Jede Reaktion fügt eine weitere Datenschicht hinzu. Die offensichtlichen Fragen – „Wer war es?" und „Wer steckt dahinter?" – sind nur zwei unter Tausenden, die entstehen, wenn wir uns weigern, unbequeme Teilmengen willkürlich auszuschließen, und stattdessen jede Schicht des Diskurses untersuchen.*

*Dieses Werkzeug extrahiert das Rohmaterial. Das Veredeln liegt bei dir.*

---

## Analyse-Perspektiven (für spätere Erweiterung)

Jede Kommunikation enthält eine **Selbstoffenbarung** – bewusst oder unbewusst. Bei der Analyse der extrahierten Daten lassen sich verschiedene Ebenen betrachten:

- **Inhaltliche Ebene**: Was wird gesagt? Welche Fakten, Behauptungen, Narrative?
- **Reaktions-Ebene**: Wer reagiert wie? Welche Muster zeigen sich bei Unterstützern vs. Kritikern?
- **Meta-Ebene**: Was verrät die *Art* der Reaktion über den Reakteur selbst?
- **Netzwerk-Ebene**: Wer verlinkt wen? Welche Cluster entstehen?
- **Temporale Ebene**: Wie entwickelt sich der Diskurs über Zeit?

*Diese Perspektiven können in zukünftigen Versionen durch spezifische Analyse-Module unterstützt werden.*

---

## Überblick

Eine Python-Desktop-Anwendung zum Extrahieren, Verwalten und KI-gestützten Analysieren von YouTube-Video-Metadaten.

### Kernfunktionen

- **Video-Extraktion** aus gespeicherten YouTube-HTML-Seiten (Standard + SingleFile)
- **Video-Manager** mit YouTube-Style Dark Theme, Thumbnails, Tags, Ratings
- **KI-Analyse** mit Claude: Zusammenfassungen, Themen-Erkennung, Chat
- **Claim-Extraktion**: Automatische Behauptungs-Extraktion aus Transkripten
- **OneTab-Import**: Videos direkt aus OneTab-Exporten importieren
- **Transkript-Service**: YouTube-Transkripte automatisch abrufen

### Unterstützte Import-Formate

| Format | Videos | Beschreibung |
|--------|--------|--------------|
| Standard HTML (Strg+S) | ~20-25 | Schnell, JSON-basiert |
| SingleFile-Export | **400+** | Komplett gescrollte Seiten |
| OneTab-Export | beliebig | Clipboard-Paste oder Datei |

## Installation

```bash
# Repository klonen
git clone https://github.com/ddumdi11/youtube-video-manager.git
cd youtube-video-manager

# Virtuelle Umgebung erstellen und aktivieren
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# Abhängigkeiten installieren
pip install -r requirements.txt

# API-Key konfigurieren (für KI-Analyse)
copy .env.example .env
# .env editieren und ANTHROPIC_API_KEY eintragen
```

### Schnellstart (Windows)

```bash
start.bat
```

## Verwendung

### Video-Manager (Hauptanwendung)

```bash
python yt_app.py
```

**Features:**
- Grid-Ansicht mit Thumbnails (YouTube-Style Dark Theme)
- SQLite-Datenbank für persistente Speicherung
- Videos bearbeiten: Metadaten, Kommentare, Sterne-Bewertung (1-5), Tags
- Filter nach Kanal, Typ, Rating, Live-Status
- Import: HTML-Dateien, Ordner, OneTab-Export
- **Analyse-Menü:**
  - Transkripte automatisch abrufen
  - KI-Analyse (Zusammenfassung, Themen, Personen)
  - Claim-Extraktion (Behauptungen strukturiert extrahieren)
  - Metadaten via yt-dlp aktualisieren
  - Chat: Fragen zur Video-Sammlung stellen
- Analyse-Status-Badges auf jeder Video-Card (T/A/!)
- CSV-Export mit Analyse-Spalten

### Extraktions-GUI

```bash
python yt_gui.py
```

Für schnelle Batch-Extraktion von HTML-Dateien zu CSV/JSON/HTML-Reports.

### CLI

```bash
# CSV-Export
python yt_extractor.py input.html -o results.csv

# JSON mit pretty-print
python yt_extractor.py input.html --format json --pretty -o results.json

# HTML-Report mit Thumbnails
python yt_extractor.py input.html --html-report report.html --download-thumbnails --open-report

# Verbose-Modus
python yt_extractor.py input.html -v
```

## KI-Analyse-Pipeline

```
1. Videos importieren (HTML / OneTab / Ordner)
      ↓
2. Metadaten aktualisieren (yt-dlp) — optional
      ↓
3. Transkripte holen (youtube-transcript-api)
      ↓
4. KI-Analyse starten (Claude: Zusammenfassung + Themen)
      ↓
5. Claims extrahieren (strukturierte Behauptungen)
      ↓
6. Chat: Fragen an die Video-Sammlung stellen
```

Jeder Schritt ist über das **Analyse-Menü** in der App erreichbar und läuft als Batch über alle relevanten Videos.

## SingleFile Extension (empfohlen für > 20 Videos)

Für **Chromium-basierte Browser** (Chrome, Edge, Brave, Comet):

- Chrome Web Store: [SingleFile](https://chromewebstore.google.com/detail/singlefile/mpiodijhokgodhhofbcjdecpffjipkle)

Für **Firefox**:

- Add-ons: [SingleFile](https://addons.mozilla.org/de/firefox/addon/single-file/)

**Verwendung:**

1. Extension installieren
2. YouTube-Seite öffnen und komplett herunterscrollen
3. Rechtsklick → "Save Page with SingleFile"
4. Mit diesem Tool parsen → **400+ Videos** extrahiert!

## Technische Details

### Parser-Modi

#### 1. JSON-Modus (Standard HTML)

- Extrahiert `ytInitialData` JSON-Struktur
- Unterstützt `shortsLockupViewModel` (Shorts)
- Unterstützt `videoRenderer` und `lockupViewModel` (normale Videos)
- Schnell und präzise für ~20-25 Videos

#### 2. DOM-Modus (SingleFile)

- BeautifulSoup-basiertes HTML-Parsing
- Traversiert `ytd-rich-item-renderer` Elemente
- Extrahiert Metadaten aus aria-labels und DOM-Text
- Unterstützt **400+ Videos** aus gescrollten Seiten

### Live-Video-Erkennung

| Status | Badge | Beschreibung |
|--------|-------|--------------|
| **LIVE** | LIVE | Aktiver Live-Stream |
| **PREMIERE** | PREMIERE | Geplante Premiere |
| **UPCOMING** | GEPLANT | Geplanter Stream |

### Datenbank-Schema

SQLite mit automatischer Migration (aktuell Schema v2):
- **videos**: Metadaten, Analyse-Daten, User-Annotationen
- **tags** + **video_tags**: Many-to-many Tag-System
- **chat_history**: Persistenter Chat-Verlauf
- **import_history**: Audit-Trail aller Importe

## Projektstruktur

```text
youtube-video-manager/
├── README.md              # Diese Datei
├── requirements.txt       # Python-Abhängigkeiten
├── .env.example           # API-Key Template
├── start.bat              # Windows-Starter
├── yt_app.py              # Video-Manager (Hauptanwendung)
├── yt_gui.py              # Extraktions-GUI
├── yt_extractor.py        # Extraktions-Engine (CLI)
├── yt_database.py         # SQLite-Datenbank-Modul
├── html_report.py         # HTML-Report-Generator
├── config.py              # Konfiguration und Logging
├── transcript_service.py  # Transkript-Abruf
├── metadata_service.py    # Metadaten via yt-dlp
├── llm_analyzer.py        # KI-Analyse (Claude)
├── onetab_parser.py       # OneTab-Import-Parser
├── yt_videos.db           # Datenbank (wird erstellt)
├── thumbnails/            # Heruntergeladene Thumbnails
└── output/                # Generierte Reports/Exports
```

## Zwei GUI-Apps

| App | Starten | Zweck |
|-----|---------|-------|
| `yt_app.py` | `python yt_app.py` | Datenbank-Verwaltung, Analyse, Chat |
| `yt_gui.py` | `python yt_gui.py` | Schnelle Extraktion → HTML-Report/CSV |

**Empfehlung:** Für dauerhafte Sammlung und Analyse → `yt_app.py`. Für einmalige Reports → `yt_gui.py`.

## Lizenz

MIT License - Für Forschungs- und Analysezwecke.
