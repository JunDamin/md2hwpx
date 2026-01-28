# CLAUDE.md - Project Guide for Claude Code

## Project Overview

**md2hwpx** is a Python CLI tool that converts Markdown documents to Korean Hancom Office HWPX format. It uses the Marko library to parse Markdown and generates HWPX output directly (Pandoc-free).

## Quick Commands

```bash
# Install for development
pip install -e .

# Run the tool
md2hwpx <input.md> -o <output.hwpx> [--reference-doc=<ref.hwpx>]

# Examples
md2hwpx test.md -o output.hwpx
md2hwpx test.md --reference-doc=custom.hwpx -o output.hwpx

# Debug outputs (JSON AST intermediate format)
md2hwpx test.md -o debug.json
```

## Project Structure

```
md2hwpx/
├── md2hwpx/                 # Main package
│   ├── __init__.py          # Package initialization
│   ├── cli.py               # CLI entry point
│   ├── MarkdownToHwpx.py    # Core HWPX conversion engine
│   ├── MarkdownToHtml.py    # HTML conversion (for debugging)
│   ├── marko_adapter.py     # Marko AST to Pandoc-like format adapter
│   ├── frontmatter_parser.py # YAML frontmatter parsing
│   └── blank.hwpx           # Default reference template
├── tests/                   # Test files (manual testing)
│   ├── test.md              # Input sample
│   └── *.hwpx               # Output samples
├── CLAUDE.md                # This file (Claude Code guide)
├── README.md                # User documentation (Korean)
├── setup.py                 # Package configuration
└── pyproject.toml           # Package metadata (if exists)
```

## Key Files to Understand

| File | Purpose |
|------|---------|
| `md2hwpx/MarkdownToHwpx.py` | Core HWPX conversion engine (~1500 lines) |
| `md2hwpx/marko_adapter.py` | Converts Marko AST to Pandoc-like dict format |
| `md2hwpx/frontmatter_parser.py` | Parses YAML frontmatter metadata |
| `md2hwpx/cli.py` | CLI argument parsing and orchestration |
| `md2hwpx/blank.hwpx` | Default template with styles |

## Dependencies

- **Python**: 3.6+
- **marko**: Markdown parser
- **python-frontmatter**: YAML frontmatter parsing
- **Pillow**: Image processing

## Architecture Summary

```
Markdown File → Marko Parser → AST → Adapter → Converter → HWPX ZIP
                                         ↑
                           Reference HWPX (styles, page setup)
```

### Conversion Pipeline

1. `marko` parses Markdown into an AST
2. `marko_adapter.py` converts Marko AST to Pandoc-like dict format
3. Reference HWPX (ZIP) provides styles from `header.xml` and page setup from `section0.xml`
4. AST blocks (paragraphs, headers, tables, lists) mapped to HWPX XML
5. Images extracted and embedded into HWPX `BinData/` directory
6. Output ZIP created with all components

## HWPX Format Basics

HWPX is a ZIP archive containing:
- `Contents/header.xml` - Style definitions
- `Contents/section0.xml` - Document body
- `Contents/content.hpf` - Package manifest
- `BinData/` - Embedded images
- `META-INF/` - Package metadata

### Key XML Namespaces

| Prefix | Purpose | URI |
|--------|---------|-----|
| `hh` | Head (styles) | `http://www.hancom.co.kr/hwpml/2011/head` |
| `hp` | Paragraph (body) | `http://www.hancom.co.kr/hwpml/2011/paragraph` |
| `hc` | Core (common) | `http://www.hancom.co.kr/hwpml/2011/core` |
| `hs` | Section | `http://www.hancom.co.kr/hwpml/2011/section` |

## Code Patterns

### Adding New Block Handler

In `MarkdownToHwpx.py`, handlers follow this pattern:
```python
def _handle_blocktype(self, content):
    # 1. Create paragraph start
    xml = self._create_para_start(style_id=..., para_pr_id=...)

    # 2. Process inline content
    xml += self._process_inlines(content, base_char_pr_id=...)

    # 3. Close paragraph
    xml += '</hp:p>'
    return xml
```

### Style System

- Styles from reference HWPX are parsed into `self.dynamic_style_map` dict
- Character properties cached with `_get_char_pr_id()`
- Placeholder-based styling supported (e.g., `{{H1}}`, `{{BODY}}` in template)
- Users can customize styles by editing the template HWPX in Hancom Office (WYSIWYG)

### Extended Header Levels (7-9)

Standard Markdown only supports header levels 1-6. md2hwpx extends this to support levels 7-9:
- `marko_adapter.py` preprocesses `#######`, `########`, `#########` lines
- Converts them to placeholders before Marko parsing
- Restores them as Header blocks with levels 7, 8, 9 after parsing

### Marko Adapter

The adapter (`marko_adapter.py`) converts Marko AST to Pandoc-like dict format:

| Marko Element | Pandoc Type |
|---------------|-------------|
| `Heading` | `Header` |
| `Paragraph` | `Para` |
| `List(ordered=False)` | `BulletList` |
| `List(ordered=True)` | `OrderedList` |
| `FencedCode` | `CodeBlock` |
| `Table` (GFM) | `Table` |
| `RawText` | `Str` + `Space` |
| `StrongEmphasis` | `Strong` |
| `Emphasis` | `Emph` |
| `Link` | `Link` |
| `Image` | `Image` |
| `CodeSpan` | `Code` |

## Testing

No automated tests. Manual testing workflow:
```bash
cd tests/
md2hwpx test.md -o test-output.hwpx
# Open in Hancom Office to verify
```

## Common Tasks

### Add support for new Marko block type

1. Add conversion logic in `marko_adapter.py` to convert Marko element to Pandoc-like format
2. If needed, add handler method `_handle_<blocktype>()` in `MarkdownToHwpx.py`
3. Register in `_process_blocks()` method's block processing loop

### Modify style handling

1. Study `_parse_styles_and_init_xml()` method in `MarkdownToHwpx.py`
2. Reference `header.xml` from `blank.hwpx` for style structure
3. Update style mapping in relevant handler

### Customize template styles (for users)

1. Copy `blank.hwpx` from the package
2. Open in Hancom Office and edit styles via Format > Styles (F6)
3. Save and use with `--reference-doc=custom.hwpx`
4. Or use placeholder method: add `{{H1}}`, `{{BODY}}` text with desired formatting

### Debug conversion issues

1. Generate intermediate JSON: `md2hwpx input.md -o debug.json`
2. Inspect AST structure for problematic content
3. Add logging in specific handler methods

## Known Limitations

- Only Markdown input is supported (no DOCX, HTML, or JSON AST input)
- Complex formatting (letter-spacing, precise styles) not supported
- Some table layouts may not convert perfectly (no colspan/rowspan in GFM)
- No underline/superscript/subscript (not part of standard Markdown)
- Tool focuses on content preservation over exact formatting
