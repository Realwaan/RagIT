"""Recover table cells from PDF geometry or a clearly ruled raster grid.

No values are inferred. Ambiguous/unruled scans retain their OCR text instead.
Bounding boxes returned here use PDF bottom-left coordinates.
"""
import ctypes
import re


def has_pdfium_ruled_table(path_objs, page_h: float) -> bool:
    """Fast-check in PDFium whether vector paths form at least a 2x2 ruled grid."""
    if len(path_objs) < 2:
        return False
    try:
        import pypdfium2.raw as pdfium_c
        from pdfplumber import utils
        from pdfplumber.table import Table, cells_to_tables, edges_to_intersections, intersections_to_cells, merge_edges
    except Exception:
        return True
    edges = []
    fx, fy = ctypes.c_float(), ctypes.c_float()
    byref_x, byref_y = ctypes.byref(fx), ctypes.byref(fy)
    get_cnt = pdfium_c.FPDFPath_CountSegments
    get_seg = pdfium_c.FPDFPath_GetPathSegment
    get_pt = pdfium_c.FPDFPathSegment_GetPoint
    get_type = pdfium_c.FPDFPathSegment_GetType
    get_close = pdfium_c.FPDFPathSegment_GetClose

    for o in path_objs:
        try:
            l, b, r, t = o.get_bounds()
        except Exception:
            continue
        w, h = r - l, t - b
        if w < 3 and h < 3:
            continue
        top, bottom = page_h - t, page_h - b
        if w >= 3 and h <= 2.0:
            edges.append({'x0': l, 'x1': r, 'top': top, 'bottom': top, 'width': w, 'height': 0, 'orientation': 'h'})
            continue
        if h >= 3 and w <= 2.0:
            edges.append({'x0': l, 'x1': l, 'top': top, 'bottom': bottom, 'width': 0, 'height': h, 'orientation': 'v'})
            continue
        raw = getattr(o, 'raw', None)
        if raw is None:
            continue
        n = get_cnt(raw)
        if n < 3 or n > 64:
            continue
        a, b_mat, c, d, e, f = o.get_matrix().get()
        sx = sy = px = py = None
        for idx in range(n):
            seg = get_seg(raw, idx)
            st = get_type(seg)
            get_pt(seg, byref_x, byref_y)
            x0, y0 = fx.value, fy.value
            x = a * x0 + c * y0 + e
            y = b_mat * x0 + d * y0 + f
            if st == 2:
                sx, sy = px, py = x, y
            elif px is not None:
                if st == 0:
                    dx, dy = abs(x - px), abs(y - py)
                    if dx >= 3 and dy <= 1.0:
                        x_min, x_max = (px, x) if px < x else (x, px)
                        ym = page_h - (py + y) * 0.5
                        edges.append({'x0': x_min, 'x1': x_max, 'top': ym, 'bottom': ym, 'width': dx, 'height': 0, 'orientation': 'h'})
                    elif dy >= 3 and dx <= 1.0:
                        y_min, y_max = (py, y) if py < y else (y, py)
                        xm = (px + x) * 0.5
                        edges.append({'x0': xm, 'x1': xm, 'top': page_h - y_max, 'bottom': page_h - y_min, 'width': 0, 'height': dy, 'orientation': 'v'})
                px, py = x, y
                if get_close(seg) and sx is not None:
                    dx, dy = abs(sx - px), abs(sy - py)
                    if dx >= 3 and dy <= 1.0:
                        x_min, x_max = (px, sx) if px < sx else (sx, px)
                        ym = page_h - (py + sy) * 0.5
                        edges.append({'x0': x_min, 'x1': x_max, 'top': ym, 'bottom': ym, 'width': dx, 'height': 0, 'orientation': 'h'})
                    elif dy >= 3 and dx <= 1.0:
                        y_min, y_max = (py, sy) if py < sy else (sy, py)
                        xm = (px + sx) * 0.5
                        edges.append({'x0': xm, 'x1': xm, 'top': page_h - y_max, 'bottom': page_h - y_min, 'width': 0, 'height': dy, 'orientation': 'v'})
                    px, py = sx, sy

    if len(edges) < 4:
        return False
    merged = utils.filter_edges(
        merge_edges(edges, snap_x_tolerance=3, snap_y_tolerance=3, join_x_tolerance=3, join_y_tolerance=3),
        min_length=3,
    )
    cells = intersections_to_cells(edges_to_intersections(merged, 3, 3))
    for cg in cells_to_tables(cells):
        if len(cg) >= 4:
            tb = Table(None, cg)
            if len(tb.rows) >= 2 and len(tb.columns) >= 2:
                return True
    return False


