"""Shared fixtures for md2hwpx tests."""

import os
import pytest

from md2hwpx.marko_adapter import MarkoToPandocAdapter


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')
PKG_DIR = os.path.join(os.path.dirname(__file__), '..', 'md2hwpx')
BLANK_HWPX = os.path.join(PKG_DIR, 'blank.hwpx')
TEMPLATE_HWPX = os.path.join(os.path.dirname(__file__), '..', 'templates', 'placeholder-template.hwpx')


@pytest.fixture
def adapter():
    """Return a fresh MarkoToPandocAdapter instance."""
    return MarkoToPandocAdapter()


@pytest.fixture
def blank_hwpx_path():
    """Return path to blank.hwpx reference template."""
    return BLANK_HWPX


@pytest.fixture
def template_hwpx_path():
    """Return path to placeholder-template.hwpx."""
    return TEMPLATE_HWPX


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def tmp_output(tmp_path):
    """Return a temporary output path for .hwpx files."""
    return str(tmp_path / "output.hwpx")
