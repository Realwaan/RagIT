"""Format extractors for Office documents (DOCX, XLSX, PPTX, CSV) and standalone images.

Zero API burn, local-first, utilizing Python standard libraries (zipfile, xml.etree, csv)
and existing project dependencies (Pillow, OpenCV, RapidOCR).
"""
import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image

from app import config as cfg
from app.image_cache import save_image
from app.ocr import recognize_image
from app.pdf_tables import raster_tables, markdown_table, normalize_table_headers_and_spans
from app.resource_limits import checked_pixels


# XML Namespaces for OpenXML standards
NS_WORD = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
NS_SHEET = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
NS_DRAW = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
           "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}


def col2num(col_str: str) -> int:
    """Converts Excel column letters (e.g. 'A', 'Z', 'AA') to 0-based index."""
    num = 0
    for c in col_str:
        num = num * 26 + (ord(c.upper()) - ord('A')) + 1
    return max(0, num - 1)


# ==============================================================================
# 1. Standalone Images & Scans (.png, .jpg, .jpeg, .webp, .tiff)
# ==============================================================================

def extract_pages_from_image(
    image_bytes: bytes,
    filename: str,
    doc_id: str,
) -> Tuple[List[Dict[str, Any]], Dict[int, str]]:
    """Ingest standalone images, scans, invoices, and charts with full OCR & visual AST."""
    with Image.open(io.BytesIO(image_bytes)) as pil_img:
        checked_pixels(pil_img.width, pil_img.height)
        img = pil_img.convert("RGB") if pil_img.mode != "RGB" else pil_img.copy()

    preview_name = f"{doc_id}_page_1.webp"
    preview_path = cfg.PREVIEWS_DIR / preview_name
    save_image(img, preview_path)
    preview_url = f"/api/preview/{doc_id}/1"

    ocr_lines = recognize_image(img)
    tables = raster_tables(img, ocr_lines)

    text_parts = [line["text"] for line in ocr_lines if line.get("text")]
    text = "\n\n".join(text_parts) if text_parts else f"Image artifact: {filename}"

    visual_obj = {
        "id": f"{doc_id}_vis_1",
        "title": filename,
        "visual_type": "image",
        "bbox": (0, 0, img.width, img.height),
        "image_url": preview_url,
        "text": text[:300],
        "page": 1,
    }

    pages = [{
        "page": 1,
        "text": text,
        "tables": tables,
        "visual_objects": [visual_obj],
        "extraction": {
            "native_text": False,
            "ocr_images": [visual_obj],
            "has_visual_objects": True,
            "structured_tables": len(tables),
            "ocr_min_confidence": min((l["confidence"] for l in ocr_lines), default=None),
        },
    }]
    page_images = {1: preview_url}
    return pages, page_images


# ==============================================================================
# 2. CSV Spreadsheets (.csv)
# ==============================================================================

