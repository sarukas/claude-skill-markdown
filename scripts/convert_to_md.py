#!/usr/bin/env python3
"""
Unified document-to-Markdown converter.

Dispatches to the right converter based on file extension.

Usage::

    python convert_to_md.py report.pdf                      # Single file
    python convert_to_md.py report.pdf output.md             # Explicit output
    python convert_to_md.py -d ./contracts/ -r               # Directory, recursive
    python convert_to_md.py -d ./contracts/ -t pdf docx      # Filter by type
    python convert_to_md.py data.xlsx --sheets Sheet1        # Format-specific option
    python convert_to_md.py --list-formats                   # Show supported formats
    python convert_to_md.py --check-deps                     # Check all dependencies
    python convert_to_md.py --check-deps pdf                 # Check PDF deps only
    python convert_to_md.py -v report.pdf                    # Verbose logging
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure the parent directory of this script is on sys.path so the
# ``converters`` package can be imported when running as a standalone script.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from converters import (  # noqa: E402
    BatchResult,
    ConversionResult,
    ConverterRegistry,
    convert,
    convert_batch,
    supported_extensions,
)

logger = logging.getLogger("convert_to_md")


# ---------------------------------------------------------------------------
# Info commands
# ---------------------------------------------------------------------------

def _list_formats() -> None:
    """Print a table of all registered formats and their dependency status."""
    converters = ConverterRegistry.unique_converters()
    if not converters:
        print("No converters registered.")
        return

    print(f"{'Format':<25} {'Extensions':<35} {'Dependencies'}")
    print("-" * 90)
    for cls in converters:
        exts = ", ".join(cls.EXTENSIONS)
        missing = cls.check_dependencies()
        if missing:
            deps = f"MISSING: pip install {' '.join(missing)}"
        else:
            deps = "OK"
        print(f"{cls.DISPLAY_NAME:<25} {exts:<35} {deps}")


def _check_deps(format_filter: str | None = None) -> int:
    """Check dependencies.  Returns 0 if all OK, 1 if any missing."""
    converters = ConverterRegistry.unique_converters()
    any_missing = False

    for cls in converters:
        if format_filter:
            # Match by extension (e.g. "pdf") or display name
            match = any(
                format_filter.lower().lstrip(".") == ext.lstrip(".").lower()
                for ext in cls.EXTENSIONS
            ) or format_filter.lower() in cls.DISPLAY_NAME.lower()
            if not match:
                continue

        missing = cls.check_dependencies()
        status = "OK" if not missing else f"MISSING: pip install {' '.join(missing)}"
        print(f"  {cls.DISPLAY_NAME:<25} {status}")
        if missing:
            any_missing = True

    if any_missing:
        print("\nSome dependencies are missing. Install them with pip.")
        return 1
    print("\nAll dependencies satisfied.")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert documents to Markdown (unified CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s report.pdf                      # Single file
  %(prog)s report.pdf output.md             # Explicit output
  %(prog)s -d ./contracts/ -r               # Directory, recursive
  %(prog)s -d ./contracts/ -t pdf docx      # Filter by type
  %(prog)s data.xlsx --sheets Sheet1        # Format-specific option
  %(prog)s --list-formats                   # Show supported formats + deps
  %(prog)s --check-deps                     # Check all dependencies
  %(prog)s --check-deps pdf                 # Check PDF deps only
  %(prog)s -v report.pdf                    # Verbose logging
        """,
    )

    # -- input ----------------------------------------------------------------
    group = parser.add_mutually_exclusive_group()
    group.add_argument("input_file", nargs="?", type=Path, help="Input file to convert")
    group.add_argument("-d", "--directory", type=Path, help="Directory to batch-convert")

    # -- output ---------------------------------------------------------------
    parser.add_argument("output_file", nargs="?", type=Path,
                        help="Output Markdown file (default: same name with .md)")
    parser.add_argument("-o", "--output-dir", type=Path,
                        help="Output directory for batch conversion")

    # -- batch options --------------------------------------------------------
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Process subdirectories recursively")
    parser.add_argument("-t", "--types", nargs="+",
                        help="File types to process (e.g. pdf docx xlsx)")
    parser.add_argument("--no-skip", action="store_true",
                        help="Re-convert even if .md is up-to-date")

    # -- info commands --------------------------------------------------------
    parser.add_argument("--list-formats", action="store_true",
                        help="List all supported formats and exit")
    parser.add_argument("--check-deps", nargs="?", const="__all__", default=None,
                        metavar="FORMAT",
                        help="Check dependencies (optionally for a specific format)")

    # -- logging --------------------------------------------------------------
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose (DEBUG) logging")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress informational output")

    # -- format-specific options ----------------------------------------------
    fmt_group = parser.add_argument_group("Format-specific options")
    for cls in ConverterRegistry.unique_converters():
        cls.add_arguments(fmt_group)

    args = parser.parse_args()

    # -- logging setup --------------------------------------------------------
    level = logging.WARNING
    if args.verbose:
        level = logging.DEBUG
    elif not args.quiet:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    # -- info commands --------------------------------------------------------
    if args.list_formats:
        _list_formats()
        sys.exit(0)

    if args.check_deps is not None:
        fmt = None if args.check_deps == "__all__" else args.check_deps
        sys.exit(_check_deps(fmt))

    # -- conversion -----------------------------------------------------------
    if args.directory:
        if not args.directory.is_dir():
            logger.error("Not a directory: %s", args.directory)
            sys.exit(1)

        batch: BatchResult = convert_batch(
            args.directory,
            output_dir=args.output_dir,
            recursive=args.recursive,
            extensions=args.types,
            skip_existing=not args.no_skip,
        )
        print(batch.summary())
        sys.exit(0 if batch.failed == 0 else 1)

    elif args.input_file:
        if not args.input_file.is_file():
            logger.error("File not found: %s", args.input_file)
            sys.exit(1)

        # Try to get format-specific converter for from_args
        ext = args.input_file.suffix.lower()
        conv_cls = ConverterRegistry.get(ext)
        if conv_cls is not None:
            missing = conv_cls.check_dependencies()
            if missing:
                logger.error("Missing deps for %s: pip install %s",
                             conv_cls.DISPLAY_NAME, " ".join(missing))
                sys.exit(1)
            converter = conv_cls.from_args(args)
            result: ConversionResult = converter.timed_convert(
                args.input_file, args.output_file,
            )
        else:
            result = convert(args.input_file, args.output_file)

        print(result)
        sys.exit(0 if result.success else 1)

    else:
        parser.error("Provide an input file or use -d/--directory for batch mode. "
                      "Use --list-formats or --check-deps for info.")


if __name__ == "__main__":
    main()
