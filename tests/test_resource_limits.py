import io
import hashlib

import pytest
from pypdf import PdfWriter

from app import config, ingest
from app.resource_limits import checked_pixels


def test_storage_guard_checks_every_artifact_location(monkeypatch):
    from types import SimpleNamespace
    from app import resource_limits
    monkeypatch.setattr(config, 'MIN_STORAGE_FREE_BYTES', 100)
    seen = []
    def disk_usage(path):
        seen.append(path)
        return SimpleNamespace(free=119 if path == config.CROPS_DIR else 1000)
    monkeypatch.setattr(resource_limits.shutil, 'disk_usage', disk_usage)
    with pytest.raises(ValueError, match='insufficient free storage'):
        resource_limits.check_storage_headroom(10)
    assert config.CROPS_DIR in seen


@pytest.mark.parametrize('mode', ['RGB', 'RGBA', 'L'])
def test_image_digest_preserves_pixels_without_full_image_copy(mode):
    from PIL import Image
    with Image.new(mode, (21, 301)) as image:
        image.putpixel((10, 129), 1 if mode == 'L' else tuple(range(len(mode))))
        expected = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        image.tobytes = lambda: pytest.fail('Full image pixel copy requested')
        assert ingest._image_digest(image) == expected


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
