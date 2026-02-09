"""
PDF to Markdown converter.

Merges the best of both previous converters:
- **Chunked processing** with gc.collect() and MemoryError fallback
  (from ``convert_pdf_to_md.py``)
- **Enhanced table extraction** via pdfplumber and document structure
  extraction (from ``convert_pdf_enhanced.py``)

Dependencies: ``pymupdf4llm``, ``pymupdf``, ``pdfplumber``, ``tabulate``.
"""

import gc
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseConverter, ConversionResult
from .registry import ConverterRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers (ported from convert_pdf_enhanced.py)
# ---------------------------------------------------------------------------

def _extract_tables_from_page(page: Any, page_num: int) -> List[Dict]:
    """Extract tables from a single pdfplumber page."""
    tables_data: List[Dict] = []
    try:
        tables = page.extract_tables()
        for idx, table in enumerate(tables):
            if not table:
                continue
            cleaned: List[List[str]] = []
            for row in table:
                if not row:
                    continue
                cleaned_row = [" ".join(str(c).split()) if c is not None else "" for c in row]
                cleaned.append(cleaned_row)
            if cleaned:
                tables_data.append({
                    "page": page_num,
                    "table_index": idx,
                    "data": cleaned,
                    "rows": len(cleaned),
                    "cols": len(cleaned[0]),
                })
    except Exception as exc:
        logger.warning("Error extracting tables from page %d: %s", page_num, exc)
    return tables_data


def _format_table_as_markdown(table_data: List[List[str]]) -> str:
    """Render a list-of-lists as a Markdown pipe table."""
    if not table_data or len(table_data) < 2:
        return ""
    headers = table_data[0]
    rows = table_data[1:]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        while len(row) < len(headers):
            row.append("")
        lines.append("| " + " | ".join(row[: len(headers)]) + " |")
    return "\n".join(lines)


def _extract_document_structure(pdf_path: Path) -> Dict:
    """Extract TOC and metadata from a PDF."""
    import pymupdf

    structure: Dict[str, Any] = {"title": "", "sections": [], "toc": [], "total_pages": 0}
    try:
        pdf = pymupdf.open(str(pdf_path))
        structure["total_pages"] = len(pdf)
        toc = pdf.get_toc()
        if toc:
            structure["toc"] = [
                {"level": item[0], "title": item[1], "page": item[2]} for item in toc
            ]
        meta = pdf.metadata
        if meta and meta.get("title"):
            structure["title"] = meta["title"]
        pdf.close()
    except Exception as exc:
        logger.warning("Could not extract document structure: %s", exc)
    return structure


def _identify_potential_diagrams(pdf_path: Path) -> List[Dict]:
    """Identify pages that likely contain diagrams."""
    import pymupdf

    results: List[Dict] = []
    try:
        pdf = pymupdf.open(str(pdf_path))
        keywords = ["figure", "diagram", "chart", "graph", "flow",
                     "architecture", "schema", "model", "framework"]
        for page_num, page in enumerate(pdf):
            images = page.get_images()
            drawings = page.get_drawings()
            text = page.get_text()
            has_kw = any(k in text.lower() for k in keywords)
            if images or drawings or has_kw:
                results.append({
                    "page": page_num + 1,
                    "images": len(images),
                    "drawings": len(drawings),
                    "has_diagram_keywords": has_kw,
                    "likely_diagram": len(images) > 0 or len(drawings) > 5,
                })
        pdf.close()
    except Exception as exc:
        logger.warning("Error identifying diagrams: %s", exc)
    return results


# ---------------------------------------------------------------------------
# Chunked conversion (ported from convert_pdf_to_md.py)
# ---------------------------------------------------------------------------

