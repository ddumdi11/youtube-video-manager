#!/usr/bin/env python3
"""
YouTube Video Manager - Extraction GUI

Provides a graphical user interface for:
- Single file selection
- Multiple file selection
- Folder selection
- Output options (CSV, JSON, HTML Report)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from threading import Thread
import webbrowser

# Import from main module
from yt_extractor import (
    extract_videos,
    output_csv,
    output_json,
    download_thumbnail,
    VideoData,
    logger
)
from html_report import generate_html_report


class YTExtractorGUI:
    """Main GUI application for YouTube Video Manager - Extractor."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YouTube Video Manager - Extractor")
        self.root.geometry("700x600")
        self.root.minsize(650, 550)

        # Configure style
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # Variables
        self.input_files: list[Path] = []
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "output"))
        self.download_thumbs = tk.BooleanVar(value=True)
        self.generate_html = tk.BooleanVar(value=True)
        self.open_html = tk.BooleanVar(value=True)
        self.export_csv = tk.BooleanVar(value=False)
        self.export_json = tk.BooleanVar(value=False)

        self._create_widgets()

    def _create_widgets(self):
        """Create all GUI widgets."""
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === Input Section ===
        input_frame = ttk.LabelFrame(main_frame, text="Eingabe-Dateien", padding="10")
        input_frame.pack(fill=tk.X, pady=(0, 10))

        # File list
        list_frame = ttk.Frame(input_frame)
        list_frame.pack(fill=tk.X, expand=True)

        self.file_listbox = tk.Listbox(list_frame, height=6, selectmode=tk.EXTENDED)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        # Buttons for file selection
        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="Datei hinzufügen", command=self._add_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Mehrere Dateien", command=self._add_files).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Ordner hinzufügen", command=self._add_folder).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Auswahl entfernen", command=self._remove_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Alle entfernen", command=self._clear_files).pack(side=tk.LEFT)

        # === Output Section ===
        output_frame = ttk.LabelFrame(main_frame, text="Ausgabe-Einstellungen", padding="10")
        output_frame.pack(fill=tk.X, pady=(0, 10))

        # Output directory
        dir_frame = ttk.Frame(output_frame)
        dir_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(dir_frame, text="Ausgabe-Ordner:").pack(side=tk.LEFT)
        ttk.Entry(dir_frame, textvariable=self.output_dir, width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(dir_frame, text="...", width=3, command=self._browse_output).pack(side=tk.LEFT)

        # Options checkboxes
        opt_frame = ttk.Frame(output_frame)
        opt_frame.pack(fill=tk.X)

        ttk.Checkbutton(opt_frame, text="Thumbnails herunterladen",
                        variable=self.download_thumbs).pack(anchor=tk.W)
        ttk.Checkbutton(opt_frame, text="HTML-Report erstellen",
                        variable=self.generate_html).pack(anchor=tk.W)
        ttk.Checkbutton(opt_frame, text="Report im Browser öffnen",
                        variable=self.open_html).pack(anchor=tk.W, padx=(20, 0))
        ttk.Checkbutton(opt_frame, text="CSV exportieren",
                        variable=self.export_csv).pack(anchor=tk.W)
        ttk.Checkbutton(opt_frame, text="JSON exportieren",
                        variable=self.export_json).pack(anchor=tk.W)

        # === Progress Section ===
        progress_frame = ttk.LabelFrame(main_frame, text="Fortschritt", padding="10")
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        self.status_label = ttk.Label(progress_frame, text="Bereit")
        self.status_label.pack(anchor=tk.W)

        # Log area
        self.log_text = tk.Text(progress_frame, height=8, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        log_scroll = ttk.Scrollbar(self.log_text, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=log_scroll.set)

        # === Action Buttons ===
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))

        # Big prominent Start button
        self.extract_btn = ttk.Button(action_frame, text="▶ Extraktion starten",
                                       command=self._start_extraction)
        self.extract_btn.pack(side=tk.LEFT, ipadx=20, ipady=5)

        ttk.Button(action_frame, text="Beenden", command=self.root.quit).pack(side=tk.RIGHT)

    def _add_file(self):
        """Add a single HTML file."""
        file = filedialog.askopenfilename(
            title="HTML-Datei auswählen",
            filetypes=[("HTML-Dateien", "*.html *.htm"), ("Alle Dateien", "*.*")]
        )
        if file:
            self._add_to_list([file])

    def _add_files(self):
        """Add multiple HTML files."""
        files = filedialog.askopenfilenames(
            title="HTML-Dateien auswählen",
            filetypes=[("HTML-Dateien", "*.html *.htm"), ("Alle Dateien", "*.*")]
        )
        if files:
            self._add_to_list(files)

    def _add_folder(self):
        """Add all HTML files from a folder."""
        folder = filedialog.askdirectory(title="Ordner auswählen")
        if folder:
            folder_path = Path(folder)
            html_files = list(folder_path.glob("*.html")) + list(folder_path.glob("*.htm"))
            if html_files:
                self._add_to_list([str(f) for f in html_files])
            else:
                messagebox.showinfo("Info", "Keine HTML-Dateien im Ordner gefunden.")

    def _add_to_list(self, files: list[str]):
        """Add files to the listbox."""
        for file in files:
            path = Path(file)
            if path not in self.input_files:
                self.input_files.append(path)
                self.file_listbox.insert(tk.END, path.name)

    def _remove_selected(self):
        """Remove selected files from the list."""
        selection = self.file_listbox.curselection()
        for index in reversed(selection):
            self.file_listbox.delete(index)
            del self.input_files[index]

    def _clear_files(self):
        """Clear all files from the list."""
        self.file_listbox.delete(0, tk.END)
        self.input_files.clear()

    def _browse_output(self):
        """Browse for output directory."""
        folder = filedialog.askdirectory(title="Ausgabe-Ordner auswählen")
        if folder:
            self.output_dir.set(folder)

    def _log(self, message: str):
        """Add message to log area."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _update_status(self, text: str):
        """Update status label."""
        self.status_label.config(text=text)

    def _start_extraction(self):
        """Start the extraction process in a separate thread."""
        if not self.input_files:
            messagebox.showwarning("Warnung", "Bitte wählen Sie mindestens eine Datei aus.")
            return

        # Disable button during processing
        self.extract_btn.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

        # Read tkinter vars in main thread before passing to background thread
        opts = {
            "output_dir": self.output_dir.get(),
            "download_thumbs": self.download_thumbs.get(),
            "generate_html": self.generate_html.get(),
            "open_html": self.open_html.get(),
            "export_csv": self.export_csv.get(),
            "export_json": self.export_json.get(),
        }

        # Snapshot mutable file list before passing to background thread
        files_snapshot = list(self.input_files)

        # Run extraction in background thread
        thread = Thread(target=self._run_extraction, args=(opts, files_snapshot), daemon=True)
        thread.start()

    def _run_extraction(self, opts: dict, files: list[Path]):
        """Run the extraction process."""
        try:
            output_dir = Path(opts["output_dir"]).resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            thumb_dir = output_dir / "thumbnails" if opts["download_thumbs"] else None

            all_videos: list[VideoData] = []
            total_files = len(files)

            for i, input_file in enumerate(files):
                progress = (i / total_files) * 100
                self.root.after(0, lambda p=progress: self.progress_var.set(p))
                self.root.after(0, lambda f=input_file.name: self._update_status(f"Verarbeite: {f}"))
                self.root.after(0, lambda f=input_file.name: self._log(f"Verarbeite: {f}"))

                try:
                    html_content = input_file.read_text(encoding='utf-8')
                    videos, _, _ = extract_videos(html_content, input_file)

                    if videos:
                        self.root.after(0, lambda n=len(videos): self._log(f"  → {n} Videos gefunden"))

                        # Download thumbnails if requested
                        if opts["download_thumbs"] and thumb_dir:
                            for video in videos:
                                if video.thumbnail_url:
                                    local_path = download_thumbnail(
                                        video.video_id, video.thumbnail_url, thumb_dir
                                    )
                                    video.thumbnail_local = local_path

                        all_videos.extend(videos)
                    else:
                        self.root.after(0, lambda: self._log("  → Keine Videos gefunden"))

                except Exception as e:
                    self.root.after(0, lambda err=str(e): self._log(f"  → Fehler: {err}"))

            # Generate outputs
            if all_videos:
                self.root.after(0, lambda: self._update_status("Erstelle Ausgabe-Dateien..."))

                # HTML Report
                if opts["generate_html"]:
                    report_path = output_dir / "report.html"
                    generate_html_report(all_videos, report_path, "YouTube Video Report", thumb_dir)
                    self.root.after(0, lambda: self._log(f"HTML-Report erstellt: {report_path}"))

                    if opts["open_html"]:
                        self.root.after(0, lambda p=report_path: webbrowser.open(p.as_uri()))

                # CSV Export
                if opts["export_csv"]:
                    csv_path = output_dir / "videos.csv"
                    output_csv(all_videos, str(csv_path))
                    self.root.after(0, lambda: self._log(f"CSV exportiert: {csv_path}"))

                # JSON Export
                if opts["export_json"]:
                    json_path = output_dir / "videos.json"
                    output_json(all_videos, "multiple files", "mixed", str(json_path), pretty=True)
                    self.root.after(0, lambda: self._log(f"JSON exportiert: {json_path}"))

                self.root.after(0, lambda: self.progress_var.set(100))
                self.root.after(0, lambda n=len(all_videos):
                               self._update_status(f"Fertig! {n} Videos aus {total_files} Dateien extrahiert."))
                self.root.after(0, lambda n=len(all_videos):
                               self._log(f"\nFertig! Insgesamt {n} Videos extrahiert."))
            else:
                self.root.after(0, lambda: self._update_status("Keine Videos gefunden."))
                self.root.after(0, lambda: self._log("Keine Videos in den ausgewählten Dateien gefunden."))

        except Exception as e:
            self.root.after(0, lambda err=str(e): self._log(f"Fehler: {err}"))
            self.root.after(0, lambda: self._update_status("Fehler bei der Verarbeitung"))

        finally:
            self.root.after(0, lambda: self.extract_btn.config(state=tk.NORMAL))


def main():
    """Run the GUI application."""
    root = tk.Tk()
    YTExtractorGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
