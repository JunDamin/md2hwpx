"""
Custom exception classes for md2hwpx converter.
"""


class HwpxError(Exception):
    """Base exception for all md2hwpx errors."""
    pass


class TemplateError(HwpxError):
    """Error related to reference template files."""
    pass


class ImageError(HwpxError):
    """Error related to image processing or embedding."""
    pass


class StyleError(HwpxError):
    """Error related to style parsing or application."""
    pass


class ConversionError(HwpxError):
    """Error during markdown-to-HWPX conversion."""
    pass


class SecurityError(HwpxError):
    """Error related to security validation (path traversal, size limits, etc.)."""
    pass
