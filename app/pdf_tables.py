"""Recover table cells from PDF geometry or a clearly ruled raster grid.

No values are inferred. Ambiguous/unruled scans retain their OCR text instead.
Bounding boxes returned here use PDF bottom-left coordinates.
"""
import re


def markdown_table(rows):
    if len(rows) < 2 or max(map(len, rows), default=0) < 2:
        return ''
    width = max(map(len, rows))
    def row(values):
        cells = [re.sub(r'\s+', ' ', str(value or '')).replace('|', '\\|').strip() for value in values]
        return '| ' + ' | '.join(cells + [''] * (width - len(cells))) + ' |'
    return '\n'.join([row(rows[0]), row(['---'] * width)] + [row(values) for values in rows[1:]])


def native_tables(page, page_number):
    """Use actual ruling geometry; try text alignment only for captioned tables."""
    tables = page.find_tables()
    aligned = not tables
    if aligned:
        tables = page.find_tables({'vertical_strategy': 'text', 'horizontal_strategy': 'text',
                                   'min_words_vertical': 3})
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
    if not any(line.get('box') for line in lines):
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