def extract_pages_from_csv(csv_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Ingests comma-separated or delimited text tables into structured AST tables."""
    text = ""
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            text = csv_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        text = csv_bytes.decode("utf-8", errors="replace")

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return [{"page": 1, "text": f"Empty CSV document: {filename}", "tables": []}]

    delimiter = ","
    try:
        sample = "\n".join(lines[:10])
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except Exception:
        first = lines[0]
        if "\t" in first:
            delimiter = "\t"
        elif ";" in first and "," not in first:
            delimiter = ";"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    raw_rows = [row for row in reader if any(c.strip() for c in row)]
    if not raw_rows:
        return [{"page": 1, "text": f"Empty CSV document: {filename}", "tables": []}]

    md_table = markdown_table(normalize_table_headers_and_spans(raw_rows))
    table_dict = {
        "title": filename,
        "text": md_table,
        "rows": len(raw_rows),
        "columns": max(len(r) for r in raw_rows),
        "source": "csv_table",
        "bbox": (0, 0, 0, 0),
    }

    page_text = f"### {filename}\n\n{md_table}"
    return [{
        "page": 1,
        "text": page_text,
        "tables": [table_dict],
        "extraction": {"native_text": True, "structured_tables": 1},
    }]


# ==============================================================================
# 3. Excel Spreadsheets (.xlsx)
# ==============================================================================

def extract_pages_from_xlsx(xlsx_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Ingests multi-sheet Excel workbooks with merged cell normalization."""
    pages = []
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes), "r") as z:
        # 1. Parse shared strings table if present
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            try:
                root_sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in root_sst.findall(".//s:si", NS_SHEET):
                    shared_strings.append("".join(si.itertext()))
            except Exception:
                pass

        # 2. Parse workbook structure to get ordered sheet names
        sheet_info: List[Tuple[str, str]] = []
        if "xl/workbook.xml" in z.namelist():
            try:
                wb_root = ET.fromstring(z.read("xl/workbook.xml"))
                for s in wb_root.findall(".//s:sheet", NS_SHEET):
                    name = s.attrib.get("name", "Sheet")
                    rid = s.attrib.get(f"{{{NS_SHEET['r']}}}id", "")
                    sheet_info.append((name, rid))
            except Exception:
                pass

        # Map relationships if possible
        rel_map: Dict[str, str] = {}
        if "xl/_rels/workbook.xml.rels" in z.namelist():
            try:
                rel_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
                for rel in rel_root:
                    rid = rel.attrib.get("Id", "")
                    target = rel.attrib.get("Target", "")
                    if target.startswith("worksheets/"):
                        rel_map[rid] = f"xl/{target}"
                    elif "worksheets/" in target:
                        rel_map[rid] = f"xl/{target.split('worksheets/')[-1]}"
            except Exception:
                pass

        # Find sheet files
        sheet_files = []
        if sheet_info:
            for sname, rid in sheet_info:
                path_target = rel_map.get(rid, "")
                if path_target and path_target in z.namelist():
                    sheet_files.append((sname, path_target))
                else:
                    # fallback matching
                    idx = len(sheet_files) + 1
                    candidate = f"xl/worksheets/sheet{idx}.xml"
                    if candidate in z.namelist():
                        sheet_files.append((sname, candidate))

        if not sheet_files:
            # Fallback to direct file discovery
            for fname in sorted(z.namelist()):
                if fname.startswith("xl/worksheets/sheet") and fname.endswith(".xml"):
                    sheet_files.append((f"Sheet {len(sheet_files) + 1}", fname))

        for page_num, (sheet_name, sheet_path) in enumerate(sheet_files, 1):
            try:
                sheet_root = ET.fromstring(z.read(sheet_path))
                cell_data: Dict[Tuple[int, int], str] = {}
                max_r, max_c = 0, 0

                for row_elem in sheet_root.findall(".//s:row", NS_SHEET):
                    r_idx = int(row_elem.attrib.get("r", "1")) - 1
                    max_r = max(max_r, r_idx)
                    for c_elem in row_elem.findall("s:c", NS_SHEET):
                        coord = c_elem.attrib.get("r", "A1")
                        m = re.match(r"([A-Za-z]+)(\d+)", coord)
                        c_idx = col2num(m.group(1)) if m else 0
                        max_c = max(max_c, c_idx)
                        cell_type = c_elem.attrib.get("t", "")
                        v_elem = c_elem.find("s:v", NS_SHEET)
                        val = ""
                        if cell_type == "s" and v_elem is not None and v_elem.text:
                            try:
                                s_idx = int(v_elem.text)
                                val = shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else v_elem.text
                            except (ValueError, IndexError):
                                val = v_elem.text or ""
                        elif cell_type == "inlineStr":
                            t_elem = c_elem.find(".//s:t", NS_SHEET)
                            val = t_elem.text if t_elem is not None and t_elem.text else ""
                        elif cell_type == "b" and v_elem is not None and v_elem.text:
                            val = "TRUE" if v_elem.text == "1" else "FALSE"
                        elif v_elem is not None and v_elem.text:
                            val = v_elem.text

                        if val:
                            cell_data[(r_idx, c_idx)] = val.strip()

                # Replicate merged cell master values across slave cells
                for m_elem in sheet_root.findall(".//s:mergeCell", NS_SHEET):
                    ref = m_elem.attrib.get("ref", "")
                    if ":" in ref:
                        start, end = ref.split(":")
                        m1 = re.match(r"([A-Za-z]+)(\d+)", start)
                        m2 = re.match(r"([A-Za-z]+)(\d+)", end)
                        if m1 and m2:
                            r_start, c_start = int(m1.group(2)) - 1, col2num(m1.group(1))
                            r_end, c_end = int(m2.group(2)) - 1, col2num(m2.group(1))
                            master_val = cell_data.get((r_start, c_start), "")
                            if master_val:
                                for r in range(r_start, r_end + 1):
                                    for c in range(c_start, c_end + 1):
                                        if (r, c) not in cell_data:
                                            cell_data[(r, c)] = master_val

                # Build dense matrix of rows
                grid: List[List[str]] = []
                for r in range(max_r + 1):
                    row_vals = [cell_data.get((r, c), "") for c in range(max_c + 1)]
                    if any(row_vals):
                        grid.append(row_vals)

                if not grid:
                    continue

                md_table = markdown_table(normalize_table_headers_and_spans(grid))
                table_dict = {
                    "title": f"Sheet: {sheet_name}",
                    "text": md_table,
                    "rows": len(grid),
                    "columns": max(len(r) for r in grid),
                    "source": "xlsx_table",
                    "bbox": (0, 0, 0, 0),
                }

                pages.append({
                    "page": page_num,
                    "text": f"## Sheet: {sheet_name}\n\n{md_table}",
                    "tables": [table_dict],
                    "extraction": {"native_text": True, "structured_tables": 1},
                })
            except Exception:
                continue

    if not pages:
        pages.append({
            "page": 1,
            "text": f"Workbook: {filename} (no readable worksheets found).",
            "tables": [],
            "extraction": {"native_text": True},
        })
    return pages


