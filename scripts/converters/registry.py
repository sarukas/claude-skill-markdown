"""
Converter registry -- maps file extensions to converter classes.

Usage::

    from converters.registry import ConverterRegistry

    @ConverterRegistry.register
    class MyConverter(BaseConverter):
        EXTENSIONS = [".xyz"]
        ...

    cls = ConverterRegistry.get(".xyz")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Type

from .base import BaseConverter

logger = logging.getLogger(__name__)


class ConverterRegistry:
    """Central registry that maps file extensions to converter classes."""

    _converters: Dict[str, Type[BaseConverter]] = {}

    # -- registration ---------------------------------------------------------

    @classmethod
    def register(cls, converter_cls: Type[BaseConverter]) -> Type[BaseConverter]:
        """Class decorator that registers *converter_cls* for its EXTENSIONS.

        Example::

            @ConverterRegistry.register
            class PdfConverter(BaseConverter):
                EXTENSIONS = [".pdf"]
                ...
        """
        for ext in converter_cls.EXTENSIONS:
            ext_lower = ext.lower()
            if not ext_lower.startswith("."):
                ext_lower = f".{ext_lower}"
            if ext_lower in cls._converters:
                existing = cls._converters[ext_lower]
                if existing is not converter_cls:
                    logger.warning(
                        "Extension %s re-registered: %s replaces %s",
                        ext_lower,
                        converter_cls.__name__,
                        existing.__name__,
                    )
            cls._converters[ext_lower] = converter_cls
        return converter_cls

    # -- lookup ---------------------------------------------------------------

    @classmethod
    def get(cls, extension: str) -> Optional[Type[BaseConverter]]:
        """Look up the converter class for *extension* (e.g. ``'.pdf'``)."""
        ext = extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        return cls._converters.get(ext)

    @classmethod
    def get_for_file(cls, path: Path | str) -> Optional[Type[BaseConverter]]:
        """Look up the converter class for a given file path."""
        return cls.get(Path(path).suffix)

    # -- introspection --------------------------------------------------------

    @classmethod
    def supported_extensions(cls) -> List[str]:
        """Return a sorted list of all registered extensions."""
        return sorted(cls._converters.keys())

    @classmethod
    def unique_converters(cls) -> List[Type[BaseConverter]]:
        """Return a deduplicated list of registered converter classes."""
        seen: Dict[int, Type[BaseConverter]] = {}
        for conv_cls in cls._converters.values():
            seen[id(conv_cls)] = conv_cls
        return list(seen.values())
