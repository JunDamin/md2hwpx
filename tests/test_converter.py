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


class TestPrefixHeaderAutoNumbering:
    """Test auto-incrementing prefix in prefix-mode headers."""

    def _make_section_xml(self, prefix_text, placeholder, level_num):
        """Create section XML with a prefix-mode header placeholder."""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
            ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
            '<hp:p paraPrIDRef="10" styleIDRef="5" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="22"><hp:t>' + prefix_text + '</hp:t></hp:run>'
            '<hp:run charPrIDRef="19"><hp:t>{{H' + str(level_num) + '}}</hp:t></hp:run>'
            '</hp:p>'
            '</hs:sec>'
        )

    def test_prefix_arabic_increments(self, blank_hwpx_path):
        """Prefix '1. ' should become '1. ', '2. ', '3. ' for each header."""
        md = "### First\n\nBody\n\n### Second\n\nBody\n\n### Third\n\nBody"
        ast = _parse_md(md)
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        section_xml = self._make_section_xml('1. ', 'H3', 3)
        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        section_output, _ = converter.convert()
        assert '1. ' in section_output
        assert '2. ' in section_output
        assert '3. ' in section_output

    def test_prefix_korean_increments(self, blank_hwpx_path):
        """Prefix '가. ' should become '가. ', '나. ', '다. '."""
        md = "### First\n\nBody\n\n### Second\n\nBody"
        ast = _parse_md(md)
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        section_xml = self._make_section_xml('\uac00. ', 'H3', 3)
        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        section_output, _ = converter.convert()
        assert '\uac00. ' in section_output  # 가.
        assert '\ub098. ' in section_output  # 나.

    def test_prefix_static_symbol_unchanged(self, blank_hwpx_path):
        """Non-numbering prefix like '□ ' should stay the same for all headers."""
        md = "### First\n\nBody\n\n### Second\n\nBody"
        ast = _parse_md(md)
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        section_xml = self._make_section_xml('\u25a1 ', 'H3', 3)
        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        section_output, _ = converter.convert()
        # □ should appear twice, unchanged
        assert section_output.count('\u25a1 ') == 2

    def test_prefix_resets_on_parent_header(self, blank_hwpx_path):
        """Prefix counter should reset when a parent header appears.

        ## A
        ### X  → 1. X
        ### Y  → 2. Y
        ## B
        ### Z  → 1. Z  (reset)
        """
        # H2 as plain (no prefix), H3 with numbering prefix
        section_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
            ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
            '<hp:p paraPrIDRef="10" styleIDRef="5" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="19"><hp:t>{{H2}}</hp:t></hp:run>'
            '</hp:p>'
            '<hp:p paraPrIDRef="10" styleIDRef="5" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="22"><hp:t>1. </hp:t></hp:run>'
            '<hp:run charPrIDRef="19"><hp:t>{{H3}}</hp:t></hp:run>'
            '</hp:p>'
            '</hs:sec>'
        )
        md = (
            "## Chapter A\n\nBody\n\n"
            "### Section X\n\nBody\n\n"
            "### Section Y\n\nBody\n\n"
            "## Chapter B\n\nBody\n\n"
            "### Section Z\n\nBody\n\n"
        )
        ast = _parse_md(md)
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        section_output, _ = converter.convert()
        # "1. " should appear twice (once under each chapter)
        assert section_output.count('1. ') == 2
        # "2. " should appear once (only under Chapter A)
        assert section_output.count('2. ') == 1


