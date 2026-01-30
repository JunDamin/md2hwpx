# md2hwpx

**md2hwpx** is a Python tool that converts Markdown (`.md`) files to Korean Hancom Office HWPX format (`.hwpx`). It works entirely in pure Python without requiring Pandoc.

[Fork of pypandoc-hwpx](https://github.com/msjang/pypandoc-hwpx). This project continues development with new features and improvements.

[한국어 README](https://github.com/msjang/md2hwpx/blob/main/README.md)

## Features

- **Pandoc-free conversion**: Pure Python pipeline using Marko + XML generation
- **CLI and Python API**: Use `md2hwpx` or import the converter classes
- **YAML front matter**: Supports metadata; document `title` is written into HWPX
- **Template-driven styling**: WYSIWYG placeholders for headings, body text, lists, and table cells
- **Tables**: GFM tables with alignment and proportional column widths
- **Lists**: Nested bullet/ordered lists, custom start numbers
- **Images**: Local image embedding, size normalization, and safe path validation
- **Block quotes & horizontal rules**
- **Footnotes**
- **Extended headers**: Levels 1–9
- **Debug outputs**: `.json` AST and `.html` outputs

## Requirements

- **Python 3.9+**
- **Libraries**: marko, python-frontmatter, Pillow

## Installation

### From PyPI (recommended)

```bash
pip install md2hwpx
```

### From source

```bash
git clone https://github.com/msjang/md2hwpx.git
cd md2hwpx
pip install -e .
```

## Usage

### CLI

```bash
# Markdown to HWPX
md2hwpx input.md -o output.hwpx

# With custom reference template
md2hwpx input.md --reference-doc=custom.hwpx -o output.hwpx

# Debug: output intermediate JSON AST
md2hwpx input.md -o debug.json

# Debug: output HTML (for inspection)
md2hwpx input.md -o output.html
```

### CLI options

| Option | Description |
|--------|-------------|
| `input_file` | Input Markdown file (.md, .markdown) |
| `-o`, `--output` | Output file (.hwpx, .json, .html) |
| `-r`, `--reference-doc` | Reference HWPX for styles and page setup (default: built-in blank.hwpx) |
| `--verbose` | Show detailed debug output |
| `-q`, `--quiet` | Suppress all non-error output |
| `-v`, `--version` | Show version number |

### Front matter (title)

```markdown
---
title: My Document Title
---

# Heading
```

The `title` is written into the HWPX document metadata.

### Python API

```python
from md2hwpx import MarkdownToHwpx, MarkoToPandocAdapter

adapter = MarkoToPandocAdapter()
ast = adapter.parse("# Hello World\n\nThis is a paragraph.")

MarkdownToHwpx.convert_to_hwpx(
    input_path="input.md",
    output_path="output.hwpx",
    reference_path="blank.hwpx",
    json_ast=ast,
)
```

## Style Customization (Template)

You can customize output styles by editing a reference HWPX template in Hancom Office.

### Method 1: Placeholder-based (recommended)

Create a template with placeholder text and apply your desired formatting:

| Placeholder | Markdown Element |
|-------------|------------------|
| `{{H1}}` | `# Heading 1` |
| `{{H2}}` | `## Heading 2` |
| `{{H3}}` | `### Heading 3` |
| `{{H4}}`–`{{H9}}` | `####`–`#########` |
| `{{BODY}}` | Body text |

#### List placeholders

Use placeholders for list styling (levels 1–7):

- `{{LIST_BULLET_1}}` … `{{LIST_BULLET_7}}`
- `{{LIST_ORDERED_1}}` … `{{LIST_ORDERED_7}}`

Text before the placeholder can be used as a prefix (e.g., `1. `, `가. `).
If your template paragraph uses numbering, md2hwpx preserves that numbering.

#### Table cell placeholders

Use these 12 placeholders inside a template table to control cell styles:

- `{{CELL_HEADER_LEFT}}`, `{{CELL_HEADER_CENTER}}`, `{{CELL_HEADER_RIGHT}}`
- `{{CELL_TOP_LEFT}}`, `{{CELL_TOP_CENTER}}`, `{{CELL_TOP_RIGHT}}`
- `{{CELL_MIDDLE_LEFT}}`, `{{CELL_MIDDLE_CENTER}}`, `{{CELL_MIDDLE_RIGHT}}`
- `{{CELL_BOTTOM_LEFT}}`, `{{CELL_BOTTOM_CENTER}}`, `{{CELL_BOTTOM_RIGHT}}`

Then convert with:

```bash
md2hwpx input.md --reference-doc=my_template.hwpx -o output.hwpx
```

### Method 2: Style editing

1. Copy the built-in template:
   ```bash
   python -c "import md2hwpx; import shutil; shutil.copy(md2hwpx.__path__[0] + '/blank.hwpx', 'my_template.hwpx')"
   ```
2. Open in Hancom Office and edit styles via **Format > Styles** (F6)
3. Use as reference template

## Supported Markdown Elements

| Element | Support |
|---------|---------|
| Headings (1–9) | Full |
| Paragraphs | Full |
| Bold / italic / strikethrough | Full |
| Links | Full (HWPX hyperlinks) |
| Images | Full (embedded) |
| Tables (GFM) | Full (alignment + proportional widths) |
| Bullet lists | Full (nested) |
| Ordered lists | Full (nested, custom start) |
| Code blocks | Full |
| Inline code | Full |
| Block quotes | Full (nested) |
| Horizontal rules | Full |
| Footnotes | Full |
| Superscript / subscript | Supported in output if present in AST |

## Security & Limits

- Input and template size limits (default: 50 MB each)
- Image count limit (default: 500)
- Image path validation blocks absolute paths and directory traversal

## Development

```bash
# Install for development
pip install -e .

# Run tests
python -m pytest tests/ -v

# Run with verbose output
md2hwpx test.md -o output.hwpx --verbose
```

## Changelog Since Fork

Highlights since the original fork:

- Placeholder-based styles for headers, lists, and table cells
- GFM tables with alignment and proportional column widths
- Front matter metadata injection (title)
- Enhanced list handling with custom starts and template numbering
- Security limits (file size, image count, path validation)

## License

MIT License. See `LICENSE` for details.
