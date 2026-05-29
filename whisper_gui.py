from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk

from app_info import APP_DISPLAY_NAME, APP_VERSION
from transcriber_core import (
    MODEL_NAMES,
    OUTPUT_FORMATS,
    TranscriptionOptions,
    WhisperBatchEngine,
    check_ffmpeg,
    discover_media_files,
    supported_filetype_patterns,
)


class WhisperBatchGui:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title(f"{APP_DISPLAY_NAME} {APP_VERSION}")
        self.root.geometry("1060x720")
        self.root.minsize(880, 620)

        self.files: list[Path] = []
        self.worker: threading.Thread | None = None
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.results: list[Path] = []

        self.model_var = StringVar(value="small")
        self.language_var = StringVar(value="ko")
        self.task_var = StringVar(value="transcribe")
        self.device_var = StringVar(value="auto")
        self.output_dir_var = StringVar(value="")
        self.overwrite_var = BooleanVar(value=False)
        self.recursive_var = BooleanVar(value=True)
        self.keep_context_var = BooleanVar(value=False)
        self.format_vars = {name: BooleanVar(value=name in {"txt", "srt"}) for name in OUTPUT_FORMATS}

        self._build_ui()
        self._check_environment()
        self.root.after(100, self._drain_messages)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=(14, 12, 14, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Whisper Batch Transcriber", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.status_label = ttk.Label(header, text="Ready")
        self.status_label.grid(row=0, column=1, sticky="e")

        main = ttk.PanedWindow(self.root, orient="horizontal")
        main.grid(row=1, column=0, sticky="nsew", padx=14, pady=8)

        left = ttk.Frame(main, padding=10)
        right = ttk.Frame(main, padding=10)
        main.add(left, weight=3)
        main.add(right, weight=2)

        self._build_file_panel(left)
        self._build_options_panel(right)
        self._build_footer()

    def _build_file_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(4, weight=1)

        ttk.Button(toolbar, text="Add Files", command=self.add_files).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(toolbar, text="Add Folder", command=self.add_folder).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(toolbar, text="Remove", command=self.remove_selected).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(toolbar, text="Clear", command=self.clear_files).grid(row=0, column=3, padx=(0, 6))
        ttk.Checkbutton(toolbar, text="Recursive folder scan", variable=self.recursive_var).grid(
            row=0, column=5, sticky="e"
        )

        list_frame = ttk.Frame(parent)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.file_list = ttk.Treeview(list_frame, columns=("path", "size"), show="headings", selectmode="extended")
        self.file_list.heading("path", text="File")
        self.file_list.heading("size", text="Size")
        self.file_list.column("path", width=560, anchor="w")
        self.file_list.column("size", width=90, anchor="e")
        self.file_list.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_list.configure(yscrollcommand=scrollbar.set)

        log_frame = ttk.LabelFrame(parent, text="Log", padding=8)
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        self.log_text = ttk.Treeview(log_frame, columns=("message",), show="headings", height=8)
        self.log_text.heading("message", text="Message")
        self.log_text.column("message", anchor="w", width=620)
        self.log_text.grid(row=0, column=0, sticky="nsew")

    def _build_options_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(parent, text="Model").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.model_var, values=MODEL_NAMES, state="readonly").grid(
            row=row, column=1, sticky="ew", pady=4
        )

        row += 1
        ttk.Label(parent, text="Language").grid(row=row, column=0, sticky="w", pady=4)
        language_frame = ttk.Frame(parent)
        language_frame.grid(row=row, column=1, sticky="ew", pady=4)
        language_frame.columnconfigure(0, weight=1)
        ttk.Entry(language_frame, textvariable=self.language_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(language_frame, text="Auto", command=lambda: self.language_var.set("")).grid(
            row=0, column=1, padx=(6, 0)
        )

        row += 1
        ttk.Label(parent, text="Task").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.task_var, values=("transcribe", "translate"), state="readonly").grid(
            row=row, column=1, sticky="ew", pady=4
        )

        row += 1
        ttk.Label(parent, text="Device").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.device_var, values=("auto", "cpu", "cuda", "mps"), state="readonly").grid(
            row=row, column=1, sticky="ew", pady=4
        )

        row += 1
        output_box = ttk.LabelFrame(parent, text="Output Formats", padding=8)
        output_box.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 6))
        for index, name in enumerate(OUTPUT_FORMATS):
            ttk.Checkbutton(output_box, text=name.upper(), variable=self.format_vars[name]).grid(
                row=index // 3, column=index % 3, sticky="w", padx=(0, 14), pady=2
            )

        row += 1
        ttk.Label(parent, text="Output Folder").grid(row=row, column=0, sticky="w", pady=4)
        folder_frame = ttk.Frame(parent)
        folder_frame.grid(row=row, column=1, sticky="ew", pady=4)
        folder_frame.columnconfigure(0, weight=1)
        ttk.Entry(folder_frame, textvariable=self.output_dir_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(folder_frame, text="Browse", command=self.select_output_dir).grid(row=0, column=1, padx=(6, 0))

        row += 1
        ttk.Checkbutton(parent, text="Overwrite existing outputs", variable=self.overwrite_var).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=4
        )

        row += 1
        ttk.Checkbutton(
            parent,
            text="Use previous text context",
            variable=self.keep_context_var,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=4)

        row += 1
        action_frame = ttk.Frame(parent)
        action_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(18, 8))
        action_frame.columnconfigure(0, weight=1)
        self.start_button = ttk.Button(action_frame, text="Start", command=self.start)
        self.start_button.grid(row=0, column=0, sticky="ew")
        self.open_output_button = ttk.Button(action_frame, text="Open Output Folder", command=self.open_output_folder)
        self.open_output_button.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        row += 1
        help_box = ttk.LabelFrame(parent, text="Supported Inputs", padding=8)
        help_box.grid(row=row, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        parent.rowconfigure(row, weight=1)
        ttk.Label(
            help_box,
            text=(
                "Audio/video decoding is handled by ffmpeg. The file picker includes common "
                "formats such as mp3, wav, flac, m4a, mp4, mov, mkv, webm, avi, wmv, m2ts, and more."
            ),
            wraplength=320,
            justify="left",
        ).grid(row=0, column=0, sticky="new")

    def _build_footer(self) -> None:
        footer = ttk.Frame(self.root, padding=(14, 4, 14, 12))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(footer, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew")
        self.count_label = ttk.Label(footer, text="0 files")
        self.count_label.grid(row=0, column=1, padx=(10, 0))

    def _check_environment(self) -> None:
        ok, detail = check_ffmpeg()
        self.log(detail)
        if not ok:
            messagebox.showwarning(
                "ffmpeg not found",
                "ffmpeg is required for broad audio/video format support. Install it, then restart this app.",
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
        for path in paths:
            resolved = path.resolve()
            if resolved in existing or not path.is_file():
                continue
            self.files.append(path)
            existing.add(resolved)
        self._refresh_file_list()

    def remove_selected(self) -> None:
        selected = set(self.file_list.selection())
        self.files = [path for index, path in enumerate(self.files) if str(index) not in selected]
        self._refresh_file_list()

    def clear_files(self) -> None:
        self.files.clear()
        self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        for item in self.file_list.get_children():
            self.file_list.delete(item)
        for index, path in enumerate(self.files):
            size_mb = path.stat().st_size / (1024 * 1024)
            self.file_list.insert("", "end", iid=str(index), values=(str(path), f"{size_mb:.1f} MB"))
        self.count_label.configure(text=f"{len(self.files)} files")
        self.progress.configure(maximum=max(len(self.files), 1), value=0)

    def select_output_dir(self) -> None:
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_dir_var.set(folder)

    def _collect_options(self) -> TranscriptionOptions:
        formats = [name for name, variable in self.format_vars.items() if variable.get()]
        if not formats:
            raise ValueError("Select at least one output format.")

        output_dir = self.output_dir_var.get().strip()
        return TranscriptionOptions(
            model_name=self.model_var.get(),
            language=self.language_var.get().strip(),
            task=self.task_var.get(),
            output_formats=formats,
            output_dir=Path(output_dir) if output_dir else None,
            overwrite=self.overwrite_var.get(),
            device=self.device_var.get(),
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
        self.start_button.configure(state="disabled")
        self.status_label.configure(text="Running")
        self.progress.configure(value=0)
        self.worker = threading.Thread(target=self._run_worker, args=(list(self.files), options), daemon=True)
        self.worker.start()

    def _run_worker(self, files: list[Path], options: TranscriptionOptions) -> None:
        try:
            engine = WhisperBatchEngine(progress=lambda msg: self.messages.put(("log", msg)))
            total = len(files)
            for index, path in enumerate(files, start=1):
                self.messages.put(("status", f"{index}/{total}: {path.name}"))
                result = engine.transcribe_file(path, options)
                self.messages.put(("result", result.output_files))
                self.messages.put(("progress", index))
            self.messages.put(("done", None))
        except Exception as exc:
            self.messages.put(("error", f"{exc}\n{traceback.format_exc()}"))

    def _drain_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "log":
                    self.log(str(payload))
                elif kind == "status":
                    self.status_label.configure(text=str(payload))
                elif kind == "progress":
                    self.progress.configure(value=int(payload))
                elif kind == "result":
                    self.results.extend(payload)
                elif kind == "error":
                    self.log(str(payload))
                    self.start_button.configure(state="normal")
                    self.status_label.configure(text="Failed")
                    messagebox.showerror("Transcription failed", str(payload).splitlines()[0])
                elif kind == "done":
                    self.start_button.configure(state="normal")
                    self.status_label.configure(text="Done")
                    self.log("All jobs finished.")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_messages)

    def log(self, message: str) -> None:
        self.log_text.insert("", "end", values=(message,))
        children = self.log_text.get_children()
        if children:
            self.log_text.see(children[-1])

    def open_output_folder(self) -> None:
        if self.output_dir_var.get().strip():
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
    if "--self-test" in sys.argv:
        ok, _detail = check_ffmpeg()
        raise SystemExit(0 if ok else 1)

    root = Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    WhisperBatchGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
