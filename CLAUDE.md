# CLAUDE.md - Project Guide for Claude Code

## Project Overview

**pypandoc-hwpx** is a Python CLI tool that converts documents (DOCX, Markdown, HTML, JSON AST) to Korean Hancom Office HWPX format using Pandoc as the conversion engine.

## Quick Commands

```bash
Install for development
pip install -e .

# Run the tool
pypandoc-hwpx <input> -o <output.hwpx> [--reference-doc=<ref.hwpx>]
# 
# Examples
pypandoc-hwpx test.md -o output.hwpx
pypandoc-hwpx test.docx --reference-doc=custom.hwpx -o output.hwpx

# Debug outputs (HTML/JSON intermediate formats)
pypandoc-hwpx test.md -o debug.html
pypandoc-hwpx test.md -o debug.json
```

## Project Structure

```
pypandoc-hwpx/
├── pypandoc_hwpx/           # Main package
│   ├── cli.py               # CLI entry point (routes by extension)
│   ├── PandocToHwpx.py      # Core HWPX conversion (main logic)
│   ├── PandocToHtml.py      # HTML conversion helper
│   └── blank.hwpx           # Default reference template
├── tests/                   # Test files (manual testing)
│   ├── test.md/html/docx/json  # Input samples
│   └── test-from-*.hwpx     # Expected outputs
├── docs/                    # Documentation (Korean)
│   └── CLAUDE_ARCHITECTURE.md  # Detailed architecture for Claude Code
└── setup.py                 # Package configuration
```

## Key Files to Understand

| File | Purpose | Lines |
|------|---------|-------|
| `pypandoc_hwpx/PandocToHwpx.py` | Core conversion engine | ~1500 |
| `pypandoc_hwpx/cli.py` | CLI argument parsing | ~80 |
| `pypandoc_hwpx/PandocToHtml.py` | HTML debug output | ~420 |

## Dependencies

- **Python**: 3.6+
- **pypandoc**: Pandoc Python wrapper
- **Pillow**: Image processing
- **Pandoc**: System requirement (must be in PATH)

## Architecture Summary

```
Input File → Pandoc → JSON AST → PandocToHwpx → HWPX ZIP
                                      ↑
                        Reference HWPX (styles, page setup)
```

### Conversion Pipeline

1. `pypandoc.convert_file()` generates JSON AST from input
2. Reference HWPX (ZIP) provides styles from `header.xml` and page setup from `section0.xml`
3. AST blocks (paragraphs, headers, tables, lists) mapped to HWPX XML
4. Images extracted and embedded into HWPX `BinData/` directory
5. Output ZIP created with all components

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

In `PandocToHwpx.py`, handlers follow this pattern:
```python
def _handle_blocktype(self, block, ...):
    # 1. Create paragraph element
    p = ET.SubElement(parent, f'{{{NS_PARA}}}p')

    # 2. Add paragraph properties
    para_pr = ET.SubElement(p, f'{{{NS_PARA}}}paraPr')

    # 3. Process content with _process_inlines()
    run = ET.SubElement(p, f'{{{NS_PARA}}}run')
    self._process_inlines(block['c'], run)
```

### Style System

- Styles from reference HWPX are parsed into `self.styles` dict
- Character properties cached with `_get_char_pr_id()`
- Numbering definitions created dynamically for lists

## Testing

No automated tests. Manual testing workflow:
```bash
cd tests/
pypandoc-hwpx test.md -o test-from-md.hwpx
# Open in Hancom Office to verify
```

## Common Tasks

### Add support for new Pandoc block type

1. Read `docs/CLAUDE_ARCHITECTURE.md` for detailed handler patterns
2. Find the block type in Pandoc AST documentation
3. Add handler method `_handle_<blocktype>()` in `PandocToHwpx.py`
4. Register in `convert()` method's block processing loop

### Modify style handling

1. Study `_parse_styles_and_init_xml()` method
2. Reference `header.xml` from `blank.hwpx` for style structure
3. Update style mapping in relevant handler

### Debug conversion issues

1. Generate intermediate JSON: `pypandoc-hwpx input.md -o debug.json`
2. Inspect AST structure for problematic content
3. Add logging in specific handler methods

## Documentation Reference

For detailed information, see:
- `docs/CLAUDE_ARCHITECTURE.md` - Detailed code architecture and patterns
- `docs/hwpx_notes.md` - HWPX format technical notes (Korean)
- `docs/format_comparison.md` - Format comparison (Korean)

## Known Limitations

- Complex formatting (letter-spacing, precise styles) lost in Pandoc AST
- Some table layouts may not convert perfectly
- Tool focuses on content preservation over exact formatting
