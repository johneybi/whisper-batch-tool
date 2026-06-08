from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox

from app_info import APP_DISPLAY_NAME, APP_NAME, APP_VERSION
from runtime_manager import (
    activate_selected_runtime,
    get_selected_runtime,
    install_runtime,
    is_runtime_installed,
    set_selected_runtime,
)

RUNTIME_ACTIVATION = activate_selected_runtime()

from transcriber_core import (
    MODEL_NAMES,
    OUTPUT_FORMATS,
    TranscriptionOptions,
    WhisperBatchEngine,
    check_ffmpeg,
    discover_media_files,
    ensure_standard_streams,
    get_torch_runtime_info,
    supported_filetype_patterns,
)


BG = "#f6f8fb"
CARD_BG = "#ffffff"
BORDER = "#d9dee8"
TEXT = "#111827"
MUTED = "#6b7280"
BLUE = "#0d6efd"
BLUE_DARK = "#0758d4"
GREEN = "#15803d"
GREEN_BG = "#dcfce7"
SOFT_BLUE_BG = "#eaf2ff"
ROW_ALT = "#f9fafb"
WARNING = "#f59e0b"
ERROR = "#dc2626"


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def diagnostic_log_path() -> Path:
    return app_data_dir() / "logs" / "app.log"


def write_diagnostic(message: str) -> None:
    try:
        path = diagnostic_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(f"{timestamp} {message}\n")
    except Exception:
        return


def install_exception_hooks(root: Tk) -> None:
    def log_exception(exc_type, exc_value, exc_traceback) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        write_diagnostic(f"Unhandled exception:\n{details}")

    def log_thread_exception(args: threading.ExceptHookArgs) -> None:
        log_exception(args.exc_type, args.exc_value, args.exc_traceback)

    def log_tk_exception(exc_type, exc_value, exc_traceback) -> None:
        log_exception(exc_type, exc_value, exc_traceback)
        messagebox.showerror("Application error", str(exc_value))

    sys.excepthook = log_exception
    threading.excepthook = log_thread_exception
    root.report_callback_exception = log_tk_exception  # type: ignore[method-assign]


def configure_app_style(root: Tk) -> None:
    root.configure(bg=BG)
    root.option_add("*Font", "Arial 12")
    root.option_add("*Button.Font", "Arial 12")
    root.option_add("*Entry.Font", "Arial 12")
    root.option_add("*Listbox.Font", "Arial 12")
    root.option_add("*Menu.Font", "Arial 12")


def bytes_to_mb(path: Path) -> str:
    return f"{path.stat().st_size / (1024 * 1024):.0f} MB"


def media_format(path: Path) -> str:
    suffix = path.suffix.upper().lstrip(".")
    return suffix or "MEDIA"


class ProgressMeter:
    def __init__(self, parent: tk.Widget, height: int = 16):
        self.maximum = 1
        self.value = 0
        self.active = False
        self.phase = 0
        self.canvas = tk.Canvas(parent, height=height, bg="#e5e7eb", highlightthickness=0)
        self.canvas.bind("<Configure>", lambda _event: self._draw())

    def grid(self, **kwargs) -> None:
        self.canvas.grid(**kwargs)

    def configure(self, maximum: int | None = None, value: int | None = None) -> None:
        if maximum is not None:
            self.maximum = max(maximum, 1)
        if value is not None:
            self.value = max(0, min(value, self.maximum))
        self._draw()

    def start_activity(self) -> None:
        if self.active:
            return
        self.active = True
        self.phase = 0
        self._tick()

    def stop_activity(self) -> None:
        self.active = False
        self._draw()

    def _tick(self) -> None:
        if not self.active:
            return
        self.phase = (self.phase + 8) % 1000
        self._draw()
        self.canvas.after(80, self._tick)

    def _draw(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        fill_width = int(width * (self.value / self.maximum)) if self.maximum else 0
        self.canvas.create_rectangle(0, 0, width, height, fill="#e5e7eb", width=0)
        if fill_width:
            self.canvas.create_rectangle(0, 0, fill_width, height, fill=BLUE, width=0)
        if self.active and self.value < self.maximum:
            remaining_start = fill_width
            remaining_width = max(width - remaining_start, 1)
            segment_width = max(int(remaining_width * 0.28), 42)
            travel = max(remaining_width + segment_width, 1)
            x1 = remaining_start + (self.phase % travel) - segment_width
            x2 = x1 + segment_width
            self.canvas.create_rectangle(max(remaining_start, x1), 0, min(width, x2), height, fill=BLUE, width=0)
        if self.maximum > 1:
            percent = int((self.value / self.maximum) * 100)
            self.canvas.create_text(width / 2, height / 2, text=f"{percent}%", fill="#ffffff", font=("Arial", 10, "bold"))


class ScrollableFrame(tk.Frame):
    def __init__(self, parent: tk.Widget, height: int, bg: str = CARD_BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, height=height, bg=bg, highlightthickness=0)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._sync_width)

    def _sync_scrollregion(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)


