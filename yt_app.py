"""
YouTube Video Manager - Desktop Application

A standalone app for managing extracted YouTube video metadata.
Features:
- Grid view with thumbnails (YouTube-style cards)
- Edit video metadata, add comments, ratings, tags
- Filter and search functionality
- SQLite database storage
- Transcript extraction and AI analysis (merged from youtube_analyzer_proto)
- Claim extraction (merged from n8n_youtube_analysen concept)
- Chat interface for questions about video collection
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from PIL import Image, ImageTk
import urllib.request
import io
import json
import threading
from pathlib import Path
from typing import Optional, List, Dict, Callable
import logging
import webbrowser

from config import setup_logging, get_logger
from yt_database import VideoDatabase, VideoRecord, get_database
from yt_extractor import extract_videos, VideoData

setup_logging()
logger = get_logger(__name__)


# =============================================================================
# Analysis Status Icons
# =============================================================================
STATUS_ICONS = {
    "none": "",
    "transcript": "T",
    "analyzed": "A",
    "error": "!",
}

STATUS_COLORS = {
    "none": "#606060",
    "transcript": "#f0a030",
    "analyzed": "#30c050",
    "error": "#cc3030",
}


class ThumbnailCache:
    """Cache for loaded thumbnail images."""

    def __init__(self, max_size: int = 200):
        self.cache: Dict[str, ImageTk.PhotoImage] = {}
        self.max_size = max_size

    def get(self, video_id: str) -> Optional[ImageTk.PhotoImage]:
        return self.cache.get(video_id)

    def set(self, video_id: str, image: ImageTk.PhotoImage):
        if len(self.cache) >= self.max_size:
            oldest = next(iter(self.cache))
            del self.cache[oldest]
        self.cache[video_id] = image

    def clear(self):
        self.cache.clear()


class VideoCard(ttk.Frame):
    """A card widget displaying a video thumbnail and info."""

    THUMB_WIDTH = 320
    THUMB_HEIGHT = 180

    def __init__(self, parent, video: VideoRecord, on_click: Callable, thumbnail_cache: ThumbnailCache):
        super().__init__(parent, style="Card.TFrame")

        self.video = video
        self.on_click = on_click
        self.thumbnail_cache = thumbnail_cache
        self.photo_image = None

        self.configure(padding=5)

        # Thumbnail frame
        self.thumb_frame = ttk.Frame(self, style="Thumb.TFrame")
        self.thumb_frame.pack(fill=tk.X)

        self.thumb_label = ttk.Label(self.thumb_frame, text="Loading...",
                                     anchor=tk.CENTER, style="Thumb.TLabel")
        self.thumb_label.pack()

        # Live badge overlay
        if video.is_live or video.live_badge == "LIVE":
            badge = ttk.Label(self.thumb_frame, text=" \u25cf LIVE ",
                             style="LiveBadge.TLabel")
            badge.place(relx=0.02, rely=0.05)
        elif video.is_premiere or video.live_badge == "PREMIERE":
            badge = ttk.Label(self.thumb_frame, text=" PREMIERE ",
                             style="PremiereBadge.TLabel")
            badge.place(relx=0.02, rely=0.05)
        elif video.is_upcoming or video.live_badge == "UPCOMING":
            badge = ttk.Label(self.thumb_frame, text=" UPCOMING ",
                             style="UpcomingBadge.TLabel")
            badge.place(relx=0.02, rely=0.05)

        # Duration badge (bottom right)
        if video.duration:
            dur_label = ttk.Label(self.thumb_frame, text=f" {video.duration} ",
                                 style="Duration.TLabel")
            dur_label.place(relx=0.98, rely=0.95, anchor=tk.SE)

        # Analysis status badge (top right)
        status = video.analysis_status or "none"
        if status != "none":
            icon = STATUS_ICONS.get(status, "?")
            style_name = f"Status{status.capitalize()}.TLabel"
            status_badge = ttk.Label(self.thumb_frame, text=f" {icon} ",
                                    style=style_name)
            status_badge.place(relx=0.98, rely=0.05, anchor=tk.NE)

        # Info section
        info_frame = ttk.Frame(self, style="CardInfo.TFrame")
        info_frame.pack(fill=tk.X, pady=(5, 0))

        title_text = video.title[:50] + "..." if len(video.title) > 50 else video.title
        self.title_label = ttk.Label(info_frame, text=title_text,
                                     wraplength=self.THUMB_WIDTH - 10,
                                     style="CardTitle.TLabel")
        self.title_label.pack(anchor=tk.W)

        if video.channel:
            ttk.Label(info_frame, text=video.channel,
                     style="CardChannel.TLabel").pack(anchor=tk.W)

        meta_parts = []
        if video.views:
            meta_parts.append(video.views)
        if video.published:
            meta_parts.append(video.published)
        if meta_parts:
            ttk.Label(info_frame, text=" \u2022 ".join(meta_parts),
                     style="CardMeta.TLabel").pack(anchor=tk.W)

        # User annotations + analysis indicator
        annotation_parts = []
        if video.user_rating:
            annotation_parts.append("\u2605" * video.user_rating)
        if video.user_tags:
            annotation_parts.append(f"[{', '.join(video.user_tags[:2])}]")
        if video.user_comment:
            annotation_parts.append("\U0001F4AC")
        if video.transcript_text:
            annotation_parts.append("T")
        if video.summary:
            annotation_parts.append("S")
        if video.claims and video.claims != "[]":
            annotation_parts.append("C")

        if annotation_parts:
            ttk.Label(info_frame, text=" ".join(annotation_parts),
                     style="CardAnnotation.TLabel").pack(anchor=tk.W)

        # Bind click events
        for widget in [self, self.thumb_frame, self.thumb_label, info_frame,
                      self.title_label]:
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

        self._load_thumbnail()

    def _on_click(self, event):
        self.on_click(self.video)

    def _on_enter(self, event):
        self.configure(style="CardHover.TFrame")

    def _on_leave(self, event):
        self.configure(style="Card.TFrame")

    def _load_thumbnail(self):
        cached = self.thumbnail_cache.get(self.video.video_id)
        if cached:
            self._set_thumbnail(cached)
            return

        def load():
            try:
                image = None
                if self.video.thumbnail_local and Path(self.video.thumbnail_local).exists():
                    image = Image.open(self.video.thumbnail_local)
                elif self.video.thumbnail_url:
                    with urllib.request.urlopen(self.video.thumbnail_url, timeout=5) as response:
                        data = response.read()
                    image = Image.open(io.BytesIO(data))

                if image:
                    # Resize in background, but create PhotoImage on main thread
                    resized = image.resize((self.THUMB_WIDTH, self.THUMB_HEIGHT), Image.Resampling.LANCZOS)
                    self.after(0, lambda img=resized: self._set_thumbnail_from_pil(img))
            except Exception as e:
                logger.debug(f"Failed to load thumbnail for {self.video.video_id}: {e}")
                self.after(0, self._set_placeholder)

        threading.Thread(target=load, daemon=True).start()

    def _set_thumbnail_from_pil(self, pil_image: Image.Image):
        """Create PhotoImage on main thread and set it."""
        photo = ImageTk.PhotoImage(pil_image)
        self._set_thumbnail(photo)

    def _set_thumbnail(self, photo: ImageTk.PhotoImage):
        self.photo_image = photo
        self.thumbnail_cache.set(self.video.video_id, photo)
        self.thumb_label.configure(image=photo, text="")

    def _set_placeholder(self):
        self.thumb_label.configure(text=f"[{self.video.video_type.upper()}]")


class VideoEditDialog(tk.Toplevel):
    """Dialog for editing video metadata, viewing transcript and summary."""

    def __init__(self, parent, video: VideoRecord, db: VideoDatabase, on_save: Optional[Callable] = None):
        super().__init__(parent)

        self.video = video
        self.db = db
        self.on_save = on_save
        self.result = None

        self.title(f"Edit: {video.title[:50]}...")
        self.geometry("700x850")
        self.resizable(True, True)

        self.transient(parent)
        self.grab_set()

        self._create_widgets()
        self._load_data()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        # Scrollable main container
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        main_frame = ttk.Frame(canvas, padding=10)
        canvas.create_window((0, 0), window=main_frame, anchor=tk.NW)
        main_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        # Scope mousewheel to this canvas only (not bind_all which leaks globally)
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        main_frame.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # Title
        ttk.Label(main_frame, text="Title:", font=("", 10, "bold")).pack(anchor=tk.W)
        self.title_text = tk.Text(main_frame, height=2, wrap=tk.WORD)
        self.title_text.pack(fill=tk.X, pady=(0, 10))

        # Channel
        ttk.Label(main_frame, text="Channel:").pack(anchor=tk.W)
        self.channel_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.channel_var).pack(fill=tk.X, pady=(0, 10))

        # Views + Published
        views_frame = ttk.Frame(main_frame)
        views_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(views_frame, text="Views:").pack(side=tk.LEFT)
        self.views_var = tk.StringVar()
        ttk.Entry(views_frame, textvariable=self.views_var, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Label(views_frame, text="Published:").pack(side=tk.LEFT, padx=(20, 0))
        self.published_var = tk.StringVar()
        ttk.Entry(views_frame, textvariable=self.published_var, width=20).pack(side=tk.LEFT, padx=5)

        # Duration + Type
        dur_frame = ttk.Frame(main_frame)
        dur_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(dur_frame, text="Duration:").pack(side=tk.LEFT)
        self.duration_var = tk.StringVar()
        ttk.Entry(dur_frame, textvariable=self.duration_var, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Label(dur_frame, text="Type:").pack(side=tk.LEFT, padx=(20, 0))
        self.type_var = tk.StringVar()
        ttk.Combobox(dur_frame, textvariable=self.type_var, width=10,
                     values=["video", "short"], state="readonly").pack(side=tk.LEFT, padx=5)

        # Live status
        live_frame = ttk.LabelFrame(main_frame, text="Live Status", padding=5)
        live_frame.pack(fill=tk.X, pady=(0, 10))
        self.is_live_var = tk.BooleanVar()
        self.is_premiere_var = tk.BooleanVar()
        self.is_upcoming_var = tk.BooleanVar()
        ttk.Checkbutton(live_frame, text="Live", variable=self.is_live_var).pack(side=tk.LEFT)
        ttk.Checkbutton(live_frame, text="Premiere", variable=self.is_premiere_var).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(live_frame, text="Upcoming", variable=self.is_upcoming_var).pack(side=tk.LEFT)

        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # User Comment
        ttk.Label(main_frame, text="Your Comment:", font=("", 10, "bold")).pack(anchor=tk.W)
        self.comment_text = tk.Text(main_frame, height=3, wrap=tk.WORD)
        self.comment_text.pack(fill=tk.X, pady=(0, 10))

        # Rating
        rating_frame = ttk.Frame(main_frame)
        rating_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(rating_frame, text="Your Rating:").pack(side=tk.LEFT)
        self.rating_var = tk.IntVar(value=0)
        for i in range(6):
            text = "None" if i == 0 else "\u2605" * i
            ttk.Radiobutton(rating_frame, text=text, variable=self.rating_var, value=i).pack(side=tk.LEFT, padx=5)

        # Tags
        ttk.Label(main_frame, text="Tags (comma separated):").pack(anchor=tk.W)
        self.tags_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.tags_var).pack(fill=tk.X, pady=(0, 10))

        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # === Analysis Section ===
        analysis_frame = ttk.LabelFrame(main_frame, text="KI-Analyse", padding=5)
        analysis_frame.pack(fill=tk.X, pady=(0, 10))

        # Analysis status
        status_frame = ttk.Frame(analysis_frame)
        status_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        self.analysis_status_label = ttk.Label(status_frame, text="")
        self.analysis_status_label.pack(side=tk.LEFT, padx=5)

        # Transcript info
        transcript_info_frame = ttk.Frame(analysis_frame)
        transcript_info_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(transcript_info_frame, text="Transkript:").pack(side=tk.LEFT)
        self.transcript_info_label = ttk.Label(transcript_info_frame, text="Nicht vorhanden")
        self.transcript_info_label.pack(side=tk.LEFT, padx=5)

        # Summary (read-only)
        ttk.Label(analysis_frame, text="Zusammenfassung:").pack(anchor=tk.W)
        self.summary_text = tk.Text(analysis_frame, height=6, wrap=tk.WORD, state=tk.DISABLED)
        self.summary_text.pack(fill=tk.X, pady=(0, 5))

        # Themes
        ttk.Label(analysis_frame, text="Themen:").pack(anchor=tk.W)
        self.themes_label = ttk.Label(analysis_frame, text="-", wraplength=650)
        self.themes_label.pack(anchor=tk.W, pady=(0, 5))

        # Claims count
        self.claims_label = ttk.Label(analysis_frame, text="Claims: -")
        self.claims_label.pack(anchor=tk.W)

        # URL and actions
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(url_frame, text="URL:").pack(side=tk.LEFT)
        self.url_label = ttk.Label(url_frame, text="", foreground="blue", cursor="hand2")
        self.url_label.pack(side=tk.LEFT, padx=5)
        self.url_label.bind("<Button-1>", self._open_url)
        ttk.Button(url_frame, text="Open in Browser", command=self._open_url).pack(side=tk.RIGHT)

        # Metadata
        meta_frame = ttk.LabelFrame(main_frame, text="Metadata", padding=5)
        meta_frame.pack(fill=tk.X, pady=(0, 10))
        self.meta_labels = {}
        for field in ["video_id", "source_file", "import_group", "first_seen", "last_updated"]:
            frame = ttk.Frame(meta_frame)
            frame.pack(fill=tk.X)
            ttk.Label(frame, text=f"{field}:", width=15).pack(side=tk.LEFT)
            self.meta_labels[field] = ttk.Label(frame, text="")
            self.meta_labels[field].pack(side=tk.LEFT)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Delete", command=self._delete).pack(side=tk.LEFT)

    def _load_data(self):
        v = self.video
        self.title_text.insert("1.0", v.title)
        self.channel_var.set(v.channel or "")
        self.views_var.set(v.views or "")
        self.published_var.set(v.published or "")
        self.duration_var.set(v.duration or "")
        self.type_var.set(v.video_type)

        self.is_live_var.set(v.is_live)
        self.is_premiere_var.set(v.is_premiere)
        self.is_upcoming_var.set(v.is_upcoming)

        self.comment_text.insert("1.0", v.user_comment or "")
        self.rating_var.set(v.user_rating or 0)
        self.tags_var.set(", ".join(v.user_tags) if v.user_tags else "")

        # Analysis section
        status = v.analysis_status or "none"
        status_text = {"none": "Nicht analysiert", "transcript": "Transkript vorhanden",
                       "analyzed": "Analysiert", "error": "Fehler"}.get(status, status)
        self.analysis_status_label.configure(text=status_text)

        if v.transcript_text:
            lang = v.transcript_language or "?"
            length = len(v.transcript_text)
            self.transcript_info_label.configure(text=f"{lang} ({length:,} Zeichen)")
        else:
            self.transcript_info_label.configure(text="Nicht vorhanden")

        if v.summary:
            self.summary_text.configure(state=tk.NORMAL)
            self.summary_text.insert("1.0", v.summary)
            self.summary_text.configure(state=tk.DISABLED)

        if v.themes:
            try:
                themes_list = json.loads(v.themes)
                self.themes_label.configure(text=", ".join(themes_list))
            except (json.JSONDecodeError, TypeError):
                self.themes_label.configure(text=v.themes)

        if v.claims:
            try:
                claims_list = json.loads(v.claims)
                self.claims_label.configure(text=f"Claims: {len(claims_list)}")
            except (json.JSONDecodeError, TypeError):
                self.claims_label.configure(text="Claims: ?")

        self.url_label.configure(text=v.url)
        self.meta_labels["video_id"].configure(text=v.video_id)
        self.meta_labels["source_file"].configure(text=v.source_file or "N/A")
        self.meta_labels["import_group"].configure(text=v.import_group or "N/A")
        self.meta_labels["first_seen"].configure(text=v.first_seen or "N/A")
        self.meta_labels["last_updated"].configure(text=v.last_updated or "N/A")

    def _open_url(self, event=None):
        webbrowser.open(self.video.url)

    def _save(self):
        self.video.title = self.title_text.get("1.0", tk.END).strip()
        self.video.channel = self.channel_var.get() or None
        self.video.views = self.views_var.get() or None
        self.video.published = self.published_var.get() or None
        self.video.duration = self.duration_var.get() or None
        self.video.video_type = self.type_var.get()

        self.video.is_live = self.is_live_var.get()
        self.video.is_premiere = self.is_premiere_var.get()
        self.video.is_upcoming = self.is_upcoming_var.get()

        if self.video.is_live:
            self.video.live_badge = "LIVE"
        elif self.video.is_premiere:
            self.video.live_badge = "PREMIERE"
        elif self.video.is_upcoming:
            self.video.live_badge = "UPCOMING"
        else:
            self.video.live_badge = None

        self.video.user_comment = self.comment_text.get("1.0", tk.END).strip() or None
        rating = self.rating_var.get()
        self.video.user_rating = rating if rating > 0 else None

        tags_text = self.tags_var.get()
        if tags_text:
            self.video.user_tags = [t.strip() for t in tags_text.split(",") if t.strip()]
        else:
            self.video.user_tags = []

        self.db.add_video(self.video)
        self.result = self.video
        if self.on_save:
            self.on_save(self.video)
        self.destroy()

    def _delete(self):
        if messagebox.askyesno("Delete Video",
                               f"Delete '{self.video.title[:50]}...'?\n\nThis cannot be undone."):
            self.db.delete_video(self.video.video_id)
            self.result = "deleted"
            if self.on_save:
                self.on_save(None)
            self.destroy()


class ChatDialog(tk.Toplevel):
    """Chat dialog for asking questions about the video collection."""

    def __init__(self, parent, db: VideoDatabase):
        super().__init__(parent)

        self.db = db
        self.analyzer = None
        self.chat_messages: List[Dict] = []

        self.title("Chat - Fragen zur Video-Sammlung")
        self.geometry("800x600")
        self.resizable(True, True)

        self._create_widgets()
        self._load_history()

    def _create_widgets(self):
        # Chat display
        self.chat_display = tk.Text(self, wrap=tk.WORD, state=tk.DISABLED,
                                    font=("", 10), padx=10, pady=10)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.chat_display.yview)
        self.chat_display.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_display.pack(fill=tk.BOTH, expand=True)

        # Configure text tags for styling
        self.chat_display.tag_configure("user", foreground="#3ea6ff", font=("", 10, "bold"))
        self.chat_display.tag_configure("assistant", foreground="#f1f1f1")
        self.chat_display.tag_configure("system", foreground="#aaaaaa", font=("", 9, "italic"))

        # Input area
        input_frame = ttk.Frame(self)
        input_frame.pack(fill=tk.X, padx=5, pady=5)

        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(input_frame, textvariable=self.input_var, font=("", 11))
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.input_entry.bind("<Return>", self._on_send)

        ttk.Button(input_frame, text="Senden", command=self._on_send).pack(side=tk.LEFT)
        ttk.Button(input_frame, text="Chat loeschen", command=self._clear_chat).pack(side=tk.LEFT, padx=5)

        # Status
        self.status_var = tk.StringVar(value="Bereit")
        ttk.Label(self, textvariable=self.status_var).pack(fill=tk.X, padx=5)

        self.input_entry.focus()

    def _load_history(self):
        history = self.db.get_chat_history()
        for msg in history:
            self._append_message(msg["role"], msg["content"])
            self.chat_messages.append({"role": msg["role"], "content": msg["content"]})

        if not history:
            self._append_message("system",
                "Willkommen! Stelle Fragen zu deiner Video-Sammlung.\n"
                "Analysierte Videos werden als Kontext verwendet.\n")

    def _append_message(self, role: str, content: str):
        self.chat_display.configure(state=tk.NORMAL)

        if role == "user":
            self.chat_display.insert(tk.END, "\nDu: ", "user")
            self.chat_display.insert(tk.END, content + "\n")
        elif role == "assistant":
            self.chat_display.insert(tk.END, "\nAssistent: ", "assistant")
            self.chat_display.insert(tk.END, content + "\n")
        else:
            self.chat_display.insert(tk.END, content + "\n", "system")

        self.chat_display.configure(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def _on_send(self, event=None):
        question = self.input_var.get().strip()
        if not question:
            return

        self.input_var.set("")
        self._append_message("user", question)
        self.db.add_chat_message("user", question)
        self.chat_messages.append({"role": "user", "content": question})

        self.status_var.set("Denke nach...")
        self.update()

        def do_chat():
            try:
                if self.analyzer is None:
                    from llm_analyzer import LLMAnalyzer, build_video_context
                    self.analyzer = LLMAnalyzer()

                from llm_analyzer import build_video_context

                # Build context from analyzed videos
                analyzed = self.db.get_analyzed_videos()
                if not analyzed:
                    # Fall back to videos with transcripts
                    analyzed = self.db.get_videos_by_status("transcript")

                if not analyzed:
                    self.after(0, lambda: self._show_response(
                        "Es sind noch keine Videos analysiert. "
                        "Bitte zuerst Transkripte holen und KI-Analyse starten."))
                    return

                video_dicts = []
                for v in analyzed[:30]:  # Limit to 30 for context window
                    video_dicts.append({
                        "title": v.title,
                        "channel": v.channel,
                        "summary": v.summary,
                        "transcript_text": v.transcript_text,
                    })

                context = build_video_context(video_dicts)
                answer = self.analyzer.chat(question, context, self.chat_messages[:-1])

                if answer:
                    self.after(0, lambda a=answer: self._show_response(a))
                else:
                    self.after(0, lambda: self._show_response("Fehler: Keine Antwort erhalten."))

            except ValueError as e:
                e_msg = str(e)
                self.after(0, lambda m=e_msg: self._show_response(f"API-Fehler: {m}"))
            except Exception as e:
                e_msg = str(e)
                self.after(0, lambda m=e_msg: self._show_response(f"Fehler: {m}"))

        threading.Thread(target=do_chat, daemon=True).start()

    def _show_response(self, answer: str):
        self._append_message("assistant", answer)
        self.db.add_chat_message("assistant", answer)
        self.chat_messages.append({"role": "assistant", "content": answer})
        self.status_var.set("Bereit")

    def _clear_chat(self):
        if messagebox.askyesno("Chat loeschen", "Gesamten Chat-Verlauf loeschen?"):
            self.db.clear_chat_history()
            self.chat_messages.clear()
            self.chat_display.configure(state=tk.NORMAL)
            self.chat_display.delete("1.0", tk.END)
            self.chat_display.configure(state=tk.DISABLED)
            self._append_message("system", "Chat wurde geloescht.\n")


class VideoManagerApp(tk.Tk):
    """Main application window."""

    CARDS_PER_ROW = 3
    CARD_PADDING = 10

    def __init__(self, db_path: str = "yt_videos.db"):
        super().__init__()

        self.title("YouTube Video Manager")
        self.geometry("1200x800")

        self.db = get_database(db_path)
        self.thumbnail_cache = ThumbnailCache()
        self.current_videos: List[VideoRecord] = []
        self.card_widgets: List[VideoCard] = []

        self._setup_styles()
        self._create_menu()
        self._create_widgets()
        self._load_videos()

    def _setup_styles(self):
        style = ttk.Style()
        available_themes = style.theme_names()
        if "clam" in available_themes:
            style.theme_use("clam")

        bg_dark = "#0f0f0f"
        bg_card = "#272727"
        bg_hover = "#3a3a3a"
        fg_white = "#f1f1f1"
        fg_gray = "#aaaaaa"
        fg_blue = "#3ea6ff"

        style.configure(".", background=bg_dark, foreground=fg_white)
        style.configure("TFrame", background=bg_dark)
        style.configure("TLabel", background=bg_dark, foreground=fg_white)
        style.configure("TButton", padding=5)

        style.configure("Card.TFrame", background=bg_card, relief="flat")
        style.configure("CardHover.TFrame", background=bg_hover, relief="flat")
        style.configure("Thumb.TFrame", background=bg_card)
        style.configure("Thumb.TLabel", background=bg_card, foreground=fg_gray,
                        width=40, anchor=tk.CENTER)
        style.configure("CardInfo.TFrame", background=bg_card)
        style.configure("CardTitle.TLabel", background=bg_card, foreground=fg_white,
                        font=("", 10, "bold"))
        style.configure("CardChannel.TLabel", background=bg_card, foreground=fg_gray,
                        font=("", 9))
        style.configure("CardMeta.TLabel", background=bg_card, foreground=fg_gray,
                        font=("", 8))
        style.configure("CardAnnotation.TLabel", background=bg_card, foreground=fg_blue,
                        font=("", 9))

        style.configure("LiveBadge.TLabel", background="#cc0000", foreground="white",
                        font=("", 8, "bold"))
        style.configure("PremiereBadge.TLabel", background="#065fd4", foreground="white",
                        font=("", 8, "bold"))
        style.configure("UpcomingBadge.TLabel", background="#606060", foreground="white",
                        font=("", 8, "bold"))
        style.configure("Duration.TLabel", background="black", foreground="white",
                        font=("", 8))

        # Analysis status badge styles
        style.configure("StatusTranscript.TLabel", background="#f0a030", foreground="black",
                        font=("", 8, "bold"))
        style.configure("StatusAnalyzed.TLabel", background="#30c050", foreground="black",
                        font=("", 8, "bold"))
        style.configure("StatusError.TLabel", background="#cc3030", foreground="white",
                        font=("", 8, "bold"))

        style.configure("Filter.TFrame", background="#181818")
        style.configure("Filter.TLabel", background="#181818", foreground=fg_white)
        style.configure("Filter.TEntry", fieldbackground="#303030")

        self.configure(bg=bg_dark)

    def _create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Import HTML...", command=self._import_html)
        file_menu.add_command(label="Import Folder...", command=self._import_folder)
        file_menu.add_command(label="Import OneTab...", command=self._import_onetab)
        file_menu.add_separator()
        file_menu.add_command(label="Export CSV...", command=self._export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        # Analyze menu
        analyze_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Analyse", menu=analyze_menu)
        analyze_menu.add_command(label="Transkripte holen (alle ohne Transkript)...",
                                command=self._fetch_all_transcripts)
        analyze_menu.add_command(label="KI-Analyse starten (alle mit Transkript)...",
                                command=self._analyze_all)
        analyze_menu.add_command(label="Claims extrahieren (alle analysierten)...",
                                command=self._extract_all_claims)
        analyze_menu.add_separator()
        analyze_menu.add_command(label="Metadaten aktualisieren (yt-dlp)...",
                                command=self._update_all_metadata)
        analyze_menu.add_separator()
        analyze_menu.add_command(label="Chat...", command=self._open_chat)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Refresh", command=self._load_videos)
        view_menu.add_command(label="Statistics", command=self._show_stats)

    def _create_widgets(self):
        # Filter bar
        filter_frame = ttk.Frame(self, style="Filter.TFrame", padding=10)
        filter_frame.pack(fill=tk.X)

        ttk.Label(filter_frame, text="Search:", style="Filter.TLabel").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self._on_filter_change())
        ttk.Entry(filter_frame, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(filter_frame, text="Type:", style="Filter.TLabel").pack(side=tk.LEFT)
        self.type_filter_var = tk.StringVar(value="all")
        type_combo = ttk.Combobox(filter_frame, textvariable=self.type_filter_var, width=10,
                                  values=["all", "video", "short"], state="readonly")
        type_combo.pack(side=tk.LEFT, padx=(5, 20))
        type_combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())

        ttk.Label(filter_frame, text="Channel:", style="Filter.TLabel").pack(side=tk.LEFT)
        self.channel_filter_var = tk.StringVar(value="")
        self.channel_combo = ttk.Combobox(filter_frame, textvariable=self.channel_filter_var, width=20)
        self.channel_combo.pack(side=tk.LEFT, padx=(5, 20))
        self.channel_combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())

        ttk.Label(filter_frame, text="Min Rating:", style="Filter.TLabel").pack(side=tk.LEFT)
        self.rating_filter_var = tk.StringVar(value="any")
        rating_combo = ttk.Combobox(filter_frame, textvariable=self.rating_filter_var, width=8,
                                    values=["any", "1+", "2+", "3+", "4+", "5"], state="readonly")
        rating_combo.pack(side=tk.LEFT, padx=(5, 20))
        rating_combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())

        self.live_filter_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_frame, text="Live only", variable=self.live_filter_var,
                       command=self._on_filter_change).pack(side=tk.LEFT, padx=10)

        self.count_label = ttk.Label(filter_frame, text="0 videos", style="Filter.TLabel")
        self.count_label.pack(side=tk.RIGHT)

        # Main content
        content_frame = ttk.Frame(self)
        content_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(content_frame, bg="#0f0f0f", highlightthickness=0)
        scrollbar = ttk.Scrollbar(content_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.cards_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.cards_frame, anchor=tk.NW)

        self.cards_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM)

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)
        new_cards_per_row = max(1, event.width // (VideoCard.THUMB_WIDTH + self.CARD_PADDING * 2))
        if new_cards_per_row != self.CARDS_PER_ROW:
            self.CARDS_PER_ROW = new_cards_per_row
            self._display_videos()

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _load_videos(self):
        search = self.search_var.get() if self.search_var.get() else None
        type_filter = self.type_filter_var.get()
        video_type = type_filter if type_filter != "all" else None
        channel = self.channel_filter_var.get() if self.channel_filter_var.get() else None

        rating_str = self.rating_filter_var.get()
        min_rating = None
        if rating_str != "any":
            min_rating = int(rating_str[0])

        is_live = True if self.live_filter_var.get() else None

        self.current_videos = self.db.search_videos(
            search_text=search, channel=channel, video_type=video_type,
            min_rating=min_rating, is_live=is_live,
            order_by="last_updated", descending=True,
        )

        self._update_channel_list()
        self._display_videos()

    def _update_channel_list(self):
        channels = [""] + self.db.get_channels()
        self.channel_combo["values"] = channels

    def _display_videos(self):
        for card in self.card_widgets:
            card.destroy()
        self.card_widgets.clear()

        for i, video in enumerate(self.current_videos):
            row = i // self.CARDS_PER_ROW
            col = i % self.CARDS_PER_ROW
            card = VideoCard(self.cards_frame, video, self._on_video_click, self.thumbnail_cache)
            card.grid(row=row, column=col, padx=self.CARD_PADDING, pady=self.CARD_PADDING)
            self.card_widgets.append(card)

        self.count_label.configure(text=f"{len(self.current_videos)} videos")

    def _on_filter_change(self):
        self._load_videos()

    def _on_video_click(self, video: VideoRecord):
        dialog = VideoEditDialog(self, video, self.db, on_save=self._on_video_saved)
        self.wait_window(dialog)

    def _on_video_saved(self, video: Optional[VideoRecord]):
        self._load_videos()

    # =========================================================================
    # Import Operations
    # =========================================================================

    def _import_html(self):
        filepath = filedialog.askopenfilename(
            title="Select HTML file",
            filetypes=[("HTML files", "*.html *.htm"), ("All files", "*.*")],
        )
        if filepath:
            self._do_import([filepath])

    def _import_folder(self):
        folder = filedialog.askdirectory(title="Select folder with HTML files")
        if folder:
            folder_path = Path(folder)
            html_files = list(folder_path.glob("*.html")) + list(folder_path.glob("*.htm"))
            if html_files:
                self._do_import([str(f) for f in html_files])
            else:
                messagebox.showwarning("No files", "No HTML files found in folder.")

    def _do_import(self, filepaths: List[str]):
        total = 0
        for filepath in filepaths:
            try:
                self.status_var.set(f"Importing {Path(filepath).name}...")
                self.update()
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    html_content = f.read()
                videos, _, _ = extract_videos(html_content, Path(filepath))
                count = self.db.import_from_extraction(videos, Path(filepath).name)
                total += count
            except Exception as e:
                logger.error(f"Failed to import {filepath}: {e}")
                messagebox.showerror("Import Error", f"Failed to import {filepath}:\n{e}")

        self.status_var.set(f"Imported {total} videos")
        self._load_videos()
        messagebox.showinfo("Import Complete", f"Successfully imported {total} videos from {len(filepaths)} file(s).")

    def _import_onetab(self):
        """Import videos from OneTab clipboard content or file."""
        dialog = tk.Toplevel(self)
        dialog.title("OneTab Import")
        dialog.geometry("600x400")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="OneTab-Inhalt einfuegen (Text oder HTML):").pack(anchor=tk.W, padx=10, pady=5)

        text_widget = tk.Text(dialog, wrap=tk.WORD, height=15)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        def do_import():
            content = text_widget.get("1.0", tk.END).strip()
            if not content:
                messagebox.showwarning("Leer", "Bitte OneTab-Inhalt einfuegen.")
                return

            try:
                from onetab_parser import parse_onetab_content
                parsed = parse_onetab_content(content)

                if not parsed:
                    messagebox.showwarning("Keine Videos", "Keine YouTube-Videos gefunden.")
                    return

                count = self.db.import_from_onetab(parsed, "onetab-clipboard")
                dialog.destroy()
                self._load_videos()
                messagebox.showinfo("Import fertig", f"{count} Videos aus OneTab importiert.")

            except Exception as e:
                messagebox.showerror("Fehler", f"Import fehlgeschlagen:\n{e}")

        def import_file():
            filepath = filedialog.askopenfilename(
                title="OneTab-Datei waehlen",
                filetypes=[("HTML/Text files", "*.html *.htm *.txt"), ("All files", "*.*")],
            )
            if filepath:
                try:
                    from onetab_parser import parse_onetab_file
                    parsed = parse_onetab_file(filepath)
                    count = self.db.import_from_onetab(parsed, Path(filepath).name)
                    dialog.destroy()
                    self._load_videos()
                    messagebox.showinfo("Import fertig", f"{count} Videos importiert.")
                except Exception as e:
                    messagebox.showerror("Fehler", f"Import fehlgeschlagen:\n{e}")

        ttk.Button(btn_frame, text="Importieren", command=do_import).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Datei waehlen...", command=import_file).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Abbrechen", command=dialog.destroy).pack(side=tk.RIGHT)

    # =========================================================================
    # Analysis Operations
    # =========================================================================

    def _fetch_all_transcripts(self):
        """Fetch transcripts for all videos that don't have one yet."""
        videos = [v for v in self.db.get_all_videos() if not v.transcript_text]
        if not videos:
            messagebox.showinfo("Fertig", "Alle Videos haben bereits ein Transkript.")
            return

        if not messagebox.askyesno("Transkripte holen",
                                    f"{len(videos)} Videos ohne Transkript gefunden.\n"
                                    f"Transkripte jetzt abrufen?"):
            return

        def do_fetch():
            try:
                from transcript_service import get_transcript
            except ImportError as e:
                self.after(0, lambda e=e: messagebox.showerror("Import-Fehler", str(e)))
                return

            success = 0
            errors = 0
            for i, video in enumerate(videos):
                title_short = video.title[:40]
                self.after(0, lambda i=i, t=title_short: self.status_var.set(
                    f"Transkript {i+1}/{len(videos)}: {t}..."))

                try:
                    result = get_transcript(video.video_id)
                    if result:
                        self.db.update_transcript(video.video_id, result.text, result.language)
                        success += 1
                    else:
                        self.db.update_analysis_status(video.video_id, "error")
                        errors += 1
                except Exception as e:
                    logger.error(f"Transkript-Fehler fuer {video.video_id}: {e}")
                    self.db.update_analysis_status(video.video_id, "error")
                    errors += 1

            self.after(0, lambda: self._on_batch_complete(
                f"Transkripte: {success} erfolgreich, {errors} fehlgeschlagen"))

        threading.Thread(target=do_fetch, daemon=True).start()

    def _analyze_all(self):
        """Run AI analysis on all videos with transcripts but no summary."""
        videos = [v for v in self.db.get_all_videos()
                  if v.transcript_text and not v.summary]
        if not videos:
            messagebox.showinfo("Fertig", "Keine Videos zur Analyse bereit.\n"
                               "(Brauchen Transkript, aber noch keine Zusammenfassung)")
            return

        if not messagebox.askyesno("KI-Analyse",
                                    f"{len(videos)} Videos bereit zur Analyse.\n"
                                    f"KI-Analyse jetzt starten?\n\n"
                                    f"(Benoetigt ANTHROPIC_API_KEY in .env)"):
            return

        def do_analyze():
            try:
                from llm_analyzer import LLMAnalyzer
                analyzer = LLMAnalyzer()
            except ValueError as e:
                e_msg = str(e)
                self.after(0, lambda e_msg=e_msg: messagebox.showerror("API-Fehler", e_msg))
                return

            success = 0
            errors = 0
            for i, video in enumerate(videos):
                title_short = video.title[:40]
                self.after(0, lambda i=i, t=title_short: self.status_var.set(
                    f"Analyse {i+1}/{len(videos)}: {t}..."))

                try:
                    result = analyzer.summarize_transcript(
                        video.transcript_text, title=video.title, channel=video.channel)

                    if result:
                        themes_json = json.dumps(result.themes, ensure_ascii=False)
                        self.db.update_summary(video.video_id, result.summary, themes_json)
                        success += 1
                    else:
                        self.db.update_analysis_status(video.video_id, "error")
                        errors += 1
                except Exception as e:
                    logger.error(f"Analyse-Fehler fuer {video.video_id}: {e}")
                    self.db.update_analysis_status(video.video_id, "error")
                    errors += 1

            self.after(0, lambda: self._on_batch_complete(
                f"Analyse: {success} erfolgreich, {errors} fehlgeschlagen"))

        threading.Thread(target=do_analyze, daemon=True).start()

    def _extract_all_claims(self):
        """Extract claims from all analyzed videos that don't have claims yet."""
        videos = [v for v in self.db.get_all_videos()
                  if v.transcript_text and v.summary and (not v.claims or v.claims == "[]")]
        if not videos:
            messagebox.showinfo("Fertig", "Keine Videos zur Claim-Extraktion bereit.")
            return

        if not messagebox.askyesno("Claims extrahieren",
                                    f"{len(videos)} analysierte Videos ohne Claims.\n"
                                    f"Claims jetzt extrahieren?"):
            return

        def do_extract():
            try:
                from llm_analyzer import LLMAnalyzer
                analyzer = LLMAnalyzer()
            except ValueError as e:
                e_msg = str(e)
                self.after(0, lambda e_msg=e_msg: messagebox.showerror("API-Fehler", e_msg))
                return

            success = 0
            errors = 0
            for i, video in enumerate(videos):
                title_short = video.title[:40]
                self.after(0, lambda i=i, t=title_short: self.status_var.set(
                    f"Claims {i+1}/{len(videos)}: {t}..."))

                try:
                    claims = analyzer.extract_claims(
                        video.transcript_text, title=video.title,
                        channel=video.channel, source_url=video.url)

                    if claims:
                        claims_json = json.dumps(
                            [{"speaker": c.speaker, "topic": c.topic,
                              "quote_text": c.quote_text, "stance": c.stance,
                              "context_note": c.context_note, "source_url": c.source_url}
                             for c in claims],
                            ensure_ascii=False,
                        )
                        self.db.update_claims(video.video_id, claims_json)
                        success += 1
                    else:
                        self.db.update_claims(video.video_id, "[]")
                        errors += 1
                except Exception as e:
                    logger.error(f"Claim-Fehler fuer {video.video_id}: {e}")
                    errors += 1

            self.after(0, lambda: self._on_batch_complete(
                f"Claims: {success} erfolgreich, {errors} fehlgeschlagen"))

        threading.Thread(target=do_extract, daemon=True).start()

    def _update_all_metadata(self):
        """Update metadata for videos missing channel/title info (e.g. OneTab imports)."""
        videos = [v for v in self.db.get_all_videos()
                  if not v.channel or v.title.startswith("Video ")]
        if not videos:
            messagebox.showinfo("Fertig", "Alle Videos haben bereits Metadaten.")
            return

        if not messagebox.askyesno("Metadaten aktualisieren",
                                    f"{len(videos)} Videos ohne vollstaendige Metadaten.\n"
                                    f"Metadaten jetzt via yt-dlp abrufen?"):
            return

        def do_update():
            try:
                from metadata_service import get_video_metadata, format_duration
            except ImportError as e:
                self.after(0, lambda e=e: messagebox.showerror("Import-Fehler", str(e)))
                return

            success = 0
            errors = 0
            for i, video in enumerate(videos):
                vid = video.video_id
                self.after(0, lambda i=i, v=vid: self.status_var.set(
                    f"Metadaten {i+1}/{len(videos)}: {v}..."))

                try:
                    meta = get_video_metadata(video.video_id)
                    if meta:
                        video.title = meta.title
                        video.channel = meta.channel
                        if meta.published_date:
                            video.published_date = meta.published_date
                        if meta.duration_seconds:
                            video.duration = format_duration(meta.duration_seconds)
                        if meta.view_count:
                            video.views = f"{meta.view_count:,} views"
                            video.views_count = meta.view_count
                        if meta.thumbnail_url:
                            video.thumbnail_url = meta.thumbnail_url
                        self.db.add_video(video)
                        success += 1
                except Exception as e:
                    logger.error(f"Metadaten-Fehler fuer {video.video_id}: {e}")
                    errors += 1

            self.after(0, lambda: self._on_batch_complete(
                f"Metadaten: {success} erfolgreich, {errors} fehlgeschlagen"))

        threading.Thread(target=do_update, daemon=True).start()

    def _on_batch_complete(self, message: str):
        self.status_var.set(message)
        self._load_videos()
        messagebox.showinfo("Fertig", message)

    def _open_chat(self):
        ChatDialog(self, self.db)

    # =========================================================================
    # Export & Stats
    # =========================================================================

    def _export_csv(self):
        filepath = filedialog.asksaveasfilename(
            title="Export to CSV", defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if filepath:
            try:
                import csv
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'video_id', 'title', 'channel', 'views', 'published', 'duration',
                        'url', 'video_type', 'is_live', 'user_comment', 'user_rating',
                        'user_tags', 'analysis_status', 'transcript_language', 'themes',
                    ])
                    for video in self.current_videos:
                        writer.writerow([
                            video.video_id, video.title, video.channel, video.views,
                            video.published, video.duration, video.url, video.video_type,
                            video.is_live, video.user_comment, video.user_rating,
                            ','.join(video.user_tags) if video.user_tags else '',
                            video.analysis_status, video.transcript_language, video.themes,
                        ])
                messagebox.showinfo("Export Complete",
                                   f"Exported {len(self.current_videos)} videos to {filepath}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export: {e}")

    def _show_stats(self):
        stats = self.db.get_stats()
        msg = f"""Database Statistics:

Total Videos: {stats['total_videos']}
  - Regular Videos: {stats['videos']}
  - Shorts: {stats['shorts']}
  - Live: {stats['live']}

User Data:
  - Rated: {stats['rated']}
  - With Comments: {stats['with_comments']}

Analysis:
  - With Transcript: {stats['with_transcript']}
  - With Summary: {stats['with_summary']}
  - With Claims: {stats['with_claims']}
  - Status: {stats['status_none']} none / {stats['status_transcript']} transcript / {stats['status_analyzed']} analyzed / {stats['status_error']} error

Unique Channels: {stats['channels']}
Total Tags: {stats['tags']}
"""
        messagebox.showinfo("Statistics", msg)

    def on_closing(self):
        self.db.close()
        self.destroy()


def main():
    app = VideoManagerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
