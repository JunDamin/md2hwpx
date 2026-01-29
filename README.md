# md2hwpx

**md2hwpx** is a Python tool that converts Markdown (`.md`) files to Korean Hancom Office HWPX format (`.hwpx`). It works entirely in pure Python without requiring Pandoc.

[한국어 README](README.ko.md)

## Features

- **Input**: Markdown (`.md`)
- **Output**: Hancom Office document (`.hwpx`)
- **Image embedding**: Local images referenced in Markdown are embedded in the output
- **Style customization**: Use a reference HWPX template to control fonts, colors, spacing, and page layout
- **Placeholder system**: Style template elements with `{{H1}}`, `{{BODY}}`, etc. in Hancom Office for WYSIWYG style control
- **Table support**: GFM tables with column alignment (left/center/right)
- **Block quotes and horizontal rules**
- **Footnotes**
- **Extended headers**: Levels 1-9 (beyond standard Markdown's 1-6)

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

### Basic conversion

```bash
# Markdown to HWPX
md2hwpx input.md -o output.hwpx

# With custom reference template
md2hwpx input.md --reference-doc=custom.hwpx -o output.hwpx

# Debug: output intermediate JSON AST
md2hwpx input.md -o debug.json
```

### CLI options

| Option | Description |
|--------|-------------|
| `input_file` | Input Markdown file (.md, .markdown) |
| `-o`, `--output` | Output file (.hwpx, .json) |
| `--reference-doc` | Reference HWPX for styles and page setup (default: built-in blank.hwpx) |
| `--verbose` | Show detailed debug output |
| `-q`, `--quiet` | Suppress all non-error output |
| `-v`, `--version` | Show version number |

### Python API

```python
from md2hwpx import MarkdownToHwpx, MarkoToPandocAdapter

# Parse markdown
adapter = MarkoToPandocAdapter()
ast = adapter.parse("# Hello World\n\nThis is a paragraph.")

# Convert to HWPX
MarkdownToHwpx.convert_to_hwpx(
    input_path="input.md",
    output_path="output.hwpx",
    reference_path="blank.hwpx",
    json_ast=ast,
)
```

## Style Customization

You can customize the output style by editing a template HWPX file in Hancom Office.

### Method 1: Placeholder-based (recommended)

Create a template with placeholder text and apply your desired formatting in Hancom Office:

| Placeholder | Markdown Element | Example Style |
|-------------|-----------------|---------------|
| `{{H1}}` | `# Heading 1` | 24pt, blue, bold |
| `{{H2}}` | `## Heading 2` | 18pt, black, bold |
| `{{H3}}` | `### Heading 3` | 14pt, black, bold |
| `{{H4}}` - `{{H9}}` | `####` - `#########` | Custom |
| `{{BODY}}` | Body text | 11pt, black |

Save the file and use it as a reference:

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
| Headings (1-9) | Full |
| Paragraphs | Full |
| Bold, italic, strikethrough | Full |
| Links | Full (HWPX hyperlinks) |
| Images | Full (embedded) |
| Tables (GFM) | Full (with alignment) |
| Bullet lists | Full (nested) |
| Ordered lists | Full (nested, custom start) |
| Code blocks | Full |
| Inline code | Full |
| Block quotes | Full (nested) |
| Horizontal rules | Full |
| Footnotes | Full |
| Superscript/subscript | Full |

## Project Structure

```
md2hwpx/
  cli.py              - CLI entry point
  MarkdownToHwpx.py   - Core HWPX conversion engine
  marko_adapter.py     - Marko AST to Pandoc-like format adapter
  frontmatter_parser.py - YAML frontmatter parsing
  config.py            - Centralized configuration constants
  exceptions.py        - Custom exception classes
  blank.hwpx           - Built-in reference template
```

## Development

```bash
# Install for development
pip install -e .

# Run tests
python -m pytest tests/ -v

# Run with verbose output
md2hwpx test.md -o output.hwpx --verbose
```

## License

MIT License. See [LICENSE](LICENSE) for details.
