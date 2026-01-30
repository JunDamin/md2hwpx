# Changelog

All notable changes to md2hwpx will be documented in this file.

Forked from pypandoc-hwpx: https://github.com/msjang/pypandoc-hwpx

## [0.2.0] - 2026-01-29

### Added
- **Placeholder-based style system**: Use `{{H1}}`, `{{BODY}}`, `{{CELL_HEADER_LEFT}}`, `{{LIST_BULLET_1}}` etc. in templates for WYSIWYG style control
- **Table cell placeholders**: 12 cell position types (header/top/middle/bottom x left/center/right) for fine-grained table styling
- **Table column alignment**: GFM alignment syntax (`:--`, `:--:`, `--:`) now applies to HWPX output
- **Block quote support**: Rendered with increased left margin, supports nesting
- **Horizontal rule support**: Rendered as paragraph with bottom border
- **Configuration system**: `ConversionConfig` class centralizes all magic numbers and defaults
- **Custom exceptions**: `HwpxError`, `TemplateError`, `ImageError`, `StyleError`, `ConversionError`
- **Input validation**: File existence, ZIP validity, required files check for templates
- **Logging**: Replaced all print statements with Python `logging` module
- **CLI flags**: `--verbose` for debug output, `-q`/`--quiet` for silent mode
- **`__main__.py`**: Support for `python -m md2hwpx` invocation
- **Test suite**: 109 tests covering adapter, converter, CLI, and end-to-end scenarios
- **English README** with full documentation

### Changed
- Refactored list handlers to use ElementTree API (`_handle_bullet_list_elem`, `_handle_ordered_list_elem`)
- Table handler uses ElementTree API (`_handle_table_elem`)
- Marko adapter now extracts column alignment from GFM table cells

### Fixed
- Table parsing with Marko GFM extension (TableRow handling)
- Footnote parsing (extension loading, attribute names)

## [0.1.0] - Initial Release

### Added
- Markdown to HWPX conversion (Pandoc-free)
- Support for headers, paragraphs, bold/italic/strikethrough, links, images, tables, lists, code blocks, footnotes
- Reference template system for style customization
- Marko-based markdown parser with GFM and footnote extensions
- Extended header levels (7-9)
- YAML frontmatter support
- CLI tool with `--reference-doc` option
