"""Real local inference benchmark; isolates artifacts from the application's vault."""
import argparse
import io
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_pdf(count=100, mode='native'):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject, NumberObject
    from PIL import Image, ImageDraw, ImageFont

    def image_font():
        for path in ('C:/Windows/Fonts/arial.ttf', 'DejaVuSans.ttf'):
            try:
                return ImageFont.truetype(path, 30)
            except OSError:
                pass
        return ImageFont.load_default(size=30)

    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')}))
    for number in range(1, count + 1):
        if mode == 'scanned' or (mode == 'mixed' and number % 10 == 0):
            image = Image.new('RGB', (1224, 1584), 'white')
            draw = ImageDraw.Draw(image)
            draw.text((70, 100), f'Facility {number} retains records for {number + 10} years.', font=image_font(), fill='black')
            draw.text((70, 180), f'Emergency code RAVEN {number}.', font=image_font(), fill='black')
            output = io.BytesIO()
            image.save(output, format='PDF', resolution=144)
            writer.add_page(PdfReader(io.BytesIO(output.getvalue())).pages[0])
            image.close()
            continue
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        lines = [f'{number}. OPERATING POLICY', f'Facility {number} retains records for {number + 10} years.']
        for row in range(18):
            lines.append(f'Control {number}-{row}: The owner reviews access every {row + 1} days.')
            lines.append('The reviewer records approval and verifies the evidence before closing the review.')
        stream = DecodedStreamObject()
        content = 'BT /F1 10 Tf 35 755 Td 17 TL ' + ' T* '.join(f'({line}) Tj' for line in lines) + ' ET'
        if mode == 'mixed' and number % 10 == 9:
            image = Image.new('RGB', (1000, 100), 'white')
            ImageDraw.Draw(image).text((20, 25), f'Image verification code COBALT {number}.', font=image_font(), fill='black')
            picture = DecodedStreamObject()
            picture.set_data(image.tobytes())
            picture.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                NameObject('/Width'): NumberObject(1000), NameObject('/Height'): NumberObject(100),
                NameObject('/ColorSpace'): NameObject('/DeviceRGB'), NameObject('/BitsPerComponent'): NumberObject(8)})
            page['/Resources'][NameObject('/XObject')] = DictionaryObject({NameObject('/Im1'): writer._add_object(picture)})
            content += ' q 500 0 0 50 35 30 cm /Im1 Do Q'
            image.close()
        stream.set_data(content.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path)
    parser.add_argument('--pages', type=int, default=100)
    parser.add_argument('--mode', choices=('native', 'mixed', 'scanned'), default='native')
    parser.add_argument('--output', type=Path, default=Path('reports/indexing-benchmark.json'))
    parser.add_argument('--baseline', action='store_true', help='Measure the committed HEAD pipeline in memory')
    args = parser.parse_args()
    import app.config as cfg
    import app.ingest as ingest
    import app.ast_builder as ast
    import app.indexing as indexing
    if args.baseline:
        import importlib
        import subprocess
        for name in ('embeddings', 'ingest', 'ast_builder', 'retriever', 'indexing'):
            module = importlib.import_module(f'app.{name}')
            source = subprocess.check_output(['git', 'show', f'HEAD:app/{name}.py'],
                                             cwd=Path(__file__).resolve().parents[1]).decode('utf-8')
            exec(compile(source, f'baseline/app/{name}.py', 'exec'), module.__dict__)
    from app.embeddings import get_embedding_model
    from app.vector_store import LanceVectorStore
    contents = args.pdf.read_bytes() if args.pdf else make_pdf(args.pages, args.mode)
    filename = args.pdf.name if args.pdf else f'generated-{args.mode}-{args.pages}-pages.pdf'
    report = {'document': filename, 'python': platform.python_version(), 'platform': platform.platform(),
              'model': cfg.DEFAULT_EMBED_MODEL, 'synthetic': not bool(args.pdf), 'baseline': args.baseline}
    before = time.perf_counter()
    get_embedding_model()
    report['model_load_ms'] = round((time.perf_counter() - before) * 1000, 2)
    with tempfile.TemporaryDirectory(prefix='ragit-bench-') as folder:
        root = Path(folder)
        for name in ('DOCS_DIR', 'PREVIEWS_DIR', 'CROPS_DIR'):
            path = root / name
            path.mkdir()
            for module in (cfg, ingest, ast):
                if hasattr(module, name):
                    setattr(module, name, path)
        indexing.CACHE_DIR = root / 'cache'
        for run in ('fresh', 'cached'):
            prepared = indexing.prepare_document(contents, filename)
            report[run] = {k: v for k, v in prepared.items() if k not in ('retriever', 'ast', 'chunks')}
            print(run, report[run]['indexing_duration_ms'], 'ms', flush=True)
            if run == 'fresh':
                store = LanceVectorStore(root / 'lance')
                worker = indexing.BackgroundIndexer(store)
                state = worker.submit(prepared['ast'])
                worker.shutdown()
                report['background'] = worker.snapshot(state)
                if not args.pdf:
                    checks = []
                    for page in (1, args.pages // 2, args.pages):
                        query = f'How long does Facility {page} retain records?'
                        hits = prepared['retriever'].retrieve(query)
                        checks.append({'page': page, 'retrieved_pages': [h['page'] for h in hits],
                                       'passed': any(h['page'] == page and f'{page + 10} years' in h['parent_text'] for h in hits)})
                    report['retrieval_checks'] = checks
                    if args.mode == 'mixed':
                        image_page = args.pages - 1
                        hits = prepared['retriever'].retrieve(f'What is the COBALT image verification code on page {image_page}?')
                        checks.append({'page': image_page, 'retrieved_pages': [h['page'] for h in hits],
                                       'passed': any(h['page'] == image_page and f'COBALT {image_page}' in h['parent_text'] for h in hits)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
