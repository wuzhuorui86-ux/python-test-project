"""Tkinter GUI for opening a PDF and listening to its text aloud.

The reader is designed for Windows 11 with pyttsx3, which uses the installed
Windows SAPI voices. PDF parsing is provided by the ``pypdf`` package.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any


@dataclass(frozen=True)
class PdfPage:
    """Text extracted from a single PDF page."""

    number: int
    text: str


class DependencyError(RuntimeError):
    """Raised when a runtime dependency required by the GUI is missing."""


class PdfTextExtractor:
    """Extract readable text from PDF pages."""

    @staticmethod
    def extract_pages(path: Path) -> list[PdfPage]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - exercised by users without deps
            raise DependencyError(
                "The pypdf package is required. Install it with: python -m pip install pypdf"
            ) from exc

        reader = PdfReader(str(path))
        pages: list[PdfPage] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append(PdfPage(number=index, text=text.strip()))
        return pages


class SpeechWorker:
    """Run text-to-speech on a background thread so the GUI stays responsive."""

    def __init__(self, status_queue: queue.Queue[str]) -> None:
        self._status_queue = status_queue
        self._thread: threading.Thread | None = None
        self._stop_requested = threading.Event()
        self._engine: Any | None = None

    @property
    def is_speaking(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def speak(self, text: str, rate: int, voice_id: str | None) -> None:
        self.stop()
        self._stop_requested.clear()
        self._thread = threading.Thread(
            target=self._speak_in_thread,
            args=(text, rate, voice_id),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        if self._engine is not None:
            try:
                self._engine.stop()
            except RuntimeError:
                pass

    def _speak_in_thread(self, text: str, rate: int, voice_id: str | None) -> None:
        try:
            try:
                import pyttsx3
            except ImportError as exc:
                raise DependencyError(
                    "The pyttsx3 package is required. Install it with: python -m pip install pyttsx3"
                ) from exc

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", rate)
            if voice_id:
                self._engine.setProperty("voice", voice_id)
            self._status_queue.put("Reading aloud...")
            if not self._stop_requested.is_set():
                self._engine.say(text)
                self._engine.runAndWait()
            self._status_queue.put("Stopped." if self._stop_requested.is_set() else "Finished reading.")
        except Exception as exc:  # pragma: no cover - GUI error reporting path
            self._status_queue.put(f"Speech error: {exc}")
        finally:
            self._engine = None


class PdfVoiceReaderApp(tk.Tk):
    """Windows-friendly GUI for opening PDFs and listening to their contents."""

    def __init__(self) -> None:
        super().__init__()
        self.title("PDF Voice Reader")
        self.geometry("900x650")
        self.minsize(760, 520)

        self._pages: list[PdfPage] = []
        self._current_file: Path | None = None
        self._status_queue: queue.Queue[str] = queue.Queue()
        self._speech = SpeechWorker(self._status_queue)
        self._voice_ids: list[str | None] = [None]

        self._build_widgets()
        self._load_voices()
        self.after(150, self._poll_status_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top_bar = ttk.Frame(self, padding=10)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.columnconfigure(1, weight=1)

        open_button = ttk.Button(top_bar, text="Open PDF", command=self.open_pdf)
        open_button.grid(row=0, column=0, padx=(0, 8))

        self.file_label = ttk.Label(top_bar, text="No PDF selected")
        self.file_label.grid(row=0, column=1, sticky="ew")

        controls = ttk.Frame(self, padding=(10, 0, 10, 10))
        controls.grid(row=1, column=0, sticky="ew")
        for column in (1, 3):
            controls.columnconfigure(column, weight=1)

        ttk.Label(controls, text="Page:").grid(row=0, column=0, sticky="w")
        self.page_var = tk.StringVar(value="All pages")
        self.page_combo = ttk.Combobox(controls, textvariable=self.page_var, state="readonly", values=["All pages"])
        self.page_combo.grid(row=0, column=1, sticky="ew", padx=(4, 12))
        self.page_combo.bind("<<ComboboxSelected>>", lambda _event: self._show_selected_page())

        ttk.Label(controls, text="Voice:").grid(row=0, column=2, sticky="w")
        self.voice_var = tk.StringVar(value="Default Windows voice")
        self.voice_combo = ttk.Combobox(controls, textvariable=self.voice_var, state="readonly")
        self.voice_combo.grid(row=0, column=3, sticky="ew", padx=(4, 12))

        ttk.Label(controls, text="Speed:").grid(row=0, column=4, sticky="w")
        self.rate_var = tk.IntVar(value=180)
        self.rate_scale = ttk.Scale(controls, from_=110, to=260, orient="horizontal", variable=self.rate_var)
        self.rate_scale.grid(row=0, column=5, sticky="ew", padx=(4, 12))

        read_button = ttk.Button(controls, text="Read aloud", command=self.read_aloud)
        read_button.grid(row=0, column=6, padx=(0, 8))
        stop_button = ttk.Button(controls, text="Stop", command=self.stop_reading)
        stop_button.grid(row=0, column=7)

        text_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text_box = tk.Text(text_frame, wrap="word", undo=False)
        self.text_box.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text_box.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text_box.configure(yscrollcommand=scrollbar.set)

        self.status_var = tk.StringVar(value="Open a PDF to begin.")
        status = ttk.Label(self, textvariable=self.status_var, padding=(10, 0, 10, 10), anchor="w")
        status.grid(row=3, column=0, sticky="ew")

    def _load_voices(self) -> None:
        voice_labels = ["Default Windows voice"]
        try:
            import pyttsx3

            engine = pyttsx3.init()
            voices = engine.getProperty("voices") or []
            self._voice_ids = [None]
            for voice in voices:
                voice_labels.append(getattr(voice, "name", "Installed voice"))
                self._voice_ids.append(getattr(voice, "id", None))
            engine.stop()
        except Exception:
            voice_labels = ["Default Windows voice"]
            self._voice_ids = [None]

        self.voice_combo.configure(values=voice_labels)
        self.voice_combo.current(0)

    def open_pdf(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not filename:
            return

        path = Path(filename)
        try:
            pages = PdfTextExtractor.extract_pages(path)
        except Exception as exc:
            messagebox.showerror("Unable to open PDF", str(exc))
            self.status_var.set("Unable to open PDF.")
            return

        self._current_file = path
        self._pages = pages
        page_values = ["All pages", *(f"Page {page.number}" for page in pages)]
        self.page_combo.configure(values=page_values)
        self.page_combo.current(0)
        self.file_label.configure(text=str(path))
        self.status_var.set(f"Loaded {len(pages)} page(s).")
        self._show_selected_page()

    def read_aloud(self) -> None:
        text = self._selected_text()
        if not text.strip():
            messagebox.showinfo("Nothing to read", "This selection does not contain readable text.")
            return

        voice_index = max(0, self.voice_combo.current())
        voice_id = self._voice_ids[voice_index] if voice_index < len(self._voice_ids) else None
        self._speech.speak(text=text, rate=int(self.rate_var.get()), voice_id=voice_id)

    def stop_reading(self) -> None:
        self._speech.stop()
        self.status_var.set("Stopping...")

    def _show_selected_page(self) -> None:
        self.text_box.delete("1.0", tk.END)
        self.text_box.insert(tk.END, self._selected_text() or "No readable text found in this selection.")

    def _selected_text(self) -> str:
        selection = self.page_var.get()
        if selection == "All pages":
            return "\n\n".join(f"Page {page.number}\n{page.text}" for page in self._pages)

        try:
            page_number = int(selection.removeprefix("Page "))
        except ValueError:
            return ""

        for page in self._pages:
            if page.number == page_number:
                return page.text
        return ""

    def _poll_status_queue(self) -> None:
        while True:
            try:
                message = self._status_queue.get_nowait()
            except queue.Empty:
                break
            self.status_var.set(message)
        self.after(150, self._poll_status_queue)

    def _on_close(self) -> None:
        self._speech.stop()
        self.destroy()


def main() -> None:
    """Launch the PDF voice reader GUI."""

    app = PdfVoiceReaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
