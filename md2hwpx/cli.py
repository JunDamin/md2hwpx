"""
md2hwpx - Markdown to HWPX Converter

A Pandoc-free tool to convert Markdown files to Korean Hancom Office HWPX format.
"""

import argparse
import sys
import json
import os

from .frontmatter_parser import parse_markdown_with_frontmatter, convert_metadata_to_pandoc_meta
from .marko_adapter import MarkoToPandocAdapter
from .MarkdownToHtml import MarkdownToHtml
from .MarkdownToHwpx import MarkdownToHwpx

__version__ = "0.2.0"


def main():
    parser = argparse.ArgumentParser(
        prog="md2hwpx",
        description="Convert Markdown to HWPX format (Pandoc-free).",
        epilog="Examples:\n"
               "  md2hwpx input.md -o output.hwpx\n"
               "  md2hwpx input.md --reference-doc=custom.hwpx -o output.hwpx\n"
               "  md2hwpx input.md -o debug.json",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("input_file", help="Input Markdown file (.md, .markdown)")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file (.hwpx, .json for debug)")
    parser.add_argument("--reference-doc", required=False, default=None,
                        help="Reference HWPX for styles and page setup (default: built-in blank.hwpx)")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()
    input_file = args.input_file

    # Validate input is Markdown
    input_ext = os.path.splitext(input_file)[1].lower()
    if input_ext not in ['.md', '.markdown']:
        print(f"Error: Only Markdown files are supported. Got: {input_ext}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(input_file):
        print(f"Error: Input file not found: {input_file}", file=sys.stderr)
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
            print("Error: --reference-doc is required and no default 'blank.hwpx' found in package.", file=sys.stderr)
            sys.exit(1)

    # Parse Markdown with front matter
    metadata, md_content = parse_markdown_with_frontmatter(input_file)

    # Convert to Pandoc-like AST using Marko adapter
    adapter = MarkoToPandocAdapter()
    ast = adapter.parse(md_content)

    # Inject metadata into AST
    ast['meta'] = convert_metadata_to_pandoc_meta(metadata)

    if output_ext == ".hwpx":
        MarkdownToHwpx.convert_to_hwpx(input_file, args.output, ref_doc, json_ast=ast)
        print(f"Successfully converted to {args.output}")

    elif output_ext == ".json":
        # Debug: output the converted AST
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(ast, f, indent=2, ensure_ascii=False)
        print(f"Successfully wrote AST to {args.output}")

    elif output_ext in [".htm", ".html"]:
        # Hidden feature: HTML output for debugging
        MarkdownToHtml.convert_to_html(input_file, args.output, json_ast=ast)
        print(f"Successfully converted to {args.output}")

    else:
        print(f"Error: Unsupported output format: {output_ext}", file=sys.stderr)
        print("Supported formats: .hwpx, .json", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
