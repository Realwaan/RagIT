"""Independent long-document acceptance suite using real OCR and embeddings.

Generated PDFs have known answers; no OCR, retrieval, or answer responses are
mocked. External LLM calls are disabled to make the checks repeatable offline.
"""
import io
import json
import re
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject, NumberObject


def scan_image(lines=None, rows=None):
    image = Image.new('RGB', (1224, 1584), 'white')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 32)
    except OSError:
        font = ImageFont.truetype('DejaVuSans.ttf', 32)
    for index, line in enumerate(lines or []):
        draw.text((70, 80 + index * 55), line, fill='black', font=font)
    if rows:
        xs = [70, 430, 790, 1150]
        ys = [250 + index * 80 for index in range(len(rows) + 1)]
        for x in xs:
            draw.line((x, ys[0], x, ys[-1]), fill='black', width=3)
        for y in ys:
            draw.line((xs[0], y, xs[-1], y), fill='black', width=3)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                draw.text((xs[c] + 16, ys[r] + 22), value, fill='black', font=font)
    return image


def pdf_fixture(kind):
    count = {'finance': 128, 'operations': 132, 'scanned': 120}[kind]
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')}))
    def text(value, x, y, size=12):
        escaped = value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        return f'BT /F1 {size} Tf {x} {y} Td ({escaped}) Tj ET\n'
    def table(title, rows, ruled=True):
        output = text(title, 60, 560)
        xs = [60, 220, 380, 540]
        ys = [530 - 35 * index for index in range(len(rows) + 1)]
        if ruled:
            for x in xs:
                output += f'{x} {ys[0]} m {x} {ys[-1]} l S\n'
            for y in ys:
                output += f'{xs[0]} {y} m {xs[-1]} {y} l S\n'
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                output += text(value, xs[c] + 10, ys[r] - 23)
        return output
    scans = {}
    for number in range(1, count + 1):
        raster = None
        if kind == 'scanned':
            key = number if number in (1, 60, 120) else 0
            if key not in scans:
                rows = [['Sample', 'Limit', 'Observed'], ['Terra', '12', '9'], ['Lunar', '12', '11']] if key == 120 else None
                label = 'Laboratory results at final review.' if key == 120 else f'Laboratory archive group {key}.'
                raster = scan_image([label, 'Calibration reference is QUARTZ.'], rows)
                output = io.BytesIO()
                raster.save(output, format='PDF', resolution=144)
                scans[key] = output.getvalue()
                raster.close()
            writer.add_page(PdfReader(io.BytesIO(scans[key])).pages[0])
            continue
        if kind == 'operations' and number == 131:
            raster = scan_image(['Operations inspection register.'],
                                [['Zone', 'Interval', 'Code'], ['Kestrel', '14', '731'], ['Harbor', '14', '529']])
            output = io.BytesIO()
            raster.save(output, format='PDF', resolution=144)
            writer.add_page(PdfReader(io.BytesIO(output.getvalue())).pages[0])
            raster.close()
            continue
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        content = text(f'{number}. ARCHIVE SECTION', 40, 750)
        content += text(f'{kind.title()} archive entry {number}. Routine review completed.', 40, 715)
        if kind == 'finance' and number in (10, 64, 90, 127):
            rows = [['Business', 'Revenue 2024', 'Revenue 2025'], ['Orion', '431', '842'], ['Vega', '250', '250']]
            if number == 10:
                rows = [['Business', 'Revenue 2024', 'Revenue 2025'], ['Orion', '111', '222'], ['Vega', '100', '100']]
            if number == 64:
                rows = [['Business', 'Budget', 'Actual'], ['Nimbus', '237', '245'], ['Cirrus', '330', '329']]
            content += table('Table 1: Final regional statement' if number == 127 else f'Table {number}: Prior statement', rows, ruled=number != 64)
            if number == 90:
                page.rotate(90)
        if number == count:
            content += text('Final authorization code is COPPER-918.' if kind == 'finance' else
                            'Atlas evacuation assembly point is Sector Kestrel.', 40, 640)
        if kind == 'operations' and number == 67:
            content += text('Figure 1: Valve routing diagram', 60, 580)
            content += text('Pressure setting is 73 kPa.', 60, 550)
            content += '60 420 170 70 re S 340 420 170 70 re S 230 455 m 340 455 l S\n'
            content += text('INLET', 100, 450) + text('OUTLET', 380, 450)
        if kind == 'operations' and number == 99:
            image = scan_image(['Image inspection code COBALT-639.'])
            picture = DecodedStreamObject()
            picture.set_data(image.tobytes())
            picture.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                NameObject('/Width'): NumberObject(image.width), NameObject('/Height'): NumberObject(image.height),
                NameObject('/ColorSpace'): NameObject('/DeviceRGB'), NameObject('/BitsPerComponent'): NumberObject(8)})
            page['/Resources'][NameObject('/XObject')] = DictionaryObject({NameObject('/Im1'): writer._add_object(picture)})
            content += 'q 500 0 0 600 40 50 cm /Im1 Do Q\n'
            image.close()
        if kind == 'operations' and number == 13:
            content = ''
        stream = DecodedStreamObject()
        stream.set_data(content.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), count


