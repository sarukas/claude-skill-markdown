# claude-skill-markdown

A Claude Code skill that converts documents to Markdown. Supports 14 formats (PDF, DOCX, XLSX, PPTX, HTML, CSV, EPUB, MSG, and more) via a unified CLI.

## Installation

Clone into your project's `.claude/skills/` directory:

```bash
git clone https://github.com/sarukas/claude-skill-markdown .claude/skills/markdown
```

Or using the [skill](https://github.com/anthropics/skill) CLI:

```bash
npx skill install sarukas/claude-skill-markdown
```

Claude Code automatically discovers skills from `SKILL.md` files in `.claude/skills/`.

### Dependencies

Install all format dependencies:

```bash
pip install -r scripts/converters/requirements-all.txt
```

Or install per-format as needed:

```bash
pip install -r scripts/converters/requirements-pdf.txt       # PDF
pip install -r scripts/converters/requirements-xlsx.txt      # XLSX
pip install -r scripts/converters/requirements-html.txt      # HTML
pip install -r scripts/converters/requirements-csv.txt       # CSV (stdlib, nothing to install)
pip install -r scripts/converters/requirements-markitdown.txt # DOCX, XLS, PPTX, EPUB, MSG, etc.
```

## Supported Formats

| Format | Extensions | Library |
|--------|-----------|---------|
| PDF | .pdf | pymupdf4llm + pdfplumber |
| XLSX | .xlsx | openpyxl |
| XLS | .xls | markitdown |
| DOCX | .docx | markitdown |
| PPTX | .pptx | markitdown |
| HTML | .html, .htm | html2text + BeautifulSoup |
| CSV/TSV | .csv, .tsv | stdlib csv |
| EPUB | .epub | markitdown |
| MSG | .msg | markitdown |
| IPYNB | .ipynb | markitdown |
| JSON | .json | markitdown |
| XML | .xml | markitdown |
| ZIP | .zip | markitdown |
| Images | .jpg, .png, .gif, .bmp, .tiff, .webp | markitdown |

**14 formats, 27 extensions total.**

## Usage

### Single File

```bash
python scripts/convert_to_md.py report.pdf
python scripts/convert_to_md.py report.pdf output.md
python scripts/convert_to_md.py data.xlsx --sheets Sheet1
```

### Batch Conversion

```bash
python scripts/convert_to_md.py -d ./contracts/ -r              # All types, recursive
python scripts/convert_to_md.py -d ./contracts/ -t pdf docx      # Only PDF and DOCX
python scripts/convert_to_md.py -d ./contracts/ -o ./output/      # Custom output dir
```

### Info Commands

```bash
python scripts/convert_to_md.py --list-formats     # Show all formats + dependency status
python scripts/convert_to_md.py --check-deps        # Check all dependencies
python scripts/convert_to_md.py --check-deps pdf    # Check PDF deps only
```

## How It Works

When installed as a Claude Code skill, Claude automatically uses this tool when you ask it to read or analyze non-Markdown documents. For example:

- "Read this PDF and summarize it"
- "Convert all the DOCX files in this folder to Markdown"
- "Extract tables from this spreadsheet"

Claude converts the document to Markdown first, then works with the text.

## Architecture

```
scripts/
  convert_to_md.py          # Unified CLI entry point
  converters/
    __init__.py
    base.py                  # Abstract converter base class
    registry.py              # Format/extension registry
    csv_converter.py         # CSV/TSV
    html_converter.py        # HTML
    xlsx_converter.py        # XLSX (openpyxl)
    pdf_converter.py         # PDF (pymupdf4llm + pdfplumber)
    markitdown_converters.py # DOCX, XLS, PPTX, EPUB, MSG, etc.
    requirements-*.txt       # Per-format dependencies
```

## License

MIT
