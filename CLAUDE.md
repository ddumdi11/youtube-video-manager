# CLAUDE.md - Anweisungen für Claude Code

## Projektziel

Entwickle einen robusten Python-Parser zum Extrahieren von Video-Metadaten aus gespeicherten YouTube-HTML-Seiten. Der Parser soll zwei Haupttypen von Seiten UND zwei verschiedene HTML-Formate unterstützen und die Ergebnisse in strukturierter Form (CSV/JSON) ausgeben.

## Unterstützte HTML-Formate

### 1. Standard HTML (Strg+S)

- Browser-native "Save as HTML"
- Enthält `ytInitialData` JSON-Struktur
- ~20-25 Videos (initial geladene)
- Dateigröße: 2-3 MB

### 2. SingleFile / Rendered DOM

- Browser-Extension (z.B. SingleFile)
- Vollständig gerenderter DOM-Zustand
- **400+ Videos** (alle gescrollten)
- Dateigröße: 20-30 MB
- Parsing via BeautifulSoup DOM-Traversierung

## Unterstützte Seitentypen

### 1. Kanal-Shorts-Übersicht (`/@channel/shorts`)

**Datenstruktur im HTML:**
```
ytInitialData enthält:
└── contents.twoColumnBrowseResultsRenderer.tabs[]
    └── tabRenderer.content.richGridRenderer.contents[]
        └── richItemRenderer.content.shortsLockupViewModel
            ├── entityId: "shorts-shelf-item-{videoId}"
            ├── accessibilityText: "{Titel}, {Aufrufe} Aufrufe – Short abspielen"
            └── onTap.innertubeCommand.reelWatchEndpoint.videoId
```

**Zu extrahieren:**
- `videoId` → Link: `https://youtube.com/shorts/{videoId}`
- Titel (aus accessibilityText parsen)
- Aufrufe (aus accessibilityText parsen, z.B. "714 Aufrufe")

### 2. Algorithmus-Empfehlungen (Startseite)

**Datenstruktur im HTML:**
```
ytInitialData enthält:
└── contents.twoColumnBrowseResultsRenderer.tabs[]
    └── tabRenderer.content.richGridRenderer.contents[]
        └── richItemRenderer.content
            ├── lockupViewModel (neues Format)
            │   └── metadata.lockupMetadataViewModel
            │       ├── title.content
            │       └── metadata.contentMetadataViewModel.metadataRows[]
            └── videoRenderer (älteres Format)
                ├── videoId
                ├── title.runs[].text
                ├── viewCountText.simpleText
                ├── publishedTimeText.simpleText
                ├── ownerText.runs[].text
                └── lengthText.simpleText
```

**Zu extrahieren:**
- `videoId` → Link: `https://youtube.com/watch?v={videoId}`
- Titel
- Kanal-Name
- Aufrufe
- Upload-Zeitraum (z.B. "vor 3 Tagen")
- Video-Dauer

## Technische Anforderungen

### Abhängigkeiten
```
beautifulsoup4>=4.12.0
lxml>=5.0.0
```

### Parser-Logik

1. **ytInitialData extrahieren:**
   ```python
   import re
   import json
   
   pattern = r'var ytInitialData = ({.*?});'
   # oder
   pattern = r'ytInitialData\s*=\s*({.*?});'
   ```

2. **Seitentyp erkennen:**
   - Prüfe `serviceTrackingParams` auf `route: "channel.shorts"` → Shorts-Seite
   - Prüfe `browse_id: "FEwhat_to_watch"` → Startseite/Algorithmus

3. **Robustes Parsing:**
   - Mehrere Fallback-Strategien für verschiedene JSON-Strukturen
   - Graceful handling bei fehlenden Feldern
   - Unicode-Support für internationale Titel

### Output-Formate

**CSV:**
```csv
video_id,title,channel,views,published,duration,url,type
uapqiY_6ewU,"Candace Owens Questioned...",Both Sides,714,,,"https://youtube.com/shorts/uapqiY_6ewU",short
Kl9wPPY09oE,"ADHD Brain Needs This",How to ADHD,133973,vor 3 Tagen,8:15,"https://youtube.com/watch?v=Kl9wPPY09oE",video
```

**JSON:**
```json
{
  "source_file": "filename.html",
  "page_type": "shorts|algorithm",
  "extraction_date": "2024-12-13T...",
  "videos": [...]
}
```

## CLI-Interface

```bash
# Grundaufruf
python yt_extractor.py <input.html>

# Optionen
--format, -f        csv|json (default: csv)
--output, -o        Output-Datei (default: stdout)
--pretty            JSON mit Einrückung
--verbose, -v       Debug-Ausgabe
--download-thumbnails   Thumbnails herunterladen
--thumbnail-dir     Verzeichnis für Thumbnails (default: thumbnails)
--html-report FILE  HTML-Report mit Thumbnails generieren
--open-report       Report im Browser öffnen
```

## GUI-Interface

```bash
python yt_gui.py
```

Features:
- Einzelne Datei, mehrere Dateien oder Ordner auswählen
- Batch-Verarbeitung mehrerer HTML-Dateien
- Thumbnails automatisch herunterladen
- HTML-Report mit Suchfunktion und Filter
- CSV/JSON Export optional
- Fortschrittsanzeige und Log-Ausgabe

## Testfälle

Stelle sicher, dass der Parser funktioniert mit:

1. Standard HTML-Dateien (Strg+S gespeichert)
2. SingleFile-Exporte (mit vollständigem DOM)
3. Shorts-Seiten und Algorithmus-Empfehlungen
4. Verschiedene Sprachen (DE/EN)

## Thumbnail-Extraktion ✅

Die Thumbnail-URLs sind bereits im HTML enthalten und müssen extrahiert werden.

