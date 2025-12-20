"""
YouTube Video Manager - Desktop Application

A standalone app for managing extracted YouTube video metadata.
Features:
- Grid view with thumbnails (YouTube-style cards)
- Edit video metadata, add comments, ratings, tags
- Filter and search functionality
- SQLite database storage
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import urllib.request
import io
import threading
from pathlib import Path
from typing import Optional, List, Dict, Callable
import logging
import webbrowser

from yt_database import VideoDatabase, VideoRecord, get_database
from yt_extractor import extract_videos, VideoData

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ThumbnailCache:
    """Cache for loaded thumbnail images."""

    def __init__(self, max_size: int = 200):
        self.cache: Dict[str, ImageTk.PhotoImage] = {}
        self.max_size = max_size

    def get(self, video_id: str) -> Optional[ImageTk.PhotoImage]:
        return self.cache.get(video_id)

    def set(self, video_id: str, image: ImageTk.PhotoImage):
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
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

        # Card container
        self.configure(padding=5)

        # Thumbnail frame (clickable)
        self.thumb_frame = ttk.Frame(self, style="Thumb.TFrame")
        self.thumb_frame.pack(fill=tk.X)

        # Thumbnail label (placeholder initially)
        self.thumb_label = ttk.Label(self.thumb_frame, text="Loading...",
                                     anchor=tk.CENTER, style="Thumb.TLabel")
        self.thumb_label.pack()

        # Live badge overlay
        if video.is_live or video.live_badge == "LIVE":
            self.live_badge = ttk.Label(self.thumb_frame, text=" \u25cf LIVE ",
                                       style="LiveBadge.TLabel")
            self.live_badge.place(relx=0.02, rely=0.05)
        elif video.is_premiere or video.live_badge == "PREMIERE":
            self.live_badge = ttk.Label(self.thumb_frame, text=" PREMIERE ",
                                       style="PremiereBadge.TLabel")
            self.live_badge.place(relx=0.02, rely=0.05)
        elif video.is_upcoming or video.live_badge == "UPCOMING":
            self.live_badge = ttk.Label(self.thumb_frame, text=" UPCOMING ",
                                       style="UpcomingBadge.TLabel")
            self.live_badge.place(relx=0.02, rely=0.05)

        # Duration badge (bottom right)
        if video.duration:
            self.duration_label = ttk.Label(self.thumb_frame, text=f" {video.duration} ",
                                           style="Duration.TLabel")
            self.duration_label.place(relx=0.98, rely=0.95, anchor=tk.SE)

        # Info section
        info_frame = ttk.Frame(self, style="CardInfo.TFrame")
        info_frame.pack(fill=tk.X, pady=(5, 0))

        # Title (truncated)
        title_text = video.title[:50] + "..." if len(video.title) > 50 else video.title
        self.title_label = ttk.Label(info_frame, text=title_text,
                                     wraplength=self.THUMB_WIDTH - 10,
                                     style="CardTitle.TLabel")
        self.title_label.pack(anchor=tk.W)

        # Channel
        if video.channel:
            self.channel_label = ttk.Label(info_frame, text=video.channel,
                                          style="CardChannel.TLabel")
            self.channel_label.pack(anchor=tk.W)

        # Views and date
        meta_parts = []
        if video.views:
            meta_parts.append(video.views)
        if video.published:
            meta_parts.append(video.published)
        if meta_parts:
            meta_text = " \u2022 ".join(meta_parts)
            self.meta_label = ttk.Label(info_frame, text=meta_text,
                                       style="CardMeta.TLabel")
            self.meta_label.pack(anchor=tk.W)

        # User annotations indicator
        annotation_parts = []
        if video.user_rating:
            annotation_parts.append("\u2605" * video.user_rating)
        if video.user_tags:
            annotation_parts.append(f"[{', '.join(video.user_tags[:2])}]")
        if video.user_comment:
            annotation_parts.append("\U0001F4AC")  # Speech bubble

        if annotation_parts:
            self.annotation_label = ttk.Label(info_frame, text=" ".join(annotation_parts),
                                             style="CardAnnotation.TLabel")
            self.annotation_label.pack(anchor=tk.W)

        # Bind click events
        for widget in [self, self.thumb_frame, self.thumb_label, info_frame,
                      self.title_label]:
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

        # Load thumbnail in background
        self._load_thumbnail()

    def _on_click(self, event):
        self.on_click(self.video)

    def _on_enter(self, event):
        self.configure(style="CardHover.TFrame")

    def _on_leave(self, event):
        self.configure(style="Card.TFrame")

    def _load_thumbnail(self):
        """Load thumbnail image in background thread."""
        # Check cache first
        cached = self.thumbnail_cache.get(self.video.video_id)
        if cached:
            self._set_thumbnail(cached)
            return

        # Load from local file or URL
        def load():
            try:
                image = None

                # Try local file first
                if self.video.thumbnail_local and Path(self.video.thumbnail_local).exists():
                    image = Image.open(self.video.thumbnail_local)
                elif self.video.thumbnail_url:
                    # Download from URL
                    with urllib.request.urlopen(self.video.thumbnail_url, timeout=5) as response:
                        data = response.read()
                    image = Image.open(io.BytesIO(data))

                if image:
                    # Resize to card size
                    image = image.resize((self.THUMB_WIDTH, self.THUMB_HEIGHT), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image)

                    # Update in main thread
                    self.after(0, lambda: self._set_thumbnail(photo))

            except Exception as e:
                logger.debug(f"Failed to load thumbnail for {self.video.video_id}: {e}")
                self.after(0, self._set_placeholder)

        thread = threading.Thread(target=load, daemon=True)
        thread.start()

    def _set_thumbnail(self, photo: ImageTk.PhotoImage):
        """Set thumbnail image."""
        self.photo_image = photo  # Keep reference
        self.thumbnail_cache.set(self.video.video_id, photo)
        self.thumb_label.configure(image=photo, text="")

    def _set_placeholder(self):
        """Set placeholder for failed thumbnails."""
        self.thumb_label.configure(text=f"[{self.video.video_type.upper()}]")


class VideoEditDialog(tk.Toplevel):
    """Dialog for editing video metadata."""

    def __init__(self, parent, video: VideoRecord, db: VideoDatabase, on_save: Optional[Callable] = None):
        super().__init__(parent)

        self.video = video
        self.db = db
        self.on_save = on_save
        self.result = None

        self.title(f"Edit: {video.title[:50]}...")
        self.geometry("600x700")
        self.resizable(True, True)

        # Make modal
        self.transient(parent)
        self.grab_set()

        self._create_widgets()
        self._load_data()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        # Main container with scrollbar
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title (read-only display)
        ttk.Label(main_frame, text="Title:", font=("", 10, "bold")).pack(anchor=tk.W)
        self.title_text = tk.Text(main_frame, height=2, wrap=tk.WORD)
        self.title_text.pack(fill=tk.X, pady=(0, 10))

        # Channel
        ttk.Label(main_frame, text="Channel:").pack(anchor=tk.W)
        self.channel_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.channel_var).pack(fill=tk.X, pady=(0, 10))

        # Views
        views_frame = ttk.Frame(main_frame)
        views_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(views_frame, text="Views:").pack(side=tk.LEFT)
        self.views_var = tk.StringVar()
        ttk.Entry(views_frame, textvariable=self.views_var, width=20).pack(side=tk.LEFT, padx=5)

        ttk.Label(views_frame, text="Published:").pack(side=tk.LEFT, padx=(20, 0))
        self.published_var = tk.StringVar()
        ttk.Entry(views_frame, textvariable=self.published_var, width=20).pack(side=tk.LEFT, padx=5)

        # Duration
        dur_frame = ttk.Frame(main_frame)
        dur_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(dur_frame, text="Duration:").pack(side=tk.LEFT)
        self.duration_var = tk.StringVar()
        ttk.Entry(dur_frame, textvariable=self.duration_var, width=15).pack(side=tk.LEFT, padx=5)

        ttk.Label(dur_frame, text="Type:").pack(side=tk.LEFT, padx=(20, 0))
        self.type_var = tk.StringVar()
        type_combo = ttk.Combobox(dur_frame, textvariable=self.type_var, width=10,
                                  values=["video", "short"], state="readonly")
        type_combo.pack(side=tk.LEFT, padx=5)

        # Live status
        live_frame = ttk.LabelFrame(main_frame, text="Live Status", padding=5)
        live_frame.pack(fill=tk.X, pady=(0, 10))

        self.is_live_var = tk.BooleanVar()
        self.is_premiere_var = tk.BooleanVar()
        self.is_upcoming_var = tk.BooleanVar()

        ttk.Checkbutton(live_frame, text="Live", variable=self.is_live_var).pack(side=tk.LEFT)
        ttk.Checkbutton(live_frame, text="Premiere", variable=self.is_premiere_var).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(live_frame, text="Upcoming", variable=self.is_upcoming_var).pack(side=tk.LEFT)

        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # User Comment
        ttk.Label(main_frame, text="Your Comment:", font=("", 10, "bold")).pack(anchor=tk.W)
        self.comment_text = tk.Text(main_frame, height=4, wrap=tk.WORD)
        self.comment_text.pack(fill=tk.X, pady=(0, 10))

        # Rating
        rating_frame = ttk.Frame(main_frame)
        rating_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(rating_frame, text="Your Rating:").pack(side=tk.LEFT)
        self.rating_var = tk.IntVar(value=0)

        for i in range(6):  # 0 = no rating, 1-5 stars
            text = "None" if i == 0 else "\u2605" * i
            rb = ttk.Radiobutton(rating_frame, text=text, variable=self.rating_var, value=i)
            rb.pack(side=tk.LEFT, padx=5)

        # Tags
        ttk.Label(main_frame, text="Tags (comma separated):").pack(anchor=tk.W)
        self.tags_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.tags_var).pack(fill=tk.X, pady=(0, 10))

        # URL and actions
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(url_frame, text="URL:").pack(side=tk.LEFT)
        self.url_label = ttk.Label(url_frame, text="", foreground="blue", cursor="hand2")
        self.url_label.pack(side=tk.LEFT, padx=5)
        self.url_label.bind("<Button-1>", self._open_url)

        ttk.Button(url_frame, text="Open in Browser", command=self._open_url).pack(side=tk.RIGHT)

        # Metadata info
        meta_frame = ttk.LabelFrame(main_frame, text="Metadata", padding=5)
        meta_frame.pack(fill=tk.X, pady=(0, 10))

        self.meta_labels = {}
        for field in ["video_id", "source_file", "first_seen", "last_updated"]:
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
        """Load video data into form."""
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

        self.url_label.configure(text=v.url)

        self.meta_labels["video_id"].configure(text=v.video_id)
        self.meta_labels["source_file"].configure(text=v.source_file or "N/A")
        self.meta_labels["first_seen"].configure(text=v.first_seen or "N/A")
        self.meta_labels["last_updated"].configure(text=v.last_updated or "N/A")

    def _open_url(self, event=None):
        """Open video URL in browser."""
        webbrowser.open(self.video.url)

    def _save(self):
        """Save changes to database."""
        # Update video object
        self.video.title = self.title_text.get("1.0", tk.END).strip()
        self.video.channel = self.channel_var.get() or None
        self.video.views = self.views_var.get() or None
        self.video.published = self.published_var.get() or None
        self.video.duration = self.duration_var.get() or None
        self.video.video_type = self.type_var.get()

        self.video.is_live = self.is_live_var.get()
        self.video.is_premiere = self.is_premiere_var.get()
        self.video.is_upcoming = self.is_upcoming_var.get()

        # Update live badge
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

        # Parse tags
        tags_text = self.tags_var.get()
        if tags_text:
            self.video.user_tags = [t.strip() for t in tags_text.split(",") if t.strip()]
        else:
            self.video.user_tags = []

        # Save to database
        self.db.add_video(self.video)

        self.result = self.video
        if self.on_save:
            self.on_save(self.video)

        self.destroy()

    def _delete(self):
        """Delete video from database."""
        if messagebox.askyesno("Delete Video",
                               f"Delete '{self.video.title[:50]}...'?\n\nThis cannot be undone."):
            self.db.delete_video(self.video.video_id)
            self.result = "deleted"
            if self.on_save:
                self.on_save(None)
            self.destroy()


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
        """Configure ttk styles for dark theme."""
        style = ttk.Style()

        # Try to use a theme that supports customization
        available_themes = style.theme_names()
        if "clam" in available_themes:
            style.theme_use("clam")

        # Colors
        bg_dark = "#0f0f0f"
        bg_card = "#272727"
        bg_hover = "#3a3a3a"
        fg_white = "#f1f1f1"
        fg_gray = "#aaaaaa"
        fg_blue = "#3ea6ff"

        # Configure styles
        style.configure(".", background=bg_dark, foreground=fg_white)
        style.configure("TFrame", background=bg_dark)
        style.configure("TLabel", background=bg_dark, foreground=fg_white)
        style.configure("TButton", padding=5)

        # Card styles
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

        # Badge styles
        style.configure("LiveBadge.TLabel", background="#cc0000", foreground="white",
                       font=("", 8, "bold"))
        style.configure("PremiereBadge.TLabel", background="#065fd4", foreground="white",
                       font=("", 8, "bold"))
        style.configure("UpcomingBadge.TLabel", background="#606060", foreground="white",
                       font=("", 8, "bold"))
        style.configure("Duration.TLabel", background="black", foreground="white",
                       font=("", 8))

        # Filter bar
        style.configure("Filter.TFrame", background="#181818")
        style.configure("Filter.TLabel", background="#181818", foreground=fg_white)
        style.configure("Filter.TEntry", fieldbackground="#303030")

        # Set window background
        self.configure(bg=bg_dark)

    def _create_menu(self):
        """Create application menu."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Import HTML...", command=self._import_html)
        file_menu.add_command(label="Import Folder...", command=self._import_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Export CSV...", command=self._export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Refresh", command=self._load_videos)
        view_menu.add_command(label="Statistics", command=self._show_stats)

    def _create_widgets(self):
        """Create main UI widgets."""
        # Filter bar
        filter_frame = ttk.Frame(self, style="Filter.TFrame", padding=10)
        filter_frame.pack(fill=tk.X)

        # Search
        ttk.Label(filter_frame, text="Search:", style="Filter.TLabel").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self._on_filter_change())
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=(5, 20))

        # Type filter
        ttk.Label(filter_frame, text="Type:", style="Filter.TLabel").pack(side=tk.LEFT)
        self.type_filter_var = tk.StringVar(value="all")
        type_combo = ttk.Combobox(filter_frame, textvariable=self.type_filter_var, width=10,
                                  values=["all", "video", "short"], state="readonly")
        type_combo.pack(side=tk.LEFT, padx=(5, 20))
        type_combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())

        # Channel filter
        ttk.Label(filter_frame, text="Channel:", style="Filter.TLabel").pack(side=tk.LEFT)
        self.channel_filter_var = tk.StringVar(value="")
        self.channel_combo = ttk.Combobox(filter_frame, textvariable=self.channel_filter_var, width=20)
        self.channel_combo.pack(side=tk.LEFT, padx=(5, 20))
        self.channel_combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())

        # Rating filter
        ttk.Label(filter_frame, text="Min Rating:", style="Filter.TLabel").pack(side=tk.LEFT)
        self.rating_filter_var = tk.StringVar(value="any")
        rating_combo = ttk.Combobox(filter_frame, textvariable=self.rating_filter_var, width=8,
                                    values=["any", "1+", "2+", "3+", "4+", "5"], state="readonly")
        rating_combo.pack(side=tk.LEFT, padx=(5, 20))
        rating_combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())

        # Live filter
        self.live_filter_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_frame, text="Live only", variable=self.live_filter_var,
                       command=self._on_filter_change).pack(side=tk.LEFT, padx=10)

        # Video count
        self.count_label = ttk.Label(filter_frame, text="0 videos", style="Filter.TLabel")
        self.count_label.pack(side=tk.RIGHT)

        # Main content area with scrollbar
        content_frame = ttk.Frame(self)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas for scrolling
        self.canvas = tk.Canvas(content_frame, bg="#0f0f0f", highlightthickness=0)
        scrollbar = ttk.Scrollbar(content_frame, orient=tk.VERTICAL, command=self.canvas.yview)

        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Frame inside canvas for cards
        self.cards_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.cards_frame, anchor=tk.NW)

        # Bind scroll events
        self.cards_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _on_frame_configure(self, event):
        """Update scroll region when frame changes."""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """Adjust frame width when canvas resizes."""
        self.canvas.itemconfig(self.canvas_window, width=event.width)
        # Recalculate cards per row
        new_cards_per_row = max(1, event.width // (VideoCard.THUMB_WIDTH + self.CARD_PADDING * 2))
        if new_cards_per_row != self.CARDS_PER_ROW:
            self.CARDS_PER_ROW = new_cards_per_row
            self._display_videos()

    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling."""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _load_videos(self):
        """Load videos from database with current filters."""
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
            search_text=search,
            channel=channel,
            video_type=video_type,
            min_rating=min_rating,
            is_live=is_live,
            order_by="last_updated",
            descending=True
        )

        self._update_channel_list()
        self._display_videos()

    def _update_channel_list(self):
        """Update channel filter dropdown."""
        channels = [""] + self.db.get_channels()
        self.channel_combo["values"] = channels

    def _display_videos(self):
        """Display videos in grid."""
        # Clear existing cards
        for card in self.card_widgets:
            card.destroy()
        self.card_widgets.clear()

        # Create new cards
        for i, video in enumerate(self.current_videos):
            row = i // self.CARDS_PER_ROW
            col = i % self.CARDS_PER_ROW

            card = VideoCard(self.cards_frame, video, self._on_video_click, self.thumbnail_cache)
            card.grid(row=row, column=col, padx=self.CARD_PADDING, pady=self.CARD_PADDING)
            self.card_widgets.append(card)

        # Update count
        self.count_label.configure(text=f"{len(self.current_videos)} videos")

    def _on_filter_change(self):
        """Handle filter changes."""
        self._load_videos()

    def _on_video_click(self, video: VideoRecord):
        """Handle video card click."""
        dialog = VideoEditDialog(self, video, self.db, on_save=self._on_video_saved)
        self.wait_window(dialog)

    def _on_video_saved(self, video: Optional[VideoRecord]):
        """Handle video save/delete."""
        self._load_videos()

    def _import_html(self):
        """Import videos from HTML file."""
        filepath = filedialog.askopenfilename(
            title="Select HTML file",
            filetypes=[("HTML files", "*.html *.htm"), ("All files", "*.*")]
        )
        if filepath:
            self._do_import([filepath])

    def _import_folder(self):
        """Import all HTML files from folder."""
        folder = filedialog.askdirectory(title="Select folder with HTML files")
        if folder:
            folder_path = Path(folder)
            html_files = list(folder_path.glob("*.html")) + list(folder_path.glob("*.htm"))
            if html_files:
                self._do_import([str(f) for f in html_files])
            else:
                messagebox.showwarning("No files", "No HTML files found in folder.")

    def _do_import(self, filepaths: List[str]):
        """Perform import from HTML files."""
        total = 0
        for filepath in filepaths:
            try:
                self.status_var.set(f"Importing {Path(filepath).name}...")
                self.update()

                # Read HTML content and extract videos
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    html_content = f.read()
                videos, _, _ = extract_videos(html_content, Path(filepath))
                count = self.db.import_from_extraction(videos, Path(filepath).name)
                total += count
                logger.info(f"Imported {count} videos from {filepath}")

            except Exception as e:
                logger.error(f"Failed to import {filepath}: {e}")
                messagebox.showerror("Import Error", f"Failed to import {filepath}:\n{e}")

        self.status_var.set(f"Imported {total} videos")
        self._load_videos()
        messagebox.showinfo("Import Complete", f"Successfully imported {total} videos from {len(filepaths)} file(s).")

    def _export_csv(self):
        """Export videos to CSV."""
        filepath = filedialog.asksaveasfilename(
            title="Export to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filepath:
            try:
                import csv
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'video_id', 'title', 'channel', 'views', 'published', 'duration',
                        'url', 'video_type', 'is_live', 'user_comment', 'user_rating', 'user_tags'
                    ])
                    for video in self.current_videos:
                        writer.writerow([
                            video.video_id, video.title, video.channel, video.views,
                            video.published, video.duration, video.url, video.video_type,
                            video.is_live, video.user_comment, video.user_rating,
                            ','.join(video.user_tags) if video.user_tags else ''
                        ])
                messagebox.showinfo("Export Complete", f"Exported {len(self.current_videos)} videos to {filepath}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export: {e}")

    def _show_stats(self):
        """Show database statistics."""
        stats = self.db.get_stats()
        msg = f"""Database Statistics:

Total Videos: {stats['total_videos']}
  - Regular Videos: {stats['videos']}
  - Shorts: {stats['shorts']}
  - Live: {stats['live']}

User Data:
  - Rated: {stats['rated']}
  - With Comments: {stats['with_comments']}

Unique Channels: {stats['channels']}
Total Tags: {stats['tags']}
"""
        messagebox.showinfo("Statistics", msg)

    def on_closing(self):
        """Handle window close."""
        self.db.close()
        self.destroy()


def main():
    app = VideoManagerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
