"""
Base classes for the pluggable document-to-Markdown converter framework.

Zero external dependencies -- only stdlib.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class ConversionResult:
    """Result of converting a single file."""

    input_path: Path
    output_path: Optional[Path] = None
    success: bool = False
    error: Optional[str] = None
    elapsed_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "OK" if self.success else "FAIL"
        name = self.input_path.name
        if self.error:
            return f"[{status}] {name} -- {self.error}"
        return f"[{status}] {name} -> {self.output_path} ({self.elapsed_seconds:.1f}s)"


@dataclass
class BatchResult:
    """Aggregated result of converting multiple files."""

    results: List[ConversionResult] = field(default_factory=list)

    # -- derived properties --------------------------------------------------

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)

    def summary(self) -> str:
        lines = [f"Batch conversion: {self.succeeded}/{self.total} succeeded"]
        for r in self.results:
            lines.append(f"  {r}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Abstract base converter
# ---------------------------------------------------------------------------

class BaseConverter(ABC):
    """Abstract base for every format converter.

    Subclasses must define *EXTENSIONS*, *DISPLAY_NAME*, *REQUIRED_PACKAGES*
    and implement *convert_file()*.
    """

    # Subclasses override these -------------------------------------------------
    EXTENSIONS: ClassVar[List[str]] = []
    DISPLAY_NAME: ClassVar[str] = ""
    REQUIRED_PACKAGES: ClassVar[Dict[str, str]] = {}
    # Keys are *import names*, values are *pip install names*.

    MAX_MEMORY_WARNING_MB: ClassVar[int] = 100
    """Log a warning before converting files larger than this (MB)."""

    def __init__(self, **options: Any) -> None:
        self.options = options

    # -- abstract -------------------------------------------------------------

    @abstractmethod
    def convert_file(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
    ) -> ConversionResult:
        """Convert *input_path* to Markdown and return a ConversionResult."""
        ...

    # -- concrete helpers -----------------------------------------------------

    def resolve_output_path(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Return *output_path* or default to *input_path* with ``.md`` suffix."""
        if output_path is not None:
            return Path(output_path)
        return Path(input_path).with_suffix(".md")

    def timed_convert(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
    ) -> ConversionResult:
        """Wrap *convert_file* with timing, exception handling, and size warning."""
        input_path = Path(input_path)

        # File-size warning
        try:
            size_mb = input_path.stat().st_size / (1024 * 1024)
            if size_mb > self.MAX_MEMORY_WARNING_MB:
                logger.warning(
                    "%s is %.0f MB (threshold %d MB) -- conversion may use significant memory",
                    input_path.name,
                    size_mb,
                    self.MAX_MEMORY_WARNING_MB,
                )
        except OSError:
            pass

        start = time.perf_counter()
        try:
            result = self.convert_file(input_path, output_path)
            result.elapsed_seconds = time.perf_counter() - start
            return result
        except Exception as exc:
            return ConversionResult(
                input_path=input_path,
                output_path=output_path,
                success=False,
                error=str(exc),
                elapsed_seconds=time.perf_counter() - start,
            )

    # -- batch / directory ----------------------------------------------------

    def convert_directory(
        self,
        directory: Path,
        output_dir: Optional[Path] = None,
        recursive: bool = False,
        skip_existing: bool = True,
    ) -> BatchResult:
        """Find files matching *self.EXTENSIONS* and convert them all."""
        directory = Path(directory)
        batch = BatchResult()

        for ext in self.EXTENSIONS:
            pattern = f"*{ext}"
            finder = directory.rglob if recursive else directory.glob
            for src in sorted(finder(pattern)):
                if not src.is_file():
                    continue

                # Determine output path
                if output_dir is not None:
                    dst = Path(output_dir) / src.with_suffix(".md").name
                else:
                    dst = src.with_suffix(".md")

                # Skip if output is newer than input (mtime check)
                if skip_existing and dst.exists():
                    try:
                        if dst.stat().st_mtime > src.stat().st_mtime:
                            logger.info("Skipping %s (up-to-date .md exists)", src.name)
                            continue
                    except OSError:
                        pass

                result = self.timed_convert(src, dst)
                batch.results.append(result)
                if result.success:
                    logger.info("Converted %s", result)
                else:
                    logger.error("Failed  %s", result)

        return batch

    # -- dependency checking --------------------------------------------------

    @classmethod
    def check_dependencies(cls) -> List[str]:
        """Return list of *pip install* names for missing packages."""
        missing: List[str] = []
        for import_name, pip_name in cls.REQUIRED_PACKAGES.items():
            try:
                __import__(import_name)
            except ImportError:
                missing.append(pip_name)
        return missing

    # -- CLI integration ------------------------------------------------------

    @classmethod
    def add_arguments(cls, parser) -> None:  # noqa: ANN001
        """Override to add format-specific CLI arguments."""
        _ = parser  # available for subclass override

    @classmethod
    def from_args(cls, args) -> "BaseConverter":  # noqa: ANN001
        """Construct a converter instance from parsed CLI *args*."""
        _ = args  # available for subclass override
        return cls()
