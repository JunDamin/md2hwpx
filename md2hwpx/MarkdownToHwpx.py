import copy
import random
import re
import sys
import os
import io
import shutil
import time
import zipfile
import json
import logging
import xml.sax.saxutils as saxutils
import xml.etree.ElementTree as ET
from PIL import Image

from .config import ConversionConfig, DEFAULT_CONFIG
from .exceptions import TemplateError, ImageError, StyleError, ConversionError, SecurityError

logger = logging.getLogger('md2hwpx')

# XML Namespaces for HWPX format
NS_HEAD = 'http://www.hancom.co.kr/hwpml/2011/head'
NS_PARA = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
NS_CORE = 'http://www.hancom.co.kr/hwpml/2011/core'
NS_SEC = 'http://www.hancom.co.kr/hwpml/2011/section'


class MarkdownToHwpx:
    # Placeholder patterns (compiled once at class level)
    PLACEHOLDER_PATTERN = re.compile(r'\{\{(\w+)\}\}')
    CELL_PATTERN = re.compile(r'\{\{CELL_(\w+)\}\}')
    LIST_PATTERN = re.compile(r'\{\{LIST_(BULLET|ORDERED)_(\d+)\}\}')
    HEADER_PATTERN = re.compile(r'\{\{(H[1-9])\}\}')

    def __init__(self, json_ast=None, header_xml_content=None, section_xml_content=None, input_path=None, config=None):
        self.ast = json_ast
        self.header_xml_content = header_xml_content
        self.section_xml_content = section_xml_content

        # Configuration (use default if not provided)
        self.config = config if config is not None else DEFAULT_CONFIG

        # Store input directory for resolving relative image paths
        self.input_dir = None
        if input_path:
            self.input_dir = os.path.dirname(os.path.abspath(input_path))

        # Dynamic Style Mappings from header.xml
        self.dynamic_style_map = {}
        self.normal_style_id = 0
        self.normal_para_pr_id = 1

        # Placeholder-based styles from template (e.g., {{H1}}, {{BODY}})
        self.placeholder_styles = {}

        # Table cell placeholder styles (12 cell types)
        self.cell_styles = {}

        # Table width from template (extracted from the table containing cell placeholders)
        self.template_table_width = None

        # List placeholder styles (bullet/ordered × levels 1-7)
        self.list_styles = {}

        # Header counters for table-mode auto-numbering (level -> count)
        self.header_counters = {}

        # XML Tree and CharPr Cache
        self.header_tree = None
        self.header_root = None
        self.namespaces = {
            'hh': 'http://www.hancom.co.kr/hwpml/2011/head',
            'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph',
            'hc': 'http://www.hancom.co.kr/hwpml/2011/core',
            'hs': 'http://www.hancom.co.kr/hwpml/2011/section'
        }
        # cache key: (base_char_pr_id, frozenset(active_formats)) -> new_char_pr_id
        self.char_pr_cache = {}
        self.max_char_pr_id = 0

        self.images = [] # metadata for images

        # Metadata extraction
        self.title = None
        self._extract_metadata()

        if self.header_xml_content:
            self._parse_styles_and_init_xml(self.header_xml_content)

        # Load placeholder styles from template section0.xml
        if self.section_xml_content and self.header_root is not None:
            self._load_placeholder_styles()

    def _extract_metadata(self):
        if not self.ast:
            return
        meta = self.ast.get('meta', {})

        # Title
        if 'title' in meta:
             t_obj = meta['title']
             # "title": {"t": "MetaInlines","c": [{"t": "Str","c": "..."}]}
             if t_obj.get('t') == 'MetaInlines':
                 self.title = self._get_plain_text(t_obj.get('c', []))
             elif t_obj.get('t') == 'MetaString': # Sometimes simple string
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
                 text.append(self._get_plain_text(c)) # recursive
            elif t == 'Link':
                 # c = [attr, [text], [url, title]]
                 text.append(self._get_plain_text(c[1]))
            elif t == 'Image':
                 # c = [attr, [caption], [url, title]]
                 text.append(self._get_plain_text(c[1]))
            elif t == 'Code':
                 text.append(c[1])
            elif t == 'Quoted':
                 # c = [quoteType, [inlines]]
                 text.append('"' + self._get_plain_text(c[1]) + '"')
        return "".join(text)

    @staticmethod
    def _validate_inputs(input_path, reference_path, json_ast, config):
        """Validate input files and parameters.

        Args:
            input_path: Original input file path
            reference_path: Reference HWPX template path
            json_ast: Pre-parsed Pandoc-like AST dict
            config: ConversionConfig instance

        Raises:
            TemplateError: If template is missing or invalid
            ConversionError: If json_ast is None
            SecurityError: If file sizes exceed limits
        """
        if not os.path.exists(reference_path):
            raise TemplateError(f"Reference template not found: {reference_path}")

        if json_ast is None:
            raise ConversionError("json_ast parameter is required")

        # Validate file sizes
        if input_path is not None:
            input_size = os.path.getsize(input_path)
            if input_size > config.MAX_INPUT_FILE_SIZE:
                raise SecurityError(
                    f"Input file too large: {input_size} bytes "
                    f"(max {config.MAX_INPUT_FILE_SIZE} bytes)"
                )

        ref_size = os.path.getsize(reference_path)
        if ref_size > config.MAX_TEMPLATE_FILE_SIZE:
            raise SecurityError(
                f"Template file too large: {ref_size} bytes "
                f"(max {config.MAX_TEMPLATE_FILE_SIZE} bytes)"
            )

        # Validate reference file is a valid ZIP
        if not zipfile.is_zipfile(reference_path):
            raise TemplateError(f"Reference template is not a valid HWPX (ZIP) file: {reference_path}")

    @staticmethod
    def _read_template(reference_path):
        """Read header.xml, section0.xml, and page setup from template.

        Args:
            reference_path: Path to the reference HWPX template

        Returns:
            tuple: (header_xml_content, section_xml_content, page_setup_xml, ref_doc_bytes)

        Raises:
            TemplateError: If template is corrupted or missing required files
        """
        with open(reference_path, 'rb') as f:
            ref_doc_bytes = f.read()

        try:
            ref_zip = zipfile.ZipFile(io.BytesIO(ref_doc_bytes))
        except zipfile.BadZipFile:
            raise TemplateError(f"Corrupted HWPX template file: {reference_path}")

        header_xml_content = ""
        section_xml_content = ""
        page_setup_xml = None

        with ref_zip as z:
            required_files = ["Contents/header.xml", "Contents/section0.xml"]
            missing = [f for f in required_files if f not in z.namelist()]
            if missing:
                raise TemplateError(
                    f"Invalid HWPX template: missing required files {missing} in {reference_path}"
                )

            header_xml_content = z.read("Contents/header.xml").decode('utf-8')

            # Read section0.xml for placeholder detection and page setup
            if "Contents/section0.xml" in z.namelist():
                section_xml_content = z.read("Contents/section0.xml").decode('utf-8')

                # Extract Page Setup from section0
                try:
                    ns = {
                        'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph',
                        'hs': 'http://www.hancom.co.kr/hwpml/2011/section',
                        'hc': 'http://www.hancom.co.kr/hwpml/2011/core'
                    }
                    for p, u in ns.items():
                        ET.register_namespace(p, u)

                    sec_root = ET.fromstring(section_xml_content)
                    first_para = sec_root.find('.//hp:p', ns)
                    if first_para is not None:
                        first_run = first_para.find('hp:run', ns)
                        if first_run is not None:
                            extracted_nodes = []
                            for child in first_run:
                                tag = child.tag
                                if tag.endswith('secPr') or tag.endswith('ctrl'):
                                    extracted_nodes.append(ET.tostring(child, encoding='unicode'))
                            if extracted_nodes:
                                page_setup_xml = "".join(extracted_nodes)
                except Exception as e:
                    logger.warning("Failed to extract Page Setup: %s", e)

        return header_xml_content, section_xml_content, page_setup_xml, ref_doc_bytes

    @staticmethod
    def _write_hwpx_output(output_path, ref_doc_bytes, xml_body, new_header_xml,
                           images, title, input_path):
        """Write the final HWPX ZIP file.

        Args:
            output_path: Output HWPX file path
            ref_doc_bytes: Raw bytes of the reference template
            xml_body: Converted XML body content
            new_header_xml: Modified header XML (or None to use original)
            images: List of image metadata dicts
            title: Document title (or None)
            input_path: Original input file path (for image resolution)
        """
        # Prepare Input Zip for reading images if needed (for DOCX)
        input_zip = None
        if input_path and zipfile.is_zipfile(input_path):
            input_zip = zipfile.ZipFile(input_path, 'r')

        try:
            with zipfile.ZipFile(io.BytesIO(ref_doc_bytes), 'r') as ref_zip:
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as out_zip:
                    # Embed images
                    MarkdownToHwpx._embed_images(out_zip, images, input_path, input_zip)

                    # Copy/Modify Files from template
                    for item in ref_zip.infolist():
                        fname = item.filename

                        if fname == "Contents/section0.xml":
                            MarkdownToHwpx._write_section0(out_zip, ref_zip, fname, xml_body)
                        elif fname == "Contents/header.xml":
                            if new_header_xml:
                                out_zip.writestr(fname, new_header_xml)
                            else:
                                out_zip.writestr(item, ref_zip.read(fname))
                        elif fname == "Contents/content.hpf":
                            MarkdownToHwpx._write_manifest(out_zip, ref_zip, fname, images, title)
                        else:
                            out_zip.writestr(item, ref_zip.read(fname))
        except Exception as e:
            logger.error("HWPX creation failed: %s", e, exc_info=True)
            raise
        finally:
            if input_zip:
                input_zip.close()

    @staticmethod
    def _embed_images(out_zip, images, input_path, input_zip):
        """Embed images into the output HWPX.

        Args:
            out_zip: Output ZipFile object
            images: List of image metadata dicts
            input_path: Original input file path
            input_zip: ZipFile of input (if DOCX) or None
        """
        for img in images:
            img_path = img['path']
            img_id = img['id']
            ext = img['ext']
            bindata_name = f"BinData/{img_id}.{ext}"

            embedded = False

            # Candidates for image source
            candidates_to_check = []

            # 1. As-is (CWD or absolute)
            candidates_to_check.append(img_path)

            # 2. Relative to Input File (if local file)
            if not zipfile.is_zipfile(input_path):
                input_dir = os.path.dirname(os.path.abspath(input_path))
                candidates_to_check.append(os.path.join(input_dir, img_path))

            # Try Local File Candidates
            for cand_path in candidates_to_check:
                if os.path.exists(cand_path):
                    out_zip.write(cand_path, bindata_name)
                    embedded = True
                    break

            if embedded:
                continue

            # 3. Try extracting from Input DOCX (In-Memory)
            zip_candidates = []
            if input_zip is not None:
                zip_candidates = [
                    img_path,
                    f"word/{img_path}",
                    img_path.replace("media/", "word/media/")
                ]

                for cand in zip_candidates:
                    if cand in input_zip.namelist():
                        image_data = input_zip.read(cand)
                        out_zip.writestr(bindata_name, image_data)
                        embedded = True
                        break

            if not embedded:
                searched = candidates_to_check
                if input_zip is not None:
                    searched += zip_candidates
                logger.warning("Image not found: %s. Searched: %s", img_path, searched)

    @staticmethod
    def _write_section0(out_zip, ref_zip, fname, xml_body):
        """Write the section0.xml file with converted body.

        Args:
            out_zip: Output ZipFile object
            ref_zip: Reference template ZipFile object
            fname: Filename (Contents/section0.xml)
            xml_body: Converted XML body content
        """
        original_xml = ref_zip.read(fname).decode('utf-8')

        # Replace body
        sec_start = original_xml.find('<hs:sec')
        tag_close = original_xml.find('>', sec_start)
        prefix = original_xml[:tag_close+1]

        # Ensure Namespaces
        if 'xmlns:hc=' not in prefix:
            prefix = prefix[:-1] + ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
        if 'xmlns:hp=' not in prefix:
            prefix = prefix[:-1] + ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'

        sec_end = original_xml.rfind('</hs:sec>')
        suffix = original_xml[sec_end:] if sec_end != -1 else ""

        out_zip.writestr(fname, prefix + "\n" + xml_body + "\n" + suffix)

    @staticmethod
    def _write_manifest(out_zip, ref_zip, fname, images, title):
        """Write the content.hpf manifest file.

        Args:
            out_zip: Output ZipFile object
            ref_zip: Reference template ZipFile object
            fname: Filename (Contents/content.hpf)
            images: List of image metadata dicts
            title: Document title (or None)
        """
        hpf_xml = ref_zip.read(fname).decode('utf-8')

        # 1. Update Title if exists
        if title:
            hpf_xml = re.sub(r'<opf:title>.*?</opf:title>', f'<opf:title>{title}</opf:title>', hpf_xml)

        # 2. Update Images
        if images:
            new_items = []
            for img in images:
                i_id = img['id']
                i_ext = img['ext']
                mime = "image/png"
                if i_ext == "jpg":
                    mime = "image/jpeg"
                elif i_ext == "gif":
                    mime = "image/gif"
                item_str = f'<opf:item id="{i_id}" href="BinData/{i_id}.{i_ext}" media-type="{mime}" isEmbeded="1"/>'
                new_items.append(item_str)

            insert_pos = hpf_xml.find("</opf:manifest>")
            if insert_pos != -1:
                hpf_xml = hpf_xml[:insert_pos] + "\n".join(new_items) + "\n" + hpf_xml[insert_pos:]

        out_zip.writestr(fname, hpf_xml)

    @staticmethod
    def convert_to_hwpx(input_path, output_path, reference_path, json_ast=None, config=None):
        """
        Convert Markdown to HWPX.

        Args:
            input_path: Original input file path (for image resolution)
            output_path: Output HWPX file path
            reference_path: Reference HWPX for styles
            json_ast: Pre-parsed Pandoc-like AST dict (from MarkoToPandocAdapter)
            config: Optional ConversionConfig instance
        """
        if config is None:
            config = DEFAULT_CONFIG

        # 1. Validate inputs
        MarkdownToHwpx._validate_inputs(input_path, reference_path, json_ast, config)

        # 2. Read Reference (Header & Section0)
        header_xml_content, section_xml_content, page_setup_xml, ref_doc_bytes = \
            MarkdownToHwpx._read_template(reference_path)

        # 3. Convert Logic (pass section_xml_content for placeholder detection)
        converter = MarkdownToHwpx(json_ast, header_xml_content, section_xml_content, input_path)
        xml_body, new_header_xml = converter.convert(page_setup_xml=page_setup_xml)

        # 4. Write Output
        MarkdownToHwpx._write_hwpx_output(
            output_path, ref_doc_bytes, xml_body, new_header_xml,
            converter.images, converter.title, input_path
        )

        logger.info("Successfully created %s", output_path)

    @staticmethod
    def _validate_image_path(image_path, base_dir=None):
        """Validate that an image path does not traverse outside allowed directories.

        Args:
            image_path: The image path from the markdown document
            base_dir: The base directory to validate against (input file's directory)

        Raises:
            SecurityError: If the path attempts directory traversal
        """
        # Reject absolute paths on any OS
        if os.path.isabs(image_path):
            raise SecurityError(
                f"Absolute image paths are not allowed: {image_path}"
            )

        # Normalize and check for directory traversal components
        normalized = os.path.normpath(image_path)
        parts = normalized.replace('\\', '/').split('/')
        if '..' in parts:
            raise SecurityError(
                f"Directory traversal in image path is not allowed: {image_path}"
            )

        # If we have a base directory, verify resolved path stays within it
        if base_dir:
            resolved = os.path.normpath(os.path.join(base_dir, image_path))
            base_resolved = os.path.normpath(base_dir)
            if not resolved.startswith(base_resolved + os.sep) and resolved != base_resolved:
                raise SecurityError(
                    f"Image path resolves outside input directory: {image_path}"
                )

    TABLE_BORDER_FILL_XML = """
    <hh:borderFill id="{id}" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0" xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">
        <hh:slash type="NONE" Crooked="0" isCounter="0"/>
        <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
        <hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>
        <hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>
        <hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>
        <hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>
        <hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>
        <hc:fillBrush>
          <hc:winBrush faceColor="none" hatchColor="#000000" alpha="0"/>
        </hc:fillBrush>
    </hh:borderFill>
    """

    def _ensure_table_border_fill(self, root):
        border_fills = root.find('.//hh:borderFills', self.namespaces)
        if border_fills is None:
             # Should practically always exist in valid hwpx, but if not:
             border_fills = ET.SubElement(root, f'{{{NS_HEAD}}}borderFills')

        max_id = 0
        for bf in border_fills.findall('hh:borderFill', self.namespaces):
            bid = int(bf.get('id', 0))
            if bid > max_id:
                max_id = bid

        self.table_border_fill_id = str(max_id + 1)

        xml_str = self.TABLE_BORDER_FILL_XML.format(id=self.table_border_fill_id).strip()
        new_node = ET.fromstring(xml_str)
        border_fills.append(new_node)

    def _parse_styles_and_init_xml(self, header_xml):
        try:
            self.header_tree = ET.ElementTree(ET.fromstring(header_xml))
            self.header_root = self.header_tree.getroot()
            root = self.header_root

            # --- 0. Find Max IDs ---
            self.max_char_pr_id = 0
            for char_pr in root.findall('.//hh:charPr', self.namespaces):
                c_id = int(char_pr.get('id', 0))
                if c_id > self.max_char_pr_id:
                    self.max_char_pr_id = c_id

            self.max_para_pr_id = 0
            for para_pr in root.findall('.//hh:paraPr', self.namespaces):
                p_id = int(para_pr.get('id', 0))
                if p_id > self.max_para_pr_id:
                     self.max_para_pr_id = p_id

            # --- Ensure Numbering Definitions ---
            self._init_numbering_structure(root)

            # --- Ensure Table Border Fill ---
            self._ensure_table_border_fill(root)

            # --- 1. Find Normal Style (id="0" or first) ---
            # ... (rest of function unchanged, just need to make sure indentation aligns) ...

            normal_style_node = root.find('.//hh:style[@id="0"]', self.namespaces)
            if normal_style_node is None:
                all_styles = root.findall('.//hh:style', self.namespaces)
                if all_styles:
                    normal_style_node = all_styles[0]

            if normal_style_node is not None:
                self.normal_style_id = normal_style_node.get('id')
                self.normal_para_pr_id = normal_style_node.get('paraPrIDRef')
                logger.debug("Normal Style Detected: StyleID=%s, ParaPrID=%s", self.normal_style_id, self.normal_para_pr_id)
            else:
                logger.debug("No Normal Style found, using defaults.")

            # --- 2. Map Outline Levels ---
            level_to_para_pr = {}
            for para_pr in root.findall('.//hh:paraPr', self.namespaces):
                p_id = para_pr.get('id')
                # Recursive search for hh:heading
                headings = para_pr.findall('.//hh:heading', self.namespaces)

                target_level = None
                for heading in headings:
                    if heading.get('type') == 'OUTLINE':
                        level_str = heading.get('level')
                        if level_str is not None:
                            target_level = int(level_str)
                            break

                if target_level is not None:
                    if target_level not in level_to_para_pr:
                        level_to_para_pr[target_level] = p_id

            # Map ParaPrID -> Style Info
            para_pr_to_style_info = {}
            for style in root.findall('.//hh:style', self.namespaces):
                s_id = style.get('id')
                p_ref = style.get('paraPrIDRef')
                c_ref = style.get('charPrIDRef')

                if p_ref not in para_pr_to_style_info:
                    para_pr_to_style_info[p_ref] = {
                        'style_id': s_id,
                        'char_pr_id': c_ref
                    }

            # Combine
            detected_levels = []
            self.outline_style_ids = {} # Initialize for usage in _handle_header

            for level, p_id in level_to_para_pr.items():
                if p_id in para_pr_to_style_info:
                    info = para_pr_to_style_info[p_id]
                    self.dynamic_style_map[level] = {
                        'style_id': info['style_id'],
                        'para_pr_id': p_id,
                        'char_pr_id': info['char_pr_id']
                    }
                    detected_levels.append(level)
                    self.outline_style_ids[level] = info['style_id']

            # --- 3. Validation ---
            detected_levels.sort()
            # if not detected_levels:
            #     raise ValueError("No OUTLINE levels found in header.xml")  <-- Relaxed for blank.hwpx? No, strictly required for Headers.
            #     But for Lists we just use Normal.

            if detected_levels: # Only validate if found
                 if detected_levels[0] != 0:
                     raise ValueError(f"Outline levels must start from 0. Found start: {detected_levels[0]}")
                 for i in range(len(detected_levels)):
                     if detected_levels[i] != i:
                         raise ValueError(f"Outline levels are missing/gapped. Expected {i}, found {detected_levels[i]}")

            logger.debug("Validated Outline Levels: %s", detected_levels)

            # --- 4. Validation: Check Normal Style Cleanliness ---
            normal_char_pr_id = 0
            if normal_style_node is not None:
                normal_char_pr_id = normal_style_node.get('charPrIDRef', '0')

            normal_char_pr = root.find(f'.//hh:charPr[@id="{normal_char_pr_id}"]', self.namespaces)
            if normal_char_pr is not None:
                 forbidden = ['bold', 'italic', 'underline', 'supscript', 'subscript']
                 found_dirty = []
                 for tag in forbidden:
                     if normal_char_pr.find(f'hh:{tag}', self.namespaces) is not None:
                         if tag == 'underline':
                             u_node = normal_char_pr.find(f'hh:{tag}', self.namespaces)
                             if u_node.get('type') == 'NONE':
                                 continue
                         found_dirty.append(tag)
                 if found_dirty:
                     raise ValueError(f"Normal Style (charPrID={normal_char_pr_id}) must be clean. Found forbidden properties: {found_dirty}")

        except Exception as e:
            logger.error("Failed to parse/validate header.xml: %s", e)
            raise e

    def _load_placeholder_styles(self):
        """
        Load placeholder-based styles from template section0.xml.

        Finds text like {{H1}}, {{BODY}}, {{CELL_HEADER_LEFT}}, {{LIST_BULLET_1}}, etc.
        and extracts their styling attributes for use during conversion.
        """
        if not self.section_xml_content:
            return

        try:
            section_root = ET.fromstring(self.section_xml_content)
            placeholders, cell_styles, list_styles = self._find_placeholders(section_root)

            # Store text style placeholders (including mode, prefix, table, styleIDRef)
            for name, info in placeholders.items():
                self.placeholder_styles[name] = {
                    'charPrIDRef': info['charPrIDRef'],
                    'paraPrIDRef': info['paraPrIDRef'],
                    'styleIDRef': info.get('styleIDRef', '0'),
                    'prefix': info.get('prefix'),
                    'prefixCharPrIDRef': info.get('prefixCharPrIDRef'),
                    'table': info.get('table'),
                    'mode': info.get('mode', 'plain'),
                    'numberingText': info.get('numberingText'),
                }
                logger.debug("Found placeholder {{%s}}: charPr=%s, paraPr=%s, style=%s, mode=%s",
                           name, info['charPrIDRef'], info['paraPrIDRef'],
                           info.get('styleIDRef'), info.get('mode'))

            # Store cell style placeholders
            for cell_key, info in cell_styles.items():
                self.cell_styles[cell_key] = info
                logger.debug("Found cell placeholder {{CELL_%s}}: borderFill=%s, charPr=%s, paraPr=%s", cell_key, info.get('borderFillIDRef'), info.get('charPrIDRef'), info.get('paraPrIDRef'))

            # Store list style placeholders
            for list_key, info in list_styles.items():
                self.list_styles[list_key] = info
                list_type, level = list_key
                logger.debug("Found list placeholder {{LIST_%s_%s}}: charPr=%s, paraPr=%s", list_type, level, info.get('charPrIDRef'), info.get('paraPrIDRef'))

            if self.placeholder_styles:
                logger.debug("Loaded %d text placeholder styles from template", len(self.placeholder_styles))
            if self.cell_styles:
                logger.debug("Loaded %d cell placeholder styles from template", len(self.cell_styles))
            if self.list_styles:
                logger.debug("Loaded %d list placeholder styles from template", len(self.list_styles))
        except Exception as e:
            logger.warning("Failed to load placeholder styles: %s", e)

    def _find_placeholders(self, section_root):
        """
        Find {{PLACEHOLDER}} text in section0.xml.

        Returns:
            tuple of (text_placeholders, cell_styles, list_styles)
            - text_placeholders: dict[name] -> {charPrIDRef, paraPrIDRef, styleIDRef, prefix, table, mode}
            - cell_styles: dict[cell_key] -> {borderFillIDRef, charPrIDRef, paraPrIDRef, cellMargin, borderFill}
            - list_styles: dict[(list_type, level)] -> {charPrIDRef, paraPrIDRef}
        """
        placeholders = {}
        cell_styles = {}
        list_styles = {}

        # Find placeholders in tables (headers and cells)
        self._find_table_placeholders(section_root, placeholders, cell_styles)

        # Find placeholders in paragraphs (headers, lists, general)
        self._find_paragraph_placeholders(section_root, placeholders, list_styles)

        return placeholders, cell_styles, list_styles

    def _find_table_placeholders(self, section_root, placeholders, cell_styles):
        """Find header and cell placeholders inside tables.

        Args:
            section_root: Root element of section0.xml
            placeholders: Dict to populate with header placeholders (modified in place)
            cell_styles: Dict to populate with cell placeholders (modified in place)
        """
        for tbl in section_root.findall('.//hp:tbl', self.namespaces):
            has_cell_placeholder = False
            for tc in tbl.findall('.//hp:tc', self.namespaces):
                for sublist in tc.findall('.//hp:subList', self.namespaces):
                    for para in sublist.findall('.//hp:p', self.namespaces):
                        for run in para.findall('hp:run', self.namespaces):
                            for text_elem in run.findall('hp:t', self.namespaces):
                                if not text_elem.text:
                                    continue

                                # Check for cell placeholder
                                cell_match = self.CELL_PATTERN.search(text_elem.text)
                                if cell_match:
                                    cell_key = cell_match.group(1).upper()
                                    cell_styles[cell_key] = self._extract_cell_attributes(tc, para, run)
                                    has_cell_placeholder = True
                                    continue

                                # Check for header placeholder in table
                                header_match = self.HEADER_PATTERN.search(text_elem.text)
                                if header_match:
                                    header_name = header_match.group(1).upper()
                                    full_text = text_elem.text
                                    prefix = full_text[:header_match.start()]

                                    styles = self._extract_style_ids(para, run)

                                    # Scan other cells for numbering text
                                    numbering_text = self._find_table_numbering_text(tbl, text_elem)

                                    placeholders[header_name] = {
                                        **styles,
                                        'prefix': prefix if prefix else None,
                                        'table': tbl,
                                        'mode': 'table',
                                        'numberingText': numbering_text,
                                    }

            # Extract table width from the table that contains cell placeholders
            if has_cell_placeholder:
                sz_elem = tbl.find('hp:sz', self.namespaces)
                if sz_elem is not None:
                    width_str = sz_elem.get('width')
                    if width_str:
                        self.template_table_width = int(width_str)
                        logger.debug("Extracted template table width: %d", self.template_table_width)

    def _find_table_numbering_text(self, tbl, placeholder_text_elem):
        """Find numbering text in table cells other than the placeholder cell.

        Scans all text elements in the table looking for non-empty text that
        is not the placeholder itself and not a placeholder pattern. Returns
        the first such text found, which is assumed to be the numbering
        indicator (e.g., "I", "1", "가").

        Args:
            tbl: The table element containing the header placeholder
            placeholder_text_elem: The hp:t element containing the placeholder

        Returns:
            The numbering text string, or None if not found
        """
        for text_elem in tbl.findall('.//hp:t', self.namespaces):
            if text_elem is placeholder_text_elem:
                continue
            if not text_elem.text:
                continue
            text = text_elem.text.strip()
            if not text:
                continue
            # Skip if it's a placeholder pattern
            if self.HEADER_PATTERN.search(text_elem.text):
                continue
            if self.CELL_PATTERN.search(text_elem.text):
                continue
            if self.PLACEHOLDER_PATTERN.search(text_elem.text):
                continue
            return text
        return None

    def _collect_preceding_runs_prefix(self, para, current_run):
        """Collect prefix text and charPrIDRef from runs preceding current_run.

        When a placeholder like {{H3}} is in a separate run from its prefix
        (e.g., run1: "□ ", run2: "{{H3}}"), this collects text from all
        preceding runs as the prefix.

        Args:
            para: The paragraph element containing the runs
            current_run: The run element containing the placeholder

        Returns:
            tuple of (prefix_text, prefix_char_pr_id) where prefix_text is the
            concatenated text from preceding runs (or None if empty), and
            prefix_char_pr_id is the charPrIDRef of the first preceding run
            with text (or None if no preceding runs with text)
        """
        prefix_parts = []
        prefix_char_pr_id = None
        for r in para.findall('hp:run', self.namespaces):
            if r is current_run:
                break
            for t in r.findall('hp:t', self.namespaces):
                if t.text:
                    prefix_parts.append(t.text)
                    if prefix_char_pr_id is None:
                        prefix_char_pr_id = r.get('charPrIDRef', '0')
        prefix_text = ''.join(prefix_parts) if prefix_parts else None
        return prefix_text, prefix_char_pr_id

    def _find_paragraph_placeholders(self, section_root, placeholders, list_styles):
        """Find header, list, and general placeholders in paragraphs.

        Args:
            section_root: Root element of section0.xml
            placeholders: Dict to populate with placeholders (modified in place)
            list_styles: Dict to populate with list placeholders (modified in place)
        """
        for para in section_root.findall('.//hp:p', self.namespaces):
            for run in para.findall('hp:run', self.namespaces):
                for text_elem in run.findall('hp:t', self.namespaces):
                    if not text_elem.text:
                        continue

                    # Check for list placeholder
                    list_match = self.LIST_PATTERN.search(text_elem.text)
                    if list_match:
                        list_type = list_match.group(1).upper()
                        level = int(list_match.group(2))
                        full_text = text_elem.text
                        prefix = full_text[:list_match.start()]

                        # Also check preceding runs for prefix text
                        if not prefix:
                            preceding_prefix, _ = self._collect_preceding_runs_prefix(para, run)
                            if preceding_prefix:
                                prefix = preceding_prefix

                        styles = self._extract_style_ids(para, run)
                        has_numbering, num_pr_id = self._check_para_pr_has_numbering(styles['paraPrIDRef'])

                        list_styles[(list_type, level)] = {
                            'charPrIDRef': styles['charPrIDRef'],
                            'paraPrIDRef': styles['paraPrIDRef'],
                            'mode': 'numbering' if has_numbering else 'prefix',
                            'prefix': prefix if not has_numbering else None,
                            'numPrIDRef': num_pr_id if has_numbering else None,
                        }
                        continue

                    # Skip cell placeholders (handled in table loop)
                    if text_elem.text.startswith('{{CELL_'):
                        continue

                    # Check for header placeholder (outside tables)
                    header_match = self.HEADER_PATTERN.search(text_elem.text)
                    if header_match:
                        header_name = header_match.group(1).upper()
                        # Only add if not already found in table
                        if header_name not in placeholders:
                            full_text = text_elem.text
                            prefix = full_text[:header_match.start()]

                            # Check preceding runs for prefix in separate run
                            preceding_prefix, prefix_char_pr_id = self._collect_preceding_runs_prefix(para, run)
                            if not prefix and preceding_prefix:
                                prefix = preceding_prefix

                            styles = self._extract_style_ids(para, run)
                            placeholders[header_name] = {
                                **styles,
                                'prefix': prefix if prefix else None,
                                'prefixCharPrIDRef': prefix_char_pr_id,
                                'table': None,
                                'mode': 'prefix' if prefix else 'plain',
                            }
                        continue

                    # Check for general placeholder (non-header, non-list)
                    match = self.PLACEHOLDER_PATTERN.search(text_elem.text)
                    if match:
                        placeholder_name = match.group(1).upper()
                        # Skip if already handled as header or list
                        if placeholder_name.startswith('H') and placeholder_name[1:].isdigit():
                            continue
                        if placeholder_name.startswith('LIST_'):
                            continue

                        full_text = text_elem.text
                        prefix = full_text[:match.start()]

                        # Check preceding runs for prefix in separate run
                        preceding_prefix, prefix_char_pr_id = self._collect_preceding_runs_prefix(para, run)
                        if not prefix and preceding_prefix:
                            prefix = preceding_prefix

                        styles = self._extract_style_ids(para, run)
                        placeholders[placeholder_name] = {
                            **styles,
                            'prefix': prefix if prefix else None,
                            'prefixCharPrIDRef': prefix_char_pr_id,
                            'table': None,
                            'mode': 'prefix' if prefix else 'plain',
                        }

    def _extract_cell_attributes(self, tc, para, run):
        """Extract styling attributes from a table cell.

        Args:
            tc: The <hp:tc> table cell element
            para: The <hp:p> paragraph element inside the cell
            run: The <hp:run> run element containing the placeholder

        Returns:
            dict with borderFillIDRef, paraPrIDRef, charPrIDRef, cellMargin, borderFill
        """
        attrs = {
            # From <hp:tc>
            'borderFillIDRef': tc.get('borderFillIDRef'),

            # From <hp:p>
            'paraPrIDRef': para.get('paraPrIDRef', '0'),
            'styleIDRef': para.get('styleIDRef', '0'),

            # From <hp:run>
            'charPrIDRef': run.get('charPrIDRef', '0'),

            # From <hp:cellMargin> if present
            'cellMargin': self._extract_cell_margin(tc),
        }

        # Also resolve borderFill details from header.xml
        if attrs['borderFillIDRef'] and self.header_root is not None:
            attrs['borderFill'] = self._resolve_border_fill(attrs['borderFillIDRef'])

        return attrs

    def _extract_cell_margin(self, tc):
        """Extract cell margin values from <hp:cellMargin> element."""
        default_margin = self.config.CELL_MARGIN_DEFAULT
        cell_margin = tc.find('.//hp:cellMargin', self.namespaces)
        if cell_margin is not None:
            return {
                'left': cell_margin.get('left', str(default_margin['left'])),
                'right': cell_margin.get('right', str(default_margin['right'])),
                'top': cell_margin.get('top', str(default_margin['top'])),
                'bottom': cell_margin.get('bottom', str(default_margin['bottom'])),
            }
        return {
            'left': str(default_margin['left']),
            'right': str(default_margin['right']),
            'top': str(default_margin['top']),
            'bottom': str(default_margin['bottom'])
        }

    def _resolve_border_fill(self, border_fill_id):
        """Look up borderFill element in header.xml and extract properties.

        Args:
            border_fill_id: The ID of the borderFill element to look up

        Returns:
            dict with border properties (leftBorder, rightBorder, topBorder, bottomBorder, fillColor)
            or None if not found
        """
        if self.header_root is None:
            return None

        bf_elem = self.header_root.find(
            f'.//hh:borderFill[@id="{border_fill_id}"]',
            self.namespaces
        )
        if bf_elem is None:
            return None

        return {
            'leftBorder': self._extract_border(bf_elem, 'leftBorder'),
            'rightBorder': self._extract_border(bf_elem, 'rightBorder'),
            'topBorder': self._extract_border(bf_elem, 'topBorder'),
            'bottomBorder': self._extract_border(bf_elem, 'bottomBorder'),
            'fillColor': self._extract_fill_color(bf_elem),
        }

    def _extract_border(self, bf_elem, border_name):
        """Extract border properties (type, width, color) from borderFill element."""
        border = bf_elem.find(f'hh:{border_name}', self.namespaces)
        if border is None:
            return {'type': 'NONE', 'width': '0.12 mm', 'color': '#000000'}
        return {
            'type': border.get('type', 'NONE'),
            'width': border.get('width', '0.12 mm'),
            'color': border.get('color', '#000000'),
        }

    def _extract_fill_color(self, bf_elem):
        """Extract background fill color from borderFill element."""
        win_brush = bf_elem.find('.//hc:winBrush', self.namespaces)
        if win_brush is not None:
            return win_brush.get('faceColor', 'none')
        return 'none'

    def _check_para_pr_has_numbering(self, para_pr_id):
        """Check if a paraPr has numPr (numbering) reference.

        Args:
            para_pr_id: The paraPr ID to check

        Returns:
            tuple: (has_numbering: bool, numPrIDRef: str or None)
        """
        if self.header_root is None:
            return False, None

        para_pr = self.header_root.find(
            f'.//hh:paraPr[@id="{para_pr_id}"]',
            self.namespaces
        )
        if para_pr is None:
            return False, None

        num_pr = para_pr.find('hh:numPr', self.namespaces)
        if num_pr is not None:
            num_pr_id = num_pr.get('numPrIDRef')
            return True, num_pr_id

        return False, None

    def convert(self, page_setup_xml=None):
        blocks = self.ast.get('blocks', [])
        # Process blocks to get section XML
        xml_body = self._process_blocks(blocks)

        # Inject page_setup_xml (secPr, ctrl) into the FIRST hp:run of the document
        if page_setup_xml:
            # Find the first hp:run start tag
            # e.g. <hp:run charPrIDRef="...">
            search_pattern = r'(<hp:run [^>]*>)'
            match = re.search(search_pattern, xml_body)
            if match:
                # Insert AFTER the opening tag, so it becomes the first child
                insert_pos = match.end()
                xml_body = xml_body[:insert_pos] + page_setup_xml + xml_body[insert_pos:]
                logger.debug("Injected Page Setup into first hp:run.")
            else:
                logger.warning("No hp:run found to inject Page Setup.")

        # Serialize the modified header.xml
        for prefix, uri in self.namespaces.items():
            ET.register_namespace(prefix, uri)

        new_header_xml = ""
        if self.header_root is not None:
             # Update itemCnt for charProperties
             char_props = self.header_root.find('.//hh:charProperties', self.namespaces)
             if char_props is not None:
                 count = len(char_props.findall('hh:charPr', self.namespaces))
                 char_props.set('itemCnt', str(count))

             # Update itemCnt for paraProperties
             para_props = self.header_root.find('.//hh:paraProperties', self.namespaces)
             if para_props is not None:
                 count = len(para_props.findall('hh:paraPr', self.namespaces))
                 para_props.set('itemCnt', str(count))

             # Update itemCnt for numberings
             numberings = self.header_root.find('.//hh:numberings', self.namespaces)
             if numberings is not None:
                 count = len(numberings.findall('hh:numbering', self.namespaces))
                 numberings.set('itemCnt', str(count))

             # Update itemCnt for borderFills
             border_fills = self.header_root.find('.//hh:borderFills', self.namespaces)
             if border_fills is not None:
                 count = len(border_fills.findall('hh:borderFill', self.namespaces))
                 border_fills.set('itemCnt', str(count))

             new_header_xml = ET.tostring(self.header_root, encoding='unicode')

        return xml_body, new_header_xml

    def _process_blocks(self, blocks):
        result = []
        if not isinstance(blocks, list):
             logger.error("_process_blocks expected list, got %s: %s", type(blocks), blocks)
             return ""

        for block in blocks:
            if not isinstance(block, dict):
                logger.error("Skipped invalid block: %s", block)
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
                result.append(self._handle_horizontal_rule())
            else:
                # logger.warning("Unhandled Block Type: %s", b_type)
                pass

        return "\n".join(result)

    def _escape_text(self, text):
        """Escape text content for XML elements."""
        return saxutils.escape(text)

    def _escape_attr(self, value):
        """Escape value for use in XML attributes (handles &, <, >, ", ')."""
        if value is None:
            return ''
        return saxutils.escape(str(value), {'"': '&quot;', "'": '&apos;'})

    # --- XML Element Builder Helpers ---

    def _make_elem(self, ns, tag, attrib=None, text=None):
        """Create XML element with namespace."""
        elem = ET.Element(f'{{{ns}}}{tag}', attrib or {})
        if text is not None:
            elem.text = str(text)
        return elem

    def _add_elem(self, parent, ns, tag, attrib=None, text=None):
        """Add child element to parent."""
        elem = ET.SubElement(parent, f'{{{ns}}}{tag}', attrib or {})
        if text is not None:
            elem.text = str(text)
        return elem

    def _elem_to_str(self, elem):
        """Convert element to XML string."""
        return ET.tostring(elem, encoding='unicode')

    # --- Paragraph/Run Element Creators ---

    def _create_para_elem(self, style_id=0, para_pr_id=1, column_break=0, merged=0):
        """Create paragraph element."""
        return self._make_elem(NS_PARA, 'p', {
            'paraPrIDRef': str(para_pr_id),
            'styleIDRef': str(style_id),
            'pageBreak': '0',
            'columnBreak': str(column_break),
            'merged': str(merged)
        })

    def _create_run_elem(self, char_pr_id=0):
        """Create run element."""
        return self._make_elem(NS_PARA, 'run', {'charPrIDRef': str(char_pr_id)})

    def _create_text_elem(self, text):
        """Create text element with escaped content."""
        return self._make_elem(NS_PARA, 't', text=text)

    def _create_text_run_elem(self, text, char_pr_id=0):
        """Create run element containing text."""
        run = self._create_run_elem(char_pr_id)
        self._add_elem(run, NS_PARA, 't', text=text)
        return run

    # --- Block Handlers ---

    def _handle_header(self, content):
        level = content[0]
        inlines = content[2]

        # Check for LineBreak at start for Column Break
        column_break_val = 0
        if inlines and len(inlines) > 0:
            first_item = inlines[0]
            if first_item.get('t') == 'LineBreak':
                column_break_val = 1
                inlines = inlines[1:]  # Remove the LineBreak

        # Reset child header counters when a parent header appears
        for child_level in list(self.header_counters):
            if child_level > level:
                del self.header_counters[child_level]

        # Check for placeholder style first (e.g., {{H1}}, {{H2}}, etc.)
        placeholder_name = f'H{level}'
        if placeholder_name in self.placeholder_styles:
            props = self.placeholder_styles[placeholder_name]
            mode = props.get('mode', 'plain')

            # Track occurrence count for auto-numbering
            if level not in self.header_counters:
                self.header_counters[level] = 0
            self.header_counters[level] += 1
            counter = self.header_counters[level]

            if mode == 'table':
                # Header is inside a table in template - copy table structure
                return self._handle_header_in_table(inlines, props, column_break_val,
                                                    counter=counter)
            else:
                # Plain or prefix mode - use template styles
                return self._handle_header_styled(inlines, props, column_break_val,
                                                  counter=counter)

        # Fallback to existing style-based logic
        hwpx_level = level - 1
        if hwpx_level not in self.dynamic_style_map:
            raise ValueError(f"Requested Header Level {level} (HWPX Level {hwpx_level}) not found in header.xml style map.")

        # Map header level to style
        style_id = 0
        if level in self.outline_style_ids:
            style_id = self.outline_style_ids[level]
        else:
            style_id = level

        # Use associated paraPr if available
        para_pr_id = self.normal_para_pr_id
        char_pr_id = 0

        if self.header_root is not None:
            style_node = self.header_root.find(f'.//hh:style[@id="{style_id}"]', self.namespaces)
            if style_node is not None:
                para_pr_id = style_node.get('paraPrIDRef', 0)
                char_pr_id = style_node.get('charPrIDRef', 0)

        para = self._create_para_elem(style_id=style_id, para_pr_id=para_pr_id, column_break=column_break_val)
        self._process_inlines_to_elems(inlines, para, base_char_pr_id=int(char_pr_id))
        return self._elem_to_str(para)

    def _format_header_numbering(self, template_text, counter):
        """Format header numbering text based on the template's pattern.

        Detects the numbering format from the template text and produces the
        corresponding value for the given counter. Supports Roman numerals,
        Arabic numerals, and Korean syllables.

        Args:
            template_text: Original numbering text from template (e.g., "I", "1", "가")
            counter: Current occurrence number (1-indexed)

        Returns:
            Formatted numbering string
        """
        stripped = template_text.strip()

        # Roman numerals (uppercase)
        roman_upper = [
            'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
            'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX',
        ]
        if stripped in roman_upper:
            result = roman_upper[counter - 1] if counter <= len(roman_upper) else str(counter)
            return template_text.replace(stripped, result)

        # Roman numerals (lowercase)
        roman_lower = [r.lower() for r in roman_upper]
        if stripped in roman_lower:
            result = roman_lower[counter - 1] if counter <= len(roman_lower) else str(counter)
            return template_text.replace(stripped, result)

        # Arabic numerals
        if re.search(r'\d+', stripped):
            return re.sub(r'\d+', str(counter), template_text, count=1)

        # Korean syllables: 가 → 나 → 다 → ...
        korean_jamo = '가나다라마바사아자차카타파하'
        match = re.search(r'[가-하]', stripped)
        if match and counter <= len(korean_jamo):
            return template_text.replace(match.group(), korean_jamo[counter - 1])

        # Fallback: return as-is
        return template_text

    def _handle_header_in_table(self, inlines, props, column_break=0, counter=1):
        """Handle header that's defined inside a table in template.

        Copies the entire table structure and replaces the placeholder
        text with the actual header content. Applies styleIDRef,
        paraPrIDRef, and charPrIDRef from template.

        The table is wrapped in a paragraph with a run so that secPr
        injection works correctly when this is the first element.

        Args:
            inlines: Inline content for the header
            props: Placeholder properties dict with table, charPrIDRef, paraPrIDRef, styleIDRef
            column_break: Column break value (0 or 1)
            counter: Occurrence number for auto-numbering (1-indexed)

        Returns:
            XML string of the paragraph containing the table with header content
        """
        table_elem = copy.deepcopy(props['table'])

        char_pr_id = int(props['charPrIDRef'])
        para_pr_id = int(props['paraPrIDRef'])
        style_id = int(props.get('styleIDRef', self.normal_style_id))

        # Remove template-specific elements that shouldn't be in output
        self._remove_template_elements(table_elem)

        # Auto-increment numbering cell if template has numbering text
        numbering_text = props.get('numberingText')
        if numbering_text:
            formatted = self._format_header_numbering(numbering_text, counter)
            for text_elem in table_elem.findall('.//hp:t', self.namespaces):
                if text_elem.text and text_elem.text.strip() == numbering_text:
                    text_elem.text = text_elem.text.replace(numbering_text, formatted)
                    break

        # Find the cell containing the placeholder and replace with header content
        for para in table_elem.findall('.//hp:p', self.namespaces):
            for run in para.findall('hp:run', self.namespaces):
                for text_elem in run.findall('hp:t', self.namespaces):
                    if text_elem.text and self.HEADER_PATTERN.search(text_elem.text):
                        # Update paragraph attributes
                        para.set('paraPrIDRef', str(para_pr_id))
                        para.set('styleIDRef', str(style_id))
                        # Update run attributes
                        run.set('charPrIDRef', str(char_pr_id))
                        # Replace placeholder with header text
                        header_text = self._get_plain_text(inlines)
                        text_elem.text = self.HEADER_PATTERN.sub(header_text, text_elem.text)

        # Wrap table in a paragraph with run so secPr injection works
        # when this is the first element in the document
        wrapper_para = self._create_para_elem(
            style_id=self.normal_style_id,
            para_pr_id=self.normal_para_pr_id,
            column_break=column_break
        )
        wrapper_run = self._create_run_elem(char_pr_id=0)
        wrapper_run.append(table_elem)
        # Add empty text element after table
        self._add_elem(wrapper_run, NS_PARA, 't')
        wrapper_para.append(wrapper_run)

        return self._elem_to_str(wrapper_para)

    def _find_parent(self, root, child):
        """Find the parent element of a child in an ElementTree."""
        for parent in root.iter():
            if child in parent:
                return parent
        return None

    def _extract_style_ids(self, para, run):
        """Extract style IDs from paragraph and run elements.

        Args:
            para: Paragraph element (hp:p)
            run: Run element (hp:run)

        Returns:
            dict with charPrIDRef, paraPrIDRef, styleIDRef
        """
        return {
            'charPrIDRef': run.get('charPrIDRef', '0'),
            'paraPrIDRef': para.get('paraPrIDRef', '0'),
            'styleIDRef': para.get('styleIDRef', '0'),
        }

    def _remove_template_elements(self, elem):
        """Remove template-specific elements from a copied element.

        Removes hp:secPr, hp:linesegarray, hp:ctrl from descendants,
        and hp:label from direct children. These elements are specific
        to the template and should not appear in the output.

        Args:
            elem: The element to clean (modified in place)
        """
        for tag in ['hp:secPr', 'hp:linesegarray', 'hp:ctrl']:
            for child in elem.findall(f'.//{tag}', self.namespaces):
                parent = self._find_parent(elem, child)
                if parent is not None:
                    parent.remove(child)

        for child in elem.findall('hp:label', self.namespaces):
            elem.remove(child)

    def _handle_header_styled(self, inlines, props, column_break=0, counter=1):
        """Handle header with template styles (plain or prefix mode).

        Creates a paragraph with the template's styleIDRef, paraPrIDRef, and
        charPrIDRef. If a prefix is specified in props, it's prepended to the
        header content. The prefix is auto-formatted using the counter (e.g.,
        "1. " becomes "2. " for the second occurrence). When the prefix comes
        from a separate run in the template, prefixCharPrIDRef preserves its
        original character style.

        Args:
            inlines: Inline content for the header
            props: Placeholder properties dict with charPrIDRef, paraPrIDRef,
                   styleIDRef, optional prefix, and optional prefixCharPrIDRef
            column_break: Column break value (0 or 1)
            counter: Occurrence number for auto-numbering the prefix (1-indexed)

        Returns:
            XML string of the paragraph
        """
        char_pr_id = int(props['charPrIDRef'])
        para_pr_id = int(props['paraPrIDRef'])
        style_id = int(props.get('styleIDRef', self.normal_style_id))
        prefix = props.get('prefix')

        para = self._create_para_elem(style_id=style_id, para_pr_id=para_pr_id, column_break=column_break)

        # Add prefix as first run if present, with auto-numbering
        if prefix:
            formatted_prefix = self._format_header_numbering(prefix, counter)
            prefix_char_pr_id = props.get('prefixCharPrIDRef')
            prefix_cid = int(prefix_char_pr_id) if prefix_char_pr_id else char_pr_id
            prefix_run = self._create_text_run_elem(formatted_prefix, prefix_cid)
            para.append(prefix_run)

        # Add header content
        self._process_inlines_to_elems(inlines, para, base_char_pr_id=char_pr_id)
        return self._elem_to_str(para)

    def _handle_text_block(self, content, placeholder_name='BODY'):
        """Handle paragraph-like block (Para, Plain).

        Args:
            content: List of inline elements
            placeholder_name: Name of placeholder style to use (default: 'BODY')

        Returns:
            XML string of the paragraph
        """
        if placeholder_name in self.placeholder_styles:
            props = self.placeholder_styles[placeholder_name]
            char_pr_id = props['charPrIDRef']
            para_pr_id = props['paraPrIDRef']
        else:
            char_pr_id = 0
            para_pr_id = self.normal_para_pr_id
            if self.header_root is not None:
                style_node = self.header_root.find(
                    f'.//hh:style[@id="{self.normal_style_id}"]', self.namespaces
                )
                if style_node is not None:
                    char_pr_id = style_node.get('charPrIDRef', 0)

        para = self._create_para_elem(style_id=self.normal_style_id, para_pr_id=para_pr_id)
        self._process_inlines_to_elems(content, para, base_char_pr_id=int(char_pr_id))
        return self._elem_to_str(para)

    def _handle_para(self, content):
        """Handle Para block."""
        return self._handle_text_block(content, 'BODY')

    def _handle_plain(self, content):
        """Handle Plain block."""
        return self._handle_text_block(content, 'BODY')

    def _handle_code_block(self, content):
        # Code formatting? IDK...
        code = content[1]
        para = self._create_para_elem(style_id=self.normal_style_id, para_pr_id=self.normal_para_pr_id)
        run = self._create_text_run_elem(code)
        para.append(run)
        return self._elem_to_str(para)

    _PANDOC_ALIGN_MAP = {
        'AlignLeft': 'LEFT',
        'AlignCenter': 'CENTER',
        'AlignRight': 'RIGHT',
        'AlignDefault': None,
    }

    def _pandoc_align_to_hwpx(self, pandoc_align):
        """Convert Pandoc alignment string to HWPX alignment value.

        Args:
            pandoc_align: e.g., 'AlignLeft', 'AlignCenter', 'AlignRight', 'AlignDefault'

        Returns:
            HWPX alignment string ('LEFT', 'CENTER', 'RIGHT') or None for default
        """
        return self._PANDOC_ALIGN_MAP.get(pandoc_align)

    def _get_aligned_para_pr(self, hwpx_align):
        """Create or retrieve a paraPr with specific horizontal alignment.

        Args:
            hwpx_align: 'LEFT', 'CENTER', or 'RIGHT'

        Returns:
            paraPr ID string, or None if alignment cannot be applied
        """
        if not hwpx_align:
            return None

        # Cache key for aligned paraPr
        cache_attr = '_aligned_para_pr_cache'
        if not hasattr(self, cache_attr):
            self._aligned_para_pr_cache = {}

        if hwpx_align in self._aligned_para_pr_cache:
            return self._aligned_para_pr_cache[hwpx_align]

        base_id = self.normal_para_pr_id
        base_node = self.header_root.find(f'.//hh:paraPr[@id="{base_id}"]', self.namespaces)
        if base_node is None:
            return None

        new_node = copy.deepcopy(base_node)
        self.max_para_pr_id += 1
        new_id = str(self.max_para_pr_id)
        new_node.set('id', new_id)

        # Set horizontal alignment
        align_elem = new_node.find('hh:align', self.namespaces)
        if align_elem is None:
            align_elem = ET.SubElement(new_node, f'{{{NS_HEAD}}}align')
        align_elem.set('horizontal', hwpx_align)

        para_props = self.header_root.find('.//hh:paraProperties', self.namespaces)
        if para_props is not None:
            para_props.append(new_node)

        self._aligned_para_pr_cache[hwpx_align] = new_id
        return new_id

    def _get_blockquote_para_pr(self, level=0):
        """Create or retrieve a paraPr with increased left margin for block quotes.

        Args:
            level: Nesting level of the block quote (0-based)

        Returns:
            paraPr ID string
        """
        # Check cache first
        if not hasattr(self, '_blockquote_para_pr_cache'):
            self._blockquote_para_pr_cache = {}

        if level in self._blockquote_para_pr_cache:
            return self._blockquote_para_pr_cache[level]

        base_id = self.normal_para_pr_id
        base_node = self.header_root.find(f'.//hh:paraPr[@id="{base_id}"]', self.namespaces)
        if base_node is None:
            return base_id

        new_node = copy.deepcopy(base_node)
        self.max_para_pr_id += 1
        new_id = str(self.max_para_pr_id)
        new_node.set('id', new_id)

        indent = self.config.BLOCKQUOTE_LEFT_INDENT + level * self.config.BLOCKQUOTE_INDENT_PER_LEVEL

        for left_node in new_node.findall('.//hc:left', self.namespaces):
            original_val = int(left_node.get('value', 0))
            left_node.set('value', str(original_val + indent))

        para_props = self.header_root.find('.//hh:paraProperties', self.namespaces)
        if para_props is not None:
            para_props.append(new_node)

        # Cache the result
        self._blockquote_para_pr_cache[level] = new_id
        return new_id

    def _handle_blockquote(self, content, level=0):
        """Handle block quote block.

        Block quotes are rendered as paragraphs with increased left margin.
        Nested block quotes increase the indent further.

        Args:
            content: List of inner blocks
            level: Nesting level (0-based)

        Returns:
            XML string of the block quote paragraphs
        """
        if level >= self.config.MAX_NESTING_DEPTH:
            logger.warning("Block quote nesting depth limit reached (%d). Flattening.", self.config.MAX_NESTING_DEPTH)
            # Flatten: treat remaining content at current level
            level = self.config.MAX_NESTING_DEPTH - 1

        results = []
        for block in content:
            b_type = block.get('t')
            b_content = block.get('c')

            if b_type == 'BlockQuote':
                # Nested block quote
                results.append(self._handle_blockquote(b_content, level=level + 1))
            elif b_type == 'Para' or b_type == 'Plain':
                bq_para_pr = self._get_blockquote_para_pr(level)
                para = self._create_para_elem(
                    style_id=self.normal_style_id,
                    para_pr_id=bq_para_pr
                )
                normal_char_pr_id = 0
                if self.header_root is not None:
                    style_node = self.header_root.find(
                        f'.//hh:style[@id="{self.normal_style_id}"]', self.namespaces
                    )
                    if style_node is not None:
                        normal_char_pr_id = int(style_node.get('charPrIDRef', 0))
                self._process_inlines_to_elems(b_content, para, base_char_pr_id=normal_char_pr_id)
                results.append(self._elem_to_str(para))
            else:
                # Other block types inside blockquote (lists, code, etc.)
                results.append(self._process_blocks([block]))

        return "\n".join(results)

    def _ensure_hr_border_fill(self):
        """Create a borderFill for horizontal rules if not already created.

        Returns:
            borderFill ID string for horizontal rules
        """
        if hasattr(self, '_hr_border_fill_id'):
            return self._hr_border_fill_id

        root = self.header_root
        if root is None:
            self._hr_border_fill_id = '1'
            return self._hr_border_fill_id

        border_fills = root.find('.//hh:borderFills', self.namespaces)
        if border_fills is None:
            border_fills = ET.SubElement(root, f'{{{NS_HEAD}}}borderFills')

        max_id = 0
        for bf in border_fills.findall('hh:borderFill', self.namespaces):
            bid = int(bf.get('id', 0))
            if bid > max_id:
                max_id = bid

        new_id = str(max_id + 1)
        self._hr_border_fill_id = new_id

        hr_type = self.config.HR_BORDER_TYPE
        hr_width = self.config.HR_BORDER_WIDTH
        hr_color = self.config.HR_BORDER_COLOR

        xml_str = f'''<hh:borderFill id="{new_id}" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0" xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">
            <hh:slash type="NONE" Crooked="0" isCounter="0"/>
            <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
            <hh:leftBorder type="NONE" width="0.1 mm" color="#000000"/>
            <hh:rightBorder type="NONE" width="0.1 mm" color="#000000"/>
            <hh:topBorder type="NONE" width="0.1 mm" color="#000000"/>
            <hh:bottomBorder type="{hr_type}" width="{hr_width}" color="{hr_color}"/>
            <hh:diagonal type="NONE" width="0.1 mm" color="#000000"/>
            <hc:fillBrush>
              <hc:winBrush faceColor="none" hatchColor="#000000" alpha="0"/>
            </hc:fillBrush>
        </hh:borderFill>'''.strip()

        new_node = ET.fromstring(xml_str)
        border_fills.append(new_node)

        return self._hr_border_fill_id

    def _get_hr_para_pr(self):
        """Create a paraPr for horizontal rule with bottom border.

        Returns:
            paraPr ID string
        """
        if hasattr(self, '_hr_para_pr_id'):
            return self._hr_para_pr_id

        border_fill_id = self._ensure_hr_border_fill()

        base_id = self.normal_para_pr_id
        base_node = self.header_root.find(f'.//hh:paraPr[@id="{base_id}"]', self.namespaces)
        if base_node is None:
            self._hr_para_pr_id = base_id
            return self._hr_para_pr_id

        new_node = copy.deepcopy(base_node)
        self.max_para_pr_id += 1
        new_id = str(self.max_para_pr_id)
        new_node.set('id', new_id)

        # Set border reference to our HR borderFill
        border = new_node.find('hh:border', self.namespaces)
        if border is None:
            border = ET.SubElement(new_node, f'{{{NS_HEAD}}}border')
        border.set('borderFillIDRef', border_fill_id)
        border.set('offsetLeft', '0')
        border.set('offsetRight', '0')
        border.set('offsetTop', '0')
        border.set('offsetBottom', '400')
        border.set('connect', '0')
        border.set('ignoreMargin', '0')

        para_props = self.header_root.find('.//hh:paraProperties', self.namespaces)
        if para_props is not None:
            para_props.append(new_node)

        self._hr_para_pr_id = new_id
        return self._hr_para_pr_id

    def _handle_horizontal_rule(self):
        """Handle horizontal rule block.

        Renders as an empty paragraph with a bottom border line.

        Returns:
            XML string of the horizontal rule paragraph
        """
        hr_para_pr = self._get_hr_para_pr()
        para = self._create_para_elem(
            style_id=self.normal_style_id,
            para_pr_id=hr_para_pr
        )
        # Empty run to create a valid paragraph
        run = self._create_text_run_elem(" ")
        para.append(run)
        return self._elem_to_str(para)

    def _get_row_type(self, row_idx, header_row_count, total_body_rows):
        """Determine row type: HEADER, TOP, MIDDLE, or BOTTOM.

        Args:
            row_idx: Current row index (0-based, across all rows)
            header_row_count: Number of header rows
            total_body_rows: Total number of body rows

        Returns:
            One of: 'HEADER', 'TOP', 'MIDDLE', 'BOTTOM'
        """
        if row_idx < header_row_count:
            return 'HEADER'

        body_idx = row_idx - header_row_count
        if total_body_rows <= 1:
            # If only one body row, it's both TOP and BOTTOM; use TOP
            return 'TOP'

        if body_idx == 0:
            return 'TOP'
        elif body_idx == total_body_rows - 1:
            return 'BOTTOM'
        else:
            return 'MIDDLE'

    def _get_col_type(self, col_idx, total_cols):
        """Determine column type: LEFT, CENTER, or RIGHT.

        Args:
            col_idx: Current column index (0-based)
            total_cols: Total number of columns

        Returns:
            One of: 'LEFT', 'CENTER', 'RIGHT'
        """
        if total_cols <= 1:
            return 'LEFT'

        if col_idx == 0:
            return 'LEFT'
        elif col_idx == total_cols - 1:
            return 'RIGHT'
        else:
            return 'CENTER'

    def _get_cell_style_key(self, row_type, col_type):
        """Get the cell style key from row and column types.

        Args:
            row_type: 'HEADER', 'TOP', 'MIDDLE', or 'BOTTOM'
            col_type: 'LEFT', 'CENTER', or 'RIGHT'

        Returns:
            Cell style key like 'HEADER_LEFT', 'MIDDLE_CENTER', etc.
        """
        return f'{row_type}_{col_type}'

    def _handle_table_elem(self, content):
        """Handle table block and return Element (ElementTree version)."""
        # content = [attr, caption, specs, table_head, table_body, table_foot]
        # Row: [attr, [cell, ...]]
        # Cell: [attr, align, rowspan, colspan, [blocks]]

        specs = content[2]
        table_head = content[3]
        table_bodies = content[4]
        table_foot = content[5]

        # Flatten Rows from head, bodies, foot
        # Track which rows are header rows for cell styling
        all_rows = []
        header_row_count = 0

        # Head Rows
        head_rows = table_head[1]
        for row in head_rows:
            all_rows.append(row)
            header_row_count += 1

        # Body Rows (count these separately)
        body_row_count = 0
        for body in table_bodies:
            inter_headers = body[2]
            for row in inter_headers:
                all_rows.append(row)
                body_row_count += 1
            main_rows = body[3]
            for row in main_rows:
                all_rows.append(row)
                body_row_count += 1

        # Foot Rows (treat as body)
        foot_rows = table_foot[1]
        for row in foot_rows:
            all_rows.append(row)
            body_row_count += 1

        if not all_rows:
            return None

        row_cnt = len(all_rows)
        col_cnt = len(specs)

        # Calculate Widths using config
        TOTAL_TABLE_WIDTH = self.template_table_width if self.template_table_width else self.config.TABLE_WIDTH

        # Use proportional widths from colspecs if available (from dash counts)
        has_proportional = any(
            s[1].get("t") == "ColWidth" for s in specs
        )
        if has_proportional:
            col_widths = []
            for spec in specs:
                width_info = spec[1]
                if width_info.get("t") == "ColWidth":
                    col_widths.append(int(width_info["c"] * TOTAL_TABLE_WIDTH))
                else:
                    col_widths.append(int(TOTAL_TABLE_WIDTH / col_cnt))
        else:
            col_widths = [int(TOTAL_TABLE_WIDTH / col_cnt) for _ in specs]

        # Generate IDs
        tbl_id = str(int(time.time() * 1000) % 100000000 + random.randint(0, 10000))

        # Create paragraph > run > table structure
        para = self._create_para_elem(style_id=self.normal_style_id, para_pr_id=self.normal_para_pr_id)
        run = self._add_elem(para, NS_PARA, 'run', {'charPrIDRef': '0'})

        # Table element
        tbl = self._add_elem(run, NS_PARA, 'tbl', {
            'id': tbl_id,
            'zOrder': '0',
            'numberingType': 'TABLE',
            'textWrap': 'TOP_AND_BOTTOM',
            'textFlow': 'BOTH_SIDES',
            'lock': '0',
            'dropcapstyle': 'None',
            'pageBreak': 'CELL',
            'repeatHeader': '1',
            'rowCnt': str(row_cnt),
            'colCnt': str(col_cnt),
            'cellSpacing': '0',
            'borderFillIDRef': '3',
            'noAdjust': '0'
        })

        # Table properties
        self._add_elem(tbl, NS_PARA, 'sz', {
            'width': str(TOTAL_TABLE_WIDTH),
            'widthRelTo': 'ABSOLUTE',
            'height': str(row_cnt * 1000),
            'heightRelTo': 'ABSOLUTE',
            'protect': '0'
        })
        self._add_elem(tbl, NS_PARA, 'pos', {
            'treatAsChar': '0',
            'affectLSpacing': '0',
            'flowWithText': '1',
            'allowOverlap': '0',
            'holdAnchorAndSO': '0',
            'vertRelTo': 'PARA',
            'horzRelTo': 'COLUMN',
            'vertAlign': 'TOP',
            'horzAlign': 'LEFT',
            'vertOffset': '0',
            'horzOffset': '0'
        })
        self._add_elem(tbl, NS_PARA, 'outMargin', {
            'left': '0', 'right': '0', 'top': '0',
            'bottom': str(self.config.TABLE_OUT_MARGIN_BOTTOM)
        })
        cell_margin = self.config.CELL_MARGIN_DEFAULT
        self._add_elem(tbl, NS_PARA, 'inMargin', {
            'left': str(cell_margin['left']),
            'right': str(cell_margin['right']),
            'top': str(cell_margin['top']),
            'bottom': str(cell_margin['bottom'])
        })

        # Generate Rows
        occupied_cells = set()
        curr_row_addr = 0

        for row in all_rows:
            cells = row[1]
            tr = self._add_elem(tbl, NS_PARA, 'tr')

            curr_col_addr = 0
            for cell in cells:
                # Find next free column
                while (curr_row_addr, curr_col_addr) in occupied_cells:
                    curr_col_addr += 1

                actual_col = curr_col_addr

                cell_align = cell[1]  # e.g., 'AlignLeft', 'AlignCenter', 'AlignRight', 'AlignDefault'
                rowspan = cell[2]
                colspan = cell[3]
                cell_blocks = cell[4]

                # Mark occupied cells
                for r in range(rowspan):
                    for c in range(colspan):
                        occupied_cells.add((curr_row_addr + r, actual_col + c))

                # Calculate cell width
                cell_width = sum(
                    col_widths[actual_col + i] if actual_col + i < len(col_widths)
                    else int(TOTAL_TABLE_WIDTH / col_cnt)
                    for i in range(colspan)
                )

                sublist_id = str(int(time.time() * 100000) % 1000000000 + random.randint(0, 100000))

                # Determine cell style based on position
                row_type = self._get_row_type(curr_row_addr, header_row_count, body_row_count)
                col_type = self._get_col_type(actual_col, col_cnt)
                cell_style_key = self._get_cell_style_key(row_type, col_type)

                # Get cell style from placeholder or use defaults
                cell_style = self.cell_styles.get(cell_style_key, {})

                # Get borderFillIDRef from cell style or use default
                border_fill_id = cell_style.get('borderFillIDRef', str(self.table_border_fill_id))

                # Get cell margin from cell style or use defaults
                default_margin = self.config.CELL_MARGIN_DEFAULT
                cell_margin = cell_style.get('cellMargin', {
                    'left': str(default_margin['left']),
                    'right': str(default_margin['right']),
                    'top': str(default_margin['top']),
                    'bottom': str(default_margin['bottom'])
                })

                # Cell element
                tc = self._add_elem(tr, NS_PARA, 'tc', {
                    'name': '',
                    'header': '1' if row_type == 'HEADER' else '0',
                    'hasMargin': '0',
                    'protect': '0',
                    'editable': '0',
                    'dirty': '0',
                    'borderFillIDRef': border_fill_id
                })

                # SubList with content
                sublist = self._add_elem(tc, NS_PARA, 'subList', {
                    'id': sublist_id,
                    'textDirection': 'HORIZONTAL',
                    'lineWrap': 'BREAK',
                    'vertAlign': 'TOP',
                    'linkListIDRef': '0',
                    'linkListNextIDRef': '0',
                    'textWidth': '0',
                    'textHeight': '0',
                    'hasTextRef': '0',
                    'hasNumRef': '0'
                })

                # Determine paragraph alignment for cell content
                hwpx_align = self._pandoc_align_to_hwpx(cell_align)

                # Process cell blocks and add to sublist
                cell_content_xml = self._process_blocks(cell_blocks)
                if cell_content_xml.strip():
                    wrapper = f'<root xmlns:hp="{NS_PARA}" xmlns:hc="{NS_CORE}">{cell_content_xml}</root>'
                    for elem in ET.fromstring(wrapper):
                        # Apply alignment to paragraph elements
                        if hwpx_align and elem.tag.endswith('}p'):
                            aligned_pr = self._get_aligned_para_pr(hwpx_align)
                            if aligned_pr:
                                elem.set('paraPrIDRef', aligned_pr)
                        sublist.append(elem)

                # Cell properties
                self._add_elem(tc, NS_PARA, 'cellAddr', {'colAddr': str(actual_col), 'rowAddr': str(curr_row_addr)})
                self._add_elem(tc, NS_PARA, 'cellSpan', {'colSpan': str(colspan), 'rowSpan': str(rowspan)})
                self._add_elem(tc, NS_PARA, 'cellSz', {'width': str(cell_width), 'height': '1000'})
                self._add_elem(tc, NS_PARA, 'cellMargin', {
                    'left': str(cell_margin.get('left', '510')),
                    'right': str(cell_margin.get('right', '510')),
                    'top': str(cell_margin.get('top', '141')),
                    'bottom': str(cell_margin.get('bottom', '141'))
                })

                curr_col_addr += colspan

            curr_row_addr += 1

        return para

    def _handle_table(self, content):
        """Handle table block (legacy wrapper)."""
        elem = self._handle_table_elem(content)
        if elem is None:
            return ""
        return self._elem_to_str(elem)

    # --- INLINE PROCESSING & FORMATTING ---

    def _process_inlines(self, inlines, base_char_pr_id=0, active_formats=None):
        """Process inlines and return XML string.

        This is a wrapper around _process_inlines_to_elems for backward compatibility.
        """
        if not isinstance(inlines, list):
            return ""

        # Create temporary parent element
        temp_parent = ET.Element('temp')
        self._process_inlines_to_elems(inlines, temp_parent, base_char_pr_id, active_formats)

        # Serialize children
        return ''.join(ET.tostring(child, encoding='unicode') for child in temp_parent)

    def _create_linebreak_run_elem(self, char_pr_id=0):
        """Create a run element containing a line break."""
        run = self._create_run_elem(char_pr_id)
        t_elem = self._add_elem(run, NS_PARA, 't')
        self._add_elem(t_elem, NS_PARA, 'lineBreak')
        return run

    def _process_inlines_to_elems(self, inlines, parent_elem, base_char_pr_id=0, active_formats=None):
        """Process inline elements and append them to parent element.

        This is the Element-based version of _process_inlines.
        Instead of returning a string, it appends run elements directly to parent.
        """
        if not isinstance(inlines, list):
            return

        if active_formats is None:
            active_formats = set()

        def get_current_id():
            return self._get_char_pr_id(base_char_pr_id, active_formats)

        for item in inlines:
            i_type = item.get('t')
            i_content = item.get('c')

            if i_type == 'Str':
                run = self._create_text_run_elem(i_content, char_pr_id=get_current_id())
                parent_elem.append(run)

            elif i_type == 'Space':
                run = self._create_text_run_elem(" ", char_pr_id=get_current_id())
                parent_elem.append(run)

            elif i_type == 'Strong':
                new_formats = active_formats.copy()
                new_formats.add('BOLD')
                self._process_inlines_to_elems(i_content, parent_elem, base_char_pr_id, new_formats)

            elif i_type == 'Emph':
                new_formats = active_formats.copy()
                new_formats.add('ITALIC')
                self._process_inlines_to_elems(i_content, parent_elem, base_char_pr_id, new_formats)

            elif i_type == 'Underline':
                new_formats = active_formats.copy()
                new_formats.add('UNDERLINE')
                self._process_inlines_to_elems(i_content, parent_elem, base_char_pr_id, new_formats)

            elif i_type == 'Superscript':
                new_formats = active_formats.copy()
                new_formats.add('SUPERSCRIPT')
                self._process_inlines_to_elems(i_content, parent_elem, base_char_pr_id, new_formats)

            elif i_type == 'Subscript':
                new_formats = active_formats.copy()
                new_formats.add('SUBSCRIPT')
                self._process_inlines_to_elems(i_content, parent_elem, base_char_pr_id, new_formats)

            elif i_type == 'Link':
                text_inlines = i_content[1]
                target_url = i_content[2][0]

                # Add field begin element
                parent_elem.append(self._create_field_begin_elem(target_url))

                # Add link text with styling
                new_formats = active_formats.copy()
                new_formats.add('UNDERLINE')
                new_formats.add('COLOR_BLUE')
                self._process_inlines_to_elems(text_inlines, parent_elem, base_char_pr_id, new_formats)

                # Add field end element
                parent_elem.append(self._create_field_end_elem())

            elif i_type == 'Note':
                note_blocks = i_content
                footnote_elem = self._create_footnote_elem(note_blocks)
                parent_elem.append(footnote_elem)

            elif i_type == 'Code':
                run = self._create_text_run_elem(i_content[1], char_pr_id=get_current_id())
                parent_elem.append(run)

            elif i_type == 'Image':
                img_elem = self._handle_image_elem(i_content, char_pr_id=get_current_id())
                parent_elem.append(img_elem)

            elif i_type == 'SoftBreak':
                run = self._create_text_run_elem(" ", char_pr_id=get_current_id())
                parent_elem.append(run)

            elif i_type == 'LineBreak':
                run = self._create_linebreak_run_elem(char_pr_id=get_current_id())
                parent_elem.append(run)

    def _parse_dimension(self, val_str):
        if not val_str:
            return None

        # Lowercase and remove whitespace
        s = val_str.lower().strip()

        # Regex to split value and unit
        import re
        match = re.match(r'^([0-9\.]+)([a-z%]+)?$', s)
        if not match:
            return None

        val = float(match.group(1))
        unit = match.group(2)

        # HWP Unit: 1 mm = 283.465 LUnit
        LUNIT_PER_MM = self.config.LUNIT_PER_MM

        mm_val = 0

        if not unit or unit == 'px':
            # Default or PX. Pandoc usually 96dpi.
            # 1 px = 25.4 / 96 mm
            mm_val = val * (25.4 / 96.0)
        elif unit == 'in':
            mm_val = val * 25.4
        elif unit == 'cm':
            mm_val = val * 10.0
        elif unit == 'mm':
            mm_val = val
        elif unit == 'pt':
            # 1 pt = 1/72 inch ? or 1/72.27?
            # 1 pt = 25.4 / 72 mm
            mm_val = val * (25.4 / 72.0)
        elif unit == '%':
             # Percentage of what? Page width?
             # Let's assume % of page content width (approx 150mm?)
             # For robustness, treat as relative scaling not absolute?
             # But HWPX needs absolute.
             # Let's just assume a standard width of 100% = 150mm
             mm_val = val * 1.5
        else:
             # Unknown, treat as px?
             mm_val = val * (25.4 / 96.0)

        return int(mm_val * LUNIT_PER_MM)

    def _handle_image_elem(self, content, char_pr_id=0):
        """Handle image inline and return Element (ElementTree version)."""
        # content = [attr, caption, [target, title]]
        # attr: [id, [classes], [[key, val]]]
        attr = content[0]
        caption = content[1]  # list of inlines
        target = content[2]

        target_url = target[0]

        # Validate image path against directory traversal
        try:
            self._validate_image_path(target_url, self.input_dir)
        except SecurityError as e:
            logger.warning("Skipping image with invalid path: %s", e)
            return self._create_text_run_elem(f"[Image: {target_url}]", char_pr_id)

        # Validate image count limit
        if len(self.images) >= self.config.MAX_IMAGE_COUNT:
            logger.warning(
                "Image count limit reached (%d). Skipping image: %s",
                self.config.MAX_IMAGE_COUNT, target_url
            )
            return self._create_text_run_elem(f"[Image limit exceeded: {target_url}]", char_pr_id)

        # Parse Attributes for Width/Height
        attrs_map = dict(attr[2])

        width_attr = attrs_map.get('width')
        height_attr = attrs_map.get('height')

        # Default Size (from config)
        width_hwp = self.config.IMAGE_DEFAULT_WIDTH
        height_hwp = self.config.IMAGE_DEFAULT_HEIGHT

        w_parsed = self._parse_dimension(width_attr)
        h_parsed = self._parse_dimension(height_attr)

        # --- Pillow Auto-Sizing & Max Width Logic ---
        px_width = 0
        px_height = 0

        if w_parsed and h_parsed:
            width_hwp = w_parsed
            height_hwp = h_parsed
        elif w_parsed:
            width_hwp = w_parsed

        # If size missing or partial, try reading file
        should_read_file = (not w_parsed) or (not h_parsed)

        if should_read_file:
            image_found = False
            try:
                candidates = [target_url]
                if self.input_dir:
                    candidates.append(os.path.join(self.input_dir, target_url))

                for cand in candidates:
                    if os.path.exists(cand):
                        with Image.open(cand) as im:
                            px_width, px_height = im.size
                            image_found = True
                        break
            except Exception:
                pass

            if image_found:
                LUNIT_PER_PX = self.config.LUNIT_PER_PX

                calc_w = int(px_width * LUNIT_PER_PX)
                calc_h = int(px_height * LUNIT_PER_PX)

                if not w_parsed and not h_parsed:
                    width_hwp = calc_w
                    height_hwp = calc_h
                elif w_parsed and not h_parsed:
                    ratio = px_height / px_width
                    height_hwp = int(w_parsed * ratio)
                elif not w_parsed and h_parsed:
                    ratio = px_width / px_height
                    width_hwp = int(h_parsed * ratio)

        # --- Max Width Constraint (from config) ---
        MAX_WIDTH_HWP = self.config.IMAGE_MAX_WIDTH

        if width_hwp > MAX_WIDTH_HWP:
            ratio = MAX_WIDTH_HWP / width_hwp
            width_hwp = MAX_WIDTH_HWP
            height_hwp = int(height_hwp * ratio)

        width = width_hwp
        height = height_hwp

        # Generate Binary ID
        timestamp = int(time.time() * 1000)
        rand = random.randint(0, 1000000)
        binary_item_id = f"img_{timestamp}_{rand}"

        # Extract Extension
        ext = "png"
        lower_url = target_url.lower()
        if lower_url.endswith('.jpg') or lower_url.endswith('.jpeg'):
            ext = "jpg"
        elif lower_url.endswith('.gif'):
            ext = "gif"
        elif lower_url.endswith('.bmp'):
            ext = "bmp"

        # Store for output
        self.images.append({
            'id': binary_item_id,
            'path': target_url,
            'ext': ext
        })

        # Generate Element
        pic_id = str(timestamp % 100000000 + rand)
        inst_id = str(random.randint(10000000, 99999999))

        run = self._create_run_elem(char_pr_id)

        pic = self._add_elem(run, NS_PARA, 'pic', {
            'id': pic_id,
            'zOrder': '0',
            'numberingType': 'NONE',
            'textWrap': 'TOP_AND_BOTTOM',
            'textFlow': 'BOTH_SIDES',
            'lock': '0',
            'dropcapstyle': 'None',
            'href': '',
            'groupLevel': '0',
            'instid': inst_id,
            'reverse': '0'
        })

        self._add_elem(pic, NS_PARA, 'offset', {'x': '0', 'y': '0'})
        self._add_elem(pic, NS_PARA, 'orgSz', {'width': str(width), 'height': str(height)})
        self._add_elem(pic, NS_PARA, 'curSz', {'width': str(width), 'height': str(height)})
        self._add_elem(pic, NS_PARA, 'flip', {'horizontal': '0', 'vertical': '0'})
        self._add_elem(pic, NS_PARA, 'rotationInfo', {
            'angle': '0', 'centerX': '0', 'centerY': '0', 'rotateimage': '1'
        })

        # renderingInfo with matrices
        render_info = self._add_elem(pic, NS_PARA, 'renderingInfo')
        for matrix_name in ['transMatrix', 'scaMatrix', 'rotMatrix']:
            self._add_elem(render_info, NS_CORE, matrix_name, {
                'e1': '1', 'e2': '0', 'e3': '0', 'e4': '0', 'e5': '1', 'e6': '0'
            })

        # img element (in core namespace)
        self._add_elem(pic, NS_CORE, 'img', {
            'binaryItemIDRef': binary_item_id,
            'bright': '0',
            'contrast': '0',
            'effect': 'REAL_PIC',
            'alpha': '0'
        })

        # imgRect with corner points
        img_rect = self._add_elem(pic, NS_PARA, 'imgRect')
        self._add_elem(img_rect, NS_CORE, 'pt0', {'x': '0', 'y': '0'})
        self._add_elem(img_rect, NS_CORE, 'pt1', {'x': str(width), 'y': '0'})
        self._add_elem(img_rect, NS_CORE, 'pt2', {'x': str(width), 'y': str(height)})
        self._add_elem(img_rect, NS_CORE, 'pt3', {'x': '0', 'y': str(height)})

        self._add_elem(pic, NS_PARA, 'imgClip', {'left': '0', 'right': '0', 'top': '0', 'bottom': '0'})
        self._add_elem(pic, NS_PARA, 'inMargin', {'left': '0', 'right': '0', 'top': '0', 'bottom': '0'})
        self._add_elem(pic, NS_PARA, 'imgDim', {'dimwidth': '0', 'dimheight': '0'})
        self._add_elem(pic, NS_PARA, 'effects')

        self._add_elem(pic, NS_PARA, 'sz', {
            'width': str(width),
            'widthRelTo': 'ABSOLUTE',
            'height': str(height),
            'heightRelTo': 'ABSOLUTE',
            'protect': '0'
        })
        self._add_elem(pic, NS_PARA, 'pos', {
            'treatAsChar': '1',
            'affectLSpacing': '0',
            'flowWithText': '1',
            'allowOverlap': '1',
            'holdAnchorAndSO': '0',
            'vertRelTo': 'PARA',
            'horzRelTo': 'COLUMN',
            'vertAlign': 'TOP',
            'horzAlign': 'LEFT',
            'vertOffset': '0',
            'horzOffset': '0'
        })
        self._add_elem(pic, NS_PARA, 'outMargin', {'left': '0', 'right': '0', 'top': '0', 'bottom': '0'})
        self._add_elem(pic, NS_PARA, 'shapeComment')

        return run

    def _create_field_begin_elem(self, url):
        """Create field begin element for hyperlink (ElementTree version)."""
        fid = str(int(time.time() * 1000) % 100000000)
        self.last_field_id = fid

        # Command needs escaping for HWPX format
        command_url = url.replace(':', r'\:').replace('?', r'\?')
        command_str = f"{command_url};1;5;-1;"

        # Create run > ctrl > fieldBegin structure
        run = self._create_run_elem(char_pr_id=0)
        ctrl = self._add_elem(run, NS_PARA, 'ctrl')
        field_begin = self._add_elem(ctrl, NS_PARA, 'fieldBegin', {
            'id': fid,
            'type': 'HYPERLINK',
            'name': '',
            'editable': '0',
            'dirty': '1',
            'zorder': '-1',
            'fieldid': fid,
            'metaTag': ''
        })

        # Add parameters
        params = self._add_elem(field_begin, NS_PARA, 'parameters', {'cnt': '6', 'name': ''})
        self._add_elem(params, NS_PARA, 'integerParam', {'name': 'Prop'}, text='0')
        self._add_elem(params, NS_PARA, 'stringParam', {'name': 'Command'}, text=command_str)
        self._add_elem(params, NS_PARA, 'stringParam', {'name': 'Path'}, text=url)
        self._add_elem(params, NS_PARA, 'stringParam', {'name': 'Category'}, text='HWPHYPERLINK_TYPE_URL')
        self._add_elem(params, NS_PARA, 'stringParam', {'name': 'TargetType'}, text='HWPHYPERLINK_TARGET_HYPERLINK')
        self._add_elem(params, NS_PARA, 'stringParam', {'name': 'DocOpenType'}, text='HWPHYPERLINK_JUMP_DONTCARE')

        return run

    def _create_field_end_elem(self):
        """Create field end element (ElementTree version)."""
        fid = getattr(self, 'last_field_id', '0')
        run = self._create_run_elem(char_pr_id=0)
        ctrl = self._add_elem(run, NS_PARA, 'ctrl')
        self._add_elem(ctrl, NS_PARA, 'fieldEnd', {'beginIDRef': fid, 'fieldid': fid})
        return run

    def _create_footnote_elem(self, blocks):
        """Create footnote element (ElementTree version)."""
        inst_id = str(random.randint(1000000, 999999999))

        # Create run > ctrl > footNote structure
        run = self._create_run_elem(char_pr_id=0)
        ctrl = self._add_elem(run, NS_PARA, 'ctrl')
        footnote = self._add_elem(ctrl, NS_PARA, 'footNote', {
            'number': '0',
            'instId': inst_id
        })

        # Add autoNum
        self._add_elem(footnote, NS_PARA, 'autoNum', {
            'num': '0',
            'numType': 'FOOTNOTE'
        })

        # Add subList with content
        sublist = self._add_elem(footnote, NS_PARA, 'subList', {
            'id': inst_id,
            'textDirection': 'HORIZONTAL',
            'lineWrap': 'BREAK',
            'vertAlign': 'TOP',
            'linkListIDRef': '0',
            'linkListNextIDRef': '0',
            'textWidth': '0',
            'textHeight': '0',
            'hasTextRef': '0',
            'hasNumRef': '0'
        })

        # Process blocks and add to sublist
        # Note: _process_blocks returns string, so we parse it back
        body_xml = self._process_blocks(blocks)
        if body_xml.strip():
            # Wrap in root element for parsing
            wrapper = f'<root xmlns:hp="{NS_PARA}" xmlns:hc="{NS_CORE}">{body_xml}</root>'
            for elem in ET.fromstring(wrapper):
                sublist.append(elem)

        return run

    def _get_char_pr_id(self, base_id, active_formats):
        # 0. If no format updates, return base_id
        if not active_formats:
            return base_id

        base_id = str(base_id)

        # 1. Check Cache
        # key = (base_id, frozen_formats)
        # frozen set of list?
        # active_formats is set.
        cache_key = (base_id, frozenset(active_formats))
        if cache_key in self.char_pr_cache:
            return self.char_pr_cache[cache_key]

        # 2. Create New CharPr
        if self.header_root is None:
            return base_id

        base_node = self.header_root.find(f'.//hh:charPr[@id="{base_id}"]', self.namespaces)
        if base_node is None:
            base_node = self.header_root.find('.//hh:charPr[@id="0"]', self.namespaces)
            if base_node is None:
                 return base_id

        new_node = copy.deepcopy(base_node)
        self.max_char_pr_id += 1
        new_id = str(self.max_char_pr_id)
        new_node.set('id', new_id)

        # Modify properties based on formats
        if 'BOLD' in active_formats:
            if new_node.find('hh:bold', self.namespaces) is None:
                ET.SubElement(new_node, f'{{{NS_HEAD}}}bold')

        if 'ITALIC' in active_formats:
            if new_node.find('hh:italic', self.namespaces) is None:
                ET.SubElement(new_node, f'{{{NS_HEAD}}}italic')

        if 'UNDERLINE' in active_formats:
            ul = new_node.find('hh:underline', self.namespaces)
            if ul is None:
                ul = ET.SubElement(new_node, f'{{{NS_HEAD}}}underline')
            ul.set('type', 'BOTTOM')
            ul.set('shape', 'SOLID')
            ul.set('color', '#000000')

        if 'COLOR_BLUE' in active_formats:
            # <hh:textColor value="#0000FF"/>
            # Note: HWPX color logic sometimes weird, but #RRGGBB standard often works.
            # Sample: <hh:textColor value="#000000"/>
            # Blue: #0000FF
            tc = new_node.find('hh:textColor', self.namespaces)
            if tc is None:
                tc = ET.SubElement(new_node, f'{{{NS_HEAD}}}textColor')
            tc.set('value', '#0000FF')

            # Also force underline color to Blue if underline exists?
            ul = new_node.find('hh:underline', self.namespaces)
            if ul is not None:
                ul.set('color', '#0000FF')

        if 'SUPERSCRIPT' in active_formats:
             sub = new_node.find('hh:subscript', self.namespaces)
             if sub is not None:
                 new_node.remove(sub)
             if new_node.find('hh:supscript', self.namespaces) is None:
                ET.SubElement(new_node, f'{{{NS_HEAD}}}supscript')

        elif 'SUBSCRIPT' in active_formats:
             sup = new_node.find('hh:supscript', self.namespaces)
             if sup is not None:
                 new_node.remove(sup)
             if new_node.find('hh:subscript', self.namespaces) is None:
                ET.SubElement(new_node, f'{{{NS_HEAD}}}subscript')

        # 4. Add to Header
        char_props = self.header_root.find('.//hh:charProperties', self.namespaces)
        if char_props is not None:
            char_props.append(new_node)

        # 5. Update Cache
        self.char_pr_cache[cache_key] = new_id

        return new_id

    # --- LIST HANDLING ---

    # Standard Numbering Definitions
    ORDERED_NUM_XML = """
    <hh:numbering id="{id}" start="1" xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">
      <hh:paraHead start="1" level="1" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="DIGIT" charPrIDRef="4294967295" checkable="0">^1.</hh:paraHead>
      <hh:paraHead start="1" level="2" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="LATIN_CAPITAL" charPrIDRef="4294967295" checkable="0">^2.</hh:paraHead>
      <hh:paraHead start="1" level="3" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="ROMAN_SMALL" charPrIDRef="4294967295" checkable="0">^3.</hh:paraHead>
      <hh:paraHead start="1" level="4" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="DIGIT" charPrIDRef="4294967295" checkable="0">^4.</hh:paraHead>
      <hh:paraHead start="1" level="5" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="LATIN_CAPITAL" charPrIDRef="4294967295" checkable="0">^5.</hh:paraHead>
      <hh:paraHead start="1" level="6" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="ROMAN_SMALL" charPrIDRef="4294967295" checkable="0">^6.</hh:paraHead>
      <hh:paraHead start="1" level="7" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="DIGIT" charPrIDRef="4294967295" checkable="0">^7.</hh:paraHead>
    </hh:numbering>
    """

    BULLET_NUM_XML = """
    <hh:numbering id="{id}" start="1" xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">
      <hh:paraHead start="1" level="1" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="DIGIT" charPrIDRef="4294967295" checkable="0">ㅇ</hh:paraHead>
      <hh:paraHead start="1" level="2" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="DIGIT" charPrIDRef="4294967295" checkable="0">-</hh:paraHead>
      <hh:paraHead start="1" level="3" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="DIGIT" charPrIDRef="4294967295" checkable="0">∙</hh:paraHead>
      <hh:paraHead start="1" level="4" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="DIGIT" charPrIDRef="4294967295" checkable="0">●</hh:paraHead>
      <hh:paraHead start="1" level="5" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="DIGIT" charPrIDRef="4294967295" checkable="0">○</hh:paraHead>
      <hh:paraHead start="1" level="6" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="DIGIT" charPrIDRef="4294967295" checkable="0">■</hh:paraHead>
      <hh:paraHead start="1" level="7" align="LEFT" useInstWidth="1" autoIndent="0" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="DIGIT" charPrIDRef="4294967295" checkable="0">●</hh:paraHead>
    </hh:numbering>
    """

    def _init_numbering_structure(self, root):
        # Just ensure hh:numberings exists
        numberings_node = root.find('.//hh:numberings', self.namespaces)
        if numberings_node is None:
            # Insert before paraProperties usually? Order matters in Head?
            # HWPX Head order: ... numberings, paraProperties, style ...
            # Let's verify order or just append to root and let HWP handle?
            # Safe to append to root for now, or find insertion point.
            # But XML standard requires order.
            # root is <hh:head>. Children: ...
            numberings_node = ET.SubElement(root, f'{{{NS_HEAD}}}numberings')

    def _create_numbering(self, type='ORDERED', start_num=1):
        # 1. Generate New ID
        # Find max currently in header to be safe (since we append dynamically)
        root = self.header_root
        max_num_id = 0
        for num in root.findall('.//hh:numbering', self.namespaces):
            nid = int(num.get('id', 0))
            if nid > max_num_id:
                max_num_id = nid

        new_id = str(max_num_id + 1)

        # 2. Get Template
        if type == 'ORDERED':
            template = self.ORDERED_NUM_XML
        else:
            template = self.BULLET_NUM_XML

        # 3. Format and Inject
        xml_str = template.format(id=new_id).strip()
        new_node = ET.fromstring(xml_str)

        # Set start number if needed (Ordered)
        new_node.set('start', str(start_num))
        # Note: XML template has paraHead start="1".
        # If we want the list to start at X, 'start' on numbering sets the global start?
        # Or individual paraHead?
        # HWPX numbering 'start' attribute is usually 1.
        # But if we want to start at 4?
        # Actually, paraHead 'start' controls the sequence reset?
        # No, hh:numbering start="X" is the main one.

        numberings_node = root.find('.//hh:numberings', self.namespaces)
        if numberings_node is None:
             self._init_numbering_structure(root)
             numberings_node = root.find('.//hh:numberings', self.namespaces)

        numberings_node.append(new_node)
        return new_id

    def _get_list_para_pr(self, num_id, level):
        base_id = self.normal_para_pr_id
        base_node = self.header_root.find(f'.//hh:paraPr[@id="{base_id}"]', self.namespaces)
        if base_node is None:
            return base_id

        new_node = copy.deepcopy(base_node)
        self.max_para_pr_id += 1
        new_id = str(self.max_para_pr_id)
        new_node.set('id', new_id)

        heading = new_node.find('hh:heading', self.namespaces)
        if heading is None:
            heading = ET.SubElement(new_node, f'{{{NS_HEAD}}}heading')
        heading.set('type', 'NUMBER')
        heading.set('idRef', str(num_id))
        heading.set('level', str(level))

        indent_per_level = self.config.LIST_INDENT_PER_LEVEL
        current_indent = (level) * indent_per_level

        for margin_node in new_node.findall('.//hc:left', self.namespaces):
            original_val = int(margin_node.get('value', 0))
            new_val = original_val + current_indent
            margin_node.set('value', str(new_val))

        hanging_val = self.config.LIST_HANGING_INDENT
        for intent_node in new_node.findall('.//hc:intent', self.namespaces):
            intent_node.set('value', str(-hanging_val))

        for left_node in new_node.findall('.//hc:left', self.namespaces):
            val = (level + 1) * hanging_val
            left_node.set('value', str(val))

        para_props = self.header_root.find('.//hh:paraProperties', self.namespaces)
        if para_props is not None:
            para_props.append(new_node)

        return new_id

    def _handle_bullet_list_elem(self, content, level=0):
        """Handle bullet list and return list of Elements (ElementTree version)."""
        if level >= self.config.MAX_NESTING_DEPTH:
            logger.warning("Bullet list nesting depth limit reached (%d). Flattening.", self.config.MAX_NESTING_DEPTH)
            level = self.config.MAX_NESTING_DEPTH - 1

        # Check if template defines style for this list level
        list_key = ('BULLET', level + 1)  # Template uses 1-indexed levels

        if list_key in self.list_styles:
            style_info = self.list_styles[list_key]
            mode = style_info.get('mode', 'prefix')

            if mode == 'numbering':
                # USE TEMPLATE NUMBERING
                return self._handle_template_numbering_list_elem(content, 'BULLET', level)
            else:
                # USE PREFIX MODE
                return self._handle_prefix_list_elem(content, 'BULLET', level)

        # FALLBACK to existing auto-numbering (create new)
        num_id = self._create_numbering('BULLET')

        elements = []
        for item_blocks in content:
            for block in item_blocks:
                b_type = block.get('t')
                b_content = block.get('c')

                list_para_pr = self._get_list_para_pr(num_id, level)

                if b_type == 'Para' or b_type == 'Plain':
                    para = self._create_para_elem(style_id=self.normal_style_id, para_pr_id=list_para_pr)
                    self._process_inlines_to_elems(b_content, para)
                    elements.append(para)
                elif b_type == 'BulletList':
                    elements.extend(self._handle_bullet_list_elem(b_content, level=level+1))
                elif b_type == 'OrderedList':
                    elements.extend(self._handle_ordered_list_elem(b_content, level=level+1))
                else:
                    # For other block types, use legacy processing
                    block_xml = self._process_blocks([block])
                    if block_xml.strip():
                        wrapper = f'<root xmlns:hp="{NS_PARA}" xmlns:hc="{NS_CORE}">{block_xml}</root>'
                        for elem in ET.fromstring(wrapper):
                            elements.append(elem)

        return elements

    def _handle_bullet_list(self, content, level=0):
        """Handle bullet list (legacy wrapper returning string)."""
        elements = self._handle_bullet_list_elem(content, level)
        return "\n".join(self._elem_to_str(elem) for elem in elements)

    def _handle_ordered_list_elem(self, content, level=0):
        """Handle ordered list and return list of Elements (ElementTree version)."""
        if level >= self.config.MAX_NESTING_DEPTH:
            logger.warning("Ordered list nesting depth limit reached (%d). Flattening.", self.config.MAX_NESTING_DEPTH)
            level = self.config.MAX_NESTING_DEPTH - 1

        # content = [ [start, style, delim], [items] ]
        attrs = content[0]
        start_num = attrs[0]  # The start number
        items = content[1]

        # Check if template defines style for this list level
        list_key = ('ORDERED', level + 1)  # Template uses 1-indexed levels

        if list_key in self.list_styles:
            style_info = self.list_styles[list_key]
            mode = style_info.get('mode', 'prefix')

            if mode == 'numbering':
                # USE TEMPLATE NUMBERING
                return self._handle_template_numbering_list_elem(items, 'ORDERED', level)
            else:
                # USE PREFIX MODE
                return self._handle_prefix_list_elem(items, 'ORDERED', level, start_num=start_num)

        # FALLBACK to existing auto-numbering (create new)
        num_id = self._create_numbering('ORDERED', start_num=start_num)

        elements = []
        for item_blocks in items:
            for block in item_blocks:
                b_type = block.get('t')
                b_content = block.get('c')

                list_para_pr = self._get_list_para_pr(num_id, level)

                if b_type == 'Para' or b_type == 'Plain':
                    para = self._create_para_elem(style_id=self.normal_style_id, para_pr_id=list_para_pr)
                    self._process_inlines_to_elems(b_content, para)
                    elements.append(para)
                elif b_type == 'BulletList':
                    elements.extend(self._handle_bullet_list_elem(b_content, level=level+1))
                elif b_type == 'OrderedList':
                    # Recursively handle nested ordered list
                    elements.extend(self._handle_ordered_list_elem(b_content, level=level+1))
                else:
                    # For other block types, use legacy processing
                    block_xml = self._process_blocks([block])
                    if block_xml.strip():
                        wrapper = f'<root xmlns:hp="{NS_PARA}" xmlns:hc="{NS_CORE}">{block_xml}</root>'
                        for elem in ET.fromstring(wrapper):
                            elements.append(elem)

        return elements

    def _handle_ordered_list(self, content, level=0):
        """Handle ordered list (legacy wrapper returning string)."""
        elements = self._handle_ordered_list_elem(content, level)
        return "\n".join(self._elem_to_str(elem) for elem in elements)

    def _format_list_prefix(self, prefix_template, list_type, counter):
        """Format list prefix, incrementing numbers/letters for ordered lists.

        Args:
            prefix_template: Original prefix from template (e.g., "1. ", "가. ")
            list_type: 'BULLET' or 'ORDERED'
            counter: Current item number (1-indexed)

        Returns:
            Formatted prefix string
        """
        if list_type == 'BULLET':
            return prefix_template  # Bullets don't change

        # For ordered lists, increment the number/letter
        # Arabic numerals: 1. → 2. → 3.
        if re.search(r'\d+', prefix_template):
            return re.sub(r'\d+', str(counter), prefix_template, count=1)

        # Korean syllables: 가. → 나. → 다.
        korean_jamo = '가나다라마바사아자차카타파하'
        match = re.search(r'[가-하]', prefix_template)
        if match and counter <= len(korean_jamo):
            return prefix_template[:match.start()] + korean_jamo[counter-1] + prefix_template[match.end():]

        # Fallback: return as-is
        return prefix_template

    def _handle_prefix_list_elem(self, content, list_type, level=0, start_num=1):
        """Handle list using prefix-based rendering (plain paragraphs with prefix text).

        Args:
            content: List items from AST
            list_type: 'BULLET' or 'ORDERED'
            level: Nesting level (0-indexed)
            start_num: Starting number for ordered lists

        Returns:
            List of paragraph Elements
        """
        elements = []
        list_key = (list_type, level + 1)  # 1-indexed in template
        style_info = self.list_styles.get(list_key, {})

        prefix = style_info.get('prefix', '')
        char_pr_id = int(style_info.get('charPrIDRef', 0))
        para_pr_id = int(style_info.get('paraPrIDRef', self.normal_para_pr_id))

        # For ordered lists, track counter to increment prefix numbers
        item_counter = start_num

        for item_blocks in content:
            for block in item_blocks:
                b_type = block.get('t')
                b_content = block.get('c')

                if b_type in ('Para', 'Plain'):
                    # Create paragraph with template styles
                    para = self._create_para_elem(
                        style_id=self.normal_style_id,
                        para_pr_id=para_pr_id
                    )

                    # Format prefix (increment numbers for ordered lists)
                    current_prefix = self._format_list_prefix(prefix, list_type, item_counter)

                    # Add prefix as first run
                    if current_prefix:
                        prefix_run = self._create_text_run_elem(current_prefix, char_pr_id)
                        para.append(prefix_run)

                    # Add content
                    self._process_inlines_to_elems(b_content, para, base_char_pr_id=char_pr_id)
                    elements.append(para)

                    item_counter += 1

                elif b_type == 'BulletList':
                    elements.extend(self._handle_bullet_list_elem(b_content, level=level+1))
                elif b_type == 'OrderedList':
                    elements.extend(self._handle_ordered_list_elem(b_content, level=level+1))
                else:
                    # Other block types - use existing processing
                    block_xml = self._process_blocks([block])
                    if block_xml.strip():
                        wrapper = f'<root xmlns:hp="{NS_PARA}" xmlns:hc="{NS_CORE}">{block_xml}</root>'
                        for elem in ET.fromstring(wrapper):
                            elements.append(elem)

        return elements

    def _handle_template_numbering_list_elem(self, content, list_type, level=0):
        """Handle list using template's numbering definition.

        The template's paraPr already references the correct numbering style,
        so we just use the paraPrIDRef directly.

        Args:
            content: List items from AST
            list_type: 'BULLET' or 'ORDERED'
            level: Nesting level (0-indexed)

        Returns:
            List of paragraph Elements
        """
        elements = []
        list_key = (list_type, level + 1)
        style_info = self.list_styles.get(list_key, {})

        char_pr_id = int(style_info.get('charPrIDRef', 0))
        para_pr_id = int(style_info.get('paraPrIDRef', self.normal_para_pr_id))

        for item_blocks in content:
            for block in item_blocks:
                b_type = block.get('t')
                b_content = block.get('c')

                if b_type in ('Para', 'Plain'):
                    # Use template's paraPr (which has numbering reference)
                    para = self._create_para_elem(
                        style_id=self.normal_style_id,
                        para_pr_id=para_pr_id
                    )
                    self._process_inlines_to_elems(b_content, para, base_char_pr_id=char_pr_id)
                    elements.append(para)

                elif b_type == 'BulletList':
                    elements.extend(self._handle_bullet_list_elem(b_content, level=level+1))
                elif b_type == 'OrderedList':
                    elements.extend(self._handle_ordered_list_elem(b_content, level=level+1))
                else:
                    block_xml = self._process_blocks([block])
                    if block_xml.strip():
                        wrapper = f'<root xmlns:hp="{NS_PARA}" xmlns:hc="{NS_CORE}">{block_xml}</root>'
                        for elem in ET.fromstring(wrapper):
                            elements.append(elem)

        return elements
