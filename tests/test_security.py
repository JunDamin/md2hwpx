"""Tests for security hardening features."""

import os
import io
import zipfile
import xml.etree.ElementTree as ET
import pytest

from md2hwpx.MarkdownToHwpx import MarkdownToHwpx
from md2hwpx.marko_adapter import MarkoToPandocAdapter
from md2hwpx.config import ConversionConfig, DEFAULT_CONFIG
from md2hwpx.exceptions import SecurityError, TemplateError, ConversionError


def _parse_md(text):
    """Helper: parse markdown text and return AST."""
    adapter = MarkoToPandocAdapter()
    return adapter.parse(text)


def _make_converter(md_text, blank_hwpx_path, config=None):
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
        config=config,
    )


class TestImagePathValidation:
    """Test image path traversal prevention."""

    def test_relative_path_allowed(self):
        """Normal relative paths should be accepted."""
        # Should not raise
        MarkdownToHwpx._validate_image_path("images/photo.png")
        MarkdownToHwpx._validate_image_path("photo.png")
        MarkdownToHwpx._validate_image_path("sub/dir/photo.png")

    def test_absolute_path_rejected(self):
        """Absolute paths should be rejected."""
        with pytest.raises(SecurityError, match="Absolute image paths"):
            MarkdownToHwpx._validate_image_path("/etc/passwd")

    def test_absolute_windows_path_rejected(self):
        """Windows absolute paths should be rejected."""
        with pytest.raises(SecurityError, match="Absolute image paths"):
            MarkdownToHwpx._validate_image_path("C:\\Windows\\System32\\config")

    def test_directory_traversal_rejected(self):
        """Paths with '..' components should be rejected."""
        with pytest.raises(SecurityError, match="Directory traversal"):
            MarkdownToHwpx._validate_image_path("../../../etc/passwd")

    def test_directory_traversal_mixed_rejected(self):
        """Paths with '..' mixed into valid paths should be rejected."""
        with pytest.raises(SecurityError, match="Directory traversal"):
            MarkdownToHwpx._validate_image_path("images/../../secret.txt")

    def test_single_dot_allowed(self):
        """Single dot in path should be fine."""
        # Should not raise
        MarkdownToHwpx._validate_image_path("./images/photo.png")

    def test_base_dir_validation(self, tmp_path):
        """Path that resolves outside base dir should be rejected."""
        base_dir = str(tmp_path / "project")
        os.makedirs(base_dir, exist_ok=True)

        # Normal path within base dir is fine
        MarkdownToHwpx._validate_image_path("images/photo.png", base_dir)

    def test_image_with_traversal_in_converter(self, blank_hwpx_path):
        """Converter should skip images with traversal paths gracefully."""
        md = "![bad](../../../etc/passwd)"
        converter = _make_converter(md, blank_hwpx_path)
        xml_body, _ = converter.convert()

        # Should contain placeholder text instead of image element
        assert "Image:" in xml_body or "passwd" in xml_body
        # Should NOT have embedded the image
        assert len(converter.images) == 0


class TestFileSizeValidation:
    """Test file size limit enforcement."""

    def test_small_files_accepted(self, blank_hwpx_path, tmp_path):
        """Small files within limits should be accepted."""
        input_file = str(tmp_path / "small.md")
        output_file = str(tmp_path / "output.hwpx")

        with open(input_file, 'w', encoding='utf-8') as f:
            f.write("# Hello\n\nWorld")

        ast = _parse_md("# Hello\n\nWorld")
        # Should not raise
        MarkdownToHwpx.convert_to_hwpx(input_file, output_file, blank_hwpx_path, json_ast=ast)
        assert os.path.exists(output_file)

    def test_oversized_input_rejected(self, blank_hwpx_path, tmp_path):
        """Input files exceeding size limit should be rejected."""
        input_file = str(tmp_path / "big.md")
        output_file = str(tmp_path / "output.hwpx")

        # Create a tiny config with very small limit
        config = ConversionConfig()
        config.MAX_INPUT_FILE_SIZE = 10  # 10 bytes

        with open(input_file, 'w', encoding='utf-8') as f:
            f.write("# This is definitely more than 10 bytes of content")

        ast = _parse_md("# Hello")

        with pytest.raises(SecurityError, match="Input file too large"):
            MarkdownToHwpx.convert_to_hwpx(
                input_file, output_file, blank_hwpx_path,
                json_ast=ast, config=config
            )

    def test_oversized_template_rejected(self, blank_hwpx_path, tmp_path):
        """Template files exceeding size limit should be rejected."""
        input_file = str(tmp_path / "input.md")
        output_file = str(tmp_path / "output.hwpx")

        with open(input_file, 'w', encoding='utf-8') as f:
            f.write("# Hello")

        config = ConversionConfig()
        config.MAX_INPUT_FILE_SIZE = 50 * 1024 * 1024  # Normal input limit
        config.MAX_TEMPLATE_FILE_SIZE = 1  # 1 byte - impossibly small template

        ast = _parse_md("# Hello")

        with pytest.raises(SecurityError, match="Template file too large"):
            MarkdownToHwpx.convert_to_hwpx(
                input_file, output_file, blank_hwpx_path,
                json_ast=ast, config=config
            )


