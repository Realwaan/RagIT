"""Local OCR for raster evidence. Inference never holds the PDFium lock."""
import os
from threading import Lock

_engine = None
_lock = Lock()
OCR_VERSION = 'rapidocr-3-local-v1'


def _is_uniform_image(image) -> bool:
    """Return True if the image is too small for glyphs or is a single solid color."""
    try:
        if image.width < 4 or image.height < 4:
            return True
        extrema = image.getextrema()
        if not extrema:
            return False
        if isinstance(extrema[0], tuple):
            return all(lo == hi for lo, hi in extrema)
        return extrema[0] == extrema[1]
    except Exception:
        return False


def recognize_image(image):
    """Return recognized lines with confidence, retaining low-confidence evidence."""
    global _engine
    if _is_uniform_image(image):
        return []
    import numpy as np
    with _lock:
        if _engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise ValueError('This PDF needs local OCR. Install the project requirements and retry.') from exc
            _engine = RapidOCR(params={
                'EngineConfig.onnxruntime.intra_op_num_threads': min(4, os.cpu_count() or 1),
                'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                'Global.text_score': 0.3,
            })
        # RapidOCR numpy input uses OpenCV's BGR channel order.
        rgb = image if getattr(image, 'mode', None) == 'RGB' else image.convert('RGB')
        try:
            bgr = np.asarray(rgb)[:, :, ::-1].copy()
        finally:
            if rgb is not image:
                rgb.close()
        result = _engine(bgr)
    boxes = result.boxes if result.boxes is not None else []
    return [{'text': str(text), 'confidence': float(score),
             'box': boxes[index].tolist() if index < len(boxes) else None}
            for index, (text, score) in enumerate(zip(result.txts or [], result.scores or []))]