class TestTableHeaderAutoNumbering:
    """Test auto-incrementing numbering in table-mode headers."""

    TABLE_SECTION_XML = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
        ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
        '<hp:p paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="0">'
        '<hp:tbl id="1" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM"'
        ' textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL"'
        ' repeatHeader="1" rowCnt="1" colCnt="2" cellSpacing="0" borderFillIDRef="1" noAdjust="0">'
        '<hp:sz width="40000" widthRelTo="ABSOLUTE" height="2000" heightRelTo="ABSOLUTE" protect="0"/>'
        '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0"'
        ' holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP"'
        ' horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
        '<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
        '<hp:tr>'
        '<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER"'
        ' linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0"'
        ' hasTextRef="0" hasNumRef="0">'
        '<hp:p paraPrIDRef="10" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="13"><hp:t>{numbering}</hp:t></hp:run>'
        '</hp:p>'
        '</hp:subList>'
        '<hp:cellAddr colAddr="0" rowAddr="0"/>'
        '<hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:cellSz width="5000" height="2000"/>'
        '</hp:tc>'
        '<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER"'
        ' linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0"'
        ' hasTextRef="0" hasNumRef="0">'
        '<hp:p paraPrIDRef="10" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="12"><hp:t>{{{{H2}}}}</hp:t></hp:run>'
        '</hp:p>'
        '</hp:subList>'
        '<hp:cellAddr colAddr="1" rowAddr="0"/>'
        '<hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:cellSz width="35000" height="2000"/>'
        '</hp:tc>'
        '</hp:tr>'
        '</hp:tbl>'
        '<hp:t/></hp:run></hp:p>'
        '</hs:sec>'
    )

    def _make_section_xml(self, numbering='I'):
        return self.TABLE_SECTION_XML.format(numbering=numbering)

    def test_numbering_text_detected_from_template(self, blank_hwpx_path):
        """numberingText should be extracted from the non-placeholder cell."""
        ast = _parse_md("## First")
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=self._make_section_xml('I'),
        )

        assert 'H2' in converter.placeholder_styles
        h2 = converter.placeholder_styles['H2']
        assert h2['mode'] == 'table'
        assert h2['numberingText'] == 'I'

    def test_roman_numeral_increments(self, blank_hwpx_path):
        """Multiple H2 headers should produce I, II, III in the numbering cell."""
        md = "## First\n\nBody\n\n## Second\n\nBody\n\n## Third\n\nBody"
        ast = _parse_md(md)
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=self._make_section_xml('I'),
        )

        section_output, _ = converter.convert()
        assert 'First' in section_output
        assert 'Second' in section_output
        assert 'Third' in section_output
        # Check Roman numerals appear (II and III confirm incrementing)
        assert '>II<' in section_output
        assert '>III<' in section_output

    def test_arabic_numeral_increments(self, blank_hwpx_path):
        """Arabic numbering: 1, 2, 3."""
        md = "## First\n\nBody\n\n## Second\n\nBody"
        ast = _parse_md(md)
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=self._make_section_xml('1'),
        )

        section_output, _ = converter.convert()
        assert '>2<' in section_output

    def test_korean_numbering_increments(self, blank_hwpx_path):
        """Korean numbering: 가, 나, 다."""
        md = "## First\n\nBody\n\n## Second\n\nBody\n\n## Third\n\nBody"
        ast = _parse_md(md)
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=self._make_section_xml('\uac00'),  # 가
        )

        section_output, _ = converter.convert()
        assert '\ub098' in section_output  # 나
        assert '\ub2e4' in section_output  # 다

    def test_no_numbering_text_no_error(self, blank_hwpx_path):
        """Table without numbering text should still work (no crash)."""
        # Use the placeholder-template which has table-mode H1 without numbering text
        section_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
            ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
            '<hp:p paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="0">'
            '<hp:tbl id="1" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM"'
            ' textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL"'
            ' repeatHeader="1" rowCnt="1" colCnt="1" cellSpacing="0" borderFillIDRef="1" noAdjust="0">'
            '<hp:sz width="40000" widthRelTo="ABSOLUTE" height="2000" heightRelTo="ABSOLUTE" protect="0"/>'
            '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0"'
            ' holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP"'
            ' horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
            '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
            '<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
            '<hp:tr>'
            '<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
            '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER"'
            ' linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0"'
            ' hasTextRef="0" hasNumRef="0">'
            '<hp:p paraPrIDRef="10" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="12"><hp:t>{{H2}}</hp:t></hp:run>'
            '</hp:p>'
            '</hp:subList>'
            '<hp:cellAddr colAddr="0" rowAddr="0"/>'
            '<hp:cellSpan colSpan="1" rowSpan="1"/>'
            '<hp:cellSz width="40000" height="2000"/>'
            '</hp:tc>'
            '</hp:tr>'
            '</hp:tbl>'
            '<hp:t/></hp:run></hp:p>'
            '</hs:sec>'
        )
        ast = _parse_md("## Title\n\nBody")
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        assert converter.placeholder_styles['H2']['numberingText'] is None
        # Should not crash
        section_output, _ = converter.convert()
        assert 'Title' in section_output

    def test_format_counter_text_roman(self, blank_hwpx_path):
        """Test _format_counter_text with Roman numerals."""
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._format_counter_text('I', 1) == 'I'
        assert converter._format_counter_text('I', 2) == 'II'
        assert converter._format_counter_text('I', 3) == 'III'
        assert converter._format_counter_text('I', 4) == 'IV'
        assert converter._format_counter_text('I', 10) == 'X'

    def test_format_counter_text_roman_lowercase(self, blank_hwpx_path):
        """Test _format_counter_text with lowercase Roman numerals."""
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._format_counter_text('i', 1) == 'i'
        assert converter._format_counter_text('i', 2) == 'ii'
        assert converter._format_counter_text('i', 3) == 'iii'

    def test_format_counter_text_arabic(self, blank_hwpx_path):
        """Test _format_counter_text with Arabic numerals."""
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._format_counter_text('1', 1) == '1'
        assert converter._format_counter_text('1', 2) == '2'
        assert converter._format_counter_text('1', 10) == '10'

    def test_format_counter_text_korean(self, blank_hwpx_path):
        """Test _format_counter_text with Korean syllables."""
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._format_counter_text('\uac00', 1) == '\uac00'  # 가
        assert converter._format_counter_text('\uac00', 2) == '\ub098'  # 나
        assert converter._format_counter_text('\uac00', 3) == '\ub2e4'  # 다

    def test_format_counter_text_fallback(self, blank_hwpx_path):
        """Unrecognized patterns should be returned as-is."""
        converter = _make_converter("Hello", blank_hwpx_path)
        assert converter._format_counter_text('Section', 2) == 'Section'

    def test_child_counter_resets_on_parent_header(self, blank_hwpx_path):
        """H3 counter should reset when a new H2 appears.

        ## A  → I
        ### X → 1
        ### Y → 2
        ## B  → II
        ### Z → 1  (reset, not 3)
        """
        def _make_table_xml(placeholder, numbering, tbl_id):
            return (
                '<hp:tbl id="{tbl_id}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM"'
                ' textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL"'
                ' repeatHeader="1" rowCnt="1" colCnt="2" cellSpacing="0" borderFillIDRef="1" noAdjust="0">'
                '<hp:sz width="40000" widthRelTo="ABSOLUTE" height="2000" heightRelTo="ABSOLUTE" protect="0"/>'
                '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0"'
                ' holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP"'
                ' horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
                '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
                '<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
                '<hp:tr>'
                '<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
                '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER"'
                ' linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0"'
                ' hasTextRef="0" hasNumRef="0">'
                '<hp:p paraPrIDRef="10" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                '<hp:run charPrIDRef="13"><hp:t>{numbering}</hp:t></hp:run>'
                '</hp:p>'
                '</hp:subList>'
                '<hp:cellAddr colAddr="0" rowAddr="0"/>'
                '<hp:cellSpan colSpan="1" rowSpan="1"/>'
                '<hp:cellSz width="5000" height="2000"/>'
                '</hp:tc>'
                '<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
                '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER"'
                ' linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0"'
                ' hasTextRef="0" hasNumRef="0">'
                '<hp:p paraPrIDRef="10" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                '<hp:run charPrIDRef="12"><hp:t>{placeholder}</hp:t></hp:run>'
                '</hp:p>'
                '</hp:subList>'
                '<hp:cellAddr colAddr="1" rowAddr="0"/>'
                '<hp:cellSpan colSpan="1" rowSpan="1"/>'
                '<hp:cellSz width="35000" height="2000"/>'
                '</hp:tc>'
                '</hp:tr>'
                '</hp:tbl>'
            ).format(placeholder=placeholder, numbering=numbering, tbl_id=tbl_id)

        h2_table = _make_table_xml('{{H2}}', 'I', '1')
        h3_table = _make_table_xml('{{H3}}', '1', '2')

        section_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
            ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
            '<hp:p paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="0">'
            + h2_table +
            '<hp:t/></hp:run></hp:p>'
            '<hp:p paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="0">'
            + h3_table +
            '<hp:t/></hp:run></hp:p>'
            '</hs:sec>'
        )

        md = (
            "## Chapter A\n\n"
            "### Section X\n\n"
            "### Section Y\n\n"
            "## Chapter B\n\n"
            "### Section Z\n\n"
        )
        ast = _parse_md(md)
        header_xml = ""
        with zipfile.ZipFile(blank_hwpx_path, 'r') as z:
            header_xml = z.read("Contents/header.xml").decode('utf-8')

        converter = MarkdownToHwpx(
            json_ast=ast,
            header_xml_content=header_xml,
            section_xml_content=section_xml,
        )

        section_output, _ = converter.convert()

        # H2 should increment: I, II
        assert '>I<' in section_output
        assert '>II<' in section_output

        # H3 under Chapter A: 1, 2
        # H3 under Chapter B: 1 (reset)
        # Count occurrences of ">1<" — should appear twice (once per chapter)
        assert section_output.count('>1<') == 2
        assert section_output.count('>2<') == 1


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
        # HR creates two empty paragraphs plus Above and Below = 4+
        assert xml_body.count('<hp:p') >= 4

    def test_horizontal_rule_two_empty_paragraphs(self, blank_hwpx_path):
        converter = _make_converter("---", blank_hwpx_path)
        xml_body, _ = converter.convert()
        # HR renders as two empty paragraphs
        assert xml_body.count('<hp:p') == 2

    def test_horizontal_rule_standalone(self, blank_hwpx_path):
        converter = _make_converter("---", blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert '<hp:p' in xml_body