class TextLabel(tk.Button):
    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        bg: str = CARD_BG,
        fg: str = TEXT,
        font=("Arial", 12),
        height: int = 24,
        anchor: str = "w",
        padx: int = 0,
        width: int | None = None,
        wraplength: int | None = None,
        justify: str | None = None,
    ):
        options = {
            "text": text,
            "bg": bg,
            "fg": fg,
            "activebackground": bg,
            "activeforeground": fg,
            "font": font,
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "anchor": anchor,
            "padx": padx,
            "pady": 0,
            "takefocus": 0,
            "cursor": "arrow",
            "command": lambda: None,
        }
        if wraplength is not None:
            options["wraplength"] = wraplength
        if justify is not None:
            options["justify"] = justify
        if width is not None:
            options["width"] = max(1, int(width / 9))
        else:
            options["width"] = max(2, min(len(text) + 2, 80))
        super().__init__(parent, **options)
        self.configure(height=max(1, int(height / 22)))

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        if cnf:
            kwargs.update(cnf)
        if "fg" in kwargs:
            kwargs["foreground"] = kwargs.pop("fg")
        if "foreground" in kwargs:
            kwargs["fg"] = kwargs.pop("foreground")
        if "bg" in kwargs:
            bg = kwargs["bg"]
            kwargs.setdefault("activebackground", bg)
        if "background" in kwargs:
            bg = kwargs.pop("background")
            kwargs["bg"] = bg
            kwargs.setdefault("activebackground", bg)
        if "fg" in kwargs:
            kwargs.setdefault("activeforeground", kwargs["fg"])
        super().configure(**kwargs)

    config = configure


