# Start-Prompt für Claude Code

Kopiere diesen Text am Anfang einer neuen Session:

---

## Projekt: YT Overview Extractor

Du arbeitest am **YT Overview Extractor** - ein Python-Tool zum Extrahieren und Verwalten von YouTube-Video-Metadaten aus gespeicherten HTML-Seiten.

### Aktueller Stand (2024-12-20)

**Fertige Komponenten:**

| Datei | Zweck |
|-------|-------|
| `yt_extractor.py` | CLI-Parser (HTML → CSV/JSON) |
| `yt_gui.py` | GUI für Extraktion + HTML-Reports |
| `yt_app.py` | **NEU:** Desktop-App mit SQLite-Datenbank |
| `yt_database.py` | **NEU:** Datenbank-Modul |
| `html_report.py` | HTML-Report-Generator |

**Features:**
- Parsing von Standard-HTML und SingleFile-Exporten
- Shorts + normale Videos
- Live-Erkennung (LIVE, PREMIERE, UPCOMING)
- Thumbnail-Download
- Neue App: Grid-Ansicht, Kommentare, Tags, Rating, Filter

### Offene Entscheidung

Es gibt zwei GUI-Apps mit Überschneidungen:
- `yt_gui.py` - Extraktion + Reports
- `yt_app.py` - Datenbank-Verwaltung

**Optionen:**
1. Beide behalten (unterschiedliche Workflows)
2. Zusammenführen zu einer App
3. Features von `yt_gui.py` in `yt_app.py` integrieren

### Bekannte Issues

- Live-Videos ohne Badge werden nicht immer erkannt (z.B. "LIVE" nur im Titel)
- Fehlende View-Counts bei Live-Streams → manuell in `yt_app.py` ergänzbar

### Nächste mögliche Schritte

- [ ] GUI-Zusammenführung entscheiden
- [ ] Thumbnail-Download in `yt_app.py`
- [ ] HTML-Report aus Datenbank (mit bearbeiteten Daten)
- [ ] Erweiterte Live-Erkennung

### Coding-Style

- Python 3.10+
- Type Hints
- Docstrings
- Logging statt print()

---

**Lies zuerst CLAUDE.md für Details!**
