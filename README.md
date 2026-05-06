# simple-python-project

A simple Python project that demonstrates package structure, a tiny calculator module, tests, and a Windows-friendly PDF voice reader GUI.

## Run tests

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## Run the CLI

```bash
PYTHONPATH=src python -m simple_project 2 3
```

## Run the PDF Voice Reader GUI on Windows 11

The PDF Voice Reader opens a PDF, extracts selectable page text, and reads the text aloud with installed Windows voices.

1. Install the project dependencies:

   ```powershell
   python -m pip install -e .
   ```

2. Start the GUI:

   ```powershell
   pdf-voice-reader
   ```

   If you are running from a source checkout without installing the script, use:

   ```powershell
   python -m simple_project.pdf_voice_reader
   ```

3. Click **Open PDF**, choose a `.pdf` file, optionally select one page or all pages, choose a voice/speed, and click **Read aloud**.
4. To use the dictionary, highlight or double-click a word in the PDF text, then click **Define selected word**. The definition appears in the Dictionary panel at the bottom of the window.
5. Click **Read definition aloud** in the Dictionary panel to listen to the definition.

The GUI uses `tkinter` for the desktop window, `pypdf` for PDF text extraction, `pyttsx3` for offline text-to-speech through Windows voices, and the online Free Dictionary API for word definitions.
