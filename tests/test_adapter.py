"""Tests for MarkoToPandocAdapter."""

import pytest
from md2hwpx.marko_adapter import MarkoToPandocAdapter


class TestAdapterBasicParsing:
    """Test basic parsing and AST structure."""

    def test_empty_document(self, adapter):
        result = adapter.parse("")
        assert result['blocks'] == []
        assert 'meta' in result

    def test_single_paragraph(self, adapter):
        result = adapter.parse("Hello world")
        blocks = result['blocks']
        assert len(blocks) == 1
        assert blocks[0]['t'] == 'Para'

    def test_multiple_paragraphs(self, adapter):
        result = adapter.parse("First paragraph.\n\nSecond paragraph.")
        blocks = result['blocks']
        assert len(blocks) == 2
        assert all(b['t'] == 'Para' for b in blocks)


class TestAdapterHeaders:
    """Test header parsing at all levels."""

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
    def test_standard_headers(self, adapter, level):
        md = "#" * level + " Header Text"
        result = adapter.parse(md)
        blocks = result['blocks']
        assert len(blocks) == 1
        assert blocks[0]['t'] == 'Header'
        assert blocks[0]['c'][0] == level

    @pytest.mark.parametrize("level", [7, 8, 9])
    def test_extended_headers(self, adapter, level):
        md = "#" * level + " Extended Header"
        result = adapter.parse(md)
        blocks = result['blocks']
        assert len(blocks) == 1
        assert blocks[0]['t'] == 'Header'
        assert blocks[0]['c'][0] == level

    def test_header_content_is_inline(self, adapter):
        result = adapter.parse("# Hello **bold** world")
        header = result['blocks'][0]
        inlines = header['c'][2]
        types = [i['t'] for i in inlines]
        assert 'Str' in types
        assert 'Strong' in types


class TestAdapterInlineFormatting:
    """Test inline formatting elements."""

    def test_bold(self, adapter):
        result = adapter.parse("**bold**")
        para = result['blocks'][0]
        inlines = para['c']
        assert any(i.get('t') == 'Strong' for i in inlines)

    def test_italic(self, adapter):
        result = adapter.parse("*italic*")
        para = result['blocks'][0]
        inlines = para['c']
        assert any(i.get('t') == 'Emph' for i in inlines)

    def test_strikethrough(self, adapter):
        result = adapter.parse("~~deleted~~")
        para = result['blocks'][0]
        inlines = para['c']
        assert any(i.get('t') == 'Strikeout' for i in inlines)

    def test_inline_code(self, adapter):
        result = adapter.parse("`code`")
        para = result['blocks'][0]
        inlines = para['c']
        assert any(i.get('t') == 'Code' for i in inlines)

    def test_link(self, adapter):
        result = adapter.parse("[text](https://example.com)")
        para = result['blocks'][0]
        inlines = para['c']
        link = next(i for i in inlines if i.get('t') == 'Link')
        assert link['c'][2][0] == 'https://example.com'

    def test_image(self, adapter):
        result = adapter.parse("![alt](image.png)")
        para = result['blocks'][0]
        inlines = para['c']
        img = next(i for i in inlines if i.get('t') == 'Image')
        assert img['c'][2][0] == 'image.png'


class TestAdapterLists:
    """Test list parsing."""

    def test_bullet_list(self, adapter):
        md = "- Item 1\n- Item 2\n- Item 3"
        result = adapter.parse(md)
        blocks = result['blocks']
        assert len(blocks) == 1
        assert blocks[0]['t'] == 'BulletList'
        assert len(blocks[0]['c']) == 3

    def test_ordered_list(self, adapter):
        md = "1. First\n2. Second\n3. Third"
        result = adapter.parse(md)
        blocks = result['blocks']
        assert len(blocks) == 1
        assert blocks[0]['t'] == 'OrderedList'
        items = blocks[0]['c'][1]
        assert len(items) == 3

    def test_ordered_list_start_number(self, adapter):
        md = "3. Third\n4. Fourth"
        result = adapter.parse(md)
        block = result['blocks'][0]
        assert block['t'] == 'OrderedList'
        start_num = block['c'][0][0]
        assert start_num == 3

    def test_nested_bullet_list(self, adapter):
        md = "- Item 1\n    - Nested A\n    - Nested B\n- Item 2"
        result = adapter.parse(md)
        block = result['blocks'][0]
        assert block['t'] == 'BulletList'
        # First item should have sub-items
        first_item_blocks = block['c'][0]
        has_nested = any(b['t'] == 'BulletList' for b in first_item_blocks)
        assert has_nested


