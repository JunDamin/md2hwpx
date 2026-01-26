import sys
import json
import os
import shutil
import zipfile
import io
from PIL import Image


class MarkdownToHtml:
    @staticmethod
    def convert_to_html(input_path, output_path, json_ast=None):
        """
        Convert Markdown to HTML.

        Args:
            input_path: Original input file path (for image resolution)
            output_path: Output HTML file path
            json_ast: Pre-parsed Pandoc-like AST dict (from MarkoToPandocAdapter)
        """
        if json_ast is None:
            raise ValueError("json_ast parameter is required")

        converter = MarkdownToHtml(json_ast)
        final_html = converter.convert()

        # Output Directory
        output_dir = os.path.dirname(output_path)
        if not output_dir:
            output_dir = "."

        # Images Directory
        images_dir = os.path.join(output_dir, "images")

        try:
             if converter.images:
                 if not os.path.exists(images_dir):
                     os.makedirs(images_dir, exist_ok=True)

                 for img in converter.images:
                     # img = {'path': ..., 'filename': ...}
                     src_path = img['src_path'] # original path in AST (media/image1.png)
                     fname = img['filename']    # image1.png
                     target_path = os.path.join(images_dir, fname)

                     embedded = False

                     # Candidates for image source
                     candidates_to_check = []

                     # 1. As-is
                     candidates_to_check.append(src_path)

                     # 2. Relative to Input File
                     input_dir = os.path.dirname(os.path.abspath(input_path))
                     candidates_to_check.append(os.path.join(input_dir, src_path))

                     # Try Local File Candidates
                     for cand_path in candidates_to_check:
                         if os.path.exists(cand_path):
                             shutil.copy2(cand_path, target_path)
                             embedded = True
                             break

                     if not embedded:
                          print(f"[Warn] Image not found: {src_path}", file=sys.stderr)

        except Exception as e:
            print(f"[Error] Image processing failed: {e}", file=sys.stderr)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_html)

    def __init__(self, json_ast):
        self.ast = json_ast
        self.output = []
        # Footnotes list
        self.footnotes = []
        self.images = [] # metadata for images
        self.title = None
        self._extract_metadata()

    def _extract_metadata(self):
        if not self.ast:
            return
        meta = self.ast.get('meta', {})

        # Title
        if 'title' in meta:
             t_obj = meta['title']
             if t_obj.get('t') == 'MetaInlines':
                 self.title = self._get_plain_text(t_obj.get('c', []))
             elif t_obj.get('t') == 'MetaString':
                 self.title = t_obj.get('c', "")

    def _get_plain_text(self, inlines):
        if not isinstance(inlines, list):
            return ""
        text = []
        for item in inlines:
            t = item.get('t')
            c = item.get('c')
            if t == 'Str':
                text.append(c)
            elif t == 'Space':
                text.append(" ")
            elif t in ['Strong', 'Emph', 'Underline', 'Strikeout', 'Superscript', 'Subscript', 'SmallCaps']:
                 text.append(self._get_plain_text(c))
            elif t == 'Link':
                 text.append(self._get_plain_text(c[1]))
            elif t == 'Image':
                 text.append(self._get_plain_text(c[1]))
            elif t == 'Code':
                 text.append(c[1])
            elif t == 'Quoted':
                 text.append('"' + self._get_plain_text(c[1]) + '"')
        return "".join(text)

    def convert(self):
        blocks = self.ast.get('blocks', [])
        body_content = self._process_blocks(blocks)

        # Footnotes
        if self.footnotes:
            body_content += "\n<hr />\n<div class='footnotes'>\n<ol>\n"
            for idx, note_blocks in enumerate(self.footnotes):
                note_html = self._process_blocks(note_blocks)
                body_content += f"<li id='fn{idx+1}'>{note_html}</li>\n"
            body_content += "</ol>\n</div>"

        # Wrap in HTML
        title_tag = f"<title>{self.title}</title>" if self.title else "<title>Document</title>"
        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
{title_tag}
<style>
  body {{ font-family: sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 2rem; }}
  img {{ max-width: 100%; height: auto; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; }}
  th {{ background-color: #f2f2f2; }}
  code {{ background-color: #f0f0f0; padding: 2px 4px; border-radius: 4px; }}
  pre {{ background-color: #f0f0f0; padding: 1rem; overflow-x: auto; }}
</style>
</head>
<body>
{body_content}
</body>
</html>"""
        return html

    def _process_blocks(self, blocks):
        result = []
        if not isinstance(blocks, list):
            return ""

        for block in blocks:
            if not isinstance(block, dict):
                continue

            b_type = block.get('t')
            b_content = block.get('c')

            if b_type == 'Header':
                result.append(self._handle_header(b_content))
            elif b_type == 'Para':
                result.append(self._handle_para(b_content))
            elif b_type == 'Plain':
                result.append(self._handle_plain(b_content))
            elif b_type == 'BulletList':
                result.append(self._handle_bullet_list(b_content))
            elif b_type == 'OrderedList':
                result.append(self._handle_ordered_list(b_content))
            elif b_type == 'CodeBlock':
                result.append(self._handle_code_block(b_content))
            elif b_type == 'Table':
                result.append(self._handle_table(b_content))
            elif b_type == 'BlockQuote':
                result.append(self._handle_blockquote(b_content))
            elif b_type == 'HorizontalRule':
                result.append("<hr />")
            else:
                # Skip unknown block types
                pass

        return "\n".join(result)

    def _process_inlines(self, inlines):
        result = []
        if not isinstance(inlines, list):
            return ""

        for item in inlines:
            if not isinstance(item, dict):
                continue

            i_type = item.get('t')
            i_content = item.get('c')

            if i_type == 'Str':
                result.append(i_content)
            elif i_type == 'Space':
                result.append(" ")
            elif i_type == 'Strong':
                result.append(f"<strong>{self._process_inlines(i_content)}</strong>")
            elif i_type == 'Emph':
                result.append(f"<em>{self._process_inlines(i_content)}</em>")
            elif i_type == 'Link':
                text_content = i_content[1]
                target_url = i_content[2][0]
                result.append(f'<a href="{target_url}">{self._process_inlines(text_content)}</a>')
            elif i_type == 'Code':
                result.append(f"<code>{i_content[1]}</code>")
            elif i_type == 'SoftBreak':
                result.append(" ")
            elif i_type == 'LineBreak':
                result.append("<br />")
            elif i_type == 'Underline':
                result.append(f"<u>{self._process_inlines(i_content)}</u>")
            elif i_type == 'Superscript':
                result.append(f"<sup>{self._process_inlines(i_content)}</sup>")
            elif i_type == 'Subscript':
                result.append(f"<sub>{self._process_inlines(i_content)}</sub>")
            elif i_type == 'Strikeout':
                result.append(f"<del>{self._process_inlines(i_content)}</del>")
            elif i_type == 'Image':
                result.append(self._handle_image(i_content))
            elif i_type == 'Note':
                result.append(self._handle_note(i_content))
            else:
                # Skip unknown inline types
                pass

        return "".join(result)

    def _handle_header(self, content):
        level = content[0]
        text = self._process_inlines(content[2])
        return f"<h{level}>{text}</h{level}>"

    def _handle_para(self, content):
        return f"<p>{self._process_inlines(content)}</p>"

    def _handle_plain(self, content):
        return self._process_inlines(content)

    def _handle_bullet_list(self, content):
        items_html = [f"<li>{self._process_blocks(item)}</li>" for item in content]
        return "<ul>\n" + "\n".join(items_html) + "\n</ul>"

    def _handle_ordered_list(self, content):
        items_html = [f"<li>{self._process_blocks(item)}</li>" for item in content[1]]
        return "<ol>\n" + "\n".join(items_html) + "\n</ol>"

    def _handle_code_block(self, content):
        return f'<pre><code>{content[1]}</code></pre>'

    def _handle_blockquote(self, content):
        inner = self._process_blocks(content)
        return f"<blockquote>{inner}</blockquote>"

    def _handle_image(self, content):
        # content = [attr, caption, [target, title]]
        attr = content[0]
        attr_dict = dict(attr[2]) if attr and len(attr) > 2 else {}

        alt_text = self._process_inlines(content[1])
        src_path = content[2][0]
        title = content[2][1] if len(content[2]) > 1 else ""

        filename = os.path.basename(src_path)

        # Store for extraction
        self.images.append({
            'src_path': src_path,
            'filename': filename
        })

        # Update src to point to images/ folder
        new_src = f"images/{filename}"

        # Calculate Dimensions
        width_attr_val = ""
        height_attr_val = ""

        w_int = None
        h_int = None

        import re
        def parse_to_px(val_str):
            if not val_str: return None
            s = val_str.lower().strip()
            m = re.match(r'([\d\.]+)([a-z%]+)?', s)
            if not m: return None
            val = float(m.group(1))
            unit = m.group(2)

            if not unit or unit == 'px': return int(val)
            if unit == 'in': return int(val * 96)
            if unit == 'cm': return int(val * 37.8)
            if unit == 'mm': return int(val * 3.78)
            if unit == '%': return None

            return int(val)

        if 'width' in attr_dict:
            w_int = parse_to_px(attr_dict['width'])

        if 'height' in attr_dict:
            h_int = parse_to_px(attr_dict['height'])

        # Pillow Auto-Sizing
        if w_int is None:
             try:
                 if os.path.exists(src_path):
                     with Image.open(src_path) as im:
                         w_int, h_int = im.size
             except:
                 pass

        # Max Width Logic
        MAX_WIDTH_PX = 600

        if w_int and w_int > MAX_WIDTH_PX:
            ratio = MAX_WIDTH_PX / w_int
            w_int = MAX_WIDTH_PX
            if h_int:
                h_int = int(h_int * ratio)

        if w_int:
            width_attr_val = f' width="{w_int}"'
        if h_int:
            height_attr_val = f' height="{h_int}"'

        title_attr = f' title="{title}"' if title else ""
        return f'<img src="{new_src}" alt="{alt_text}"{title_attr}{width_attr_val}{height_attr_val} />'

    def _handle_note(self, content):
        self.footnotes.append(content)
        fn_num = len(self.footnotes)
        return f'<sup><a href="#fn{fn_num}">[{fn_num}]</a></sup>'

    def _handle_table(self, content):
        table_head = content[3]
        table_bodies = content[4]
        html_parts = ["<table border='1'>"]

        head_rows = table_head[1]
        if head_rows:
            html_parts.append("<thead>")
            for row in head_rows:
                html_parts.append(self._process_table_row(row, is_header=True))
            html_parts.append("</thead>")

        if table_bodies:
            html_parts.append("<tbody>")
            for body in table_bodies:
                body_rows = body[3]
                for row in body_rows:
                    html_parts.append(self._process_table_row(row, is_header=False))
            html_parts.append("</tbody>")

        html_parts.append("</table>")
        return "\n".join(html_parts)

    def _process_table_row(self, row, is_header=False):
        cells = row[1]
        row_html = ["<tr>"]
        tag = "th" if is_header else "td"

        for cell in cells:
            cell_blocks = cell[4]
            cell_content = self._process_blocks(cell_blocks)
            row_span = cell[2]
            col_span = cell[3]

            attrs = ""
            if row_span > 1: attrs += f' rowspan="{row_span}"'
            if col_span > 1: attrs += f' colspan="{col_span}"'

            row_html.append(f'<{tag}{attrs}>{cell_content}</{tag}>')

        row_html.append("</tr>")
        return "".join(row_html)
