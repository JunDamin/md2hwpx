"""Tests for md2hwpx library API (convert_string)."""

import os
import zipfile
import xml.etree.ElementTree as ET
import pytest

from md2hwpx import convert_string


PKG_DIR = os.path.join(os.path.dirname(__file__), '..', 'md2hwpx')
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates')


class TestConvertString:
    """Tests for convert_string() function."""

    def test_basic_conversion(self, tmp_path):
        output = str(tmp_path / "output.hwpx")
        convert_string("# Hello\n\nWorld", output)
        assert os.path.exists(output)
        assert zipfile.is_zipfile(output)

    def test_output_contains_required_files(self, tmp_path):
        output = str(tmp_path / "output.hwpx")
        convert_string("# Test\n\nParagraph", output)
        with zipfile.ZipFile(output, 'r') as zf:
            names = zf.namelist()
            assert 'Contents/header.xml' in names
            assert 'Contents/section0.xml' in names
            assert 'Contents/content.hpf' in names

    def test_content_in_output(self, tmp_path):
        output = str(tmp_path / "output.hwpx")
        convert_string("# MyHeader\n\nSomeText", output)
        with zipfile.ZipFile(output, 'r') as zf:
            section = zf.read('Contents/section0.xml').decode('utf-8')
            assert 'MyHeader' in section
            assert 'SomeText' in section

    def test_with_frontmatter(self, tmp_path):
        output = str(tmp_path / "output.hwpx")
        md = "---\ntitle: Test Title\n---\n\n# Heading\n\nBody"
        convert_string(md, output)
        assert os.path.exists(output)
        with zipfile.ZipFile(output, 'r') as zf:
            section = zf.read('Contents/section0.xml').decode('utf-8')
            assert 'Heading' in section

    def test_with_custom_reference_doc(self, tmp_path):
        gov_template = os.path.join(TEMPLATES_DIR, 'gov_template.hwpx')
        if not os.path.exists(gov_template):
            pytest.skip("gov_template.hwpx not found")
        output = str(tmp_path / "output.hwpx")
        convert_string("# Header\n\nBody text", output, reference_doc=gov_template)
        assert os.path.exists(output)
        assert zipfile.is_zipfile(output)

    def test_formatting(self, tmp_path):
        output = str(tmp_path / "output.hwpx")
        convert_string("**bold** *italic* ~~strike~~", output)
        with zipfile.ZipFile(output, 'r') as zf:
            section = zf.read('Contents/section0.xml').decode('utf-8')
            assert 'bold' in section
            assert 'italic' in section

    def test_table(self, tmp_path):
        output = str(tmp_path / "output.hwpx")
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        convert_string(md, output)
        with zipfile.ZipFile(output, 'r') as zf:
            section = zf.read('Contents/section0.xml').decode('utf-8')
            assert 'tbl' in section

    def test_unicode_korean(self, tmp_path):
        output = str(tmp_path / "output.hwpx")
        convert_string("# 한글제목\n\n본문내용입니다.", output)
        with zipfile.ZipFile(output, 'r') as zf:
            section = zf.read('Contents/section0.xml').decode('utf-8')
            assert '한글제목' in section
            assert '본문내용입니다.' in section

    def test_empty_string(self, tmp_path):
        output = str(tmp_path / "output.hwpx")
        convert_string("", output)
        assert os.path.exists(output)
        assert zipfile.is_zipfile(output)

    def test_invalid_reference_doc(self, tmp_path):
        output = str(tmp_path / "output.hwpx")
        with pytest.raises(Exception):
            convert_string("# Test", output, reference_doc="/nonexistent/path.hwpx")
