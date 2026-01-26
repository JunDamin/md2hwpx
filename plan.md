# Plan: Convert pypandoc-hwpx to md2hwpx (Pandoc-free)

## Overview

Replace Pandoc dependency with Marko (pure Python Markdown parser) and rename package to `md2hwpx`. Only Markdown input will be supported.

**Architecture Change:**
```
Old: Input (DOCX/MD/HTML) -> Pandoc -> JSON AST -> handlers -> HWPX
New: Input (MD only) -> python-frontmatter -> Marko -> Adapter -> handlers -> HWPX
```

## Key Design Decision: Adapter Layer

Create an adapter (`marko_adapter.py`) that converts Marko's AST to Pandoc-like dict format. This:
- Minimizes changes to existing 1500+ line `PandocToHwpx.py`
- Keeps existing handler logic intact
- Enables easier testing (compare adapter output to known Pandoc format)

## Files to Create

| File | Purpose |
|------|---------|
| `md2hwpx/marko_adapter.py` | Converts Marko AST to Pandoc-like dict |
| `md2hwpx/frontmatter_parser.py` | Parses YAML front matter metadata |

## Files to Rename/Modify

| Old | New | Changes |
|-----|-----|---------|
| `pypandoc_hwpx/` | `md2hwpx/` | Directory rename |
| `PandocToHwpx.py` | `MarkdownToHwpx.py` | Remove pypandoc, accept pre-parsed AST |
| `PandocToHtml.py` | `MarkdownToHtml.py` | Keep for debug output |
| `cli.py` | `cli.py` | New parsing flow, MD-only input |
| `setup.py` | `setup.py` | New name, dependencies, Python 3.9+ |

## Dependency Changes

- **Remove**: `pypandoc` (and system Pandoc requirement)
- **Add**: `marko>=2.0.0`, `python-frontmatter>=1.0.0`
- **Keep**: `Pillow`

## Implementation Steps

### Step 1: Package Rename
1. Rename directory `pypandoc_hwpx/` to `md2hwpx/`
2. Update `setup.py`:
   - name: `md2hwpx`
   - python_requires: `>=3.9`
   - Remove `pypandoc`, add `marko`, `python-frontmatter`
   - Entry point: `md2hwpx=md2hwpx.cli:main`

### Step 2: Create Adapter Module (`md2hwpx/marko_adapter.py`)
Convert Marko AST to Pandoc-like dict format:

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
| `FootnoteRef` | `Note` |

### Step 3: Create Front Matter Parser (`md2hwpx/frontmatter_parser.py`)
- Use `python-frontmatter` to extract YAML metadata
- Convert to Pandoc meta format for existing handler compatibility

### Step 4: Update CLI (`md2hwpx/cli.py`)
- Validate input is `.md` only
- Parse front matter, then parse Markdown with Marko adapter
- Pass pre-parsed AST to converter
- Support outputs: `.hwpx`, `.html` (debug), `.json` (AST debug)

### Step 5: Update Core Module (`md2hwpx/MarkdownToHwpx.py`)
- Remove `import pypandoc`
- Modify `convert_to_hwpx()` to accept `json_ast` parameter
- Keep all `_handle_*` methods unchanged (adapter provides compatible format)

### Step 6: Update `__init__.py`
- Update imports for renamed modules

### Step 7: Handle Special Features
- **Tables**: Use Marko GFM extension, convert to simplified Pandoc table format
- **Footnotes**: Use Marko footnote extension, convert refs to Pandoc Note type
- **Missing features**: Underline, superscript, subscript not available in standard Markdown (document as limitation)

## Verification

1. **AST comparison**: `md2hwpx test.md -o test.json` - inspect adapter output
2. **HWPX output**: `md2hwpx test.md -o test.hwpx` - open in Hancom Office
3. **Test features**:
   - Headers (levels 1-6)
   - Bold, italic, combined formatting
   - Bullet and ordered lists (nested)
   - Code blocks
   - Tables
   - Images
   - Links
   - Footnotes
   - YAML front matter metadata

## Critical Files (in order of implementation)

1. `setup.py` - package config and dependencies
2. `md2hwpx/marko_adapter.py` - core AST conversion (new)
3. `md2hwpx/frontmatter_parser.py` - YAML handling (new)
4. `md2hwpx/cli.py` - entry point updates
5. `md2hwpx/MarkdownToHwpx.py` - minimal changes from PandocToHwpx.py
6. `md2hwpx/MarkdownToHtml.py` - minimal changes from PandocToHtml.py

## Known Limitations

- **Markdown only**: No DOCX, HTML, or other input formats
- **No underline/superscript/subscript**: Not part of standard Markdown
- **Simplified tables**: No colspan/rowspan (GFM limitation)