# ==============================================================================
# 4. Word Documents (.docx)
# ==============================================================================

def extract_pages_from_docx(docx_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Ingests Word documents, mapping headings, paragraphs, and native Word tables."""
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as z:
        if "word/document.xml" not in z.namelist():
            return [{"page": 1, "text": f"Invalid DOCX structure: {filename}", "tables": []}]
        xml_content = z.read("word/document.xml")

    root = ET.fromstring(xml_content)
    body = root.find("w:body", NS_WORD)
    if body is None:
        return [{"page": 1, "text": f"Empty DOCX document: {filename}", "tables": []}]

    # Collect structural units: headings, paragraphs, and tables
    pages: List[Dict[str, Any]] = []
    current_page_text: List[str] = []
    current_page_tables: List[Dict[str, Any]] = []
    page_num = 1
    word_count_page = 0

    def flush_page():
        nonlocal page_num, current_page_text, current_page_tables, word_count_page
        if current_page_text or current_page_tables:
            pages.append({
                "page": page_num,
                "text": "\n\n".join(current_page_text),
                "tables": list(current_page_tables),
                "extraction": {"native_text": True, "structured_tables": len(current_page_tables)},
            })
            page_num += 1
            current_page_text = []
            current_page_tables = []
            word_count_page = 0

    for elem in body:
        tag = elem.tag.split("}")[-1]

        # Explicit page break detection
        if elem.findall(".//w:br[@w:type='page']", NS_WORD) or elem.findall(".//w:lastRenderedPageBreak", NS_WORD):
            flush_page()

        if tag == "p":
            style_elem = elem.find(".//w:pStyle", NS_WORD)
            style_val = style_elem.attrib.get(f"{{{NS_WORD['w']}}}val", "") if style_elem is not None else ""
            txt = "".join(elem.itertext()).strip()
            if not txt:
                continue

            if "Heading1" in style_val or style_val == "1":
                current_page_text.append(f"# {txt}")
            elif "Heading2" in style_val or style_val == "2":
                current_page_text.append(f"## {txt}")
            elif "Heading3" in style_val or style_val == "3":
                current_page_text.append(f"### {txt}")
            elif elem.find(".//w:numPr", NS_WORD) is not None:
                current_page_text.append(f"- {txt}")
            else:
                current_page_text.append(txt)

            word_count_page += len(txt.split())
            if word_count_page >= 600:
                flush_page()

        elif tag == "tbl":
            grid: List[List[str]] = []
            v_merge_masters: Dict[int, str] = {}

            for tr in elem.findall(".//w:tr", NS_WORD):
                row_vals: List[str] = []
                col_cursor = 0
                for tc in tr.findall(".//w:tc", NS_WORD):
                    tc_pr = tc.find("w:tcPr", NS_WORD)
                    cell_txt = " ".join("".join(p.itertext()).strip() for p in tc.findall("w:p", NS_WORD)).strip()

                    # Colspan handling (<w:gridSpan>)
                    span = 1
                    if tc_pr is not None:
                        gs = tc_pr.find("w:gridSpan", NS_WORD)
                        if gs is not None:
                            try:
                                span = int(gs.attrib.get(f"{{{NS_WORD['w']}}}val", "1"))
                            except ValueError:
                                span = 1

                    # Rowspan handling (<w:vMerge>)
                    if tc_pr is not None and tc_pr.find("w:vMerge", NS_WORD) is not None:
                        vm = tc_pr.find("w:vMerge", NS_WORD)
                        val = vm.attrib.get(f"{{{NS_WORD['w']}}}val", "")
                        if val == "restart":
                            v_merge_masters[col_cursor] = cell_txt
                        else:
                            cell_txt = v_merge_masters.get(col_cursor, cell_txt)

                    row_vals.append(cell_txt)
                    for _ in range(span - 1):
                        row_vals.append(cell_txt)
                    col_cursor += span

                if any(row_vals):
                    grid.append(row_vals)

            if grid:
                md_tbl = markdown_table(normalize_table_headers_and_spans(grid))
                table_obj = {
                    "title": f"Table {len(current_page_tables) + 1}",
                    "text": md_tbl,
                    "rows": len(grid),
                    "columns": max(len(r) for r in grid),
                    "source": "docx_table",
                    "bbox": (0, 0, 0, 0),
                }
                current_page_tables.append(table_obj)
                current_page_text.append(md_tbl)
                word_count_page += len(grid) * 5

    flush_page()
    if not pages:
        pages.append({
            "page": 1,
            "text": f"Document: {filename} (no body text found).",
            "tables": [],
            "extraction": {"native_text": True},
        })
    return pages


# ==============================================================================
# 5. PowerPoint Presentations (.pptx)
# ==============================================================================

def extract_pages_from_pptx(pptx_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Ingests PowerPoint slides, mapping slide titles, text frames, and slide tables."""
    pages = []
    with zipfile.ZipFile(io.BytesIO(pptx_bytes), "r") as z:
        # Find slides in natural sort order: slide1.xml, slide2.xml...
        slide_entries = []
        for name in z.namelist():
            m = re.match(r"ppt/slides/slide(\d+)\.xml", name)
            if m:
                slide_entries.append((int(m.group(1)), name))
        slide_entries.sort()

        for page_num, (slide_idx, slide_path) in enumerate(slide_entries, 1):
            try:
                slide_root = ET.fromstring(z.read(slide_path))
                slide_text_lines: List[str] = []
                slide_tables: List[Dict[str, Any]] = []

                # Extract text shapes
                for sp in slide_root.findall(".//p:sp", NS_DRAW):
                    txBody = sp.find("p:txBody", NS_DRAW)
                    if txBody is None:
                        continue
                    ph = sp.find(".//p:ph", NS_DRAW)
                    is_title = ph is not None and ph.attrib.get("type") in ("title", "ctrTitle")

                    paragraphs = txBody.findall("a:p", NS_DRAW)
                    for p_elem in paragraphs:
                        p_txt = "".join(p_elem.itertext()).strip()
                        if not p_txt:
                            continue
                        if is_title:
                            slide_text_lines.append(f"# {p_txt}")
                        else:
                            slide_text_lines.append(f"- {p_txt}")

                # Extract slide tables
                for tbl_elem in slide_root.findall(".//a:tbl", NS_DRAW):
                    grid: List[List[str]] = []
                    for tr in tbl_elem.findall("a:tr", NS_DRAW):
                        row_vals = [" ".join("".join(p.itertext()).strip() for p in tc.findall(".//a:p", NS_DRAW)).strip()
                                    for tc in tr.findall("a:tc", NS_DRAW)]
                        if any(row_vals):
                            grid.append(row_vals)
                    if grid:
                        md_tbl = markdown_table(normalize_table_headers_and_spans(grid))
                        slide_tables.append({
                            "title": f"Slide {page_num} Table",
                            "text": md_tbl,
                            "rows": len(grid),
                            "columns": max(len(r) for r in grid),
                            "source": "pptx_table",
                            "bbox": (0, 0, 0, 0),
                        })
                        slide_text_lines.append(md_tbl)

                page_text = "\n\n".join(slide_text_lines) if slide_text_lines else f"Slide {page_num}"
                pages.append({
                    "page": page_num,
                    "text": page_text,
                    "tables": slide_tables,
                    "extraction": {"native_text": True, "structured_tables": len(slide_tables)},
                })
            except Exception:
                continue

    if not pages:
        pages.append({
            "page": 1,
            "text": f"Presentation: {filename} (no readable slides found).",
            "tables": [],
            "extraction": {"native_text": True},
        })
    return pages
