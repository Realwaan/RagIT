"""Local OCR for raster evidence. Inference never holds the PDFium lock."""
import os
from threading import Lock

_engine = None
_lock = Lock()
OCR_VERSION = 'rapidocr-3-local-v1'


def recognize_image(image):
    """Return recognized lines with confidence, retaining low-confidence evidence."""
    global _engine
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
        result = _engine(np.asarray(image.convert('RGB'))[:, :, ::-1].copy())
    return [{'text': str(text), 'confidence': float(score)}
            for text, score in zip(result.txts or [], result.scores or [])]
