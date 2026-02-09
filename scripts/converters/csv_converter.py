"""
CSV / TSV to Markdown converter.

Zero external dependencies (stdlib ``csv`` only).
Uses ``tabulate`` for table formatting when available, falls back to manual
pipe-table construction.
"""

import csv
import logging
from pathlib import Path
from typing import Optional

from .base import BaseConverter, ConversionResult
from .registry import ConverterRegistry

logger = logging.getLogger(__name__)

# How many rows to buffer before flushing to the output file.
_FLUSH_EVERY = 1000


def _format_row(cells: list[str]) -> str:
    """Format a single row as a Markdown pipe-table line."""
    escaped = [c.replace("|", "\\|") for c in cells]
    return "| " + " | ".join(escaped) + " |"


def _separator(ncols: int) -> str:
    return "|" + "|".join(["---"] * ncols) + "|"


def _try_tabulate(rows: list[list[str]], headers: list[str]) -> Optional[str]:
    """Try to format with tabulate; return None if unavailable."""
    try:
        from tabulate import tabulate
        return tabulate(rows, headers=headers, tablefmt="pipe")
    except ImportError:
        return None


@ConverterRegistry.register
class CsvConverter(BaseConverter):
    """Convert CSV and TSV files to Markdown tables."""

    EXTENSIONS = [".csv", ".tsv"]
    DISPLAY_NAME = "CSV / TSV"
    REQUIRED_PACKAGES: dict[str, str] = {}  # stdlib only

    def __init__(self, **options):
        super().__init__(**options)
        self.delimiter: Optional[str] = options.get("delimiter")

    def convert_file(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
    ) -> ConversionResult:
        input_path = Path(input_path)
        output_path = self.resolve_output_path(input_path, output_path)

        # Decide delimiter
        delimiter = self.delimiter
        if delimiter is None:
            if input_path.suffix.lower() == ".tsv":
                delimiter = "\t"
            else:
                # Auto-detect via Sniffer on the first 8 KB
                with open(input_path, "r", encoding="utf-8", errors="replace") as f:
                    sample = f.read(8192)
                try:
                    dialect = csv.Sniffer().sniff(sample)
                    delimiter = dialect.delimiter
                except csv.Error:
                    delimiter = ","

        # Read rows and stream output
        output_path.parent.mkdir(parents=True, exist_ok=True)

        row_count = 0
        col_count = 0

        with (
            open(input_path, "r", encoding="utf-8", errors="replace", newline="") as fin,
            open(output_path, "w", encoding="utf-8") as fout,
        ):
            reader = csv.reader(fin, delimiter=delimiter)

            # -- metadata header --
            fout.write(f"# {input_path.name}\n\n")

            # -- first row (headers) --
            try:
                headers = next(reader)
            except StopIteration:
                fout.write("*Empty file*\n")
                return ConversionResult(
                    input_path=input_path,
                    output_path=output_path,
                    success=True,
                    metadata={"rows": 0, "columns": 0},
                )

            col_count = len(headers)

            # Collect all rows so we can optionally use tabulate for small files
            # For large files (streaming), we write manually.
            all_rows: list[list[str]] = []
            is_large = False

            for row in reader:
                all_rows.append(row)
                row_count += 1
                if row_count > _FLUSH_EVERY:
                    is_large = True
                    break

            if not is_large:
                # Small file -- try tabulate first
                table_str = _try_tabulate(all_rows, headers)
                if table_str is not None:
                    fout.write(table_str)
                    fout.write("\n")
                else:
                    # Manual formatting
                    fout.write(_format_row(headers) + "\n")
                    fout.write(_separator(col_count) + "\n")
                    for row in all_rows:
                        padded = row + [""] * (col_count - len(row))
                        fout.write(_format_row(padded[:col_count]) + "\n")
            else:
                # Large file -- stream manually
                fout.write(_format_row(headers) + "\n")
                fout.write(_separator(col_count) + "\n")
                # Write already-buffered rows
                for row in all_rows:
                    padded = row + [""] * (col_count - len(row))
                    fout.write(_format_row(padded[:col_count]) + "\n")
                # Continue reading
                for row in reader:
                    row_count += 1
                    padded = row + [""] * (col_count - len(row))
                    fout.write(_format_row(padded[:col_count]) + "\n")

        total_rows = row_count  # data rows (excludes header)

        logger.info("Converted %s (%d rows, %d cols)", input_path.name, total_rows, col_count)
        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            success=True,
            metadata={"rows": total_rows, "columns": col_count},
        )

    @classmethod
    def add_arguments(cls, parser) -> None:
        parser.add_argument(
            "--delimiter",
            help="Column delimiter (auto-detected if omitted)",
        )

    @classmethod
    def from_args(cls, args) -> "CsvConverter":
        return cls(delimiter=getattr(args, "delimiter", None))
