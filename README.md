# YT Overview Extractor

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

Ein Python-Tool zum Extrahieren von Video-Metadaten aus gespeicherten YouTube-HTML-Seiten.

### Unterstützte Formate

1. **Standard HTML** (Strg+S) - ~20-25 Videos
2. **SingleFile-Export** - **400+ Videos** (komplett gescrollte Seiten!)

### Unterstützte Seitentypen

1. **Kanal-Shorts-Übersicht** (`/@channel/shorts`)
2. **Algorithmus-Empfehlungen** (YouTube-Startseite)

## Extrahierte Daten

| Feld | Shorts | Algorithmus |
|------|--------|-------------|
| Video-ID | ✅ | ✅ |
| Titel | ✅ | ✅ |
| Aufrufe | ✅ | ✅ |
| Kanal | ❌ (aus Kontext) | ✅ |
| Upload-Zeitraum | ❌ | ✅ |
| Dauer | ❌ (Shorts=<60s) | ✅ |
| Thumbnail-URL | ✅ | ✅ |
| Live-Status | ✅ | ✅ |
| Live-Badge | ✅ | ✅ |

## Installation

```bash
pip install -r requirements.txt
```

## Verwendung

### Schnellstart (Standard HTML)

```bash
# 1. YouTube-Seite öffnen
# 2. Strg+S → "Webseite, nur HTML" speichern
# 3. Extrahieren (~ 20-25 Videos)
python yt_extractor.py input.html -o results.csv
```

### Für viele Videos (SingleFile)

```bash
# 1. SingleFile Extension installieren (siehe unten)
# 2. YouTube-Seite öffnen und KOMPLETT herunterscrollen
# 3. Rechtsklick → "Save with SingleFile"
# 4. Extrahieren (400+ Videos!)
python yt_extractor.py singlefile.html -o results.csv
```

### Weitere Optionen

```bash
# JSON-Format mit pretty-print
python yt_extractor.py input.html --format json --pretty -o results.json

# Mit Thumbnail-Download
python yt_extractor.py input.html --download-thumbnails
python yt_extractor.py input.html --download-thumbnails --thumbnail-dir ./my_thumbs

# HTML-Report generieren (mit Thumbnails und Filterung)
python yt_extractor.py input.html --html-report report.html --download-thumbnails
python yt_extractor.py input.html --html-report report.html --open-report

# Verbose-Modus für Debugging
python yt_extractor.py input.html -v
```

## GUI-Oberfläche

Für eine grafische Benutzeroberfläche (keine zusätzlichen Abhängigkeiten):

```bash
python yt_gui.py
```

**Features der GUI:**

- Einzelne Datei, mehrere Dateien oder ganzen Ordner auswählen
- Batch-Verarbeitung mehrerer HTML-Dateien
- Thumbnails automatisch herunterladen
- HTML-Report mit Suchfunktion und Filter generieren
- CSV/JSON Export optional
- Fortschrittsanzeige und Log-Ausgabe
- Report automatisch im Browser öffnen

**HTML-Report Features:**

- YouTube-Style Dark Theme
- Responsive Video-Grid mit Thumbnails
- Suchfunktion (nach Titel)
- Filter nach Typ (Videos/Shorts)
- Filter nach Live-Status (Live/Premiere/Geplant/Unbekannt)
- Sortierung (Aufrufe aufsteigend/absteigend, Titel A-Z/Z-A)
- Live-Badges mit visueller Hervorhebung (🔴 LIVE pulsierend)
- Fallback auf Online-Thumbnails wenn lokale nicht verfügbar

## SingleFile Extension (empfohlen für > 20 Videos)

Für **Chromium-basierte Browser** (Chrome, Edge, Brave, **Comet**):

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

#### Automatische Format-Erkennung

Der Parser erkennt automatisch, welches Format vorliegt und wählt die passende Methode!

### Live-Video-Erkennung

Live-Streams, Premieren und geplante Videos werden automatisch erkannt:

| Status | Badge | Beschreibung |
|--------|-------|--------------|
| **LIVE** | 🔴 LIVE | Aktiver Live-Stream |
| **PREMIERE** | 🎬 PREMIERE | Geplante Premiere |
| **UPCOMING** | ⏳ GEPLANT | Geplanter Stream (noch nicht gestartet) |
| **UNKNOWN** | ? | Video ohne Metadaten (wahrscheinlich Live) |

**Fallback-Werte für Live-Videos:**

Da Live-Videos oft keine Aufrufzahlen oder Veröffentlichungsdatum haben, werden automatisch sinnvolle Fallback-Werte gesetzt:

- `published` → "Live am {source_date}" / "Premiere am {source_date}"
- `views` → "Live" / "Premiere" / "Geplant"
- `views_count` → 0

Das `source_date` ist der Zeitpunkt, an dem die HTML-Seite gespeichert wurde.

## Video-Manager App (NEU)

Für die Verwaltung und Bearbeitung der extrahierten Videos:

```bash
python yt_app.py
```

**Features der Manager-App:**

- Grid-Ansicht mit Thumbnails (YouTube-Style)
- SQLite-Datenbank für persistente Speicherung
- Videos bearbeiten: Metadaten korrigieren, Kommentare hinzufügen
- Sterne-Bewertung (1-5)
- Tag-System für eigene Kategorisierung
- Filter nach Kanal, Typ, Rating, Live-Status
- Textsuche in Titel und Kanal
- Import direkt aus HTML-Dateien
- CSV-Export der gefilterten Ergebnisse
- Klick auf Video → Bearbeiten oder im Browser öffnen

**Workflow:**

1. `File → Import HTML` oder `Import Folder`
2. Videos werden in Datenbank gespeichert (`yt_videos.db`)
3. Klick auf Karte → Bearbeitungs-Dialog
4. Kommentare/Tags/Rating hinzufügen
5. Fehlende Metadaten manuell ergänzen (z.B. bei Live-Videos)

## Projektstruktur

```text
yt_overview_extractor/
├── CLAUDE.md           # Anweisungen für Claude Code
├── README.md           # Diese Datei
├── requirements.txt    # Python-Abhängigkeiten
├── yt_extractor.py     # Haupt-Script (CLI)
├── yt_gui.py           # GUI für Extraktion + Reports
├── yt_app.py           # GUI für Verwaltung + Bearbeitung (NEU)
├── yt_database.py      # SQLite-Datenbank-Modul (NEU)
├── html_report.py      # HTML-Report-Generator
├── yt_videos.db        # SQLite-Datenbank (wird erstellt)
├── test_data/          # Test-HTML-Dateien
└── output/             # Generierte Exports
```

## Zwei GUI-Apps

| App | Starten | Zweck |
|-----|---------|-------|
| `yt_gui.py` | `python yt_gui.py` | Schnelle Extraktion → HTML-Report/CSV |
| `yt_app.py` | `python yt_app.py` | Datenbank-Verwaltung, Bearbeitung, Tags |

**Empfehlung:** Für einmalige Reports → `yt_gui.py`. Für dauerhafte Sammlung → `yt_app.py`.

## Lizenz

MIT License - Für Forschungs- und Analysezwecke.