def normalize_table_headers_and_spans(rows: list[list[str]]) -> list[list[str]]:
    """Normalize multi-level headers and forward-fill merged cell spans."""
    if len(rows) < 2 or not any(rows):
        return rows

    cleaned = [[re.sub(r'\s+', ' ', str(c or '')).strip() for c in r] for r in rows]
    width = max(len(r) for r in cleaned)
    if width < 2:
        return cleaned

    for r in cleaned:
        r.extend([''] * (width - len(r)))

    # Detect multi-level headers with colspan/merged cells
    has_subheaders = False
    if len(cleaned) >= 3:
        r0, r1 = cleaned[0], cleaned[1]
        def has_data(r):
            for c in r[1:]:
                c = c.strip()
                if not c:
                    continue
                if re.fullmatch(r'(?:19|20)\d{2}|Q[1-4]|FY\s*\d{2,4}', c, re.IGNORECASE):
                    continue
                if re.search(r'[\$€£¥₹%]|(?:\d+[,.]\d+)|(?:^\s*\d+\s*(?:[MKBkmb])\s*$)', c):
                    return True
                if re.fullmatch(r'\d+', c) and not re.fullmatch(r'(?:19|20)\d{2}', c):
                    return True
            return False

        if not has_data(r0) and not has_data(r1) and any(r1):
            empty_in_r0 = any(not c for c in r0[1:])
            distinct_in_r1 = len(set(c for c in r1[1:] if c)) > 1
            if empty_in_r0 and distinct_in_r1:
                has_subheaders = True

    if has_subheaders:
        filled_r0 = list(cleaned[0])
        for c in range(1, width):
            if not filled_r0[c] and filled_r0[c - 1]:
                filled_r0[c] = filled_r0[c - 1]

        composite_header = []
        for p, ch in zip(filled_r0, cleaned[1]):
            if p and ch and p != ch:
                composite_header.append(f"{p} > {ch}")
            else:
                composite_header.append(ch or p)
        cleaned = [composite_header] + cleaned[2:]

    return cleaned


def markdown_table(rows):
    if len(rows) < 2 or max(map(len, rows), default=0) < 2:
        return ''
    width = max(map(len, rows))
    def row(values):
        cells = [re.sub(r'\s+', ' ', str(value or '')).replace('|', '\\|').strip() for value in values]
        return '| ' + ' | '.join(cells + [''] * (width - len(cells))) + ' |'
    return '\n'.join([row(rows[0]), row(['---'] * width)] + [row(values) for values in rows[1:]])


