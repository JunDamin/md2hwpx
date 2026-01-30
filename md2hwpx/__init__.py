"""
md2hwpx - Convert Markdown to HWPX (Korean Hancom Office format)

This package provides a pure Python solution for converting Markdown files
to HWPX format without requiring Pandoc.
"""

from .MarkdownToHwpx import MarkdownToHwpx
from .MarkdownToHtml import MarkdownToHtml
from .marko_adapter import MarkoToPandocAdapter
from .frontmatter_parser import (
    parse_markdown_with_frontmatter,
    parse_markdown_string_with_frontmatter,
    convert_metadata_to_pandoc_meta,
)
from .config import ConversionConfig, DEFAULT_CONFIG
from .exceptions import HwpxError, TemplateError, ImageError, StyleError, ConversionError
from .converter_api import convert_string

__version__ = "0.2.0"
__all__ = [
    "MarkdownToHwpx",
    "MarkdownToHtml",
    "MarkoToPandocAdapter",
    "parse_markdown_with_frontmatter",
    "parse_markdown_string_with_frontmatter",
    "convert_metadata_to_pandoc_meta",
    "ConversionConfig",
    "DEFAULT_CONFIG",
    "HwpxError",
    "TemplateError",
    "ImageError",
    "StyleError",
    "ConversionError",
    "convert_string",
]
