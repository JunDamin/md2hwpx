import argparse
import sys
import json
import os

from .frontmatter_parser import parse_markdown_with_frontmatter, convert_metadata_to_pandoc_meta
from .marko_adapter import MarkoToPandocAdapter
from .MarkdownToHtml import MarkdownToHtml
from .MarkdownToHwpx import MarkdownToHwpx


def main():
    parser = argparse.ArgumentParser(
        description="Convert Markdown to HWPX (md2hwpx)."
    )

    parser.add_argument("input_file", help="Input Markdown file (.md)")
    parser.add_argument("-o", "--output", required=True, help="Output file (.hwpx, .html, .json)")
    parser.add_argument("--reference-doc", required=False, default=None,
                        help="Reference HWPX for styles (default: built-in blank.hwpx)")

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

    elif output_ext in [".htm", ".html"]:
        MarkdownToHtml.convert_to_html(input_file, args.output, json_ast=ast)
        print(f"Successfully converted to {args.output}")

    elif output_ext == ".json":
        # Debug: output the converted AST
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(ast, f, indent=2, ensure_ascii=False)
        print(f"Successfully wrote AST to {args.output}")

    else:
        print(f"Error: Unsupported output format: {output_ext}", file=sys.stderr)
        print("Supported formats: .hwpx, .html, .htm, .json", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
