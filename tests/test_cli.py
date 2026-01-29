"""Integration tests for md2hwpx CLI."""

import os
import sys
import zipfile
import xml.etree.ElementTree as ET
import subprocess
import pytest

from md2hwpx.MarkdownToHwpx import MarkdownToHwpx
from md2hwpx.marko_adapter import MarkoToPandocAdapter
from md2hwpx.exceptions import TemplateError, ConversionError


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')
PKG_DIR = os.path.join(os.path.dirname(__file__), '..', 'md2hwpx')
BLANK_HWPX = os.path.join(PKG_DIR, 'blank.hwpx')


def run_cli(*args):
    """Run md2hwpx CLI as subprocess and return result."""
    cmd = [sys.executable, '-m', 'md2hwpx'] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), '..'),
    )
    return result


class TestCLIBasic:
    """Test basic CLI invocation."""

    def test_help_flag(self):
        result = run_cli('--help')
        assert result.returncode == 0
        assert 'md2hwpx' in result.stdout.lower() or 'markdown' in result.stdout.lower()

    def test_version_flag(self):
        result = run_cli('--version')
        assert result.returncode == 0

    def test_no_args_shows_error(self):
        result = run_cli()
        assert result.returncode != 0

    def test_missing_input_file(self, tmp_path):
        output = str(tmp_path / "out.hwpx")
        result = run_cli('nonexistent.md', '-o', output)
        assert result.returncode != 0
        assert 'not found' in result.stderr.lower() or 'error' in result.stderr.lower()

    def test_missing_output_flag(self):
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        result = run_cli(fixture)
        assert result.returncode != 0

    def test_unsupported_input_format(self, tmp_path):
        # Create a .txt file
        txt_file = str(tmp_path / "test.txt")
        with open(txt_file, 'w') as f:
            f.write("hello")
        output = str(tmp_path / "out.hwpx")
        result = run_cli(txt_file, '-o', output)
        assert result.returncode != 0
        assert 'error' in result.stderr.lower()


