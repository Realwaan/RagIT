"""Coverage for missing pages, image text, and short critical facts."""
import io

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

import app.ingest as ingest
from app.ast_builder import build_document_ast
from scripts.bench_indexing import make_pdf


def scanned_pdf(count=1):
    output = io.BytesIO()
    image = Image.new('RGB', (300, 400), 'white')
    image.save(output, format='PDF', save_all=True, append_images=[image] * (count - 1))
    return output.getvalue()


def test_mixed_120_pages_preserves_scan_blank_and_native_page_numbers(monkeypatch):
    writer = PdfWriter()
    native = PdfReader(io.BytesIO(make_pdf(118)))
    for page in native.pages:
        writer.add_page(page)
    writer.add_page(PdfReader(io.BytesIO(scanned_pdf())).pages[0])
    writer.add_blank_page(width=300, height=400)
    output = io.BytesIO()
    writer.write(output)
    calls = []
    def ocr(image):
        calls.append(image.size)
        return [{'text': 'Emergency code is RAVEN-731.', 'confidence': .97}]
    monkeypatch.setattr(ingest, 'recognize_image', ocr)
    pages = ingest.extract_pages_from_pdf(output.getvalue(), 'mixed.pdf')
    assert len(pages) == 120
    assert [p['page'] for p in pages] == list(range(1, 121))
    assert 'Facility 118' in pages[117]['text']
    assert 'RAVEN-731' in pages[118]['text']
    assert not pages[119]['text'].strip()
    assert len(calls) == 1
    ast = build_document_ast('test', pages)
    chunks, _ = ingest.hierarchical_chunk(pages, ast=ast)
    assert any(c['page'] == 119 and 'RAVEN-731' in c['child_text'] for c in chunks)


def test_repeated_scan_reuses_ocr_but_preserves_each_page(monkeypatch):
    calls = []
    monkeypatch.setattr(ingest, 'recognize_image', lambda image: calls.append(1) or [
        {'text': 'Fee is $50.', 'confidence': .7}])
    pages = ingest.extract_pages_from_pdf(scanned_pdf(3), 'scan.pdf')
    assert len(calls) == 1
    assert all('Fee is $50.' in page['text'] for page in pages)
    assert all(page['extraction']['ocr_min_confidence'] == .7 for page in pages)


def test_ocr_failure_never_silently_publishes_partial_document(monkeypatch):
    def broken(image):
        raise RuntimeError('model unavailable')
    monkeypatch.setattr(ingest, 'recognize_image', broken)
    with pytest.raises(ValueError, match='OCR failed on page 1'):
        ingest.extract_pages_from_pdf(scanned_pdf(), 'scan.pdf')


def test_native_pages_do_not_invoke_ocr(monkeypatch):
    monkeypatch.setattr(ingest, 'recognize_image', lambda image: pytest.fail('Native PDF invoked OCR'))
    pages = ingest.extract_pages_from_pdf(make_pdf(3), 'native.pdf')
    assert len(pages) == 3
    assert all(page['extraction']['ocr_images'] == 0 for page in pages)


def test_short_clauses_remain_searchable_with_and_without_ast():
    pages = ingest.extract_pages_from_text('Fee is $50. The agreement is renewed every calendar year.\n\nNo liability.', 'terms.txt')
    ast = build_document_ast('test', pages)
    for tree in (None, ast):
        chunks, _ = ingest.hierarchical_chunk(pages, ast=tree)
        texts = [chunk['child_text'] for chunk in chunks]
        assert 'Fee is $50.' in texts
        assert 'No liability.' in texts