class WhisperBatchGui:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title(f"{APP_DISPLAY_NAME} {APP_VERSION}")
        self.root.geometry("1280x820")
        self.root.minsize(1040, 700)

        self.files: list[Path] = []
        self.file_states: list[str] = []
        self.selected_files: set[int] = set()
        self.worker: threading.Thread | None = None
        self.cancel_requested = threading.Event()
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.results: list[Path] = []
        self.current_file_index = -1
        self.torch_runtime = None
        self.runtime_activation = RUNTIME_ACTIVATION
        self.runtime_installing = False

        self.model_var = StringVar(value="small")
        self.language_var = StringVar(value="ko")
        self.task_var = StringVar(value="transcribe")
        self.device_var = StringVar(value="auto")
        self.output_location_var = StringVar(value="source")
        self.output_dir_var = StringVar(value="")
        self.overwrite_var = BooleanVar(value=False)
        self.recursive_var = BooleanVar(value=True)
        self.keep_context_var = BooleanVar(value=True)
        self.format_vars = {name: BooleanVar(value=name in {"txt", "srt"}) for name in OUTPUT_FORMATS}

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._start_environment_check)
        self.root.after(100, self._drain_messages)
        write_diagnostic(f"{APP_DISPLAY_NAME} {APP_VERSION} started")

    def _card(self, parent: tk.Widget, title: str | None = None) -> tk.Frame:
        outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        card = tk.Frame(outer, bg=CARD_BG, padx=16, pady=14)
        card.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        if title:
            TextLabel(card, text=title, bg=CARD_BG, fg=TEXT, font=("Arial", 14, "bold"), height=28).grid(
                row=0, column=0, sticky="w", pady=(0, 12)
            )
        outer.content = card  # type: ignore[attr-defined]
        return outer

    def _button(self, parent: tk.Widget, text: str, command, primary: bool = False, **kwargs) -> tk.Button:
        bg = BLUE if primary else "#ffffff"
        fg = "#ffffff" if primary else TEXT
        active_bg = BLUE_DARK if primary else "#eef2f7"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            **kwargs,
        )
        return button

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(
                "Transcription running",
                "A transcription job is still running. Close the app and stop the job?",
            ):
                return
            self.cancel_requested.set()
            write_diagnostic("Window close confirmed while transcription was running")
        else:
            write_diagnostic("Window closed")
        self.root.destroy()

    def _section_label(self, parent: tk.Widget, text: str, row: int, column: int = 0) -> None:
        TextLabel(parent, text=text, bg=CARD_BG, fg=TEXT, font=("Arial", 12, "bold"), height=24).grid(
            row=row, column=column, sticky="w", pady=(8, 4)
        )

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_header()

        main = tk.Frame(self.root, bg=BG, padx=24, pady=8)
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=7)
        main.columnconfigure(1, weight=5)
        main.rowconfigure(0, weight=1)

        left = tk.Frame(main, bg=BG)
        right = tk.Frame(main, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        left.columnconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=5)
        left.rowconfigure(1, weight=2)
        left.rowconfigure(2, weight=3)

        self._build_file_card(left)
        self._build_progress_card(left)
        self._build_log_card(left)
        self._build_settings_card(right)
        self._build_action_panel(right)

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=BG, padx=28, pady=20)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title_area = tk.Frame(header, bg=BG)
        title_area.grid(row=0, column=0, sticky="w")
        TextLabel(
            title_area,
            text="Whisper Batch Transcriber",
            bg=BG,
            fg=TEXT,
            font=("Arial", 24, "bold"),
            height=36,
        ).grid(row=0, column=0, sticky="w")
        TextLabel(
            title_area,
            text="Convert local audio and video files into transcripts and subtitles.",
            bg=BG,
            fg=MUTED,
            font=("Arial", 12),
            height=22,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        nav = tk.Frame(header, bg=BG)
        nav.grid(row=0, column=1, sticky="e")
        self.ffmpeg_badge = TextLabel(
            nav,
            text="ffmpeg checking...",
            bg=SOFT_BLUE_BG,
            fg=BLUE_DARK,
            font=("Arial", 12, "bold"),
            height=38,
            width=150,
            anchor="center",
        )
        self.ffmpeg_badge.grid(row=0, column=0, padx=(0, 10))
        self.torch_badge = TextLabel(
            nav,
            text="Torch checking...",
            bg=SOFT_BLUE_BG,
            fg=BLUE_DARK,
            height=38,
            width=180,
            anchor="center",
        )
        self.torch_badge.grid(row=0, column=1, padx=(0, 10))
        self._button(nav, "Settings", lambda: self.log("Settings are shown in the right panel.")).grid(
            row=0, column=2, padx=(0, 8)
        )
        self._button(nav, "Help", self.show_help).grid(row=0, column=3)

    def _build_file_card(self, parent: tk.Frame) -> None:
        outer = self._card(parent)
        outer.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        card = outer.content  # type: ignore[attr-defined]
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)

        self.file_title = TextLabel(
            card,
            text="File List (0)",
            bg=CARD_BG,
            fg=TEXT,
            font=("Arial", 14, "bold"),
            height=28,
        )
        self.file_title.grid(row=0, column=0, sticky="w", pady=(0, 12))

        toolbar = tk.Frame(card, bg=CARD_BG)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        toolbar.columnconfigure(4, weight=1)
        self._button(toolbar, "+ Add Files", self.add_files, primary=True).grid(row=0, column=0, padx=(0, 8))
        self._button(toolbar, "+ Add Folder", self.add_folder).grid(row=0, column=1, padx=(0, 8))
        self._button(toolbar, "Remove", self.remove_selected).grid(row=0, column=2, padx=(0, 8))
        self._button(toolbar, "Clear", self.clear_files).grid(row=0, column=3, padx=(0, 8))
        tk.Checkbutton(
            toolbar,
            text="Include subfolders",
            variable=self.recursive_var,
            bg=CARD_BG,
            fg=TEXT,
            selectcolor=CARD_BG,
            activebackground=CARD_BG,
        ).grid(row=0, column=5, sticky="e")

        table = tk.Frame(card, bg=BORDER, padx=1, pady=1)
        table.grid(row=2, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(1, weight=1)

        headings = tk.Frame(table, bg="#f3f4f6", padx=10, pady=8)
        headings.grid(row=0, column=0, sticky="ew")
        for col, (label, width) in enumerate((("Filename", 36), ("Format", 8), ("Size", 9), ("Status", 14), ("", 4))):
            headings.columnconfigure(col, weight=1 if col == 0 else 0)
            TextLabel(
                headings,
                text=label,
                bg="#f3f4f6",
                fg="#4b5563",
                width=width * 9,
                height=22,
            ).grid(
                row=0, column=col, sticky="ew"
            )

        self.file_rows = ScrollableFrame(table, height=210, bg=CARD_BG)
        self.file_rows.grid(row=1, column=0, sticky="nsew")

        self.file_summary = TextLabel(card, text="0 files", bg=CARD_BG, fg=MUTED, height=22)
        self.file_summary.grid(row=3, column=0, sticky="w", pady=(12, 0))

    def _build_progress_card(self, parent: tk.Frame) -> None:
        outer = self._card(parent, "Progress")
        outer.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        card = outer.content  # type: ignore[attr-defined]
        card.columnconfigure(0, weight=1)

        top = tk.Frame(card, bg=CARD_BG)
        top.grid(row=1, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        self.current_file_label = TextLabel(top, text="Current file: none", bg=CARD_BG, fg=TEXT, height=24)
        self.current_file_label.grid(row=0, column=0, sticky="w")
        self.current_progress_label = TextLabel(
            top,
            text="Current: 0%",
            bg=CARD_BG,
            fg=TEXT,
            height=24,
            width=140,
            anchor="e",
        )
        self.current_progress_label.grid(row=0, column=1, sticky="e")

        self.current_progress = ProgressMeter(card, height=18)
        self.current_progress.grid(row=2, column=0, sticky="ew", pady=(8, 12))

        overall = tk.Frame(card, bg=CARD_BG)
        overall.grid(row=3, column=0, sticky="ew")
        overall.columnconfigure(0, weight=1)
        TextLabel(overall, text="Overall progress", bg=CARD_BG, fg=TEXT, height=24).grid(row=0, column=0, sticky="w")
        self.total_progress_label = TextLabel(
            overall,
            text="Overall: 0 / 0 (0%)",
            bg=CARD_BG,
            fg=TEXT,
            height=24,
            width=180,
            anchor="e",
        )
        self.total_progress_label.grid(row=0, column=1, sticky="e")

        self.progress = ProgressMeter(card, height=18)
        self.progress.grid(row=4, column=0, sticky="ew", pady=(8, 10))
        bottom = tk.Frame(card, bg=CARD_BG)
        bottom.grid(row=5, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.status_label = TextLabel(bottom, text="Ready", bg=CARD_BG, fg=MUTED, height=30)
        self.status_label.grid(row=0, column=0, sticky="w")
        self.cancel_button = self._button(bottom, "Cancel after current file", self.cancel, state="disabled")
        self.cancel_button.grid(row=0, column=1, sticky="e")

    def _build_log_card(self, parent: tk.Frame) -> None:
        outer = self._card(parent)
        outer.grid(row=2, column=0, sticky="nsew")
        card = outer.content  # type: ignore[attr-defined]
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        header = tk.Frame(card, bg=CARD_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        TextLabel(header, text="Log", bg=CARD_BG, fg=TEXT, font=("Arial", 14, "bold"), height=28).grid(
            row=0, column=0, sticky="w"
        )
        self._button(header, "Clear Log", self.clear_log).grid(row=0, column=1, sticky="e")

        log_frame = tk.Frame(card, bg=CARD_BG)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Listbox(
            log_frame,
            height=7,
            activestyle="none",
            bg=CARD_BG,
            fg=TEXT,
            relief="flat",
            highlightthickness=0,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _build_settings_card(self, parent: tk.Frame) -> None:
        outer = self._card(parent, "Transcription Settings")
        outer.grid(row=0, column=0, sticky="nsew", pady=(0, 18))
        card = outer.content  # type: ignore[attr-defined]
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        TextLabel(card, text="Model", bg=CARD_BG, fg=TEXT, font=("Arial", 12, "bold"), height=24).grid(
            row=1, column=0, sticky="w"
        )
        TextLabel(card, text="Language", bg=CARD_BG, fg=TEXT, font=("Arial", 12, "bold"), height=24).grid(
            row=1, column=1, sticky="w", padx=(16, 0)
        )
        self._option(card, self.model_var, MODEL_NAMES).grid(row=2, column=0, sticky="ew", pady=(6, 12))
        language = tk.Frame(card, bg=CARD_BG)
        language.grid(row=2, column=1, sticky="ew", padx=(16, 0), pady=(6, 12))
        language.columnconfigure(0, weight=1)
        tk.Entry(language, textvariable=self.language_var, relief="solid", bd=1).grid(row=0, column=0, sticky="ew")
        self._button(language, "Auto", lambda: self.language_var.set("")).grid(row=0, column=1, padx=(8, 0))

        self._section_label(card, "Task", 3, 0)
        task_frame = tk.Frame(card, bg=CARD_BG)
        task_frame.grid(row=4, column=0, sticky="w")
        for index, (value, label) in enumerate((("transcribe", "Transcribe"), ("translate", "Translate"))):
            tk.Radiobutton(
                task_frame,
                text=label,
                value=value,
                variable=self.task_var,
                bg=CARD_BG,
                fg=TEXT,
                selectcolor=CARD_BG,
                activebackground=CARD_BG,
            ).grid(row=index, column=0, sticky="w", pady=2)

        self._section_label(card, "Device", 3, 1)
        device_frame = tk.Frame(card, bg=CARD_BG)
        device_frame.grid(row=4, column=1, sticky="new", padx=(16, 0))
        device_frame.columnconfigure(0, weight=1)
        self._option(device_frame, self.device_var, ("auto", "cpu", "cuda", "mps")).grid(
            row=0, column=0, sticky="ew"
        )
        self.device_status_label = TextLabel(
            device_frame,
            text="Checking PyTorch/CUDA...",
            bg=CARD_BG,
            fg=MUTED,
            height=42,
            anchor="w",
            wraplength=320,
            justify="left",
        )
        self.device_status_label.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        runtime_actions = tk.Frame(device_frame, bg=CARD_BG)
        runtime_actions.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        runtime_actions.columnconfigure(0, weight=1)
        runtime_actions.columnconfigure(1, weight=1)
        self.install_cuda_button = self._button(
            runtime_actions,
            "Install CUDA runtime",
            self.install_cuda_runtime,
        )
        self.install_cuda_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.use_cpu_button = self._button(
            runtime_actions,
            "Use bundled CPU",
            self.use_bundled_cpu_runtime,
        )
        self.use_cpu_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self._divider(card, 5)
        self._section_label(card, "Output Files", 6, 0)
        self._section_label(card, "Where to save results", 6, 1)

        formats = tk.Frame(card, bg=CARD_BG)
        formats.grid(row=7, column=0, sticky="w")
        for index, name in enumerate(OUTPUT_FORMATS):
            tk.Checkbutton(
                formats,
                text=name.upper(),
                variable=self.format_vars[name],
                bg=CARD_BG,
                fg=TEXT,
                selectcolor=CARD_BG,
                activebackground=CARD_BG,
            ).grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 16), pady=4)

        output = tk.Frame(card, bg=CARD_BG)
        output.grid(row=7, column=1, sticky="nsew", padx=(16, 0))
        output.columnconfigure(0, weight=1)
        for index, (value, label) in enumerate(
            (
                ("source", "Same folder as each source file"),
                ("custom", "Choose one output folder"),
            )
        ):
            tk.Radiobutton(
                output,
                text=label,
                value=value,
                variable=self.output_location_var,
                command=self._sync_output_controls,
                bg=CARD_BG,
                fg=TEXT,
                selectcolor=CARD_BG,
                activebackground=CARD_BG,
            ).grid(row=index, column=0, sticky="w", pady=2)
        path_row = tk.Frame(output, bg=CARD_BG)
        path_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        path_row.columnconfigure(0, weight=1)
        self.output_entry = tk.Entry(path_row, textvariable=self.output_dir_var, relief="solid", bd=1)
        self.output_entry.grid(row=0, column=0, sticky="ew")
        self.output_browse_button = self._button(path_row, "Browse", self.select_output_dir)
        self.output_browse_button.grid(row=0, column=1, padx=(8, 0))
        TextLabel(
            output,
            text="Default: results are saved beside each original file. To choose a folder, select the second option and click Browse.",
            bg=CARD_BG,
            fg=MUTED,
            font=("Arial", 10),
            height=44,
            width=300,
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))

        self._divider(card, 8)
        advanced_header = tk.Frame(card, bg=CARD_BG)
        advanced_header.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        advanced_header.columnconfigure(0, weight=1)
        TextLabel(
            advanced_header,
            text="Advanced Settings",
            bg=CARD_BG,
            fg=TEXT,
            font=("Arial", 12, "bold"),
            height=24,
        ).grid(
            row=0, column=0, sticky="w"
        )
        TextLabel(advanced_header, text="v", bg=CARD_BG, fg=MUTED, height=24, width=24, anchor="e").grid(
            row=0, column=1, sticky="e"
        )

        advanced = tk.Frame(card, bg=CARD_BG)
        advanced.grid(row=10, column=0, columnspan=2, sticky="ew")
        tk.Checkbutton(
            advanced,
            text="Use previous text context",
            variable=self.keep_context_var,
            bg=CARD_BG,
            fg=TEXT,
            selectcolor=CARD_BG,
            activebackground=CARD_BG,
        ).grid(row=0, column=0, sticky="w", pady=3)
        tk.Checkbutton(
            advanced,
            text="Overwrite existing files",
            variable=self.overwrite_var,
            bg=CARD_BG,
            fg=TEXT,
            selectcolor=CARD_BG,
            activebackground=CARD_BG,
        ).grid(row=1, column=0, sticky="w", pady=3)
        self._sync_output_controls()

    def _build_action_panel(self, parent: tk.Frame) -> None:
        action = tk.Frame(parent, bg=BG)
        action.grid(row=1, column=0, sticky="ew")
        action.columnconfigure(0, weight=1)
        self.start_button = self._button(action, "Start Transcription", self.start, primary=True)
        self.start_button.configure(font=("Arial", 15, "bold"), pady=16)
        self.start_button.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.open_output_button = self._button(action, "Open Output Folder", self.open_output_folder)
        self.open_output_button.configure(font=("Arial", 14, "bold"), pady=14)
        self.open_output_button.grid(row=1, column=0, sticky="ew")

    def _option(self, parent: tk.Widget, variable: StringVar, values) -> tk.OptionMenu:
        menu = tk.OptionMenu(parent, variable, *values)
        menu.configure(bg="#ffffff", fg=TEXT, activebackground="#eef2f7", relief="solid", bd=1, highlightthickness=0)
        menu["menu"].configure(bg="#ffffff", fg=TEXT)
        return menu

    def _divider(self, parent: tk.Widget, row: int) -> None:
        line = tk.Frame(parent, bg="#e5e7eb", height=1)
        line.grid(row=row, column=0, columnspan=2, sticky="ew", pady=14)

    def _start_environment_check(self) -> None:
        threading.Thread(target=self._run_environment_check, daemon=True).start()

    def _run_environment_check(self) -> None:
        ok, detail = check_ffmpeg()
        torch_info = get_torch_runtime_info()
        self.messages.put(("environment", (ok, detail, torch_info)))

    def install_cuda_runtime(self) -> None:
        if self.runtime_installing:
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Busy", "Wait until the current transcription job finishes.")
            return
        confirmed = messagebox.askyesno(
            "Install CUDA runtime",
            "This will download and install NVIDIA CUDA PyTorch into your user profile. "
            "It can take several minutes and requires an internet connection. Continue?",
        )
        if not confirmed:
            return
        self.runtime_installing = True
        self.install_cuda_button.configure(state="disabled")
        self.use_cpu_button.configure(state="disabled")
        self.status_label.configure(text="Installing CUDA runtime...")
        self.log("CUDA runtime installation started.")
        threading.Thread(target=self._install_cuda_runtime_worker, daemon=True).start()

    def _install_cuda_runtime_worker(self) -> None:
        try:
            install_runtime("cuda", progress=lambda msg: self.messages.put(("log", msg)))
            self.messages.put(("runtime_installed", "cuda"))
        except Exception as exc:
            self.messages.put(("runtime_error", f"{exc}\n{traceback.format_exc()}"))

    def use_bundled_cpu_runtime(self) -> None:
        set_selected_runtime("bundled")
        self.log("Bundled CPU runtime selected. Restart the app to fully apply this change.")
        messagebox.showinfo("Restart required", "Bundled CPU runtime will be used after restarting the app.")

    def show_help(self) -> None:
        messagebox.showinfo(
            "Help",
            "Add audio or video files, choose model and output formats, then start transcription.",
        )

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select audio or video files",
            filetypes=[
                ("Audio/video files", supported_filetype_patterns()),
                ("All files", "*.*"),
            ],
        )
        self._add_paths(Path(path) for path in paths)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder")
        if not folder:
            return
        files = discover_media_files(Path(folder), recursive=self.recursive_var.get())
        self._add_paths(files)
        self.log(f"Added {len(files)} media files from folder.")

    def _add_paths(self, paths) -> None:
        existing = {path.resolve() for path in self.files}
        added = 0
        for path in paths:
            resolved = path.resolve()
            if resolved in existing or not path.is_file():
                continue
            self.files.append(path)
            self.file_states.append("Waiting")
            existing.add(resolved)
            added += 1
        if added:
            self.log(f"Added {added} file(s).")
        self._refresh_file_list()

    def remove_selected(self) -> None:
        if not self.selected_files:
            return
        keep_files: list[Path] = []
        keep_states: list[str] = []
        for index, path in enumerate(self.files):
            if index not in self.selected_files:
                keep_files.append(path)
                keep_states.append(self.file_states[index])
        self.files = keep_files
        self.file_states = keep_states
        self.selected_files.clear()
        self._refresh_file_list()

    def clear_files(self) -> None:
        self.files.clear()
        self.file_states.clear()
        self.selected_files.clear()
        self._refresh_file_list()

    def clear_log(self) -> None:
        self.log_text.delete(0, tk.END)

    def _toggle_file_selection(self, index: int) -> None:
        if index in self.selected_files:
            self.selected_files.remove(index)
        else:
            self.selected_files.add(index)
        self._refresh_file_list()

    def _refresh_file_list(self, reset_progress: bool = True) -> None:
        for child in self.file_rows.inner.winfo_children():
            child.destroy()

        self.file_title.configure(text=f"File List ({len(self.files)})")
        total_mb = 0.0
        for index, path in enumerate(self.files):
            total_mb += path.stat().st_size / (1024 * 1024)
            self._render_file_row(index, path, self.file_states[index])

        summary = f"{len(self.files)} files"
        if self.files:
            summary += f"  -  total {total_mb:.0f} MB"
        self.file_summary.configure(text=summary)
        if reset_progress:
            self.current_file_index = -1
            self.current_progress.configure(maximum=1000, value=0)
            self.progress.configure(maximum=1000, value=0)
            self.current_progress_label.configure(text="Current: 0%")
            self.total_progress_label.configure(text=f"Overall: 0 / {len(self.files)} (0%)")

    def _render_file_row(self, index: int, path: Path, state: str) -> None:
        selected = index in self.selected_files
        bg = SOFT_BLUE_BG if selected else (ROW_ALT if index % 2 else CARD_BG)
        row = tk.Frame(self.file_rows.inner, bg=bg, padx=10, pady=8)
        row.grid(row=index, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        row.bind("<Button-1>", lambda _event, i=index: self._toggle_file_selection(i))

        name = path.name
        icon = "VIDEO" if media_format(path) in {"MP4", "MOV", "MKV", "WEBM", "AVI", "WMV", "M4V"} else "AUDIO"
        TextLabel(row, text=f"{icon}  {name}", bg=bg, fg=TEXT, height=24).grid(row=0, column=0, sticky="ew")
        TextLabel(row, text=media_format(path), bg=bg, fg=TEXT, width=70, height=24).grid(
            row=0, column=1, sticky="w"
        )
        TextLabel(row, text=bytes_to_mb(path), bg=bg, fg=TEXT, width=80, height=24).grid(
            row=0, column=2, sticky="w"
        )

        status_fg = BLUE if state == "Running" else GREEN if state == "Done" else ERROR if state == "Failed" else MUTED
        TextLabel(row, text=state, bg=bg, fg=status_fg, width=115, height=24).grid(row=0, column=3, sticky="w")
        tk.Button(
            row,
            text="x",
            command=lambda i=index: self._remove_one(i),
            bg=bg,
            fg=MUTED,
            relief="flat",
            padx=6,
            pady=0,
        ).grid(row=0, column=4, sticky="e")

    def _remove_one(self, index: int) -> None:
        if 0 <= index < len(self.files):
            self.files.pop(index)
            self.file_states.pop(index)
            self.selected_files = {i for i in self.selected_files if i != index}
            self.selected_files = {i if i < index else i - 1 for i in self.selected_files}
            self._refresh_file_list()

    def select_output_dir(self) -> None:
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_dir_var.set(folder)
            self.output_location_var.set("custom")
            self._sync_output_controls()

    def _sync_output_controls(self) -> None:
        state = "normal" if self.output_location_var.get() == "custom" else "disabled"
        self.output_entry.configure(state=state)
        self.output_browse_button.configure(state=state)

    def _collect_options(self) -> TranscriptionOptions:
        formats = [name for name, variable in self.format_vars.items() if variable.get()]
        if not formats:
            raise ValueError("Select at least one output format.")

        output_dir = None
        if self.output_location_var.get() == "custom":
            selected = self.output_dir_var.get().strip()
            if not selected:
                raise ValueError("Select an output folder or save next to source files.")
            output_dir = Path(selected)

        selected_device = self.device_var.get()
        torch_info = self.torch_runtime or get_torch_runtime_info()
        if selected_device == "cuda" and not torch_info.cuda_available:
            if torch_info.cuda_build:
                raise ValueError(
                    "CUDA was selected, but no NVIDIA CUDA GPU is available to PyTorch. "
                    "Check the NVIDIA driver and GPU availability."
                )
            raise ValueError(
                "CUDA was selected, but this app is running with a CPU-only PyTorch build. "
                "Click Install CUDA runtime, restart the app, then select cuda again."
            )
        if selected_device == "mps" and not torch_info.mps_available:
            raise ValueError("MPS was selected, but Apple Silicon MPS is not available in this environment.")

        return TranscriptionOptions(
            model_name=self.model_var.get(),
            language=self.language_var.get().strip(),
            task=self.task_var.get(),
            output_formats=formats,
            output_dir=output_dir,
            overwrite=self.overwrite_var.get(),
            device=selected_device,
            condition_on_previous_text=self.keep_context_var.get(),
        )

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.files:
            messagebox.showinfo("No files", "Add at least one audio or video file.")
            return

        try:
            options = self._collect_options()
        except ValueError as exc:
            messagebox.showerror("Invalid options", str(exc))
            return

        self.results.clear()
        self.cancel_requested.clear()
        self.current_file_index = -1
        self.file_states = ["Waiting" for _ in self.files]
        self._refresh_file_list()
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status_label.configure(text="Preparing transcription...")
        self.current_progress.configure(maximum=1000, value=0)
        self.progress.configure(maximum=1000, value=0)
        self.current_progress_label.configure(text="Current: 0%")
        self.total_progress_label.configure(text=f"Overall: 0 / {len(self.files)} (0%)")
        self.current_progress.start_activity()
        self.progress.start_activity()
        write_diagnostic(f"Batch started: files={len(self.files)}, model={options.model_name}, device={options.device}")
        self.worker = threading.Thread(target=self._run_worker, args=(list(self.files), options), daemon=True)
        self.worker.start()

    def cancel(self) -> None:
        if self.worker and self.worker.is_alive():
            self.cancel_requested.set()
            self.cancel_button.configure(state="disabled")
            self.status_label.configure(text="Canceling after current file")
            self.log("Cancel requested. The current file will finish before the batch stops.")

    def _run_worker(self, files: list[Path], options: TranscriptionOptions) -> None:
        try:
            active_index = {"value": -1}

            def frame_progress(current: int, total: int) -> None:
                self.messages.put(("file_progress", (active_index["value"], current, total)))

            engine = WhisperBatchEngine(
                progress=lambda msg: self.messages.put(("log", msg)),
                frame_progress=frame_progress,
            )
            total = len(files)
            for index, path in enumerate(files, start=1):
                if self.cancel_requested.is_set():
                    self.messages.put(("canceled", None))
                    return
                active_index["value"] = index - 1
                self.messages.put(("file_state", (index - 1, "Running")))
                self.messages.put(("status", f"{index}/{total}: {path.name}"))
                self.messages.put(("file_progress", (index - 1, 0, 1)))
                result = engine.transcribe_file(path, options)
                self.messages.put(("result", result.output_files))
                self.messages.put(("file_progress", (index - 1, 1, 1)))
                self.messages.put(("file_state", (index - 1, "Done")))
                self.messages.put(("progress", index))
                if self.cancel_requested.is_set():
                    self.messages.put(("canceled", None))
                    return
            self.messages.put(("done", None))
        except Exception as exc:
            details = f"{exc}\n{traceback.format_exc()}"
            write_diagnostic(f"Worker failed:\n{details}")
            self.messages.put(("error", details))

    def _drain_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "log":
                    self.log(str(payload))
                elif kind == "status":
                    self.status_label.configure(text=str(payload))
                    self.current_file_label.configure(text=f"Current file: {str(payload).split(': ', 1)[-1]}")
                elif kind == "file_progress":
                    index, current, total = payload
                    if 0 <= int(index) < len(self.files):
                        self.current_file_index = int(index)
                    total_frames = max(int(total), 1)
                    fraction = max(0.0, min(float(current) / total_frames, 1.0))
                    current_percent = int(fraction * 100)
                    self.current_progress.configure(value=int(fraction * 1000))
                    self.current_progress_label.configure(text=f"Current: {current_percent}%")

                    completed = sum(1 for state in self.file_states if state == "Done")
                    if 0 <= int(index) < len(self.file_states) and self.file_states[int(index)] != "Done":
                        overall_fraction = (completed + fraction) / max(len(self.files), 1)
                    else:
                        overall_fraction = completed / max(len(self.files), 1)
                    overall_percent = int(overall_fraction * 100)
                    self.progress.configure(value=int(overall_fraction * 1000))
                    self.total_progress_label.configure(
                        text=f"Overall: {completed} / {len(self.files)} ({overall_percent}%)"
                    )
                elif kind == "progress":
                    value = int(payload)
                    overall_fraction = value / max(len(self.files), 1)
                    self.progress.configure(value=int(overall_fraction * 1000))
                    self.total_progress_label.configure(
                        text=f"Overall: {value} / {len(self.files)} ({int(overall_fraction * 100)}%)"
                    )
                elif kind == "result":
                    self.results.extend(payload)
                elif kind == "file_state":
                    index, state = payload
                    if 0 <= index < len(self.file_states):
                        self.file_states[index] = state
                        self._refresh_file_list(reset_progress=False)
                elif kind == "environment":
                    ok, detail, torch_info = payload
                    self.torch_runtime = torch_info
                    self.ffmpeg_badge.configure(
                        text="ffmpeg OK" if ok else "ffmpeg missing",
                        bg=GREEN_BG if ok else "#fee2e2",
                        fg=GREEN if ok else ERROR,
                    )
                    cuda_ready = bool(torch_info.cuda_available)
                    torch_label = "CUDA ready" if cuda_ready else "CPU build"
                    if not torch_info.installed:
                        torch_label = "Torch missing"
                    elif torch_info.cuda_build and not cuda_ready:
                        torch_label = "CUDA unavailable"
                    self.torch_badge.configure(
                        text=torch_label,
                        bg=GREEN_BG if cuda_ready else SOFT_BLUE_BG,
                        fg=GREEN if cuda_ready else BLUE_DARK,
                    )
                    selected_runtime = get_selected_runtime()
                    runtime_note = "Runtime: bundled CPU"
                    if selected_runtime == "cuda":
                        runtime_note = "Runtime: CUDA installed" if is_runtime_installed("cuda") else "Runtime: CUDA selected, not installed"
                    self.device_status_label.configure(text=f"{torch_info.device_label()}\n{runtime_note}")
                    self.log(str(detail))
                    self.log(self.runtime_activation.message)
                    self.log(f"PyTorch {torch_info.version}: {torch_info.device_label()}")
                    if not ok:
                        messagebox.showwarning(
                            "ffmpeg not found",
                            "ffmpeg is required for broad audio/video format support. Install it, then restart this app.",
                        )
                elif kind == "runtime_installed":
                    self.runtime_installing = False
                    self.install_cuda_button.configure(state="normal")
                    self.use_cpu_button.configure(state="normal")
                    self.status_label.configure(text="CUDA runtime installed")
                    self.log("CUDA runtime installed. Restart the app, then select device=cuda.")
                    messagebox.showinfo(
                        "Restart required",
                        "CUDA runtime was installed. Restart the app before starting a CUDA transcription.",
                    )
                elif kind == "runtime_error":
                    self.runtime_installing = False
                    self.install_cuda_button.configure(state="normal")
                    self.use_cpu_button.configure(state="normal")
                    self.status_label.configure(text="CUDA runtime install failed")
                    self.log(str(payload))
                    messagebox.showerror("CUDA runtime install failed", str(payload).splitlines()[0])
                elif kind == "error":
                    self.log(str(payload))
                    self.current_progress.stop_activity()
                    self.progress.stop_activity()
                    self.start_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.status_label.configure(text="Failed")
                    messagebox.showerror("Transcription failed", str(payload).splitlines()[0])
                elif kind == "canceled":
                    self.current_progress.stop_activity()
                    self.progress.stop_activity()
                    self.start_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.status_label.configure(text="Canceled")
                    self.log("Batch canceled.")
                elif kind == "done":
                    self.current_progress.stop_activity()
                    self.progress.stop_activity()
                    self.current_progress.configure(value=1000)
                    self.progress.configure(value=1000)
                    self.current_progress_label.configure(text="Current: 100%")
                    self.total_progress_label.configure(text=f"Overall: {len(self.files)} / {len(self.files)} (100%)")
                    self.start_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.status_label.configure(text="Done")
                    self.current_file_label.configure(text="Current file: none")
                    self.log("All jobs finished.")
                    write_diagnostic("Batch finished")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_messages)

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"{timestamp}   {message}")
        self.log_text.see(tk.END)
        write_diagnostic(message)

    def open_output_folder(self) -> None:
        if self.output_location_var.get() == "custom" and self.output_dir_var.get().strip():
            folder = Path(self.output_dir_var.get().strip())
        elif self.results:
            folder = self.results[-1].parent
        elif self.files:
            folder = self.files[0].parent
        else:
            folder = Path.cwd()

        folder = folder.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            webbrowser.open(folder.as_uri())


def main() -> None:
    ensure_standard_streams()
    if "--self-test" in sys.argv:
        ok, _detail = check_ffmpeg()
        raise SystemExit(0 if ok else 1)
    if "--install-runtime" in sys.argv:
        index = sys.argv.index("--install-runtime")
        flavor = sys.argv[index + 1] if index + 1 < len(sys.argv) else "cuda"
        install_runtime(flavor, progress=lambda message: print(message, flush=True))
        raise SystemExit(0)

    root = Tk()
    install_exception_hooks(root)
    configure_app_style(root)
    WhisperBatchGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
