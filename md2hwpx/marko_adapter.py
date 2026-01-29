"""
Marko AST to Pandoc-like dict adapter.

Converts Marko's object-based AST to the dict format expected by MarkdownToHwpx handlers.
"""

import re
from marko import Markdown
from marko.ext.gfm import GFM


class MarkoToPandocAdapter:
    """Converts Marko AST to Pandoc-like dict format."""

    # Regex to match extended headers (7-9 levels)
    # Standard Markdown only supports 1-6, but HWPX supports up to 9
    EXTENDED_HEADER_RE = re.compile(r'^(#{7,9})\s+(.+)$')

    def __init__(self):
        # Initialize Marko with GFM (tables, strikethrough, etc.) and Footnote support
        # Extensions are loaded by name string
        self.md = Markdown(extensions=['gfm', 'footnote'])
        self.footnotes = {}  # Store footnote definitions from document
        self.extended_headers = {}  # Store extended header placeholders

    def _preprocess_extended_headers(self, markdown_text: str) -> str:
        """
        Preprocess markdown to handle header levels 7-9.

        Standard Markdown only supports levels 1-6.
        We convert ####### lines to unique placeholders, then restore
        them as Header blocks after Marko parsing.

        Each placeholder is wrapped with blank lines to ensure it becomes
        its own paragraph block (not merged with adjacent text).
        """
        lines = markdown_text.split('\n')
        processed_lines = []
        placeholder_counter = 0

        for line in lines:
            match = self.EXTENDED_HEADER_RE.match(line)
            if match:
                hashes = match.group(1)
                content = match.group(2)
                level = len(hashes)

                # Use a placeholder that won't trigger markdown formatting
                # (no __, *, or other special chars)
                placeholder = f"EXTHEADER{placeholder_counter}MARKER"
                self.extended_headers[placeholder] = {
                    'level': level,
                    'content': content
                }
                # Add blank lines around placeholder to ensure it's a separate paragraph
                processed_lines.append('')
                processed_lines.append(placeholder)
                processed_lines.append('')
                placeholder_counter += 1
            else:
                processed_lines.append(line)

        return '\n'.join(processed_lines)

    def _create_extended_header_block(self, level: int, content: str) -> dict:
        """Create a Header block for extended levels (7-9)."""
        # Parse the content as inline markdown
        inlines = self._convert_raw_text(content)
        return {
            "t": "Header",
            "c": [level, ["", [], []], inlines]
        }

    def parse(self, markdown_text: str) -> dict:
        """
        Parse markdown and return Pandoc-like AST dict.

        Returns:
            {"pandoc-api-version": [...], "meta": {...}, "blocks": [...]}
        """
        # Reset state for each parse
        self.extended_headers = {}
        self.footnotes = {}

        # Preprocess to handle extended headers (7-9)
        processed_text = self._preprocess_extended_headers(markdown_text)

        doc = self.md.parse(processed_text)

        # Store footnotes from document (if footnote extension is active)
        if hasattr(doc, 'footnotes'):
            self.footnotes = doc.footnotes

        blocks = []
        for child in doc.children:
            block = self._convert_block(child)
            if block:
                # Check if this is an extended header placeholder
                block = self._restore_extended_header(block)
                blocks.append(block)

        return {
            "pandoc-api-version": [1, 23, 1],  # Compatibility marker
            "meta": {},  # Metadata handled separately by python-frontmatter
            "blocks": blocks
        }

    def _restore_extended_header(self, block: dict) -> dict:
        """
        Check if a block is an extended header placeholder and restore it.

        Extended header placeholders become paragraphs with text like
        "__EXTENDED_HEADER_0__", which we convert back to Header blocks.
        """
        if block.get('t') != 'Para':
            return block

        inlines = block.get('c', [])
        if len(inlines) != 1:
            return block

        first = inlines[0]
        if first.get('t') != 'Str':
            return block

        text = first.get('c', '')
        if text in self.extended_headers:
            info = self.extended_headers[text]
            return self._create_extended_header_block(info['level'], info['content'])

        return block

    def _convert_block(self, element) -> dict | None:
        """Convert a Marko block element to Pandoc dict format."""
        elem_type = type(element).__name__

        if elem_type == 'Heading':
            return self._convert_heading(element)
        elif elem_type == 'Paragraph':
            return self._convert_paragraph(element)
        elif elem_type == 'List':
            return self._convert_list(element)
        elif elem_type == 'FencedCode':
            return self._convert_fenced_code(element)
        elif elem_type == 'CodeBlock':
            return self._convert_code_block(element)
        elif elem_type == 'Table':
            return self._convert_table(element)
        elif elem_type == 'Quote':
            return self._convert_blockquote(element)
        elif elem_type == 'ThematicBreak':
            return {"t": "HorizontalRule"}
        elif elem_type == 'BlankLine':
            return None  # Skip blank lines
        elif elem_type == 'HTMLBlock':
            return self._convert_raw_block(element)
        elif elem_type == 'LinkRefDef':
            return None  # Skip link reference definitions (handled during parsing)
        elif elem_type == 'SetextHeading':
            return self._convert_heading(element)
        elif elem_type == 'FootnoteDef':
            return None  # Skip - footnote content is handled via FootnoteRef

        # Unknown block type - skip with warning
        # print(f"[Warn] Unknown block type: {elem_type}")
        return None

    def _convert_heading(self, elem) -> dict:
        """Heading -> {"t": "Header", "c": [level, [id, [], []], inlines]}"""
        inlines = self._convert_children_to_inlines(elem.children)
        level = getattr(elem, 'level', 1)
        return {
            "t": "Header",
            "c": [level, ["", [], []], inlines]
        }

    def _convert_paragraph(self, elem) -> dict:
        """Paragraph -> {"t": "Para", "c": [inlines]}"""
        inlines = self._convert_children_to_inlines(elem.children)
        return {"t": "Para", "c": inlines}

    def _convert_list(self, elem) -> dict:
        """List -> BulletList or OrderedList"""
        items = []
        for item in elem.children:
            item_blocks = []
            for child in item.children:
                block = self._convert_block(child)
                if block:
                    item_blocks.append(block)
            items.append(item_blocks)

        ordered = getattr(elem, 'ordered', False)
        if ordered:
            # OrderedList: [[start, style, delim], items]
            start = getattr(elem, 'start', 1) or 1
            return {
                "t": "OrderedList",
                "c": [[start, {"t": "Decimal"}, {"t": "Period"}], items]
            }
        else:
            return {"t": "BulletList", "c": items}

    def _convert_fenced_code(self, elem) -> dict:
        """FencedCode -> {"t": "CodeBlock", "c": [[id, classes, attrs], code]}"""
        lang = getattr(elem, 'lang', '') or ''
        code = ''
        for child in elem.children:
            if hasattr(child, 'children'):
                code += child.children
            else:
                code += str(child)
        return {
            "t": "CodeBlock",
            "c": [["", [lang] if lang else [], []], code]
        }

    def _convert_code_block(self, elem) -> dict:
        """CodeBlock (indented) -> {"t": "CodeBlock", "c": [[id, [], []], code]}"""
        code = ''
        for child in elem.children:
            if hasattr(child, 'children'):
                code += child.children
            else:
                code += str(child)
        return {
            "t": "CodeBlock",
            "c": [["", [], []], code]
        }

    _ALIGN_MAP = {
        'left': 'AlignLeft',
        'center': 'AlignCenter',
        'right': 'AlignRight',
    }

    def _convert_table(self, elem) -> dict:
        """Convert Marko GFM Table to Pandoc Table format."""
        # Pandoc Table: [attr, caption, specs, head, bodies, foot]

        children = list(elem.children)
        if not children:
            return None

        # Marko GFM tables can have children as:
        # 1. TableHead + TableBody (older/some versions)
        # 2. Direct TableRow elements (current GFM extension)
        head_rows = []
        body_rows = []

        for child in children:
            child_type = type(child).__name__
            if child_type == 'TableHead':
                # Wrapped in TableHead
                for row in child.children:
                    head_rows.append(row)
            elif child_type == 'TableBody':
                # Wrapped in TableBody
                for row in child.children:
                    body_rows.append(row)
            elif child_type == 'TableRow':
                # Direct TableRow - first row is header, rest are body
                if not head_rows:
                    head_rows.append(child)
                else:
                    body_rows.append(child)

        # Determine column count from header or first body row
        col_count = 0
        first_row = head_rows[0] if head_rows else (body_rows[0] if body_rows else None)
        if first_row and first_row.children:
            col_count = len(first_row.children)

        # Column specs (alignment) - extract from first row cells
        specs = []
        if first_row and first_row.children:
            for cell in first_row.children:
                cell_align = getattr(cell, 'align', None)
                align_str = self._ALIGN_MAP.get(cell_align, 'AlignDefault')
                specs.append([align_str, {"t": "ColWidthDefault"}])
        else:
            specs = [["AlignDefault", {"t": "ColWidthDefault"}] for _ in range(col_count)]

        # Convert header
        head_converted = [self._convert_table_row(row) for row in head_rows]
        head = [["", [], []], head_converted]

        # Convert body
        body_converted = [self._convert_table_row(r) for r in body_rows]
        bodies = [[["", [], []], 0, [], body_converted]] if body_converted else []

        # Foot (GFM doesn't have)
        foot = [["", [], []], []]

        return {
            "t": "Table",
            "c": [
                ["", [], []],           # attr
                [None, []],             # caption
                specs,                  # colspecs
                head,                   # thead
                bodies,                 # tbody
                foot                    # tfoot
            ]
        }

    def _convert_table_row(self, row) -> list:
        """Convert TableRow to Pandoc row format."""
        # Pandoc row: [attr, [cells]]
        cells = []
        for cell in row.children:
            # Pandoc cell: [attr, align, rowspan, colspan, [blocks]]
            content = self._convert_children_to_inlines(cell.children)
            para = {"t": "Plain", "c": content}
            cell_align = getattr(cell, 'align', None)
            align_str = self._ALIGN_MAP.get(cell_align, 'AlignDefault')
            cells.append([
                ["", [], []],   # attr
                align_str,      # align
                1,              # rowspan (GFM doesn't support)
                1,              # colspan (GFM doesn't support)
                [para]          # blocks
            ])
        return [["", [], []], cells]

    def _convert_blockquote(self, elem) -> dict:
        """Quote -> {"t": "BlockQuote", "c": [blocks]}"""
        blocks = []
        for child in elem.children:
            block = self._convert_block(child)
            if block:
                blocks.append(block)
        return {"t": "BlockQuote", "c": blocks}

    def _convert_raw_block(self, elem) -> dict:
        """HTMLBlock -> {"t": "RawBlock", "c": ["html", content]}"""
        content = getattr(elem, 'children', '')
        return {"t": "RawBlock", "c": ["html", content]}

    def _convert_children_to_inlines(self, children) -> list:
        """Convert Marko inline children to Pandoc inline list."""
        if children is None:
            return []

        result = []
        for child in children:
            inlines = self._convert_inline(child)
            if isinstance(inlines, list):
                result.extend(inlines)
            elif inlines:
                result.append(inlines)
        return result

    def _convert_inline(self, elem):
        """Convert a Marko inline element to Pandoc inline dict."""
        elem_type = type(elem).__name__

        if elem_type == 'RawText':
            return self._convert_raw_text(elem.children)
        elif elem_type == 'Emphasis':
            inlines = self._convert_children_to_inlines(elem.children)
            return {"t": "Emph", "c": inlines}
        elif elem_type == 'StrongEmphasis':
            inlines = self._convert_children_to_inlines(elem.children)
            return {"t": "Strong", "c": inlines}
        elif elem_type == 'Link':
            inlines = self._convert_children_to_inlines(elem.children)
            dest = getattr(elem, 'dest', '')
            title = getattr(elem, 'title', '') or ''
            return {"t": "Link", "c": [["", [], []], inlines, [dest, title]]}
        elif elem_type == 'Image':
            inlines = self._convert_children_to_inlines(elem.children)
            dest = getattr(elem, 'dest', '')
            title = getattr(elem, 'title', '') or ''
            return {"t": "Image", "c": [["", [], []], inlines, [dest, title]]}
        elif elem_type == 'CodeSpan':
            code = getattr(elem, 'children', '')
            return {"t": "Code", "c": [["", [], []], code]}
        elif elem_type == 'LineBreak':
            return {"t": "LineBreak"}
        elif elem_type == 'SoftBreak':
            return {"t": "SoftBreak"}
        elif elem_type == 'Strikethrough':
            inlines = self._convert_children_to_inlines(elem.children)
            return {"t": "Strikeout", "c": inlines}
        elif elem_type == 'InlineHTML':
            content = getattr(elem, 'children', '')
            return {"t": "RawInline", "c": ["html", content]}
        elif elem_type == 'AutoLink':
            dest = getattr(elem, 'dest', '')
            return {"t": "Link", "c": [["", [], []], [{"t": "Str", "c": dest}], [dest, ""]]}
        elif elem_type == 'Literal':
            text = getattr(elem, 'children', '')
            return self._convert_raw_text(text)
        elif elem_type == 'FootnoteRef':
            # Convert footnote reference to Pandoc Note
            return self._convert_footnote_ref(elem)

        # Handle string children (e.g., from RawText)
        if isinstance(elem, str):
            return self._convert_raw_text(elem)

        # Unknown inline type - try to get text content
        if hasattr(elem, 'children'):
            if isinstance(elem.children, str):
                return self._convert_raw_text(elem.children)
            elif isinstance(elem.children, list):
                return self._convert_children_to_inlines(elem.children)

        return None

    def _convert_raw_text(self, text: str) -> list:
        """Convert raw text to Str and Space tokens."""
        if not text:
            return []

        result = []
        # Split by spaces but keep track of leading/trailing spaces
        parts = text.split(' ')

        for i, part in enumerate(parts):
            if part:
                result.append({"t": "Str", "c": part})
            if i < len(parts) - 1:
                result.append({"t": "Space"})

        return result

    def _convert_footnote_ref(self, elem) -> dict:
        """Convert FootnoteRef to Pandoc Note format."""
        # Get footnote label from the element (stored as 'label' attribute)
        label = getattr(elem, 'label', None)
        if not label:
            return None

        # Look up the footnote definition (keys are lowercase)
        footnote_def = self.footnotes.get(label.lower())
        if not footnote_def:
            # Footnote not found - return the reference as plain text
            return {"t": "Str", "c": f"[^{label}]"}

        # Convert footnote content to blocks
        blocks = []
        for child in footnote_def.children:
            block = self._convert_block(child)
            if block:
                blocks.append(block)

        # Pandoc Note format: {"t": "Note", "c": [blocks]}
        return {"t": "Note", "c": blocks}