def run():
    import app.config as cfg
    import app.ingest as ingest
    import app.ast_builder as ast_module
    import app.indexing as indexing
    import app.main as main
    from fastapi.testclient import TestClient
    checks = []
    def check(label, condition, **details):
        checks.append({'check': label, 'passed': bool(condition), **details})
        print(f"{'PASS' if condition else 'FAIL'} {label}", flush=True)
    with tempfile.TemporaryDirectory(prefix='ragit-long-pdfs-') as directory, ExitStack() as stack:
        root = Path(directory)
        for name in ('DOCS_DIR', 'PREVIEWS_DIR', 'CROPS_DIR'):
            folder = root / name
            folder.mkdir()
            for module in (cfg, ingest, ast_module, main):
                if hasattr(module, name):
                    stack.enter_context(patch.object(module, name, folder))
        stack.enter_context(patch.object(indexing, 'CACHE_DIR', root / 'cache'))
        stack.enter_context(patch.object(main, 'DOCUMENT_VAULT', {}))
        stack.enter_context(patch.object(main, 'DOCUMENT_ASTS', {}))
        stack.enter_context(patch('app.generator.has_valid_primary_key', return_value=False))
        stack.enter_context(patch('app.generator.has_valid_fallback_key', return_value=False))
        stack.enter_context(patch('app.vision.configured', return_value=False))
        client = TestClient(main.app)
        for kind in ('finance', 'operations', 'scanned'):
            print(f'Preparing {kind} PDF with actual extraction/OCR and embeddings...', flush=True)
            contents, count = pdf_fixture(kind)
            started = time.perf_counter()
            prepared = indexing.prepare_document(contents, f'{kind}-{count}.pdf')
            ast, retriever = prepared['ast'], prepared['retriever']
            main.DOCUMENT_VAULT[ast.doc_id] = prepared
            main.DOCUMENT_ASTS[ast.doc_id] = ast
            check(f'{kind}: all physical pages extracted', prepared['pages'] == count,
                  pages=prepared['pages'], duration_ms=round((time.perf_counter()-started)*1000))
            if kind == 'finance':
                cases = [('Orion Revenue 2025 on PDF page 127', 127, '842'),
                         ('Orion Revenue 2025 on PDF page 90', 90, '842'),
                         ('Nimbus Actual', 64, '245'), ('Final authorization code', 128, 'COPPER-918')]
                for page in (64, 90, 127):
                    tables = [node for node in ast.get_visual_nodes() if node.page == page and node.visual_type == 'table']
                    check(f'finance: structured table on page {page}', bool(tables))
                    if page == 90:
                        check('finance: rotated table preserves axes', any('| Orion | 431 | 842 |' in node.text for node in tables))
            elif kind == 'operations':
                cases = [('Kestrel Code', 131, '731'), ('image inspection code COBALT', 99, '639'),
                         ('pressure setting valve routing', 67, '73'), ('Atlas evacuation assembly point', 132, 'Kestrel')]
                check('operations: blank page stays numbered', 13 in prepared['extraction']['empty_text_pages'])
                check('operations: vector diagram represented', any(v.page == 67 and v.visual_type == 'diagram' for v in ast.get_visual_nodes()))
            else:
                cases = [('Terra Observed', 120, '9'), ('Lunar Limit', 120, '12')]
                check('scanned: OCR covered every page', len(prepared['extraction']['ocr_pages']) == count)
                last_tables = [v for v in ast.get_visual_nodes() if v.page == 120 and v.visual_type == 'table']
                check('scanned: repeated cell values retained', any('| Terra | 12 | 9 |' in v.text and '| Lunar | 12 | 11 |' in v.text for v in last_tables))
            for query, page, answer in cases:
                hits = retriever.retrieve(query)
                matching = [hit for hit in hits if hit['page'] == page and answer in hit['parent_text']]
                check(f'{kind}: retrieve {query}', bool(matching), retrieved_pages=[hit['page'] for hit in hits])
                response = client.post('/api/chat', json={'query': query, 'doc_id': ast.doc_id})
                events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
                result = next((event for event in events if event['type'] == 'done'), {})
                lead = result.get('answer', '').split('### Source excerpts')[0]
                cited_ids = {int(value) for value in re.findall(r'\[(\d+)\]', lead)}
                cited_pages = {source['page'] for source in result.get('sources', []) if source['citation_id'] in cited_ids}
                check(f'{kind}: answer {query}', result.get('status') == 'SUCCESS' and answer in lead and page in cited_pages,
                      answer=lead[:500], cited_pages=sorted(cited_pages))
                for hit in matching[:1]:
                    urls = [hit.get('image_url')] + [v.get('image_url') for v in hit.get('linked_visuals', [])]
                    urls = [url for url in urls if url and url.startswith('/api/')]
                    check(f'{kind}: evidence opens on page {page}', bool(urls) and all(client.get(url).status_code == 200 for url in urls))
            restored = indexing.prepare_document(contents, f'{kind}-renamed.pdf')
            check(f'{kind}: cache keeps source identity', restored['cache_hit'] and restored['doc_id'] == ast.doc_id
                  and all(chunk['filename'] == f'{kind}-renamed.pdf' for chunk in restored['chunks']))
    report = {'passed': all(check['passed'] for check in checks),
              'scope': 'Generated 128-page finance, 132-page mixed operations, 120-page raster laboratory PDFs. Scanned background pages intentionally repeat; key evidence pages differ. Real OCR and embeddings, offline generation.',
              'checks': checks}
    Path('reports/long-pdf-acceptance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(run())
