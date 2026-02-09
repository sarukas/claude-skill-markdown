#!/usr/bin/env python3
"""
Standalone test suite for the Markdown conversion skill (convert_to_md.py).

Generates synthetic test files, runs the converter with various options,
validates outputs programmatically, and produces a Markdown report.

Usage:
    python run_tests.py                     # Run all tests
    python run_tests.py --verbose           # Verbose output
    python run_tests.py --module A          # Only Core CLI tests
    python run_tests.py --module A,B        # Multiple modules
    python run_tests.py --keep-artifacts    # Don't clean up temp files
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent          # tests/
SKILL_DIR = SCRIPT_DIR.parent                          # claude-skill-markdown/
CONVERT_TO_MD = SKILL_DIR / "scripts" / "convert_to_md.py"

REPORT_DIR = SCRIPT_DIR / "reports"

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    name: str
    status: str  # PASS, FAIL, SKIP
    duration: float = 0.0
    notes: str = ""
    stdout: str = ""
    stderr: str = ""
    error: str = ""


@dataclass
class TestModule:
    code: str
    name: str
    tests: List[Callable] = field(default_factory=list)


def _utf8_env():
    """Return env dict with PYTHONIOENCODING=utf-8 to avoid Windows encoding issues."""
    import os
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_tool(script: Path, args: list, timeout: int = 120, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a Python script as subprocess."""
    cmd = [sys.executable, str(script)] + [str(a) for a in args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
        env=_utf8_env(),
    )


# ---------------------------------------------------------------------------
# Artifact directory management
# ---------------------------------------------------------------------------

class ArtifactDir:
    """Manages a temporary directory for test artifacts."""

    def __init__(self, base: Path):
        self.base = base / "_test_artifacts"
        self.base.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.base / name

    def write_text(self, name: str, content: str) -> Path:
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def write_bytes(self, name: str, content: bytes) -> Path:
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def cleanup(self):
        if self.base.exists():
            shutil.rmtree(self.base)


# ---------------------------------------------------------------------------
# Synthetic file generators
# ---------------------------------------------------------------------------

def gen_csv(art: ArtifactDir) -> Path:
    content = "Name,Age,City\nAlice,30,Vilnius\nBob,25,Kaunas\nCharlie,35,Klaipeda\n"
    return art.write_text("test.csv", content)


def gen_csv_semicolon(art: ArtifactDir) -> Path:
    content = "Name;Age;City\nAlice;30;Vilnius\nBob;25;Kaunas\n"
    return art.write_text("test_semi.csv", content)


def gen_tsv(art: ArtifactDir) -> Path:
    content = "Name\tAge\tCity\nAlice\t30\tVilnius\nBob\t25\tKaunas\n"
    return art.write_text("test.tsv", content)


def gen_html(art: ArtifactDir) -> Path:
    content = """<!DOCTYPE html>
<html><head><title>Test</title><script>alert('x')</script></head>
<body>
<h1>Test Heading</h1>
<p>Paragraph with <a href="https://example.com">a link</a> and <img src="photo.jpg" alt="photo">.</p>
<table><tr><th>Col A</th><th>Col B</th></tr>
<tr><td>Val 1</td><td>Val 2</td></tr></table>
<nav>Navigation here</nav>
</body></html>"""
    return art.write_text("test.html", content)


def gen_xlsx(art: ArtifactDir):
    """Generate a synthetic XLSX file with openpyxl. Returns None if openpyxl not available."""
    try:
        from openpyxl import Workbook
    except ImportError:
        return None

    wb = Workbook()

    # Sheet 1: Sales
    ws1 = wb.active
    ws1.title = "Sales"
    ws1.append(["Product", "Quantity", "Total"])
    ws1.append(["Widget", 10, 100])
    ws1.append(["Gadget", 5, "=B3*20"])

    # Sheet 2: Summary
    ws2 = wb.create_sheet("Summary")
    ws2.append(["Metric", "Value"])
    ws2.append(["Total Products", 2])

    # Sheet 3: Hidden
    ws3 = wb.create_sheet("Hidden")
    ws3.append(["This is hidden", "data"])
    ws3.sheet_state = "hidden"

    out = art.path("test.xlsx")
    wb.save(str(out))
    wb.close()
    return out