class TestCLIHwpxOutput:
    """Test HWPX output generation via CLI."""

    def test_simple_conversion(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        output = str(tmp_path / "output.hwpx")
        result = run_cli(fixture, '-o', output)
        assert result.returncode == 0
        assert os.path.exists(output)
        assert zipfile.is_zipfile(output)

    def test_output_contains_required_files(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        output = str(tmp_path / "output.hwpx")
        run_cli(fixture, '-o', output)
        with zipfile.ZipFile(output, 'r') as z:
            names = z.namelist()
            assert 'Contents/header.xml' in names
            assert 'Contents/section0.xml' in names
            assert 'Contents/content.hpf' in names

    def test_output_section0_valid_xml(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        output = str(tmp_path / "output.hwpx")
        run_cli(fixture, '-o', output)
        with zipfile.ZipFile(output, 'r') as z:
            xml_content = z.read('Contents/section0.xml').decode('utf-8')
            # Should parse without error
            ET.fromstring(xml_content)

    def test_output_header_valid_xml(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        output = str(tmp_path / "output.hwpx")
        run_cli(fixture, '-o', output)
        with zipfile.ZipFile(output, 'r') as z:
            xml_content = z.read('Contents/header.xml').decode('utf-8')
            ET.fromstring(xml_content)

    def test_headers_conversion(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'headers.md')
        output = str(tmp_path / "output.hwpx")
        result = run_cli(fixture, '-o', output)
        assert result.returncode == 0
        with zipfile.ZipFile(output, 'r') as z:
            section = z.read('Contents/section0.xml').decode('utf-8')
            assert 'Header' in section or 'hp:p' in section

    def test_tables_conversion(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'tables.md')
        output = str(tmp_path / "output.hwpx")
        result = run_cli(fixture, '-o', output)
        assert result.returncode == 0
        with zipfile.ZipFile(output, 'r') as z:
            section = z.read('Contents/section0.xml').decode('utf-8')
            assert 'hp:tbl' in section
            assert 'hp:tc' in section

    def test_lists_conversion(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'lists.md')
        output = str(tmp_path / "output.hwpx")
        result = run_cli(fixture, '-o', output)
        assert result.returncode == 0
        assert os.path.exists(output)

    def test_formatting_conversion(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'formatting.md')
        output = str(tmp_path / "output.hwpx")
        result = run_cli(fixture, '-o', output)
        assert result.returncode == 0
        with zipfile.ZipFile(output, 'r') as z:
            section = z.read('Contents/section0.xml').decode('utf-8')
            header = z.read('Contents/header.xml').decode('utf-8')
            # Bold should create charPr with bold element
            assert 'hh:bold' in header

    def test_empty_file_conversion(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'empty.md')
        output = str(tmp_path / "output.hwpx")
        result = run_cli(fixture, '-o', output)
        assert result.returncode == 0
        assert os.path.exists(output)


class TestCLIJsonOutput:
    """Test JSON debug output."""

    def test_json_output(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        output = str(tmp_path / "output.json")
        result = run_cli(fixture, '-o', output)
        assert result.returncode == 0
        assert os.path.exists(output)

        import json
        with open(output, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert 'blocks' in data
        assert 'meta' in data

    def test_json_output_has_blocks(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        output = str(tmp_path / "output.json")
        run_cli(fixture, '-o', output)

        import json
        with open(output, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert len(data['blocks']) > 0


class TestCLIReferenceDoc:
    """Test --reference-doc flag."""

    def test_custom_reference_doc(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        output = str(tmp_path / "output.hwpx")
        result = run_cli(fixture, f'--reference-doc={BLANK_HWPX}', '-o', output)
        assert result.returncode == 0
        assert os.path.exists(output)

    def test_nonexistent_reference_doc(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        output = str(tmp_path / "output.hwpx")
        result = run_cli(fixture, '--reference-doc=nonexistent.hwpx', '-o', output)
        assert result.returncode != 0

    def test_invalid_reference_doc(self, tmp_path):
        # Create a non-zip file as reference
        bad_ref = str(tmp_path / "bad.hwpx")
        with open(bad_ref, 'w') as f:
            f.write("not a zip file")
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        output = str(tmp_path / "output.hwpx")
        result = run_cli(fixture, f'--reference-doc={bad_ref}', '-o', output)
        assert result.returncode != 0


class TestCLIUnsupportedOutput:
    """Test unsupported output formats."""

    def test_unsupported_output_format(self, tmp_path):
        fixture = os.path.join(FIXTURES_DIR, 'simple.md')
        output = str(tmp_path / "output.docx")
        result = run_cli(fixture, '-o', output)
        assert result.returncode != 0
        assert 'unsupported' in result.stderr.lower() or 'error' in result.stderr.lower()


class TestEndToEnd:
    """End-to-end tests using the Python API directly."""

    def test_full_pipeline_simple(self, tmp_path):
        """Test the full conversion pipeline with simple markdown."""
        md_text = "# Hello World\n\nThis is a test paragraph."
        md_file = str(tmp_path / "input.md")
        output = str(tmp_path / "output.hwpx")

        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_text)

        adapter = MarkoToPandocAdapter()
        ast = adapter.parse(md_text)

        MarkdownToHwpx.convert_to_hwpx(
            input_path=md_file,
            output_path=output,
            reference_path=BLANK_HWPX,
            json_ast=ast,
        )

        assert os.path.exists(output)
        assert zipfile.is_zipfile(output)

        with zipfile.ZipFile(output, 'r') as z:
            section = z.read('Contents/section0.xml').decode('utf-8')
            # Words are split into separate <hp:t> elements
            assert 'Hello' in section
            assert 'World' in section
            assert 'test' in section
            assert 'paragraph' in section

    def test_full_pipeline_table(self, tmp_path):
        """Test conversion with tables."""
        md_text = "| Name | Value |\n|------|-------|\n| A | 1 |\n| B | 2 |"
        md_file = str(tmp_path / "input.md")
        output = str(tmp_path / "output.hwpx")

        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_text)

        adapter = MarkoToPandocAdapter()
        ast = adapter.parse(md_text)

        MarkdownToHwpx.convert_to_hwpx(
            input_path=md_file,
            output_path=output,
            reference_path=BLANK_HWPX,
            json_ast=ast,
        )

        with zipfile.ZipFile(output, 'r') as z:
            section = z.read('Contents/section0.xml').decode('utf-8')
            assert 'hp:tbl' in section
            assert 'Name' in section
            assert 'Value' in section

    def test_full_pipeline_unicode(self, tmp_path):
        """Test conversion with Korean text."""
        md_text = "# 한글 제목\n\n한글 본문 테스트입니다."
        md_file = str(tmp_path / "input.md")
        output = str(tmp_path / "output.hwpx")

        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_text)

        adapter = MarkoToPandocAdapter()
        ast = adapter.parse(md_text)

        MarkdownToHwpx.convert_to_hwpx(
            input_path=md_file,
            output_path=output,
            reference_path=BLANK_HWPX,
            json_ast=ast,
        )

        with zipfile.ZipFile(output, 'r') as z:
            section = z.read('Contents/section0.xml').decode('utf-8')
            assert '한글' in section

    def test_full_pipeline_code_block(self, tmp_path):
        """Test conversion with code blocks."""
        md_text = "```python\nprint('hello')\n```"
        md_file = str(tmp_path / "input.md")
        output = str(tmp_path / "output.hwpx")

        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_text)

        adapter = MarkoToPandocAdapter()
        ast = adapter.parse(md_text)

        MarkdownToHwpx.convert_to_hwpx(
            input_path=md_file,
            output_path=output,
            reference_path=BLANK_HWPX,
            json_ast=ast,
        )

        with zipfile.ZipFile(output, 'r') as z:
            section = z.read('Contents/section0.xml').decode('utf-8')
            assert 'hello' in section

    def test_full_pipeline_link(self, tmp_path):
        """Test conversion with links."""
        md_text = "[Click here](https://example.com)"
        md_file = str(tmp_path / "input.md")
        output = str(tmp_path / "output.hwpx")

        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_text)

        adapter = MarkoToPandocAdapter()
        ast = adapter.parse(md_text)

        MarkdownToHwpx.convert_to_hwpx(
            input_path=md_file,
            output_path=output,
            reference_path=BLANK_HWPX,
            json_ast=ast,
        )

        with zipfile.ZipFile(output, 'r') as z:
            section = z.read('Contents/section0.xml').decode('utf-8')
            # Words are split into separate <hp:t> elements
            assert 'Click' in section
            assert 'here' in section
            assert 'HYPERLINK' in section

    def test_full_pipeline_mixed_content(self, tmp_path):
        """Test conversion with various markdown elements combined."""
        md_text = """# Document Title

This is a paragraph with **bold** and *italic* text.

## Section 1

| Col A | Col B |
|-------|-------|
| 1     | 2     |

- Bullet one
- Bullet two

1. Ordered one
2. Ordered two

```
code block
```

[Link](https://example.com)
"""
        md_file = str(tmp_path / "input.md")
        output = str(tmp_path / "output.hwpx")

        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_text)

        adapter = MarkoToPandocAdapter()
        ast = adapter.parse(md_text)

        MarkdownToHwpx.convert_to_hwpx(
            input_path=md_file,
            output_path=output,
            reference_path=BLANK_HWPX,
            json_ast=ast,
        )

        assert os.path.exists(output)
        with zipfile.ZipFile(output, 'r') as z:
            section = z.read('Contents/section0.xml').decode('utf-8')
            header = z.read('Contents/header.xml').decode('utf-8')

            # Verify various elements exist (words split into separate <hp:t> elements)
            assert 'Document' in section
            assert 'Title' in section
            assert 'bold' in section
            assert 'italic' in section
            assert 'hp:tbl' in section
            assert 'Bullet' in section or 'bullet' in section.lower()
            assert 'Ordered' in section or 'ordered' in section.lower()
            assert 'code block' in section or ('code' in section and 'block' in section)
            assert 'HYPERLINK' in section
            # Bold should have added charPr
            assert 'hh:bold' in header

            # Verify XML validity
            ET.fromstring(section)
            ET.fromstring(header)
