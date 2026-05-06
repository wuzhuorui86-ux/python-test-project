"""Tkinter GUI for opening a PDF and listening to its text aloud.

The reader is designed for Windows 11 with pyttsx3, which uses the installed
Windows SAPI voices. PDF parsing is provided by the ``pypdf`` package.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import queue
import re
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class PdfPage:
    """Text extracted from a single PDF page."""

    number: int
    text: str


class DependencyError(RuntimeError):
    """Raised when a runtime dependency required by the GUI is missing."""


def require_module(module_name: str, package_name: str) -> Any:
    """Load an optional runtime module or raise a helpful install message."""

    if importlib.util.find_spec(module_name) is None:
        raise DependencyError(
            f"The {package_name} package is required. "
            f"Install it with: python -m pip install {package_name}"
        )
    return importlib.import_module(module_name)


@dataclass(frozen=True)
class DictionaryEntry:
    """Definition text returned for a selected word."""

    word: str
    definition: str


class PdfTextExtractor:
    """Extract readable text from PDF pages."""

    @staticmethod
    def extract_pages(path: Path) -> list[PdfPage]:
        pypdf = require_module("pypdf", "pypdf")
        reader = pypdf.PdfReader(str(path))
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
            pyttsx3 = require_module("pyttsx3", "pyttsx3")
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


class DictionaryClient:
    """Look up English definitions with the public Free Dictionary API."""

    API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

    @classmethod
    def define(cls, word: str) -> DictionaryEntry:
        normalized_word = normalize_word(word)
        if not normalized_word:
            raise ValueError("Select one word in the PDF text first.")

        request = Request(
            cls.API_URL.format(word=quote(normalized_word)),
            headers={"User-Agent": "simple-python-project-pdf-voice-reader"},
        )
        try:
            with urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                raise LookupError(f'No dictionary definition found for "{normalized_word}".') from exc
            raise LookupError(f"Dictionary lookup failed with HTTP {exc.code}.") from exc
        except (TimeoutError, URLError) as exc:
            raise ConnectionError("Dictionary lookup needs an internet connection.") from exc
        except json.JSONDecodeError as exc:
            raise LookupError("Dictionary lookup returned an unreadable response.") from exc

        return DictionaryEntry(word=normalized_word, definition=cls._format_definition(payload, normalized_word))

    @staticmethod
    def _format_definition(payload: Any, word: str) -> str:
        if not isinstance(payload, list) or not payload:
            raise LookupError(f'No dictionary definition found for "{word}".')

        entry = payload[0]
        display_word = entry.get("word", word) if isinstance(entry, dict) else word
        phonetic = entry.get("phonetic", "") if isinstance(entry, dict) else ""
        lines = [display_word.title()]
        if phonetic:
            lines.append(phonetic)
        lines.append("")

        meanings = entry.get("meanings", []) if isinstance(entry, dict) else []
        definition_number = 1
        for meaning in meanings:
            part_of_speech = meaning.get("partOfSpeech", "word")
            definitions = meaning.get("definitions", [])
            for definition_info in definitions[:2]:
                definition = definition_info.get("definition")
                if not definition:
                    continue
                lines.append(f"{definition_number}. ({part_of_speech}) {definition}")
                example = definition_info.get("example")
                if example:
                    lines.append(f"   Example: {example}")
                definition_number += 1
            if definition_number > 4:
                break

        if definition_number == 1:
            raise LookupError(f'No dictionary definition found for "{word}".')

        lines.append("")
        lines.append("Source: Free Dictionary API")
        return "\n".join(lines)


def normalize_word(text: str) -> str:
    """Return one dictionary-friendly word from selected text."""

    matches = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    return matches[0].lower() if matches else ""


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
        self._dictionary_queue: queue.Queue[tuple[str, str, str]] = queue.Queue()
        self._speech = SpeechWorker(self._status_queue)
        self._voice_ids: list[str | None] = [None]
        self._current_definition = ""

        self._build_widgets()
        self._load_voices()
        self.after(150, self._poll_status_queue)
        self.after(150, self._poll_dictionary_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(3, weight=0)

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
        define_button = ttk.Button(controls, text="Define selected word", command=self.define_selected_word)
        define_button.grid(row=0, column=7, padx=(0, 8))
        stop_button = ttk.Button(controls, text="Stop", command=self.stop_reading)
        stop_button.grid(row=0, column=8)

        text_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text_box = tk.Text(text_frame, wrap="word", undo=False)
        self.text_box.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text_box.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text_box.configure(yscrollcommand=scrollbar.set)
        self.text_box.bind("<Double-Button-1>", lambda _event: self.after(50, self.define_selected_word))

        dictionary_frame = ttk.LabelFrame(self, text="Dictionary", padding=(10, 6, 10, 10))
        dictionary_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        dictionary_frame.columnconfigure(0, weight=1)

        self.dictionary_text = tk.Text(dictionary_frame, wrap="word", height=6, undo=False)
        self.dictionary_text.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        dictionary_scrollbar = ttk.Scrollbar(dictionary_frame, orient="vertical", command=self.dictionary_text.yview)
        dictionary_scrollbar.grid(row=0, column=1, sticky="ns")
        self.dictionary_text.configure(yscrollcommand=dictionary_scrollbar.set)
        self.dictionary_text.insert(tk.END, "Select a word in the PDF text, then click Define selected word.")

        read_definition_button = ttk.Button(
            dictionary_frame,
            text="Read definition aloud",
            command=self.read_definition_aloud,
        )
        read_definition_button.grid(row=0, column=2, sticky="ns", padx=(8, 0))

        self.status_var = tk.StringVar(value="Open a PDF to begin.")
        status = ttk.Label(self, textvariable=self.status_var, padding=(10, 0, 10, 10), anchor="w")
        status.grid(row=4, column=0, sticky="ew")

    def _load_voices(self) -> None:
        voice_labels = ["Default Windows voice"]
        try:
            pyttsx3 = require_module("pyttsx3", "pyttsx3")
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

        self._speak_text(text)

    def read_definition_aloud(self) -> None:
        if not self._current_definition.strip():
            messagebox.showinfo("No definition", "Look up a word before reading a definition aloud.")
            return
        self._speak_text(self._current_definition)

    def define_selected_word(self) -> None:
        word = self._word_from_text_selection()
        if not word:
            messagebox.showinfo("Select a word", "Highlight or double-click one word in the PDF text first.")
            return

        self._set_dictionary_text(f'Looking up "{word}"...', store_for_reading=False)
        self.status_var.set(f'Looking up "{word}" in the dictionary...')
        threading.Thread(target=self._lookup_definition, args=(word,), daemon=True).start()

    def stop_reading(self) -> None:
        self._speech.stop()
        self.status_var.set("Stopping...")

    def _speak_text(self, text: str) -> None:
        voice_index = max(0, self.voice_combo.current())
        voice_id = self._voice_ids[voice_index] if voice_index < len(self._voice_ids) else None
        self._speech.speak(text=text, rate=int(self.rate_var.get()), voice_id=voice_id)

    def _lookup_definition(self, word: str) -> None:
        try:
            entry = DictionaryClient.define(word)
        except Exception as exc:
            self._dictionary_queue.put(("error", word, str(exc)))
            return
        self._dictionary_queue.put(("definition", entry.word, entry.definition))

    def _word_from_text_selection(self) -> str:
        try:
            selected_text = self.text_box.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            insert_index = self.text_box.index(tk.INSERT)
            start = self.text_box.index(f"{insert_index} wordstart")
            end = self.text_box.index(f"{insert_index} wordend")
            selected_text = self.text_box.get(start, end)
        return normalize_word(selected_text)

    def _set_dictionary_text(self, text: str, *, store_for_reading: bool = True) -> None:
        if store_for_reading:
            self._current_definition = text
        self.dictionary_text.delete("1.0", tk.END)
        self.dictionary_text.insert(tk.END, text)

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

    def _poll_dictionary_queue(self) -> None:
        while True:
            try:
                message_type, word, message = self._dictionary_queue.get_nowait()
            except queue.Empty:
                break
            self._set_dictionary_text(message, store_for_reading=message_type == "definition")
            if message_type == "definition":
                self.status_var.set(f'Definition loaded for "{word}". Click Read definition aloud to listen.')
            else:
                self.status_var.set(f'Dictionary error for "{word}".')
        self.after(150, self._poll_dictionary_queue)

    def _on_close(self) -> None:
        self._speech.stop()
        self.destroy()


def main() -> None:
    """Launch the PDF voice reader GUI."""

    app = PdfVoiceReaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
