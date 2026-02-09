---
name: markdown
description: Convert any document format TO Markdown. Supports 14 formats (PDF, DOCX, XLSX, PPTX, HTML, CSV, EPUB, MSG, and more) via unified CLI. Use when Claude needs to read or extract text from non-Markdown files.
---

# Markdown - Document-to-Markdown Conversion

Convert documents to Markdown for reading, analysis, and processing.

## Decision Tree

```
User Request
|
+-- Convert file to Markdown
|   +-- Single file --> scripts/convert_to_md.py input.pdf
|   +-- With explicit output --> scripts/convert_to_md.py input.pdf output.md
|   +-- Batch directory --> scripts/convert_to_md.py -d ./folder/ -r [-t pdf docx]
|   +-- Check available formats --> scripts/convert_to_md.py --list-formats
|   +-- Check dependencies --> scripts/convert_to_md.py --check-deps [format]
|
+-- Read/analyze document content
|   +-- Convert first, then analyze the Markdown output
|
+-- XLSX with specific sheets
|   +-- scripts/convert_to_md.py data.xlsx --sheets Sheet1 Sheet2
```

## Single File Conversion

```bash
python scripts/convert_to_md.py report.pdf
python scripts/convert_to_md.py report.pdf output.md
python scripts/convert_to_md.py data.xlsx --sheets Sheet1
```

Output defaults to same name with `.md` extension in the same directory.

## Batch Conversion

```bash
python scripts/convert_to_md.py -d ./contracts/ -r              # All supported types, recursive
python scripts/convert_to_md.py -d ./contracts/ -t pdf docx      # Only PDF and DOCX
python scripts/convert_to_md.py -d ./contracts/ -o ./output/      # Custom output directory
python scripts/convert_to_md.py -d ./contracts/ --no-skip         # Re-convert even if .md exists
```

## Info Commands

```bash
python scripts/convert_to_md.py --list-formats     # Show all formats + dependency status
python scripts/convert_to_md.py --check-deps        # Check all dependencies
python scripts/convert_to_md.py --check-deps pdf    # Check PDF deps only
```

## Supported Formats

| Format | Extensions | Library | Notes |
|--------|-----------|---------|-------|
| PDF | .pdf | pymupdf4llm + pdfplumber | Best table extraction, dual-engine |
| XLSX | .xlsx | openpyxl | Sheet selection, formula preservation |
| XLS | .xls | markitdown | Legacy Excel |
| DOCX | .docx | markitdown | Word documents |
| PPTX | .pptx | markitdown | PowerPoint slides |
| HTML | .html, .htm | html2text + BeautifulSoup | Table preservation |
| CSV/TSV | .csv, .tsv | stdlib csv | Auto-detect delimiter |
| EPUB | .epub | markitdown | E-books |
| MSG | .msg | markitdown | Outlook messages |
| IPYNB | .ipynb | markitdown | Jupyter notebooks |
| JSON | .json | markitdown | Structured data |
| XML | .xml | markitdown | Structured markup |
| ZIP | .zip | markitdown | Archive contents |
| Images | .jpg, .jpeg, .png, .gif, .bmp, .tiff, .webp | markitdown | OCR/description |
| Audio | .mp3, .wav | markitdown | Transcription |

**14 formats, 27 extensions total.**

## Format-Specific Options

### PDF
- Dual-engine: pymupdf4llm (primary) with pdfplumber fallback for tables
- Large files chunked automatically

### XLSX
- `--sheets Sheet1 Sheet2`: Convert only specific sheets
- Preserves table structure with headers

### HTML
- Strips scripts/styles, preserves tables and links
- Handles both local files and saved web pages

### CSV/TSV
- Auto-detects delimiter (comma, tab, semicolon, pipe)
- Outputs as Markdown table

## Dependencies

Each format has its own requirements file in `scripts/converters/`:

```bash
# Install all dependencies
pip install -r scripts/converters/requirements-all.txt

# Or install per-format
pip install -r scripts/converters/requirements-pdf.txt
pip install -r scripts/converters/requirements-xlsx.txt
pip install -r scripts/converters/requirements-html.txt
pip install -r scripts/converters/requirements-csv.txt
pip install -r scripts/converters/requirements-markitdown.txt   # DOCX, XLS, PPTX, EPUB, MSG, etc.
```

Core dependencies:
- **PDF**: `pymupdf pymupdf4llm pdfplumber`
- **XLSX**: `openpyxl`
- **HTML**: `beautifulsoup4 html2text`
- **CSV**: stdlib (no install needed)
- **Markitdown formats**: `markitdown`

## Troubleshooting

**"Unsupported file extension"**
- Run `--list-formats` to see supported extensions
- Check file has correct extension

**"Missing dependencies"**
- Run `--check-deps [format]` to see what's needed
- Install with pip as shown above

**Large PDF produces poor output**
- The converter uses dual-engine approach; pdfplumber handles complex tables better
- For scanned PDFs, OCR support depends on markitdown

**XLSX tables look wrong**
- Try specifying `--sheets` to convert individual sheets
- Very wide tables may wrap in Markdown

**Verbose logging**
```bash
python scripts/convert_to_md.py -v report.pdf    # Debug-level logging
python scripts/convert_to_md.py -q report.pdf    # Suppress informational output
```