### URL-Struktur

```
https://i.ytimg.com/vi/{videoId}/hq720.jpg      # Hohe Qualität (720p)
https://i.ytimg.com/vi/{videoId}/mqdefault.jpg  # Mittlere Qualität
https://i.ytimg.com/vi/{videoId}/sddefault.jpg  # Standard
https://i.ytimg.com/vi/{videoId}/maxresdefault.jpg  # Maximale Auflösung (nicht immer verfügbar)
```

### Implementierung

1. **URL-Extraktion aus ytInitialData:**
   - Bei `lockupViewModel`: `contentImage.thumbnailViewModel.image.sources[].url`
   - Bei `videoRenderer`: `thumbnail.thumbnails[].url`
   - Bei `shortsLockupViewModel`: `onTap.innertubeCommand.reelWatchEndpoint.thumbnail.thumbnails[].url`

2. **Neues Feld in VideoData:**
   ```python
   thumbnail_url: Optional[str] = None
   ```

3. **CLI-Erweiterung für Download:**
   ```bash
   # Nur URLs extrahieren (Standard)
   python yt_extractor.py input.html
   
   # Thumbnails herunterladen
   python yt_extractor.py input.html --download-thumbnails
   python yt_extractor.py input.html --download-thumbnails --thumbnail-dir ./thumbnails
   ```

4. **Download-Logik:**
   ```python
   import urllib.request
   
   def download_thumbnail(video_id: str, url: str, output_dir: Path) -> Path:
       output_path = output_dir / f"{video_id}.jpg"
       urllib.request.urlretrieve(url, output_path)
       return output_path
   ```

5. **Qualitäts-Fallback:**
   - Versuche `hq720.jpg` zuerst
   - Fallback auf `mqdefault.jpg` wenn 404

### Output-Erweiterung

**CSV:**
```csv
video_id,title,channel,views,published,duration,url,video_type,thumbnail_url,thumbnail_local
abc123,...,...,...,...,...,...,video,https://i.ytimg.com/vi/abc123/hq720.jpg,thumbnails/abc123.jpg
```

**JSON:**
```json
{
  "video_id": "abc123",
  "thumbnail_url": "https://i.ytimg.com/vi/abc123/hq720.jpg",
  "thumbnail_local": "thumbnails/abc123.jpg"
}
```

## Implementierungsstatus

### ✅ Fertig implementiert (Teil 1 - Extraktion)

- [x] ytInitialData JSON-Parsing (Standard HTML)
- [x] DOM-Parsing für SingleFile-Exporte
- [x] Automatische Format-Erkennung
- [x] Shorts-Unterstützung (beide Formate)
- [x] Algorithmus-Empfehlungen
- [x] Thumbnail-URL-Extraktion
- [x] Thumbnail-Download mit Qualitäts-Fallback (hq720 → mqdefault → sddefault → default)
- [x] CSV/JSON Export
- [x] View-Count-Parsing (deutsche Mio./Tsd. und englische M/K Formate)
- [x] Unicode/Emoji-Support
- [x] HTML-Report-Generator (YouTube-Style Dark Theme)
- [x] Tkinter GUI für Dateiauswahl und Batch-Verarbeitung (`yt_gui.py`)
- [x] Batch-Verarbeitung mehrerer HTML-Dateien (via GUI)
- [x] Live-Video-Erkennung (LIVE, PREMIERE, UPCOMING)
- [x] Fallback-Werte für Live-Streams (source_date als published)
- [x] Live-Badges im HTML-Report (mit pulsierendem 🔴 LIVE Badge)
- [x] Filter nach Live-Status im HTML-Report

### ✅ Fertig implementiert (Teil 2 - Verwaltung)

- [x] SQLite-Datenbank (`yt_database.py`)
- [x] VideoRecord-Dataclass mit User-Feldern
- [x] Desktop-App mit Grid-Ansicht (`yt_app.py`)
- [x] Tkinter-Grid für Desktop-Ansicht mit Thumbnails
- [x] Bearbeitungs-Dialog für einzelne Videos
- [x] Eigene Kommentare zu Videos hinzufügen
- [x] Sterne-Bewertung (1-5)
- [x] Tag-System (many-to-many)
- [x] Filter nach Kanal, Typ, Rating, Live-Status
- [x] Textsuche in Titel/Kanal
- [x] Import aus HTML-Dateien in Datenbank
- [x] CSV-Export aus der App

### 🔄 In Diskussion: Zusammenführung der GUIs

Aktuell gibt es zwei GUI-Apps:

| App | Zweck | Features |
|-----|-------|----------|
| `yt_gui.py` | Extraktion + Reports | HTML→CSV/JSON, Thumbnails, HTML-Report |
| `yt_app.py` | Verwaltung + Bearbeitung | Datenbank, Grid-Ansicht, Kommentare/Tags/Rating |

**Mögliche nächste Schritte:**
1. Beide behalten (für unterschiedliche Workflows)
2. Zusammenführen zu einer einheitlichen App
3. `yt_gui.py` Features in `yt_app.py` integrieren

### Offene Erweiterungsmöglichkeiten

- [ ] Thumbnail-Download in `yt_app.py` integrieren
- [ ] HTML-Report aus Datenbank generieren (mit bearbeiteten Daten)
- [ ] Kanal-Metadaten (Abonnenten, Beschreibung)
- [ ] Playlist-Support
- [ ] Erweiterte Live-Erkennung ("LIVE" im Titel)

## Coding-Style

- Python 3.10+
- Type Hints verwenden
- Docstrings für Funktionen
- Logging statt print() für Debug-Output
- Klare Fehlerbehandlung mit aussagekräftigen Meldungen
