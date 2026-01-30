"""
High-level convenience API for md2hwpx.

Provides simple functions to convert Markdown strings or files to HWPX
without needing to understand the internal pipeline.
"""

import os

from .marko_adapter import MarkoToPandocAdapter
from .frontmatter_parser import parse_markdown_string_with_frontmatter, convert_metadata_to_pandoc_meta
from .MarkdownToHwpx import MarkdownToHwpx
from .config import ConversionConfig, DEFAULT_CONFIG


def _get_default_reference_doc():
    """Return path to the built-in blank.hwpx template."""
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(pkg_dir, "blank.hwpx")


def convert_string(markdown_string, output_path, reference_doc=None, config=None):
    """Convert a Markdown string to an HWPX file.

    Args:
        markdown_string: Markdown-formatted text (may include YAML frontmatter)
        output_path: Output .hwpx file path
        reference_doc: Path to a reference HWPX template for styles and page setup.
                       If None, uses the built-in blank.hwpx.
        config: Optional ConversionConfig instance. Uses DEFAULT_CONFIG if None.

    Raises:
        TemplateError: If the reference template is missing or invalid.
        ConversionError: If conversion fails.
    """
    if reference_doc is None:
        reference_doc = _get_default_reference_doc()

    # Parse frontmatter and markdown content
    metadata, md_content = parse_markdown_string_with_frontmatter(markdown_string)

    # Convert to Pandoc-like AST
    adapter = MarkoToPandocAdapter()
    ast = adapter.parse(md_content)
    ast['meta'] = convert_metadata_to_pandoc_meta(metadata)

    # Convert AST to HWPX file (no input_path since source is a string)
    MarkdownToHwpx.convert_to_hwpx(
        input_path=None,
        output_path=output_path,
        reference_path=reference_doc,
        json_ast=ast,
        config=config,
    )