class TestAdapterTable:
    """Test table parsing."""

    def test_simple_table(self, adapter):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = adapter.parse(md)
        blocks = result['blocks']
        assert len(blocks) == 1
        assert blocks[0]['t'] == 'Table'

    def test_table_structure(self, adapter):
        md = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
        result = adapter.parse(md)
        table = result['blocks'][0]
        content = table['c']
        specs = content[2]
        assert len(specs) == 3  # 3 columns

        head = content[3]
        head_rows = head[1]
        assert len(head_rows) == 1  # 1 header row

        bodies = content[4]
        assert len(bodies) >= 1
        body_rows = bodies[0][3]
        assert len(body_rows) == 1  # 1 body row

    def test_table_multiple_body_rows(self, adapter):
        md = "| H1 | H2 |\n|---|---|\n| A | B |\n| C | D |\n| E | F |"
        result = adapter.parse(md)
        table = result['blocks'][0]
        bodies = table['c'][4]
        body_rows = bodies[0][3]
        assert len(body_rows) == 3

    def test_table_alignment_specs(self, adapter):
        md = "| Left | Center | Right |\n|:-----|:------:|------:|\n| a | b | c |"
        result = adapter.parse(md)
        table = result['blocks'][0]
        specs = table['c'][2]
        assert specs[0][0] == 'AlignLeft'
        assert specs[1][0] == 'AlignCenter'
        assert specs[2][0] == 'AlignRight'

    def test_table_alignment_cells(self, adapter):
        md = "| Left | Center | Right |\n|:-----|:------:|------:|\n| a | b | c |"
        result = adapter.parse(md)
        table = result['blocks'][0]
        # Check body row cell alignment
        body_rows = table['c'][4][0][3]
        cells = body_rows[0][1]
        assert cells[0][1] == 'AlignLeft'
        assert cells[1][1] == 'AlignCenter'
        assert cells[2][1] == 'AlignRight'

    def test_table_default_alignment(self, adapter):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = adapter.parse(md)
        table = result['blocks'][0]
        specs = table['c'][2]
        assert specs[0][0] == 'AlignDefault'
        assert specs[1][0] == 'AlignDefault'


class TestAdapterCodeBlock:
    """Test code block parsing."""

    def test_fenced_code(self, adapter):
        md = "```python\nprint('hello')\n```"
        result = adapter.parse(md)
        blocks = result['blocks']
        assert len(blocks) == 1
        assert blocks[0]['t'] == 'CodeBlock'

    def test_fenced_code_language(self, adapter):
        md = "```python\ncode\n```"
        result = adapter.parse(md)
        block = result['blocks'][0]
        classes = block['c'][0][1]
        assert 'python' in classes


class TestAdapterFootnotes:
    """Test footnote parsing."""

    def test_footnote_ref(self, adapter):
        md = "Text with footnote[^1].\n\n[^1]: Footnote content here."
        result = adapter.parse(md)
        para = result['blocks'][0]
        inlines = para['c']
        has_note = any(i.get('t') == 'Note' for i in inlines)
        assert has_note

    def test_footnote_content(self, adapter):
        md = "Text[^fn1].\n\n[^fn1]: The footnote body."
        result = adapter.parse(md)
        para = result['blocks'][0]
        note = next(i for i in para['c'] if i.get('t') == 'Note')
        blocks = note['c']
        assert len(blocks) > 0


class TestAdapterSpecialChars:
    """Test special character handling."""

    def test_unicode_text(self, adapter):
        result = adapter.parse("한글 테스트입니다.")
        para = result['blocks'][0]
        assert para['t'] == 'Para'

    def test_ampersand_in_text(self, adapter):
        result = adapter.parse("A & B")
        para = result['blocks'][0]
        inlines = para['c']
        text_parts = [i['c'] for i in inlines if i.get('t') == 'Str']
        assert any('&' in t for t in text_parts)

    def test_angle_brackets(self, adapter):
        result = adapter.parse("a < b > c")
        para = result['blocks'][0]
        inlines = para['c']
        text_parts = [i['c'] for i in inlines if i.get('t') == 'Str']
        full_text = ' '.join(text_parts)
        assert '<' in full_text or '&lt;' in full_text


class TestAdapterBlockQuote:
    """Test block quote parsing."""

    def test_blockquote(self, adapter):
        result = adapter.parse("> This is a quote.")
        blocks = result['blocks']
        assert len(blocks) == 1
        assert blocks[0]['t'] == 'BlockQuote'

    def test_blockquote_content(self, adapter):
        result = adapter.parse("> Quoted text here.")
        bq = result['blocks'][0]
        inner_blocks = bq['c']
        assert len(inner_blocks) > 0
        assert inner_blocks[0]['t'] == 'Para'


class TestAdapterHorizontalRule:
    """Test horizontal rule parsing."""

    def test_horizontal_rule(self, adapter):
        result = adapter.parse("---")
        blocks = result['blocks']
        assert len(blocks) == 1
        assert blocks[0]['t'] == 'HorizontalRule'
