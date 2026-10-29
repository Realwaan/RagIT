import io

import pytest
from pypdf import PdfWriter

from app import config, ingest
from app.resource_limits import checked_pixels


@pytest.mark.parametrize('width,height', [(float('inf'), 1), (float('nan'), 10), (-1, 3), (1, 0), (100000, 100000)])
def test_bad_dimensions_rejected_before_render(width, height):
    with pytest.raises(ValueError):
        checked_pixels(width, height)


def test_pdf_page_limit_rejects_instead_of_truncating(monkeypatch):
    monkeypatch.setattr(config, 'MAX_DOCUMENT_PAGES', 1)
    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(100, 100)
    stream = io.BytesIO()
    writer.write(stream)
    with pytest.raises(ValueError, match='2 pages'):
        ingest.extract_pages_from_pdf(stream.getvalue(), 'two.pdf')


def test_expanded_text_and_chunk_limits(monkeypatch):
    monkeypatch.setattr(config, 'MAX_EXTRACTED_TEXT_BYTES', 10)
    with pytest.raises(ValueError, match='text exceeds'):
        ingest.extract_pages_from_text('a' * 11, 'text.txt')
    monkeypatch.setattr(config, 'MAX_DOCUMENT_CHUNKS', 1)
    pages = [{'filename': 'text.txt', 'page': 1, 'text': 'First sentence. Second sentence.'}]
    with pytest.raises(ValueError, match='passage processing limit'):
        ingest.hierarchical_chunk(pages)
