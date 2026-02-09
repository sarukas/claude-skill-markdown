"""
Pluggable document-to-Markdown converter framework.

Public API
----------
- ``convert(input_path, output_path=None, **options)`` -- convert a single file
- ``convert_batch(directory, output_dir=None, recursive=False, ...)`` -- batch convert
- ``get_converter(extension)`` -- look up converter class by extension
- ``supported_extensions()`` -- list all registered extensions

Quick start::

    from converters import convert
    result = convert("report.pdf")
    print(result)
"""

from pathlib import Path
from typing import List, Optional, Type

from .base import BaseConverter, BatchResult, ConversionResult
from .registry import ConverterRegistry

# Import every converter module to trigger @ConverterRegistry.register.
from . import csv_converter       # noqa: F401
from . import markitdown_converters  # noqa: F401
from . import xlsx_converter      # noqa: F401
from . import pdf_converter       # noqa: F401
from . import html_converter      # noqa: F401

__all__ = [
    "convert",
    "convert_batch",
    "get_converter",
    "supported_extensions",
    "ConversionResult",
    "BatchResult",
    "BaseConverter",
    "ConverterRegistry",
]


def get_converter(extension: str) -> Optional[Type[BaseConverter]]:
    """Return the converter class registered for *extension*, or ``None``."""
    return ConverterRegistry.get(extension)


def supported_extensions() -> List[str]:
    """Return a sorted list of all file extensions that can be converted."""
    return ConverterRegistry.supported_extensions()


def convert(
    input_path: str | Path,
    output_path: str | Path | None = None,
    **options,
) -> ConversionResult:
    """Convert a single file to Markdown.

    Looks up the converter by file extension, checks dependencies, and runs
    a timed conversion.
    """
    input_path = Path(input_path)
    ext = input_path.suffix.lower()

    conv_cls = ConverterRegistry.get(ext)
    if conv_cls is None:
        return ConversionResult(
            input_path=input_path,
            success=False,
            error=f"Unsupported file extension: {ext}. "
                  f"Supported: {', '.join(supported_extensions())}",
        )

    missing = conv_cls.check_dependencies()
    if missing:
        return ConversionResult(
            input_path=input_path,
            success=False,
            error=f"Missing dependencies for {conv_cls.DISPLAY_NAME}: "
                  f"pip install {' '.join(missing)}",
        )

    converter = conv_cls(**options)
    out = Path(output_path) if output_path else None
    return converter.timed_convert(input_path, out)


def convert_batch(
    directory: str | Path,
    output_dir: str | Path | None = None,
    recursive: bool = False,
    extensions: Optional[List[str]] = None,
    skip_existing: bool = True,
    **options,
) -> BatchResult:
    """Batch-convert all supported files in *directory*.

    Groups files by extension, instantiates the right converter for each
    group, and runs ``convert_directory()`` on each.
    """
    directory = Path(directory)
    out_dir = Path(output_dir) if output_dir else None

    # Decide which extensions to process
    if extensions:
        exts = [e if e.startswith(".") else f".{e}" for e in extensions]
    else:
        exts = supported_extensions()

    # Group extensions by converter class
    groups: dict[Type[BaseConverter], list[str]] = {}
    for ext in exts:
        cls = ConverterRegistry.get(ext)
        if cls is not None:
            groups.setdefault(cls, []).append(ext)

    batch = BatchResult()
    for cls, cls_exts in groups.items():
        missing = cls.check_dependencies()
        if missing:
            # Skip converters with missing deps -- log a warning
            import logging
            logging.getLogger(__name__).warning(
                "Skipping %s (missing: %s)", cls.DISPLAY_NAME, ", ".join(missing)
            )
            continue

        converter = cls(**options)
        # Temporarily narrow EXTENSIONS so convert_directory only finds matching files
        original_exts = converter.EXTENSIONS
        converter.EXTENSIONS = cls_exts  # type: ignore[assignment]
        result = converter.convert_directory(
            directory, output_dir=out_dir, recursive=recursive, skip_existing=skip_existing,
        )
        converter.EXTENSIONS = original_exts  # type: ignore[assignment]
        batch.results.extend(result.results)

    return batch
