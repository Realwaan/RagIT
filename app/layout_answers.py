"""Bounded local OCR lookups for simple spatially explicit document layouts.

These are layout heuristics, not semantic verification. Ambiguous layouts fall
through to hosted vision or the normal refusal path.
"""
import re
from functools import lru_cache


def boxes(lines):
    result = []
    for line in lines:
        if line.get('confidence', 0) < .95 or not line.get('box'):
            continue
        xs, ys = zip(*line['box'])
        result.append((line['text'], min(xs), min(ys), max(xs), max(ys)))
    return result


def aligned(a, b):
    return abs((a[1] + a[3] - b[1] - b[3]) / 2) < max(a[3]-a[1], b[3]-b[1]) * .35


def range_cards(query, lines):
    if not re.search(r'how many.+(?:category|categories)', query, re.I):
        return None
    rows = boxes(lines)
    answers = []
    for value in rows:
        if not re.fullmatch(r'\d+\s*[-–]\s*\d+', value[0]):
            continue
        height = value[4] - value[2]
        labels = [r for r in rows if aligned(r, value) and 0 < value[2]-r[2] < height*4
                  and re.fullmatch(r'[A-Za-z]+', r[0]) and re.search(r'\b'+re.escape(r[0])+r'\b', query, re.I)]
        # A repeated group label (e.g. "Plans") is not the category name.
        labels = [r for r in labels if sum(other[0].casefold() == r[0].casefold() for other in rows) == 1]
        units = [r for r in rows if aligned(r, value) and 0 < r[2]-value[2] < height*2
                 and re.search(r'\b'+re.escape(r[0])+r'\b', query, re.I)]
        if len(labels) == len(units) == 1:
            answers.append(f'{labels[0][0]}: {value[0]} {units[0][0]}')
    if len(answers) < 2 or len({a.split(':')[0] for a in answers}) != len(answers):
        return None
    return '; '.join(answers) + '.'


def numbered_panels(query, lines):
    numbers = re.findall(r'\b\d+\.\d+\b', query)
    if len(numbers) < 2:
        return None
    rows = boxes(lines)
    headings = [r for r in rows if r[0] in numbers]
    if len(headings) != len(set(numbers)):
        return None
    parts = []
    for heading in sorted(headings, key=lambda r:r[1]):
        right = min((r[1] for r in headings if r[1] > heading[3]), default=float('inf'))
        height = heading[4]-heading[2]
        prose = sorted([r for r in rows if heading[3] < r[1] < right and
                        heading[2]-height*.65 <= r[2] <= heading[4] and len(r[0].split()) >= 3], key=lambda r:r[2])
        if not prose:
            return None
        parts.append(f'{heading[0]}: ' + ' '.join(r[0] for r in prose))
    return '\n\n'.join(parts)


def fraction_formula(query, lines, image):
    if not re.search(r'\bformula\b', query, re.I):
        return None
    import numpy as np
    rows = boxes(lines)
    subjects = [r for r in rows if re.fullmatch(r'[A-Za-z]+', r[0]) and re.search(r'\b'+r[0]+r'\b', query, re.I)]
    answers = []
    for subject in subjects:
        height = subject[4]-subject[2]
        above = [r for r in rows if r[1] > subject[3] and 0 < subject[2]-r[2] < height]
        below = [r for r in rows if r[1] > subject[3] and 0 < r[2]-subject[2] < height]
        if len(above) != 1 or len(below) != 1 or not aligned(above[0], below[0]):
            continue
        numerator, denominator = above[0], below[0]
        # Require a real fraction bar, not merely stacked OCR labels.
        left, right = max(numerator[1], denominator[1]), min(numerator[3], denominator[3])
        top, bottom = numerator[4], denominator[2]
        if bottom <= top or right <= left:
            continue
        pixels = np.asarray(image.convert('L'))
        strip = pixels[int(top):int(bottom)+1, int(left):int(right)]
        if not strip.size or not ((strip < 100).mean(axis=1) > .8).any():
            continue
        # Also require the two horizontal strokes of an equals sign.
        eq = pixels[int(subject[2]):int(subject[4]), int(subject[3]):int(left)]
        if not eq.size:
            continue
        ink = (eq < 100).mean(axis=1) > .3
        bands = sum(bool(v) and (i == 0 or not ink[i-1]) for i, v in enumerate(ink))
        if bands != 2:
            continue
        answers.append(f'{subject[0]} = {numerator[0]} / {denominator[0]}.')
    return answers[0] if len(answers) == 1 else None


@lru_cache(maxsize=8)
def page_evidence(path, modified, page_number):
    import pypdfium2 as pdfium
    from app.pdf_lock import PDF_LOCK
    from app.ocr import recognize_image
    with PDF_LOCK:
        pdf = pdfium.PdfDocument(path)
        try:
            page = pdf[page_number-1]
            bitmap = page.render(scale=2)
            image = bitmap.to_pil().copy()
            bitmap.close()
            page.close()
        finally:
            pdf.close()
    return image, recognize_image(image)


def local_layout_answer(ast, query, hits):
    if not ast or not hits or not (re.search(r'\bformula\b|how many.+(?:category|categories)', query, re.I)
                                   or len(re.findall(r'\b\d+\.\d+\b', query)) >= 2):
        return None
    from app import config as cfg
    from app.retriever import requested_pdf_pages
    from pathlib import Path
    if not re.fullmatch(r'doc_[0-9a-f]{32}', ast.doc_id):
        return None
    path = Path(cfg.DOCS_DIR) / f'{ast.doc_id}.pdf'
    if not path.is_file():
        return None
    page = hits[0].get('page')
    requested = requested_pdf_pages(query)
    if not page or (requested and page not in requested):
        return None
    image, lines = page_evidence(str(path), path.stat().st_mtime_ns, page)
    answer = range_cards(query, lines) or numbered_panels(query, lines) or fraction_formula(query, lines, image)
    if not answer:
        return None
    source = {'citation_id': 1, 'doc_id': ast.doc_id, 'page': page,
              'filename': hits[0].get('filename', ast.doc_id), 'parent_text': '\n'.join(r['text'] for r in lines),
              'image_url': f'/api/preview/{ast.doc_id}/{page}', 'evidence_origin': 'extracted',
              'verification_status': 'layout_heuristic_needs_review'}
    return {'answer': answer + ' [1]', 'sources': [source], 'status': 'SUCCESS',
            'generation_mode': 'local_ocr_layout', 'token_telemetry': {'total_tokens': 0},
            'evaluation': {'citation_verified': True, 'claim_support': 'needs_review',
                'visual_support': 'local_ocr_layout', 'badge': 'OCR layout — review source image',
                'claims': [{'text': answer, 'status': 'uncertain', 'reason': 'Local OCR and spatial heuristics; inspect original image.'}]}}