def _convert_chunked(
    input_path: Path,
    output_path: Path,
    chunk_size: int = 50,
    total_pages: Optional[int] = None,
) -> bool:
    """Process a large PDF in page-range chunks with gc.collect()."""
    import pymupdf
    import pymupdf4llm

    pdf = pymupdf.open(str(input_path))
    if total_pages is None:
        total_pages = len(pdf)

    logger.info("Chunked processing: %d pages in chunks of %d", total_pages, chunk_size)

    with open(output_path, "w", encoding="utf-8") as out:
        for start in range(0, total_pages, chunk_size):
            end = min(start + chunk_size, total_pages)
            logger.info("Processing pages %d-%d of %d", start + 1, end, total_pages)
            try:
                md_chunk = pymupdf4llm.to_markdown(
                    str(input_path), pages=list(range(start, end))
                )
                out.write(md_chunk)
                if end < total_pages:
                    out.write("\n\n---\n\n")
                gc.collect()
            except MemoryError:
                logger.warning("MemoryError at pages %d-%d, halving chunk size", start, end)
                if chunk_size > 10:
                    pdf.close()
                    return _convert_chunked(input_path, output_path, chunk_size // 2, total_pages)
                raise
            except Exception as exc:
                logger.error("Error on pages %d-%d: %s", start + 1, end, exc)
                out.write(f"\n\n[Error processing pages {start + 1}-{end}]\n\n")

    pdf.close()
    return True


# ---------------------------------------------------------------------------
# Registered converter
# ---------------------------------------------------------------------------

@ConverterRegistry.register
class PdfConverter(BaseConverter):
    """PDF to Markdown with chunked processing and enhanced table extraction."""

    EXTENSIONS = [".pdf"]
    DISPLAY_NAME = "PDF"
    REQUIRED_PACKAGES = {
        "pymupdf4llm": "pymupdf4llm",
        "pymupdf": "pymupdf",
        "pdfplumber": "pdfplumber",
        "tabulate": "tabulate",
    }
    MAX_MEMORY_WARNING_MB = 100

    def __init__(self, **options: Any) -> None:
        super().__init__(**options)
        self.chunk_size: int = options.get("chunk_size", 50)
        self.max_memory_mb: int = options.get("max_memory_mb", 500)
        self.enhanced_tables: bool = options.get("enhanced_tables", True)
        self.extract_structure: bool = options.get("extract_structure", True)
        self.identify_diagrams: bool = options.get("identify_diagrams", False)

    def convert_file(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
    ) -> ConversionResult:
        import pymupdf
        import pymupdf4llm

        input_path = Path(input_path)
        output_path = self.resolve_output_path(input_path, output_path)

        file_size_mb = input_path.stat().st_size / (1024 * 1024)

        # Page count
        try:
            pdf = pymupdf.open(str(input_path))
            total_pages = len(pdf)
            pdf.close()
        except Exception:
            total_pages = None

        logger.info("PDF %s: %.1f MB, %s pages",
                     input_path.name, file_size_mb,
                     total_pages if total_pages else "unknown")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------
        # Base conversion (chunked or direct)
        # ------------------------------------------------------------------
        use_chunked = (
            file_size_mb > self.max_memory_mb
            or (total_pages is not None and total_pages > 200)
        )

        try:
            if use_chunked:
                logger.info("Using chunked processing (chunk_size=%d)", self.chunk_size)
                ok = _convert_chunked(input_path, output_path, self.chunk_size, total_pages)
                if not ok:
                    return ConversionResult(input_path=input_path, output_path=output_path,
                                            success=False, error="Chunked conversion failed")
                base_markdown = output_path.read_text(encoding="utf-8")
            else:
                base_markdown = pymupdf4llm.to_markdown(str(input_path))
        except MemoryError:
            logger.warning("MemoryError -- falling back to chunked processing")
            ok = _convert_chunked(input_path, output_path, chunk_size=25, total_pages=total_pages)
            if not ok:
                return ConversionResult(input_path=input_path, output_path=output_path,
                                        success=False, error="Chunked fallback also failed")
            base_markdown = output_path.read_text(encoding="utf-8")

        # ------------------------------------------------------------------
        # Enhanced metadata / structure / tables (appended to output)
        # ------------------------------------------------------------------
        enhanced_sections: List[str] = []

        # Document structure
        structure: Dict = {}
        if self.extract_structure:
            structure = _extract_document_structure(input_path)
            if structure.get("toc"):
                toc_lines = ["## Table of Contents", ""]
                for item in structure["toc"]:
                    indent = "  " * (item["level"] - 1)
                    toc_lines.append(f"{indent}- {item['title']} (Page {item['page']})")
                toc_lines.extend(["", "---", ""])
                enhanced_sections.append("\n".join(toc_lines))

        # Diagram identification
        if self.identify_diagrams:
            diagrams = _identify_potential_diagrams(input_path)
            likely = [d for d in diagrams if d.get("likely_diagram")]
            if likely:
                lines = [
                    "## Diagrams Requiring Manual Conversion",
                    "",
                    "The following pages contain diagrams that may benefit from Mermaid conversion:",
                    "",
                ]
                for d in likely:
                    lines.append(
                        f"- **Page {d['page']}**: {d['images']} images, "
                        f"{d['drawings']} vector graphics"
                    )
                lines.extend(["", "---", ""])
                enhanced_sections.append("\n".join(lines))

        # Enhanced table extraction
        all_tables: List[Dict] = []
        if self.enhanced_tables:
            try:
                import pdfplumber
                with pdfplumber.open(str(input_path)) as ppdf:
                    for page_num, page in enumerate(ppdf.pages):
                        all_tables.extend(_extract_tables_from_page(page, page_num + 1))
                logger.info("Enhanced table extraction: %d tables found", len(all_tables))
            except Exception as exc:
                logger.warning("Enhanced table extraction failed: %s", exc)

        if all_tables:
            table_lines = [
                "",
                "---",
                "",
                "## Appendix: Extracted Tables",
                "",
                "*Tables extracted separately for better formatting.*",
                "",
            ]
            for t in all_tables:
                table_lines.append(
                    f"### Table {t['table_index'] + 1} (Page {t['page']})"
                )
                table_lines.append(
                    f"\n*Dimensions: {t['rows']} rows x {t['cols']} columns*\n"
                )
                md_table = _format_table_as_markdown(t["data"])
                if md_table:
                    table_lines.append(md_table)
                    table_lines.append("")
            enhanced_sections.append("\n".join(table_lines))

        # ------------------------------------------------------------------
        # Write final output
        # ------------------------------------------------------------------
        parts = []
        if enhanced_sections:
            # Prepend structure/toc, append tables
            parts.append("\n".join(enhanced_sections[:2]))  # TOC + diagrams
            parts.append(base_markdown)
            if len(enhanced_sections) > 2:
                parts.append("\n".join(enhanced_sections[2:]))  # tables
        else:
            parts.append(base_markdown)

        output_path.write_text("\n".join(parts), encoding="utf-8")

        meta = {
            "pages": total_pages,
            "tables_found": len(all_tables),
        }
        if structure.get("title"):
            meta["title"] = structure["title"]

        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            success=True,
            metadata=meta,
        )

    # -- CLI ------------------------------------------------------------------

    @classmethod
    def add_arguments(cls, parser) -> None:
        parser.add_argument("--chunk-size", type=int, default=50,
                            help="Pages per chunk for large PDFs (default: 50)")
        parser.add_argument("--max-memory", type=int, default=500,
                            help="File size (MB) threshold for chunked mode (default: 500)")
        parser.add_argument("--no-enhanced-tables", action="store_true",
                            help="Disable pdfplumber table extraction")
        parser.add_argument("--no-structure", action="store_true",
                            help="Skip document structure / TOC extraction")
        parser.add_argument("--identify-diagrams", action="store_true",
                            help="Identify pages with potential diagrams")

    @classmethod
    def from_args(cls, args) -> "PdfConverter":
        return cls(
            chunk_size=getattr(args, "chunk_size", 50),
            max_memory_mb=getattr(args, "max_memory", 500),
            enhanced_tables=not getattr(args, "no_enhanced_tables", False),
            extract_structure=not getattr(args, "no_structure", False),
            identify_diagrams=getattr(args, "identify_diagrams", False),
        )
