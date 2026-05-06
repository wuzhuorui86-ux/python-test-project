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

The PDF Voice Reader opens text-based PDF files, extracts selectable page text, shows dictionary definitions for selected words, and reads PDF text or definitions aloud with installed Windows voices.

### Install

From the project directory, install the package and its dependencies:

```powershell
python -m pip install -e .
```

This installs the `pypdf` and `pyttsx3` dependencies and creates the `pdf-voice-reader` launcher.

### Start the GUI

After installing the package, run:

```powershell
pdf-voice-reader
```

If you are running from a source checkout without installing the launcher, install only the dependencies and run the module from the repository root:

```powershell
python -m pip install pypdf pyttsx3
$env:PYTHONPATH = "src"
python -m simple_project.pdf_voice_reader
```

### Use the reader and dictionary

1. Click **Open PDF** and choose a `.pdf` file.
2. Select **All pages** or a single page.
3. Choose a voice and speed.
4. Click **Read aloud** to listen to the selected PDF text.
5. Highlight or double-click a word in the PDF text, then click **Define selected word**.
6. Read the definition in the **Dictionary** panel at the bottom of the window.
7. Click **Read definition aloud** to listen to the definition.
8. Click **Stop** to stop speech playback.

### Notes

- `tkinter` is included with the standard Python installer for Windows.
- `pyttsx3` reads aloud offline using installed Windows SAPI voices.
- Dictionary definitions use the online Free Dictionary API, so dictionary lookup requires an internet connection.
- `pypdf` can extract embedded text from PDFs. Scanned image-only PDFs may need OCR before this app can read their contents.
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

The GUI uses `tkinter` for the desktop window, `pypdf` for PDF text extraction, and `pyttsx3` for offline text-to-speech through Windows voices.