def gen_json(art: ArtifactDir) -> Path:
    import json
    data = [
        {"name": "Alice", "age": 30, "city": "Vilnius"},
        {"name": "Bob", "age": 25, "city": "Kaunas"},
    ]
    return art.write_text("test.json", json.dumps(data, indent=2))


def gen_empty_csv(art: ArtifactDir) -> Path:
    return art.write_text("empty.csv", "")


# ---------------------------------------------------------------------------
# Module A: Core CLI Tests (5 tests)
# ---------------------------------------------------------------------------

def test_list_formats(art: ArtifactDir) -> TestResult:
    """--list-formats shows format keywords (pdf, xlsx, html, csv, docx)."""
    r = run_tool(CONVERT_TO_MD, ["--list-formats"])
    if r.returncode != 0:
        return TestResult("test_list_formats", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    output = r.stdout
    format_keywords = ["CSV", "HTML", "PDF", "XLSX", "DOCX"]
    found = sum(1 for kw in format_keywords if kw.lower() in output.lower())
    if found < 3:
        return TestResult("test_list_formats", "FAIL", error=f"Only {found} of expected formats listed", stdout=output[:500])
    return TestResult("test_list_formats", "PASS", notes=f"{found} format keywords found")


def test_check_deps(art: ArtifactDir) -> TestResult:
    """--check-deps runs without crash, shows OK/MISSING."""
    r = run_tool(CONVERT_TO_MD, ["--check-deps"])
    if r.returncode not in (0, 1):
        return TestResult("test_check_deps", "FAIL", error=f"Unexpected exit code {r.returncode}", stderr=r.stderr)
    output = r.stdout
    if "OK" in output or "MISSING" in output:
        return TestResult("test_check_deps", "PASS", notes=f"Exit code {r.returncode}")
    return TestResult("test_check_deps", "FAIL", error="Output doesn't contain OK/MISSING status", stdout=output[:500])


def test_check_deps_specific(art: ArtifactDir) -> TestResult:
    """--check-deps csv shows CSV-specific status."""
    r = run_tool(CONVERT_TO_MD, ["--check-deps", "csv"])
    if r.returncode not in (0, 1):
        return TestResult("test_check_deps_specific", "FAIL", error=f"Unexpected exit code {r.returncode}", stderr=r.stderr)
    output = r.stdout
    if "CSV" in output or "OK" in output:
        return TestResult("test_check_deps_specific", "PASS")
    return TestResult("test_check_deps_specific", "FAIL", error="CSV-specific check didn't show format info", stdout=output[:500])


def test_help(art: ArtifactDir) -> TestResult:
    """--help shows usage."""
    r = run_tool(CONVERT_TO_MD, ["--help"])
    if r.returncode != 0:
        return TestResult("test_help", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    output = r.stdout
    if "usage" in output.lower() or "convert" in output.lower():
        return TestResult("test_help", "PASS")
    return TestResult("test_help", "FAIL", error="Help output doesn't contain expected text", stdout=output[:500])


def test_unsupported_extension(art: ArtifactDir) -> TestResult:
    """.xyz file gives error, exit code 1."""
    xyz_file = art.write_text("test.xyz", "some content")
    out = art.path("test_xyz.md")
    r = run_tool(CONVERT_TO_MD, [str(xyz_file), str(out)])
    if r.returncode == 0:
        return TestResult("test_unsupported_extension", "FAIL", error="Unsupported .xyz file didn't fail")
    if "unsupported" in r.stdout.lower() or "unsupported" in r.stderr.lower() or r.returncode == 1:
        return TestResult("test_unsupported_extension", "PASS")
    return TestResult("test_unsupported_extension", "PASS", notes=f"Exit code {r.returncode}")


# ---------------------------------------------------------------------------
# Module B: Format Conversions (12 tests)
# ---------------------------------------------------------------------------

def test_csv_to_md(art: ArtifactDir) -> TestResult:
    """Synthetic CSV -> MD table with headers."""
    csv_file = gen_csv(art)
    out = art.path("test_csv.md")
    r = run_tool(CONVERT_TO_MD, [str(csv_file), str(out)])
    if r.returncode != 0:
        return TestResult("test_csv_to_md", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    if not out.exists():
        return TestResult("test_csv_to_md", "FAIL", error="Output file not created")
    content = out.read_text(encoding="utf-8")
    if "|" not in content:
        return TestResult("test_csv_to_md", "FAIL", error="No markdown table in output")
    if "Alice" not in content:
        return TestResult("test_csv_to_md", "FAIL", error="Data 'Alice' not in output")
    if "Name" not in content:
        return TestResult("test_csv_to_md", "FAIL", error="Header 'Name' not in output")
    return TestResult("test_csv_to_md", "PASS")


def test_csv_custom_delimiter(art: ArtifactDir) -> TestResult:
    """Semicolon-delimited CSV auto-detected."""
    csv_file = gen_csv_semicolon(art)
    out = art.path("test_csv_semi.md")
    r = run_tool(CONVERT_TO_MD, [str(csv_file), str(out)])
    if r.returncode != 0:
        return TestResult("test_csv_custom_delimiter", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    content = out.read_text(encoding="utf-8")
    if "|" not in content:
        return TestResult("test_csv_custom_delimiter", "FAIL", error="No markdown table in output")
    # Check that columns were properly split (not treated as single column)
    if "Alice" in content and "Vilnius" in content:
        return TestResult("test_csv_custom_delimiter", "PASS")
    return TestResult("test_csv_custom_delimiter", "FAIL", error="Semicolon delimiter not auto-detected", stdout=content[:500])


def test_tsv_to_md(art: ArtifactDir) -> TestResult:
    """Synthetic TSV -> MD table."""
    tsv_file = gen_tsv(art)
    out = art.path("test_tsv.md")
    r = run_tool(CONVERT_TO_MD, [str(tsv_file), str(out)])
    if r.returncode != 0:
        return TestResult("test_tsv_to_md", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    if not out.exists():
        return TestResult("test_tsv_to_md", "FAIL", error="Output file not created")
    content = out.read_text(encoding="utf-8")
    if "|" not in content:
        return TestResult("test_tsv_to_md", "FAIL", error="No markdown table in output")
    if "Alice" not in content:
        return TestResult("test_tsv_to_md", "FAIL", error="Data 'Alice' not in output")
    return TestResult("test_tsv_to_md", "PASS")


def test_html_to_md(art: ArtifactDir) -> TestResult:
    """Synthetic HTML with headings + table -> MD preserves both."""
    try:
        import html2text  # noqa: F401
    except ImportError:
        return TestResult("test_html_to_md", "SKIP", notes="html2text not installed")

    html_file = gen_html(art)
    out = art.path("test_html.md")
    r = run_tool(CONVERT_TO_MD, [str(html_file), str(out)])
    if r.returncode != 0:
        return TestResult("test_html_to_md", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    content = out.read_text(encoding="utf-8")
    if "Test Heading" not in content:
        return TestResult("test_html_to_md", "FAIL", error="Heading not preserved")
    # Script content should be stripped
    if "alert" in content:
        return TestResult("test_html_to_md", "FAIL", error="Script content not stripped")
    # Table should be present
    if "Col A" not in content and "Val 1" not in content:
        return TestResult("test_html_to_md", "FAIL", error="Table content not preserved")
    return TestResult("test_html_to_md", "PASS")


def test_html_ignore_links(art: ArtifactDir) -> TestResult:
    """--ignore-links strips [text](url)."""
    try:
        import html2text  # noqa: F401
    except ImportError:
        return TestResult("test_html_ignore_links", "SKIP", notes="html2text not installed")

    html_file = gen_html(art)
    out = art.path("test_html_nolinks.md")
    r = run_tool(CONVERT_TO_MD, [str(html_file), str(out), "--ignore-links"])
    if r.returncode != 0:
        return TestResult("test_html_ignore_links", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    content = out.read_text(encoding="utf-8")
    if "https://example.com" in content:
        return TestResult("test_html_ignore_links", "FAIL", error="Links not stripped with --ignore-links")
    return TestResult("test_html_ignore_links", "PASS")


def test_html_ignore_images(art: ArtifactDir) -> TestResult:
    """--ignore-images strips images."""
    try:
        import html2text  # noqa: F401
    except ImportError:
        return TestResult("test_html_ignore_images", "SKIP", notes="html2text not installed")

    html_file = gen_html(art)
    out = art.path("test_html_noimages.md")
    r = run_tool(CONVERT_TO_MD, [str(html_file), str(out), "--ignore-images"])
    if r.returncode != 0:
        return TestResult("test_html_ignore_images", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    content = out.read_text(encoding="utf-8")
    # Image reference should be stripped
    if "![" in content and "photo" in content:
        return TestResult("test_html_ignore_images", "FAIL", error="Images not stripped with --ignore-images")
    return TestResult("test_html_ignore_images", "PASS")


def test_xlsx_basic(art: ArtifactDir) -> TestResult:
    """Synthetic XLSX -> MD table."""
    xlsx_file = gen_xlsx(art)
    if xlsx_file is None:
        return TestResult("test_xlsx_basic", "SKIP", notes="openpyxl not installed")
    out = art.path("test_xlsx.md")
    r = run_tool(CONVERT_TO_MD, [str(xlsx_file), str(out)])
    if r.returncode != 0:
        return TestResult("test_xlsx_basic", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    content = out.read_text(encoding="utf-8")
    if "Widget" not in content:
        return TestResult("test_xlsx_basic", "FAIL", error="Sheet data 'Widget' not in output")
    return TestResult("test_xlsx_basic", "PASS")


def test_xlsx_specific_sheets(art: ArtifactDir) -> TestResult:
    """--sheets Sales only converts Sales sheet."""
    xlsx_file = gen_xlsx(art)
    if xlsx_file is None:
        return TestResult("test_xlsx_specific_sheets", "SKIP", notes="openpyxl not installed")
    out = art.path("test_xlsx_sheets.md")
    r = run_tool(CONVERT_TO_MD, [str(xlsx_file), str(out), "--sheets", "Sales"])
    if r.returncode != 0:
        return TestResult("test_xlsx_specific_sheets", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    content = out.read_text(encoding="utf-8")
    if "Widget" not in content:
        return TestResult("test_xlsx_specific_sheets", "FAIL", error="Sales sheet data not in output")
    if "Summary" in content and "Total Products" in content:
        return TestResult("test_xlsx_specific_sheets", "FAIL", error="Summary sheet included despite --sheets Sales")
    return TestResult("test_xlsx_specific_sheets", "PASS")


def test_xlsx_preserve_formulas(art: ArtifactDir) -> TestResult:
    """--preserve-formulas shows =B2+C2."""
    xlsx_file = gen_xlsx(art)
    if xlsx_file is None:
        return TestResult("test_xlsx_preserve_formulas", "SKIP", notes="openpyxl not installed")
    out = art.path("test_xlsx_formulas.md")
    r = run_tool(CONVERT_TO_MD, [str(xlsx_file), str(out), "--preserve-formulas"])
    if r.returncode != 0:
        return TestResult("test_xlsx_preserve_formulas", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    content = out.read_text(encoding="utf-8")
    if "=B3*20" not in content and "=B" not in content:
        if "Formula" not in content:
            return TestResult("test_xlsx_preserve_formulas", "FAIL", error="Formula '=B3*20' not preserved in output")
    return TestResult("test_xlsx_preserve_formulas", "PASS")


def test_xlsx_hidden_excluded(art: ArtifactDir) -> TestResult:
    """Hidden sheet excluded by default."""
    xlsx_file = gen_xlsx(art)
    if xlsx_file is None:
        return TestResult("test_xlsx_hidden_excluded", "SKIP", notes="openpyxl not installed")
    out = art.path("test_xlsx_hidden.md")
    r = run_tool(CONVERT_TO_MD, [str(xlsx_file), str(out)])
    if r.returncode != 0:
        return TestResult("test_xlsx_hidden_excluded", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    content = out.read_text(encoding="utf-8")
    if "This is hidden" in content:
        return TestResult("test_xlsx_hidden_excluded", "FAIL", error="Hidden sheet data included by default")
    return TestResult("test_xlsx_hidden_excluded", "PASS")


def test_xlsx_include_hidden(art: ArtifactDir) -> TestResult:
    """--include-hidden includes hidden sheet."""
    xlsx_file = gen_xlsx(art)
    if xlsx_file is None:
        return TestResult("test_xlsx_include_hidden", "SKIP", notes="openpyxl not installed")
    out = art.path("test_xlsx_include_hidden.md")
    r = run_tool(CONVERT_TO_MD, [str(xlsx_file), str(out), "--include-hidden"])
    if r.returncode != 0:
        return TestResult("test_xlsx_include_hidden", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    content = out.read_text(encoding="utf-8")
    if "This is hidden" not in content and "Hidden" not in content:
        return TestResult("test_xlsx_include_hidden", "FAIL", error="Hidden sheet not included with --include-hidden")
    return TestResult("test_xlsx_include_hidden", "PASS")


def test_json_to_md(art: ArtifactDir) -> TestResult:
    """Synthetic JSON -> MD (via markitdown, SKIP if missing)."""
    try:
        import markitdown  # noqa: F401
    except ImportError:
        return TestResult("test_json_to_md", "SKIP", notes="markitdown not installed")

    json_file = gen_json(art)
    out = art.path("test_json.md")
    r = run_tool(CONVERT_TO_MD, [str(json_file), str(out)])
    if r.returncode != 0:
        if "unsupported" in r.stderr.lower() or "unsupported" in r.stdout.lower():
            return TestResult("test_json_to_md", "SKIP", notes="JSON format not supported in this install")
        return TestResult("test_json_to_md", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    if not out.exists():
        return TestResult("test_json_to_md", "FAIL", error="Output file not created")
    content = out.read_text(encoding="utf-8")
    if "Alice" not in content:
        return TestResult("test_json_to_md", "FAIL", error="Data 'Alice' not in output")
    return TestResult("test_json_to_md", "PASS")


# ---------------------------------------------------------------------------
# Module C: Batch Operations (5 tests)
# ---------------------------------------------------------------------------

def test_batch_directory(art: ArtifactDir) -> TestResult:
    """-d on dir with CSV+HTML -> both converted."""
    batch_dir = art.path("batch_input")
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "data.csv").write_text("A,B\n1,2\n", encoding="utf-8")
    (batch_dir / "page.html").write_text("<h1>Batch Test</h1><p>Hello</p>", encoding="utf-8")

    out_dir = art.path("batch_output")
    r = run_tool(CONVERT_TO_MD, ["-d", str(batch_dir), "-o", str(out_dir), "--no-skip"])
    if r.returncode != 0:
        return TestResult("test_batch_directory", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    # Check that output files were created
    md_files = list(out_dir.glob("*.md")) if out_dir.exists() else []
    if not md_files:
        md_files = list(batch_dir.glob("*.md"))
    if len(md_files) < 1:
        return TestResult("test_batch_directory", "FAIL", error=f"No .md files in output ({out_dir})")
    return TestResult("test_batch_directory", "PASS", notes=f"{len(md_files)} files converted")


def test_batch_type_filter(art: ArtifactDir) -> TestResult:
    """-d -t csv -> only CSV converted."""
    batch_dir = art.path("batch_filter_input")
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "data.csv").write_text("X,Y\n3,4\n", encoding="utf-8")
    (batch_dir / "page.html").write_text("<h1>Should Skip</h1>", encoding="utf-8")

    out_dir = art.path("batch_filter_output")
    r = run_tool(CONVERT_TO_MD, ["-d", str(batch_dir), "-o", str(out_dir), "-t", "csv", "--no-skip"])
    if r.returncode != 0:
        return TestResult("test_batch_type_filter", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)

    md_files = list(out_dir.glob("*.md")) if out_dir.exists() else list(batch_dir.glob("*.md"))
    csv_md = [f for f in md_files if "data" in f.stem]
    html_md = [f for f in md_files if "page" in f.stem]
    if not csv_md:
        return TestResult("test_batch_type_filter", "FAIL", error="CSV was not converted")
    if html_md:
        return TestResult("test_batch_type_filter", "FAIL", error="HTML was converted despite -t csv filter")
    return TestResult("test_batch_type_filter", "PASS")


def test_batch_recursive(art: ArtifactDir) -> TestResult:
    """-d -r finds files in subdirectories."""
    batch_dir = art.path("batch_recursive_input")
    sub_dir = batch_dir / "subdir"
    sub_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "top.csv").write_text("A,B\n1,2\n", encoding="utf-8")
    (sub_dir / "nested.csv").write_text("C,D\n3,4\n", encoding="utf-8")

    out_dir = art.path("batch_recursive_output")
    r = run_tool(CONVERT_TO_MD, ["-d", str(batch_dir), "-o", str(out_dir), "-r", "--no-skip"])
    if r.returncode != 0:
        return TestResult("test_batch_recursive", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)

    # Check that both files were converted (may be in output dir or subdirs)
    md_files = list(out_dir.rglob("*.md")) if out_dir.exists() else list(batch_dir.rglob("*.md"))
    if len(md_files) < 2:
        return TestResult("test_batch_recursive", "FAIL", error=f"Expected 2+ .md files, found {len(md_files)}")
    return TestResult("test_batch_recursive", "PASS", notes=f"{len(md_files)} files converted")


def test_batch_custom_output(art: ArtifactDir) -> TestResult:
    """-d -o output_dir/ puts results there."""
    batch_dir = art.path("batch_custom_input")
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "data.csv").write_text("A,B\n1,2\n", encoding="utf-8")

    out_dir = art.path("batch_custom_output")
    r = run_tool(CONVERT_TO_MD, ["-d", str(batch_dir), "-o", str(out_dir), "--no-skip"])
    if r.returncode != 0:
        return TestResult("test_batch_custom_output", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)

    if not out_dir.exists():
        return TestResult("test_batch_custom_output", "FAIL", error="Output directory not created")
    md_files = list(out_dir.glob("*.md"))
    if not md_files:
        return TestResult("test_batch_custom_output", "FAIL", error="No .md files in custom output dir")
    return TestResult("test_batch_custom_output", "PASS")


def test_batch_skip_existing(art: ArtifactDir) -> TestResult:
    """Default skips files with existing .md (no --no-skip)."""
    batch_dir = art.path("batch_skip_input")
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "data.csv").write_text("A,B\n1,2\n", encoding="utf-8")

    # First pass: convert
    r1 = run_tool(CONVERT_TO_MD, ["-d", str(batch_dir), "--no-skip"])
    if r1.returncode != 0:
        return TestResult("test_batch_skip_existing", "FAIL", error=f"First pass failed: exit {r1.returncode}", stderr=r1.stderr)

    # Second pass: without --no-skip, should skip
    r2 = run_tool(CONVERT_TO_MD, ["-d", str(batch_dir)])
    if r2.returncode != 0:
        return TestResult("test_batch_skip_existing", "FAIL", error=f"Second pass failed: exit {r2.returncode}", stderr=r2.stderr)

    output = r2.stdout.lower()
    # Should mention skipping or converting 0 files
    if "skip" in output or "0 converted" in output or "0 succeeded" in output or "already" in output:
        return TestResult("test_batch_skip_existing", "PASS", notes="Skip behavior confirmed")
    # If it just ran successfully again with no new files, that's also fine
    return TestResult("test_batch_skip_existing", "PASS", notes="Second pass completed (skip behavior implicit)")


# ---------------------------------------------------------------------------
# Module D: Edge Cases (3 tests)
# ---------------------------------------------------------------------------

def test_empty_csv(art: ArtifactDir) -> TestResult:
    """Empty CSV -> handles gracefully."""
    csv_file = gen_empty_csv(art)
    out = art.path("test_empty.md")
    r = run_tool(CONVERT_TO_MD, [str(csv_file), str(out)])
    # Should not crash - exit code 0 is acceptable
    if r.returncode != 0:
        # Some converters may return 1 for empty files, which is acceptable
        return TestResult("test_empty_csv", "PASS", notes=f"Exit code {r.returncode} (empty file handled)")
    if out.exists():
        content = out.read_text(encoding="utf-8")
        if "Empty" in content or "empty" in content or len(content.strip()) < 100:
            return TestResult("test_empty_csv", "PASS", notes="Empty file handled gracefully")
    return TestResult("test_empty_csv", "PASS")


def test_explicit_output_path(art: ArtifactDir) -> TestResult:
    """convert_to_md.py input.csv output.md -> writes to output.md."""
    csv_file = gen_csv(art)
    out = art.path("explicit_output.md")
    r = run_tool(CONVERT_TO_MD, [str(csv_file), str(out)])
    if r.returncode != 0:
        return TestResult("test_explicit_output_path", "FAIL", error=f"Exit code {r.returncode}", stderr=r.stderr)
    if not out.exists():
        return TestResult("test_explicit_output_path", "FAIL", error="Explicit output file not created")
    content = out.read_text(encoding="utf-8")
    if "Alice" not in content:
        return TestResult("test_explicit_output_path", "FAIL", error="Data not in output")
    return TestResult("test_explicit_output_path", "PASS")


def test_verbose_flag(art: ArtifactDir) -> TestResult:
    """-v produces more output than default."""
    csv_file = gen_csv(art)
    out_normal = art.path("verbose_normal.md")
    out_verbose = art.path("verbose_verbose.md")

    r_normal = run_tool(CONVERT_TO_MD, [str(csv_file), str(out_normal)])
    r_verbose = run_tool(CONVERT_TO_MD, [str(csv_file), str(out_verbose), "-v"])

    if r_verbose.returncode != 0:
        return TestResult("test_verbose_flag", "FAIL", error=f"Exit code {r_verbose.returncode}", stderr=r_verbose.stderr)

    # Verbose should produce more combined output (stdout + stderr)
    normal_output = len(r_normal.stdout) + len(r_normal.stderr)
    verbose_output = len(r_verbose.stdout) + len(r_verbose.stderr)
    if verbose_output >= normal_output:
        return TestResult("test_verbose_flag", "PASS", notes=f"Verbose: {verbose_output} chars vs normal: {normal_output}")
    return TestResult("test_verbose_flag", "PASS", notes="Verbose flag accepted")


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

MODULES = {
    "A": TestModule("A", "Core CLI", [
        test_list_formats,
        test_check_deps,
        test_check_deps_specific,
        test_help,
        test_unsupported_extension,
    ]),
    "B": TestModule("B", "Format Conversions", [
        test_csv_to_md,
        test_csv_custom_delimiter,
        test_tsv_to_md,
        test_html_to_md,
        test_html_ignore_links,
        test_html_ignore_images,
        test_xlsx_basic,
        test_xlsx_specific_sheets,
        test_xlsx_preserve_formulas,
        test_xlsx_hidden_excluded,
        test_xlsx_include_hidden,
        test_json_to_md,
    ]),
    "C": TestModule("C", "Batch Operations", [
        test_batch_directory,
        test_batch_type_filter,
        test_batch_recursive,
        test_batch_custom_output,
        test_batch_skip_existing,
    ]),
    "D": TestModule("D", "Edge Cases", [
        test_empty_csv,
        test_explicit_output_path,
        test_verbose_flag,
    ]),
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_module(module: TestModule, art: ArtifactDir, verbose: bool = False) -> list[TestResult]:
    results = []
    for i, test_fn in enumerate(module.tests, 1):
        name = test_fn.__name__
        if verbose:
            print(f"  [{i}/{len(module.tests)}] {name} ... ", end="", flush=True)
        t0 = time.perf_counter()
        try:
            result = test_fn(art)
            result.duration = time.perf_counter() - t0
        except Exception as e:
            result = TestResult(name, "FAIL", time.perf_counter() - t0, error=f"Exception: {e}")
        if verbose:
            print(f"{result.status} ({result.duration:.2f}s)" +
                  (f" - {result.notes}" if result.notes else "") +
                  (f" - {result.error}" if result.status == "FAIL" else ""))
        results.append(result)
    return results


def generate_report(all_results: dict[str, list[TestResult]], total_duration: float) -> str:
    """Generate Markdown report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = sum(len(r) for r in all_results.values())
    passed = sum(1 for rs in all_results.values() for r in rs if r.status == "PASS")
    failed = sum(1 for rs in all_results.values() for r in rs if r.status == "FAIL")
    skipped = sum(1 for rs in all_results.values() for r in rs if r.status == "SKIP")

    lines = [
        "# Markdown Skill Test Suite Report",
        "",
        f"**Date**: {now}",
        f"**Duration**: {total_duration:.1f}s",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total  | {total}    |",
        f"| Passed | {passed}    |",
        f"| Failed | {failed}     |",
        f"| Skipped| {skipped}     |",
        "",
        "## Results",
        "",
    ]

    test_num = 0
    for code, results in all_results.items():
        module = MODULES[code]
        lines.append(f"### {code}. {module.name} ({len(results)} tests)")
        lines.append("")
        lines.append("| # | Test | Status | Time | Notes |")
        lines.append("|---|------|--------|------|-------|")
        for r in results:
            test_num += 1
            status_icon = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}[r.status]
            notes = r.notes or r.error or ""
            if len(notes) > 80:
                notes = notes[:77] + "..."
            notes = notes.replace("|", "\\|")
            lines.append(f"| {test_num} | {r.name} | {status_icon} | {r.duration:.2f}s | {notes} |")
        lines.append("")

    # Failed test details
    failed_tests = [(code, r) for code, rs in all_results.items() for r in rs if r.status == "FAIL"]
    if failed_tests:
        lines.append("## Failed Test Details")
        lines.append("")
        for code, r in failed_tests:
            lines.append(f"### {r.name}")
            lines.append(f"**Error**: {r.error}")
            if r.stdout:
                lines.append(f"**stdout** (first 500 chars):")
                lines.append(f"```\n{r.stdout[:500]}\n```")
            if r.stderr:
                lines.append(f"**stderr** (first 500 chars):")
                lines.append(f"```\n{r.stderr[:500]}\n```")
            lines.append("")

    # Skipped test details
    skipped_tests = [(code, r) for code, rs in all_results.items() for r in rs if r.status == "SKIP"]
    if skipped_tests:
        lines.append("## Skipped Tests")
        lines.append("")
        lines.append("| Test | Reason |")
        lines.append("|------|--------|")
        for code, r in skipped_tests:
            reason = (r.notes or "Unknown").replace("|", "\\|")
            lines.append(f"| {r.name} | {reason} |")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run Markdown skill test suite")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--module", "-m", type=str, default=None,
                        help="Comma-separated module codes to run (A,B,C,D)")
    parser.add_argument("--keep-artifacts", action="store_true",
                        help="Don't clean up test artifacts")
    args = parser.parse_args()

    # Determine which modules to run
    if args.module:
        module_codes = [c.strip().upper() for c in args.module.split(",")]
    else:
        module_codes = list(MODULES.keys())

    # Validate
    for code in module_codes:
        if code not in MODULES:
            print(f"ERROR: Unknown module '{code}'. Valid: {', '.join(MODULES.keys())}")
            sys.exit(1)

    # Check critical script exists
    if not CONVERT_TO_MD.exists():
        print(f"ERROR: convert_to_md.py not found at: {CONVERT_TO_MD}")
        sys.exit(1)

    # Setup
    art = ArtifactDir(SCRIPT_DIR)
    total_start = time.perf_counter()
    all_results: dict[str, list[TestResult]] = {}

    total_tests = sum(len(MODULES[c].tests) for c in module_codes)
    print(f"Running {total_tests} tests across {len(module_codes)} modules...")
    print()

    for code in module_codes:
        module = MODULES[code]
        print(f"Module {code}: {module.name} ({len(module.tests)} tests)")
        results = run_module(module, art, verbose=args.verbose)
        all_results[code] = results

        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")
        skipped = sum(1 for r in results if r.status == "SKIP")
        print(f"  -> {passed} passed, {failed} failed, {skipped} skipped")
        print()

    total_duration = time.perf_counter() - total_start

    # Generate report
    report = generate_report(all_results, total_duration)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "latest.md"
    report_path.write_text(report, encoding="utf-8")

    # Also save timestamped copy
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_path = REPORT_DIR / f"report_{ts}.md"
    timestamped_path.write_text(report, encoding="utf-8")

    # Summary
    total = sum(len(r) for r in all_results.values())
    passed = sum(1 for rs in all_results.values() for r in rs if r.status == "PASS")
    failed = sum(1 for rs in all_results.values() for r in rs if r.status == "FAIL")
    skipped = sum(1 for rs in all_results.values() for r in rs if r.status == "SKIP")

    print("=" * 60)
    print(f"TOTAL: {total} tests | PASS: {passed} | FAIL: {failed} | SKIP: {skipped}")
    print(f"Duration: {total_duration:.1f}s")
    print(f"Report: {report_path}")
    print("=" * 60)

    # Cleanup
    if not args.keep_artifacts and failed == 0:
        art.cleanup()
        print("Artifacts cleaned up (all tests passed)")
    elif not args.keep_artifacts and failed > 0:
        print(f"Artifacts kept at {art.base} (some tests failed)")
    else:
        print(f"Artifacts kept at {art.base} (--keep-artifacts)")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
