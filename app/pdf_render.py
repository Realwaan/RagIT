"""PDFium rasterization is serialized; Pillow conversion and encoding are not."""
import os
import tempfile
from pathlib import Path
import pypdfium2 as pdfium
from app.pdf_lock import PDF_LOCK


def render_pdf_image(source, page_num, scale=1.5, bbox=None):
    with PDF_LOCK:
        pdf = pdfium.PdfDocument(str(source) if isinstance(source, Path) else source)
        try:
            if not 1 <= page_num <= len(pdf):
                raise ValueError("Page outside PDF")
            page = pdf[page_num - 1]
            crop = (0, 0, 0, 0)
            if bbox is not None:
                width, height = page.get_width(), page.get_height()
                x0, y0, x1, y1 = bbox
                crop = (max(0, x0), max(0, y0), max(0, width - x1), max(0, height - y1))
            bitmap = page.render(scale=scale, crop=crop)
        finally:
            pdf.close()
    try:
        return bitmap.to_pil().copy()
    finally:
        with PDF_LOCK:
            bitmap.close()


def save_webp(image, path):
    """Atomic publication prevents concurrent requests from serving partial files."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".webp", delete=False) as stream:
            temporary = stream.name
        image.save(temporary, "WEBP", lossless=False, quality=80, method=1)
        os.replace(temporary, path)
    finally:
        image.close()
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
