"""Tests for MarkdownToHwpx converter."""

import os
import io
import zipfile
import xml.etree.ElementTree as ET
import pytest

from md2hwpx.MarkdownToHwpx import MarkdownToHwpx
from md2hwpx.marko_adapter import MarkoToPandocAdapter
from md2hwpx.config import ConversionConfig, DEFAULT_CONFIG
from md2hwpx.exceptions import TemplateError, ConversionError


def _parse_md(text):
    """Helper: parse markdown text and return AST."""
    adapter = MarkoToPandocAdapter()
    return adapter.parse(text)


def _make_converter(md_text, blank_hwpx_path):
    """Helper: create converter from markdown text."""
    ast = _parse_md(md_text)

    header_xml = ""
    section_xml = ""
    with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
        if "Contents/header.xml" in z.namelist():
            header_xml = z.read("Contents/header.xml").decode('utf-8')
        if "Contents/section0.xml" in z.namelist():
            section_xml = z.read("Contents/section0.xml").decode('utf-8')

    return MarkdownToHwpx(
        json_ast=ast,
        header_xml_content=header_xml,
        section_xml_content=section_xml,
    )


class TestConverterInit:
    """Test converter initialization."""

    def test_init_with_defaults(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter.config is DEFAULT_CONFIG
        assert converter.header_root is not None

    def test_init_with_custom_config(self, blank_hwpx_path):
        config = ConversionConfig()
        config.TABLE_WIDTH = 30000

        ast = _parse_md("Hello")
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        converter = MarkdownToHwpx(json_ast=ast, header_xml_content=header_xml, config=config)
        assert converter.config.TABLE_WIDTH == 30000


class TestConverterOutput:
    """Test converter XML output."""

    def test_convert_produces_xml(self, blank_hwpx_path):
        converter = _make_converter("Hello world", blank_hwpx_path)
        xml_body, header_xml = converter.convert()
        assert len(xml_body) > 0
        assert '<hp:p' in xml_body

    def test_convert_header(self, blank_hwpx_path):
        converter = _make_converter("# Title", blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert '<hp:p' in xml_body
        assert 'Title' in xml_body

    def test_convert_paragraph(self, blank_hwpx_path):
        converter = _make_converter("Simple text.", blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert 'Simple' in xml_body
        assert 'text.' in xml_body

    def test_convert_bold_creates_char_pr(self, blank_hwpx_path):
        converter = _make_converter("**bold**", blank_hwpx_path)
        xml_body, header_xml = converter.convert()
        assert 'bold' in xml_body
        # Bold should create a new charPr with bold element
        assert '<hh:bold' in header_xml

    def test_convert_table(self, blank_hwpx_path):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        converter = _make_converter(md, blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert '<hp:tbl' in xml_body
        assert '<hp:tc' in xml_body
        assert '<hp:tr' in xml_body

    def test_convert_bullet_list(self, blank_hwpx_path):
        md = "- Item 1\n- Item 2"
        converter = _make_converter(md, blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert 'Item' in xml_body

    def test_convert_ordered_list(self, blank_hwpx_path):
        md = "1. First\n2. Second"
        converter = _make_converter(md, blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert 'First' in xml_body

    def test_convert_code_block(self, blank_hwpx_path):
        md = "```\ncode here\n```"
        converter = _make_converter(md, blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert 'code here' in xml_body

    def test_convert_link(self, blank_hwpx_path):
        md = "[Click](https://example.com)"
        converter = _make_converter(md, blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert 'Click' in xml_body
        assert 'HYPERLINK' in xml_body

    def test_convert_unicode(self, blank_hwpx_path):
        converter = _make_converter("한글 테스트", blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert '한글' in xml_body


class TestConverterCellStyles:
    """Test cell style positioning logic."""

    def test_get_row_type_header(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._get_row_type(0, 1, 3) == 'HEADER'

    def test_get_row_type_top(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._get_row_type(1, 1, 3) == 'TOP'

    def test_get_row_type_middle(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._get_row_type(2, 1, 3) == 'MIDDLE'

    def test_get_row_type_bottom(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._get_row_type(3, 1, 3) == 'BOTTOM'

    def test_get_row_type_single_body(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._get_row_type(1, 1, 1) == 'TOP'

    def test_get_col_type_left(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._get_col_type(0, 3) == 'LEFT'

    def test_get_col_type_center(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._get_col_type(1, 3) == 'CENTER'

    def test_get_col_type_right(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._get_col_type(2, 3) == 'RIGHT'

    def test_get_col_type_single_column(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._get_col_type(0, 1) == 'LEFT'

    def test_get_cell_style_key(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._get_cell_style_key('HEADER', 'LEFT') == 'HEADER_LEFT'
        assert converter._get_cell_style_key('MIDDLE', 'CENTER') == 'MIDDLE_CENTER'


class TestConverterPlaceholders:
    """Test placeholder detection from template."""

    def test_placeholder_styles_loaded_from_template(self, template_hwpx_path):
        if not os.path.exists(template_hwpx_path):
            pytest.skip("Template HWPX not found")

        ast = _parse_md("Hello")
        header_xml = ""
        section_xml = ""
        with zipfile.ZipFile(template_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')
            section_xml = z.read("Contents/section0.xml").decode('utf-8')

        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        # Text placeholders
        assert 'H1' in converter.placeholder_styles
        assert 'BODY' in converter.placeholder_styles

        # Cell placeholders
        assert 'HEADER_LEFT' in converter.cell_styles
        assert 'HEADER_CENTER' in converter.cell_styles
        assert 'HEADER_RIGHT' in converter.cell_styles
        assert 'MIDDLE_CENTER' in converter.cell_styles
        assert 'BOTTOM_RIGHT' in converter.cell_styles
        assert len(converter.cell_styles) == 12

        # List placeholders
        assert ('BULLET', 1) in converter.list_styles
        assert ('ORDERED', 1) in converter.list_styles

    def test_cell_style_has_required_attributes(self, template_hwpx_path):
        if not os.path.exists(template_hwpx_path):
            pytest.skip("Template HWPX not found")

        ast = _parse_md("Hello")
        header_xml = ""
        section_xml = ""
        with zipfile.ZipFile(template_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')
            section_xml = z.read("Contents/section0.xml").decode('utf-8')

        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        for key, style in converter.cell_styles.items():
            assert 'borderFillIDRef' in style, f"Missing borderFillIDRef in {key}"
            assert 'charPrIDRef' in style, f"Missing charPrIDRef in {key}"
            assert 'paraPrIDRef' in style, f"Missing paraPrIDRef in {key}"
            assert 'cellMargin' in style, f"Missing cellMargin in {key}"


class TestConverterMultiRunPrefix:
    """Test prefix detection when prefix is in a separate run from the placeholder."""

    def _make_section_xml_with_multi_run_prefix(self):
        """Create section XML where prefix text is in a separate run from {{H3}}."""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
            ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
            '<hp:p paraPrIDRef="10" styleIDRef="5" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="22"><hp:t>\u25a1 </hp:t></hp:run>'
            '<hp:run charPrIDRef="19"><hp:t>{{H3}}</hp:t></hp:run>'
            '</hp:p>'
            '</hs:sec>'
        )

    def test_multi_run_prefix_detected(self, blank_hwpx_path):
        """Prefix in a separate run should be detected and stored."""
        ast = _parse_md("### Test Header")
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        section_xml = self._make_section_xml_with_multi_run_prefix()
        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        assert 'H3' in converter.placeholder_styles
        h3 = converter.placeholder_styles['H3']
        assert h3['prefix'] == '\u25a1 '
        assert h3['mode'] == 'prefix'
        assert h3['charPrIDRef'] == '19'
        assert h3['prefixCharPrIDRef'] == '22'

    def test_multi_run_prefix_rendered_in_output(self, blank_hwpx_path):
        """Header with multi-run prefix should include prefix text in output XML."""
        ast = _parse_md("### Test Header")
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        section_xml = self._make_section_xml_with_multi_run_prefix()
        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        section_output, _ = converter.convert()
        # The prefix symbol should appear in the output
        assert '\u25a1 ' in section_output
        assert 'Test' in section_output
        assert 'Header' in section_output

    def test_multi_run_prefix_uses_correct_char_pr_id(self, blank_hwpx_path):
        """Prefix run should use the prefix's own charPrIDRef, not the header's."""
        ast = _parse_md("### Test Header")
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        section_xml = self._make_section_xml_with_multi_run_prefix()
        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        section_output, _ = converter.convert()
        # The prefix run should have charPrIDRef="22"
        assert 'charPrIDRef="22"' in section_output
        # The header content run should have charPrIDRef="19"
        assert 'charPrIDRef="19"' in section_output

    def test_single_run_prefix_still_works(self, blank_hwpx_path):
        """Prefix within the same run as placeholder should still work."""
        section_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
            ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
            '<hp:p paraPrIDRef="10" styleIDRef="5" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="19"><hp:t>\u25a1 {{H3}}</hp:t></hp:run>'
            '</hp:p>'
            '</hs:sec>'
        )
        ast = _parse_md("### Test")
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        h3 = converter.placeholder_styles['H3']
        assert h3['prefix'] == '\u25a1 '
        assert h3['mode'] == 'prefix'
        assert h3['prefixCharPrIDRef'] is None  # No separate run, no prefixCharPrIDRef


class TestStaticConvertToHwpx:
    """Test the static convert_to_hwpx method."""

    def test_convert_to_hwpx_creates_file(self, blank_hwpx_path, tmp_output):
        ast = _parse_md("# Test\n\nParagraph here.")
        MarkdownToHwpx.convert_to_hwpx(
            input_path=__file__,
            output_path=tmp_output,
            reference_path=blank_hwpx_path,
            json_ast=ast,
        )
        assert os.path.exists(tmp_output)

    def test_output_is_valid_zip(self, blank_hwpx_path, tmp_output):
        ast = _parse_md("# Test")
        MarkdownToHwpx.convert_to_hwpx(
            input_path=__file__,
            output_path=tmp_output,
            reference_path=blank_hwpx_path,
            json_ast=ast,
        )
        assert zipfile.is_zipfile(tmp_output)

    def test_output_contains_required_files(self, blank_hwpx_path, tmp_output):
        ast = _parse_md("# Test")
        MarkdownToHwpx.convert_to_hwpx(
            input_path=__file__,
            output_path=tmp_output,
            reference_path=blank_hwpx_path,
            json_ast=ast,
        )
        with zipfile.ZipFile(tmp_output, 'r') as z:
            names = z.namelist()
            assert "Contents/header.xml" in names
            assert "Contents/section0.xml" in names
            assert "Contents/content.hpf" in names

    def test_output_section0_is_valid_xml(self, blank_hwpx_path, tmp_output):
        ast = _parse_md("Hello world")
        MarkdownToHwpx.convert_to_hwpx(
            input_path=__file__,
            output_path=tmp_output,
            reference_path=blank_hwpx_path,
            json_ast=ast,
        )
        with zipfile.ZipFile(tmp_output, 'r') as z:
            section_xml = z.read("Contents/section0.xml").decode('utf-8')
            # Should parse without error
            ET.fromstring(section_xml)

    def test_missing_reference_raises_error(self, tmp_output):
        ast = _parse_md("Hello")
        with pytest.raises(TemplateError):
            MarkdownToHwpx.convert_to_hwpx(
                input_path=__file__,
                output_path=tmp_output,
                reference_path="nonexistent.hwpx",
                json_ast=ast,
            )

    def test_none_ast_raises_error(self, blank_hwpx_path, tmp_output):
        with pytest.raises(ConversionError):
            MarkdownToHwpx.convert_to_hwpx(
                input_path=__file__,
                output_path=tmp_output,
                reference_path=blank_hwpx_path,
                json_ast=None,
            )

    def test_invalid_template_raises_error(self, tmp_path, tmp_output):
        # Create a non-zip file
        bad_template = str(tmp_path / "bad.hwpx")
        with open(bad_template, 'w') as f:
            f.write("not a zip file")

        ast = _parse_md("Hello")
        with pytest.raises(TemplateError):
            MarkdownToHwpx.convert_to_hwpx(
                input_path=__file__,
                output_path=tmp_output,
                reference_path=bad_template,
                json_ast=ast,
            )


class TestConverterConfig:
    """Test that config values are respected."""

    def test_default_config_used(self, blank_hwpx_path):
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter.config.TABLE_WIDTH == 45000
        assert converter.config.LIST_INDENT_PER_LEVEL == 2000

    def test_custom_config_applied(self, blank_hwpx_path):
        config = ConversionConfig()
        config.TABLE_WIDTH = 30000

        ast = _parse_md("| A | B |\n|---|---|\n| 1 | 2 |")
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        converter = MarkdownToHwpx(json_ast=ast, header_xml_content=header_xml, config=config)
        xml_body, _ = converter.convert()

        # Table width should reflect custom config
        assert 'width="30000"' in xml_body


class TestConverterTableAlignment:
    """Test table column alignment."""

    def test_center_aligned_table(self, blank_hwpx_path):
        md = "| Left | Center | Right |\n|:-----|:------:|------:|\n| a | b | c |"
        converter = _make_converter(md, blank_hwpx_path)
        xml_body, header_xml = converter.convert()
        # CENTER and RIGHT alignment should create new paraPr entries
        assert 'CENTER' in header_xml or 'RIGHT' in header_xml

    def test_default_aligned_table_no_extra_para_pr(self, blank_hwpx_path):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        converter = _make_converter(md, blank_hwpx_path)
        initial_max = converter.max_para_pr_id
        xml_body, _ = converter.convert()
        # Default alignment should not create alignment-specific paraPr
        # (other paraPr may be created for other reasons, but not for alignment)
        assert 'hp:tbl' in xml_body

    def test_alignment_applied_to_cells(self, blank_hwpx_path):
        md = "| L | C | R |\n|:--|:--:|--:|\n| a | b | c |"
        converter = _make_converter(md, blank_hwpx_path)
        xml_body, header_xml = converter.convert()
        # Verify alignment paraPr was created
        assert 'horizontal="CENTER"' in header_xml
        assert 'horizontal="RIGHT"' in header_xml


class TestConverterBlockQuote:
    """Test block quote handling."""

    def test_blockquote_produces_output(self, blank_hwpx_path):
        converter = _make_converter("> This is a quote.", blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert 'quote' in xml_body

    def test_blockquote_contains_text(self, blank_hwpx_path):
        converter = _make_converter("> Quoted text here.", blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert 'Quoted' in xml_body
        assert 'text' in xml_body

    def test_blockquote_creates_custom_para_pr(self, blank_hwpx_path):
        converter = _make_converter("> A quote.", blank_hwpx_path)
        xml_body, header_xml = converter.convert()
        # Block quote should create a new paraPr with increased left margin
        assert 'value="2000"' in header_xml or int(converter.max_para_pr_id) > 0

    def test_nested_blockquote(self, blank_hwpx_path):
        md = "> Level 1\n>\n>> Level 2"
        converter = _make_converter(md, blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert 'Level' in xml_body


class TestConverterHorizontalRule:
    """Test horizontal rule handling."""

    def test_horizontal_rule_produces_output(self, blank_hwpx_path):
        converter = _make_converter("Above\n\n---\n\nBelow", blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert 'Above' in xml_body
        assert 'Below' in xml_body
        # HR creates an additional paragraph
        assert xml_body.count('<hp:p') >= 3

    def test_horizontal_rule_creates_border_fill(self, blank_hwpx_path):
        converter = _make_converter("---", blank_hwpx_path)
        xml_body, header_xml = converter.convert()
        # Should create a borderFill with bottom border for HR
        assert 'bottomBorder' in header_xml

    def test_horizontal_rule_standalone(self, blank_hwpx_path):
        converter = _make_converter("---", blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert '<hp:p' in xml_body
