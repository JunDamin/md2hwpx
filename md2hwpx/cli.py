"""
md2hwpx - Markdown to HWPX Converter

A Pandoc-free tool to convert Markdown files to Korean Hancom Office HWPX format.
"""

import argparse
import sys
import json
import os
import logging

from .frontmatter_parser import parse_markdown_with_frontmatter, convert_metadata_to_pandoc_meta
from .marko_adapter import MarkoToPandocAdapter
from .MarkdownToHtml import MarkdownToHtml
from .MarkdownToHwpx import MarkdownToHwpx
from .exceptions import HwpxError, SecurityError
from .config import DEFAULT_CONFIG

__version__ = "0.2.0"

logger = logging.getLogger('md2hwpx')


def setup_logging(verbose=False, quiet=False):
    """Configure logging based on CLI flags.

    Args:
        verbose: If True, show DEBUG level messages
        quiet: If True, suppress all non-error output
    """
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    root_logger = logging.getLogger('md2hwpx')
    root_logger.setLevel(level)
    root_logger.addHandler(handler)


def main():
    parser = argparse.ArgumentParser(
        prog="md2hwpx",
        description="Convert Markdown to HWPX format (Pandoc-free).",
        epilog="Examples:\n"
               "  md2hwpx input.md -o output.hwpx\n"
               "  md2hwpx input.md --reference-doc=custom.hwpx -o output.hwpx\n"
               "  md2hwpx input.md -o debug.json\n"
               "  md2hwpx input.md -o output.hwpx --verbose",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("input_file", help="Input Markdown file (.md, .markdown)")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file (.hwpx, .json for debug)")
    parser.add_argument("--reference-doc", required=False, default=None,
                        help="Reference HWPX for styles and page setup (default: built-in blank.hwpx)")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--verbose", action="store_true", default=False,
                        help="Show detailed debug output")
    parser.add_argument("-q", "--quiet", action="store_true", default=False,
                        help="Suppress all non-error output")

    args = parser.parse_args()

    # Set up logging
    setup_logging(verbose=args.verbose, quiet=args.quiet)

    input_file = args.input_file

    # Validate input is Markdown
    input_ext = os.path.splitext(input_file)[1].lower()
    if input_ext not in ['.md', '.markdown']:
        logger.error("Only Markdown files are supported. Got: %s", input_ext)
        sys.exit(1)

    if not os.path.exists(input_file):
        logger.error("Input file not found: %s", input_file)
        sys.exit(1)

    # Validate input file size
    input_size = os.path.getsize(input_file)
    if input_size > DEFAULT_CONFIG.MAX_INPUT_FILE_SIZE:
        logger.error(
            "Input file too large: %d bytes (max %d bytes)",
            input_size, DEFAULT_CONFIG.MAX_INPUT_FILE_SIZE
        )
        sys.exit(1)

    output_ext = os.path.splitext(args.output)[1].lower()

    # Determine Reference Doc
    ref_doc = args.reference_doc
    if not ref_doc and output_ext == ".hwpx":
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        default_ref = os.path.join(pkg_dir, "blank.hwpx")
        if os.path.exists(default_ref):
            ref_doc = default_ref
        else:
            logger.error("--reference-doc is required and no default 'blank.hwpx' found in package.")
            sys.exit(1)

    # Parse Markdown with front matter
    metadata, md_content = parse_markdown_with_frontmatter(input_file)

    # Convert to Pandoc-like AST using Marko adapter
    adapter = MarkoToPandocAdapter()
    ast = adapter.parse(md_content)

    # Inject metadata into AST
    ast['meta'] = convert_metadata_to_pandoc_meta(metadata)

    try:
        if output_ext == ".hwpx":
            MarkdownToHwpx.convert_to_hwpx(input_file, args.output, ref_doc, json_ast=ast)
            logger.info("Successfully converted to %s", args.output)

        elif output_ext == ".json":
            # Debug: output the converted AST
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(ast, f, indent=2, ensure_ascii=False)
            logger.info("Successfully wrote AST to %s", args.output)

        elif output_ext in [".htm", ".html"]:
            # Hidden feature: HTML output for debugging
            MarkdownToHtml.convert_to_html(input_file, args.output, json_ast=ast)
            logger.info("Successfully converted to %s", args.output)

        else:
            logger.error("Unsupported output format: %s", output_ext)
            logger.error("Supported formats: .hwpx, .json")
            sys.exit(1)

    except HwpxError as e:
        logger.error("%s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
