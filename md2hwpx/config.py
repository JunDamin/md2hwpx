"""
Configuration constants for md2hwpx converter.

This module centralizes all magic numbers and default values used throughout
the conversion process. Values can be overridden by:
1. Placeholder styles extracted from reference template
2. CLI arguments (future)
"""


class ConversionConfig:
    """Default configuration values for HWPX conversion."""

    # === Unit Conversion ===
    LUNIT_PER_MM = 283.465  # HWP logical units per millimeter
    LUNIT_PER_PX = (25.4 * 283.465) / 96.0  # Logical units per pixel (96 DPI)

    # === Table Layout ===
    TABLE_WIDTH = 45000  # Default table width in logical units (~159mm)
    TABLE_OUT_MARGIN_BOTTOM = 1417  # Bottom margin after table

    # === Cell Margins (default padding inside cells) ===
    CELL_MARGIN_DEFAULT = {
        'left': 510,
        'right': 510,
        'top': 141,
        'bottom': 141
    }

    # === Table Borders ===
    TABLE_BORDER_TYPE = 'SOLID'
    TABLE_BORDER_WIDTH = '0.12 mm'
    TABLE_BORDER_COLOR = '#000000'

    # === Table Cell Styling ===
    TABLE_CELL_BG_COLOR = 'none'
    TABLE_HEADER_BG_COLOR = 'none'

    # === List Indentation ===
    LIST_INDENT_PER_LEVEL = 2000  # Indentation per nesting level
    LIST_HANGING_INDENT = 2000  # Hanging indent for list items

    # Bullet characters for different levels (Korean style)
    LIST_BULLET_CHARS = ['ㅇ', '-', '∙', '●', '○', '■', '●']

    # === Image Settings ===
    IMAGE_MAX_WIDTH_MM = 150  # Maximum image width in mm
    IMAGE_MAX_WIDTH = int(150 * LUNIT_PER_MM)  # ~42520 logical units
    IMAGE_DEFAULT_WIDTH = 8504  # Default width (~30mm)
    IMAGE_DEFAULT_HEIGHT = 8504  # Default height (~30mm)

    # === Block Quote ===
    BLOCKQUOTE_LEFT_INDENT = 2000  # Left margin indent for block quotes
    BLOCKQUOTE_INDENT_PER_LEVEL = 2000  # Additional indent per nesting level

    # === Page Break ===
    PAGE_BREAK_BEFORE_H1 = True  # Insert page break before H1 when not first block

    # === Header Spacing ===
    BLANK_LINE_BEFORE_HEADER: bool = False          # Insert empty para before headers in middle of doc
    BLANK_LINE_BEFORE_HEADER_LEVELS: tuple = (1, 2, 3)  # Which header levels get blank lines

    # Per-level page break: {level: bool}, None = use PAGE_BREAK_BEFORE_H1 fallback
    PAGE_BREAK_BEFORE_HEADER_LEVELS: dict = None    # e.g. {1: True, 2: True}

    # Per-level blank line count: {level: int 0-2}, None = use BLANK_LINE_BEFORE_HEADER fallback
    BLANK_LINES_BEFORE_HEADER: dict = None          # e.g. {2: 2, 3: 1}

    # Per-level precise space height (mm): {level: float}, None = not set. Overrides BLANK_LINES_BEFORE_HEADER.
    SPACE_BEFORE_HEADER_MM: dict = None             # e.g. {2: 10.0, 3: 5.0}

    # === Table Options ===
    TABLE_REPEAT_HEADER: bool = True                # repeatHeader attribute on tbl element

    # === Link Styling ===
    LINK_COLOR = '#0000FF'  # Blue
    LINK_UNDERLINE = True

    # === Character/Paragraph Property IDs ===
    # These are typically extracted from template, but defaults are provided
    DEFAULT_CHAR_PR_ID = 0
    DEFAULT_PARA_PR_ID = 0
    DEFAULT_STYLE_ID = 0

    # === Security Limits ===
    MAX_INPUT_FILE_SIZE = 50 * 1024 * 1024  # 50 MB max input file
    MAX_TEMPLATE_FILE_SIZE = 50 * 1024 * 1024  # 50 MB max template file
    MAX_NESTING_DEPTH = 20  # Max recursion for nested lists/quotes
    MAX_IMAGE_COUNT = 500  # Max number of images in a single document


    @classmethod
    def from_file(cls, path):
        """Load config from a JSON or YAML file.

        File keys use snake_case matching ConversionConfig attribute names
        (e.g. ``page_break_before_h1`` maps to ``PAGE_BREAK_BEFORE_H1``).
        Unknown keys are silently ignored.

        For dict-valued fields, integer-string keys are automatically converted
        to integers (e.g. JSON ``{"2": 1}`` becomes ``{2: 1}``).

        Args:
            path: Path to a .json or .yaml/.yml file.

        Returns:
            ConversionConfig instance with values loaded from the file.
        """
        import json as _json
        try:
            import yaml as _yaml
            _has_yaml = True
        except ImportError:
            _has_yaml = False

        cfg = cls()
        with open(path, 'r', encoding='utf-8') as f:
            if path.lower().endswith('.json'):
                data = _json.load(f)
            elif _has_yaml:
                data = _yaml.safe_load(f) or {}
            else:
                raise ImportError(
                    "PyYAML is required to load YAML config files. "
                    "Install it with: pip install pyyaml"
                )

        for key, value in data.items():
            attr = key.upper()
            if hasattr(cfg, attr):
                if isinstance(value, dict):
                    value = {int(k) if str(k).isdigit() else k: v
                             for k, v in value.items()}
                setattr(cfg, attr, value)
        return cfg


# Global default config instance
DEFAULT_CONFIG = ConversionConfig()
