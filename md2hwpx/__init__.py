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

__version__ = "0.2.0"
__all__ = [
    "MarkdownToHwpx",
    "MarkdownToHtml",
    "MarkoToPandocAdapter",
    "parse_markdown_with_frontmatter",
    "parse_markdown_string_with_frontmatter",
    "convert_metadata_to_pandoc_meta",
]
