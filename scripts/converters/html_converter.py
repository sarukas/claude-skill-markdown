"""
HTML to Markdown converter.

Uses ``beautifulsoup4`` for HTML cleaning and ``html2text`` for conversion.
For very large HTML files (>10 MB), skips BeautifulSoup preprocessing and
runs html2text directly as a fallback.

Ported from the original ``convert_html_to_md.py``.
"""

import logging
import re
from pathlib import Path
from typing import Any, Optional

from .base import BaseConverter, ConversionResult
from .registry import ConverterRegistry

logger = logging.getLogger(__name__)

# Files larger than this skip the BeautifulSoup preprocessing step.
_LARGE_HTML_THRESHOLD = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Three-stage pipeline (ported from convert_html_to_md.py:34-105)
# ---------------------------------------------------------------------------

def _clean_html(html_content: str) -> str:
    """Remove scripts, styles, nav, footer, and comments."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "meta", "link"]):
        tag.decompose()
    for tag in soup(["nav", "footer"]):
        tag.decompose()
    for comment in soup.find_all(
        string=lambda text: isinstance(text, str) and text.startswith("<!--")
    ):
        comment.extract()
    return str(soup)


def _html_to_markdown(
    html_content: str,
    *,
    ignore_links: bool = False,
    ignore_images: bool = False,
    body_width: int = 0,
) -> str:
    """Convert (already cleaned) HTML to Markdown via html2text."""
    import html2text

    h = html2text.HTML2Text()
    h.ignore_links = ignore_links
    h.ignore_images = ignore_images
    h.body_width = body_width
    h.ignore_emphasis = False
    h.skip_internal_links = False
    h.inline_links = True
    h.protect_links = True
    h.wrap_lists = True
    h.unicode_snob = True
    h.use_automatic_links = True
    h.single_line_break = False

    return h.handle(html_content)


def _post_process_markdown(md: str) -> str:
    """Clean up excessive whitespace and fix heading spacing."""
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(r"\n(#{1,6})", r"\n\n\1", md)
    md = re.sub(r"(#{1,6}.*?)\n(?!\n)", r"\1\n\n", md)
    md = re.sub(r"\n\s*\*\s+", "\n* ", md)
    md = re.sub(r"\n\s*\d+\.\s+", lambda m: "\n" + m.group().strip() + " ", md)
    md = "\n".join(line.rstrip() for line in md.split("\n"))
    return md.rstrip() + "\n"


# ---------------------------------------------------------------------------
# Registered converter
# ---------------------------------------------------------------------------

@ConverterRegistry.register
class HtmlConverter(BaseConverter):
    """Convert HTML files to clean Markdown."""

    EXTENSIONS = [".html", ".htm"]
    DISPLAY_NAME = "HTML"
    REQUIRED_PACKAGES = {"html2text": "html2text", "bs4": "beautifulsoup4"}

    def __init__(self, **options: Any) -> None:
        super().__init__(**options)
        self.ignore_links: bool = options.get("ignore_links", False)
        self.ignore_images: bool = options.get("ignore_images", False)
        self.body_width: int = options.get("body_width", 0)

    def convert_file(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
    ) -> ConversionResult:
        input_path = Path(input_path)
        output_path = self.resolve_output_path(input_path, output_path)

        raw_html = input_path.read_text(encoding="utf-8", errors="replace")

        # For very large files, skip BeautifulSoup preprocessing
        file_size = input_path.stat().st_size
        if file_size > _LARGE_HTML_THRESHOLD:
            logger.info("Large HTML file (%.1f MB) -- skipping BeautifulSoup cleanup",
                        file_size / (1024 * 1024))
            cleaned = raw_html
        else:
            cleaned = _clean_html(raw_html)

        md = _html_to_markdown(
            cleaned,
            ignore_links=self.ignore_links,
            ignore_images=self.ignore_images,
            body_width=self.body_width,
        )
        md = _post_process_markdown(md)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md, encoding="utf-8")

        logger.info("Converted %s", input_path.name)
        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            success=True,
        )

    # -- CLI ------------------------------------------------------------------

    @classmethod
    def add_arguments(cls, parser) -> None:
        parser.add_argument("--ignore-links", action="store_true",
                            help="Omit hyperlinks from output")
        parser.add_argument("--ignore-images", action="store_true",
                            help="Omit images from output")
        parser.add_argument("--body-width", type=int, default=0,
                            help="Wrap lines at width (0 = no wrap)")

    @classmethod
    def from_args(cls, args) -> "HtmlConverter":
        return cls(
            ignore_links=getattr(args, "ignore_links", False),
            ignore_images=getattr(args, "ignore_images", False),
            body_width=getattr(args, "body_width", 0),
        )