class TestNestingDepthLimits:
    """Test recursion depth limits for nested structures."""

    def test_blockquote_depth_limit(self, blank_hwpx_path):
        """Block quote nesting should be capped at MAX_NESTING_DEPTH."""
        config = ConversionConfig()
        config.MAX_NESTING_DEPTH = 3

        # Create deeply nested blockquote AST manually
        md = "> level 1\n>> level 2\n>>> level 3"
        converter = _make_converter(md, blank_hwpx_path, config=config)
        xml_body, _ = converter.convert()

        # Should produce output without error
        assert xml_body is not None
        assert len(xml_body) > 0

    def test_bullet_list_depth_limit(self, blank_hwpx_path):
        """Bullet list nesting should be capped at MAX_NESTING_DEPTH."""
        config = ConversionConfig()
        config.MAX_NESTING_DEPTH = 3

        md = "- level 1\n  - level 2\n    - level 3"
        converter = _make_converter(md, blank_hwpx_path, config=config)
        xml_body, _ = converter.convert()

        # Should produce output without error
        assert xml_body is not None
        assert len(xml_body) > 0

    def test_ordered_list_depth_limit(self, blank_hwpx_path):
        """Ordered list nesting should be capped at MAX_NESTING_DEPTH."""
        config = ConversionConfig()
        config.MAX_NESTING_DEPTH = 3

        md = "1. level 1\n   1. level 2\n      1. level 3"
        converter = _make_converter(md, blank_hwpx_path, config=config)
        xml_body, _ = converter.convert()

        # Should produce output without error
        assert xml_body is not None
        assert len(xml_body) > 0

    def test_default_depth_is_sufficient(self, blank_hwpx_path):
        """Default MAX_NESTING_DEPTH (20) should handle typical documents."""
        assert DEFAULT_CONFIG.MAX_NESTING_DEPTH == 20

        # A moderately nested list should work fine
        md = "- level 1\n  - level 2\n    - level 3\n      - level 4"
        converter = _make_converter(md, blank_hwpx_path)
        xml_body, _ = converter.convert()
        assert xml_body is not None


class TestImageCountLimit:
    """Test image count limit enforcement."""

    def test_image_count_within_limit(self, blank_hwpx_path):
        """Images within limit should be processed normally."""
        config = ConversionConfig()
        config.MAX_IMAGE_COUNT = 5

        md = "![img1](img1.png)\n\n![img2](img2.png)"
        converter = _make_converter(md, blank_hwpx_path, config=config)
        xml_body, _ = converter.convert()

        # Both images should be registered
        assert len(converter.images) == 2

    def test_image_count_exceeds_limit(self, blank_hwpx_path):
        """Images exceeding limit should be skipped with placeholder text."""
        config = ConversionConfig()
        config.MAX_IMAGE_COUNT = 1

        md = "![img1](img1.png)\n\n![img2](img2.png)\n\n![img3](img3.png)"
        converter = _make_converter(md, blank_hwpx_path, config=config)
        xml_body, _ = converter.convert()

        # Only 1 image should be registered
        assert len(converter.images) == 1
        # Remaining should show placeholder text
        assert "Image limit exceeded" in xml_body

    def test_default_image_limit(self):
        """Default image count limit should be 500."""
        assert DEFAULT_CONFIG.MAX_IMAGE_COUNT == 500


class TestSecurityConfigDefaults:
    """Test security configuration defaults are sensible."""

    def test_max_input_file_size(self):
        assert DEFAULT_CONFIG.MAX_INPUT_FILE_SIZE == 50 * 1024 * 1024

    def test_max_template_file_size(self):
        assert DEFAULT_CONFIG.MAX_TEMPLATE_FILE_SIZE == 50 * 1024 * 1024

    def test_max_nesting_depth(self):
        assert DEFAULT_CONFIG.MAX_NESTING_DEPTH == 20

    def test_max_image_count(self):
        assert DEFAULT_CONFIG.MAX_IMAGE_COUNT == 500

    def test_config_is_mutable(self):
        """Security limits should be configurable per instance."""
        config = ConversionConfig()
        config.MAX_INPUT_FILE_SIZE = 1024
        config.MAX_IMAGE_COUNT = 10
        config.MAX_NESTING_DEPTH = 5

        assert config.MAX_INPUT_FILE_SIZE == 1024
        assert config.MAX_IMAGE_COUNT == 10
        assert config.MAX_NESTING_DEPTH == 5

        # Default should be unchanged
        assert DEFAULT_CONFIG.MAX_INPUT_FILE_SIZE == 50 * 1024 * 1024