def native_tables(page, page_number, allow_text_strategy: bool = True):
    """Use actual ruling geometry; try text alignment only for captioned tables."""
    tables = [t for t in page.find_tables() if len(t.cells) >= 4 and len(t.rows) >= 2 and len(t.columns) >= 2]

    aligned = not tables and allow_text_strategy
    if aligned:
        tables = [t for t in page.find_tables({'vertical_strategy': 'text', 'horizontal_strategy': 'text',
                                               'min_words_vertical': 3})
                  if len(t.cells) >= 4 and len(t.rows) >= 2 and len(t.columns) >= 2]
    results = []
    for table in tables:
        rows = [row for row in table.extract() if any(value for value in row)]
        # Text-alignment can mistake two-column prose for a table. Require a
        # compact matrix with consistent populated columns before promoting it.
        if len(rows) < 2 or len(rows[0]) < 2:
            continue
        if aligned:
            width = len(rows[0])
            first_header = next((i for i, row in enumerate(rows)
                                 if sum(bool(value) for value in row) >= max(2, width * .6)), None)
            if first_header is None:
                continue
            rows = rows[first_header:]
            numeric_cells = sum(bool(re.search(r'\d', str(value or ''))) for row in rows[1:] for value in row[1:])
            if len(rows) < 3 or numeric_cells < (len(rows)-1) * (width-1) * .25:
                continue
        if any(len(str(value or '').split()) > 24 for row in rows for value in row):
            continue
        x0, top, x1, bottom = table.bbox
        caption_area = page.crop((x0, max(0, top - 55), x1, top)) if top > 0 else None
        caption = caption_area.extract_text() if caption_area else ''
        matches = re.findall(r'(?im)^.*?\b(Table\s+\d+[A-Za-z]?(?:[.: -].*)?)$', caption or '')
        title = matches[-1].strip() if matches else f'Extracted table {len(results) + 1} on PDF page {page_number}'
        results.append({'title': title, 'text': markdown_table(rows),
                        'bbox': (x0, page.height - bottom, x1, page.height - top),
                        'source': 'native_table', 'rows': len(rows), 'columns': len(rows[0]),
                        'extraction_warnings': ['Some PDF glyphs could not be decoded; inspect the original table.']
                        if any('\ufffd' in str(value or '') for row in rows for value in row) else []})
    return results


def raster_tables(image, lines):
    """Recover rectangular ruled tables from OCR boxes in original image pixels.

    Detect grids rather than guessing columns from OCR reading order. Merged or
    irregular grids are skipped so their values are not assigned to wrong cells.
    """
    import cv2
    import numpy as np
    if sum(bool(line.get('box')) for line in lines) < 3:
        return []
    gray = np.asarray(image.convert('L'))
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    height, width = binary.shape
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((1, max(30, width // 20)), np.uint8))
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((max(30, height // 20), 1), np.uint8))
    contours, _ = cv2.findContours(horizontal | vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    def positions(mask, axis, threshold):
        points = np.flatnonzero(np.count_nonzero(mask, axis=axis) >= threshold)
        groups = np.split(points, np.where(np.diff(points) > 2)[0] + 1)
        return [int(np.mean(group)) for group in groups if len(group)]
    results = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 100 or h < 60:
            continue
        xs = positions(vertical[y:y+h, x:x+w], 0, h * .85)
        ys = positions(horizontal[y:y+h, x:x+w], 1, w * .85)
        if len(xs) < 3 or len(ys) < 3:
            continue
        # Partial lines indicate merged cells. Reject those grids for now.
        if len(positions(vertical[y:y+h, x:x+w], 0, h * .2)) != len(xs):
            continue
        if len(positions(horizontal[y:y+h, x:x+w], 1, w * .2)) != len(ys):
            continue
        cells = [[[] for _ in range(len(xs)-1)] for _ in range(len(ys)-1)]
        scores = []
        for line in lines:
            if not line.get('box'):
                continue
            box = np.asarray(line['box'])
            cx, cy = box.mean(axis=0) - (x, y)
            col, row = int(np.searchsorted(xs, cx)-1), int(np.searchsorted(ys, cy)-1)
            if 0 <= col < len(xs)-1 and 0 <= row < len(ys)-1:
                cells[row][col].append((float(box[:, 1].min()), float(box[:, 0].min()), line['text']))
                scores.append(line['confidence'])
        rows = [[' '.join(value[2] for value in sorted(cell)) for cell in row] for row in cells]
        if not all(rows[0]) or not any(any(row) for row in rows[1:]):
            continue
        results.append({'text': markdown_table(rows), 'pixel_bbox': (x, y, x+w, y+h),
                        'source': 'ocr_table', 'rows': len(rows), 'columns': len(rows[0]),
                        'ocr_min_confidence': min(scores) if scores else None})
    return results
