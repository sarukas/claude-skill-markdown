"""
Markitdown-backed converters.

All formats where Microsoft's ``markitdown`` library produces good-quality
Markdown are handled here.  Each format is a thin class that declares
EXTENSIONS, DISPLAY_NAME, and REQUIRED_PACKAGES.  They all share the same
``convert_file()`` implementation via ``MarkitdownBase``.
"""

import logging
from pathlib import Path
from typing import Optional

from .base import BaseConverter, ConversionResult
from .registry import ConverterRegistry

logger = logging.getLogger(__name__)


class MarkitdownBase(BaseConverter):
    """Shared logic for all markitdown-backed converters."""

    REQUIRED_PACKAGES = {"markitdown": "markitdown"}

    def convert_file(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
    ) -> ConversionResult:
        from markitdown import MarkItDown

        input_path = Path(input_path)
        output_path = self.resolve_output_path(input_path, output_path)

        md = MarkItDown()
        result = md.convert(str(input_path))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.text_content, encoding="utf-8")

        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            success=True,
        )


# ---------------------------------------------------------------------------
# Individual format classes
# ---------------------------------------------------------------------------

@ConverterRegistry.register
class DocxConverter(MarkitdownBase):
    """Word (DOCX) via markitdown -- pure Python, no pandoc."""

    EXTENSIONS = [".docx"]
    DISPLAY_NAME = "Word (DOCX)"
    REQUIRED_PACKAGES = {"markitdown": "markitdown"}
    MAX_MEMORY_WARNING_MB = 50

    def convert_file(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
    ) -> ConversionResult:
        """Convert DOCX.  Falls back to python-docx paragraph iteration
        for very large files if markitdown raises MemoryError."""
        input_path = Path(input_path)
        output_path = self.resolve_output_path(input_path, output_path)

        try:
            return super().convert_file(input_path, output_path)
        except MemoryError:
            logger.warning(
                "%s: markitdown MemoryError -- falling back to python-docx paragraph extraction",
                input_path.name,
            )
            return self._fallback_convert(input_path, output_path)

    @staticmethod
    def _fallback_convert(input_path: Path, output_path: Path) -> ConversionResult:
        """Incremental extraction via python-docx for very large DOCX files."""
        try:
            from docx import Document
        except ImportError:
            return ConversionResult(
                input_path=input_path,
                output_path=output_path,
                success=False,
                error="MemoryError with markitdown and python-docx not installed for fallback",
            )

        doc = Document(str(input_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as fout:
            for para in doc.paragraphs:
                style_name = (para.style.name or "").lower() if para.style else ""
                text = para.text.strip()
                if not text:
                    fout.write("\n")
                    continue
                if "heading 1" in style_name:
                    fout.write(f"# {text}\n\n")
                elif "heading 2" in style_name:
                    fout.write(f"## {text}\n\n")
                elif "heading 3" in style_name:
                    fout.write(f"### {text}\n\n")
                elif "heading" in style_name:
                    fout.write(f"#### {text}\n\n")
                else:
                    fout.write(f"{text}\n\n")

            # Tables
            for table in doc.tables:
                for i, row in enumerate(table.rows):
                    cells = [cell.text.replace("|", "\\|").strip() for cell in row.cells]
                    fout.write("| " + " | ".join(cells) + " |\n")
                    if i == 0:
                        fout.write("|" + "|".join(["---"] * len(cells)) + "|\n")
                fout.write("\n")

        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            success=True,
            metadata={"fallback": True},
        )


@ConverterRegistry.register
class XlsConverter(MarkitdownBase):
    """Legacy Excel (XLS) via markitdown."""

    EXTENSIONS = [".xls"]
    DISPLAY_NAME = "Excel (Legacy XLS)"
    REQUIRED_PACKAGES = {"markitdown": "markitdown", "xlrd": "xlrd"}


@ConverterRegistry.register
class PptxConverter(MarkitdownBase):
    """PowerPoint (PPTX) via markitdown."""

    EXTENSIONS = [".pptx"]
    DISPLAY_NAME = "PowerPoint (PPTX)"
    REQUIRED_PACKAGES = {"markitdown": "markitdown", "pptx": "python-pptx"}


@ConverterRegistry.register
class EpubConverter(MarkitdownBase):
    """E-book (EPUB) via markitdown."""

    EXTENSIONS = [".epub"]
    DISPLAY_NAME = "E-book (EPUB)"
    REQUIRED_PACKAGES = {"markitdown": "markitdown"}


@ConverterRegistry.register
class OutlookConverter(MarkitdownBase):
    """Outlook Message (.msg) via markitdown."""

    EXTENSIONS = [".msg"]
    DISPLAY_NAME = "Outlook Message"
    REQUIRED_PACKAGES = {"markitdown": "markitdown", "extract_msg": "extract-msg"}


@ConverterRegistry.register
class NotebookConverter(MarkitdownBase):
    """Jupyter Notebook (.ipynb) via markitdown."""

    EXTENSIONS = [".ipynb"]
    DISPLAY_NAME = "Jupyter Notebook"
    REQUIRED_PACKAGES = {"markitdown": "markitdown"}


@ConverterRegistry.register
class DataConverter(MarkitdownBase):
    """Structured data (JSON / XML) via markitdown."""

    EXTENSIONS = [".json", ".xml"]
    DISPLAY_NAME = "Data (JSON/XML)"
    REQUIRED_PACKAGES = {"markitdown": "markitdown"}


@ConverterRegistry.register
class ArchiveConverter(MarkitdownBase):
    """ZIP archive -- markitdown iterates and converts contents."""

    EXTENSIONS = [".zip"]
    DISPLAY_NAME = "Archive (ZIP)"
    REQUIRED_PACKAGES = {"markitdown": "markitdown"}


@ConverterRegistry.register
class ImageConverter(MarkitdownBase):
    """Image files -- EXIF metadata extraction only.

    LIMITATION: This converter extracts EXIF metadata (camera model, GPS
    coordinates, date taken, etc.) from image files.  It does NOT perform
    OCR, image description, or any visual content analysis.  Images that
    lack EXIF metadata (e.g. screenshots, web graphics, cropped photos)
    will produce empty output.
    """

    EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".gif"]
    DISPLAY_NAME = "Images (EXIF metadata only)"
    REQUIRED_PACKAGES = {"markitdown": "markitdown"}


@ConverterRegistry.register
class AudioConverter(MarkitdownBase):
    """Audio files -- markitdown transcribes via SpeechRecognition."""

    EXTENSIONS = [".wav", ".mp3", ".m4a"]
    DISPLAY_NAME = "Audio"
    REQUIRED_PACKAGES = {
        "markitdown": "markitdown",
        "pydub": "pydub",
        "speech_recognition": "SpeechRecognition",
    }
