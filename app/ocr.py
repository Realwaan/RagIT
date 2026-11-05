"""Local OCR for raster evidence. Inference never holds the PDFium lock."""
import os
from threading import Lock, local

_engines = local()
_init_lock = Lock()
OCR_VERSION = 'rapidocr-3-local-v2'


def _int_env(name, default, low, high):
    try:
        return max(low, min(high, int(os.environ.get(name, default))))
    except ValueError:
        return default


# Parallel OCR workers each own an engine; ONNX threads are split between them.
OCR_WORKERS = _int_env('RAGIT_OCR_WORKERS', max(1, min(4, (os.cpu_count() or 1) // 4)), 1, 16)
# Lines scoring below this are re-read once from an upscaled crop.
OCR_RERUN_BELOW = float(os.environ.get('RAGIT_OCR_RERUN_BELOW', '0.6'))
OCR_RERUN_MAX_LINES = _int_env('RAGIT_OCR_RERUN_MAX_LINES', 24, 0, 500)


def _is_uniform_image(image) -> bool:
    """Return True if the image is too small for glyphs or is a single solid color."""
    try:
        if image.width < 8 or image.height < 8:
            return True
        extrema = image.getextrema()
        if not extrema:
            return False
        if isinstance(extrema[0], tuple):
            return all((hi - lo) < 4 for lo, hi in extrema)
        return (extrema[1] - extrema[0]) < 4
    except Exception:
        return False


def _get_engine():
    """Return this thread's engine so OCR inference can run concurrently."""
    engine = getattr(_engines, 'engine', None)
    if engine is None:
        with _init_lock:
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise ValueError('This PDF needs local OCR. Install the project requirements and retry.') from exc
            engine = RapidOCR(params={
                'EngineConfig.onnxruntime.enable_cpu_mem_arena': False,
                'EngineConfig.onnxruntime.intra_op_num_threads': max(1, (os.cpu_count() or 1) // OCR_WORKERS),
                'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                'Global.text_score': 0.3,
                'Global.log_level': 'error',
            })
            det = engine._load_det_model()
            orig_get_preprocess = det.get_preprocess

            def _bounded_preprocess():
                op = orig_get_preprocess()
                orig_resize = op.resize

                def _resize(img):
                    h, w = img.shape[:2]
                    if min(h, w) < op.limit_side_len and max(h, w) > 0:
                        import cv2
                        ratio = min(float(op.limit_side_len) / min(h, w), 2.0, max(1.0, 1024.0 / max(h, w)))
                        rh = max(32, int(round(h * ratio / 32) * 32))
                        rw = max(32, int(round(w * ratio / 32) * 32))
                        return cv2.resize(img, (rw, rh))
                    elif max(h, w) > 1024:
                        import cv2
                        ratio = 1024.0 / max(h, w)
                        rh = max(32, int(round(h * ratio / 32) * 32))
                        rw = max(32, int(round(w * ratio / 32) * 32))
                        return cv2.resize(img, (rw, rh))
                    return orig_resize(img)

                op.resize = _resize
                return op

            det.get_preprocess = _bounded_preprocess
        _engines.engine = engine
    return engine


def _run(engine, image, use_det=True, use_cls=True, use_rec=True):
    import numpy as np
    # RapidOCR numpy input uses OpenCV's BGR channel order.
    rgb = image if getattr(image, 'mode', None) == 'RGB' else image.convert('RGB')
    try:
        bgr = np.asarray(rgb)[:, :, ::-1].copy()
    finally:
        if rgb is not image:
            rgb.close()
    result = engine(bgr, use_det=use_det, use_cls=use_cls, use_rec=use_rec)
    boxes = getattr(result, 'boxes', None)
    boxes = boxes if boxes is not None else []
    return [{'text': str(text), 'confidence': float(score),
             'box': boxes[index].tolist() if index < len(boxes) else None}
            for index, (text, score) in enumerate(zip(result.txts or [], result.scores or []))]


def _reread_low_confidence(engine, image, lines):
    """Re-read weak lines from a padded 2x crop; keep the result only if it scores higher."""
    from PIL import Image
    weak = sorted((l for l in lines if l['confidence'] < OCR_RERUN_BELOW and l.get('box')
                   and any(c.isascii() and c.isalnum() for c in l.get('text', ''))),
                  key=lambda l: l['confidence'])[:OCR_RERUN_MAX_LINES]
    for line in weak:
        try:
            xs = [p[0] for p in line['box']]
            ys = [p[1] for p in line['box']]
            pad = max(4, int((max(ys) - min(ys)) * 0.25))
            box = (max(0, int(min(xs)) - pad), max(0, int(min(ys)) - pad),
                   min(image.width, int(max(xs)) + pad), min(image.height, int(max(ys)) + pad))
            if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                continue
            crop = image.crop(box)
            try:
                crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
                again = _run(engine, crop, use_det=False, use_cls=False, use_rec=True)
            finally:
                crop.close()
            if not again:
                continue
            text = ' '.join(item['text'] for item in again).strip()
            score = min(item['confidence'] for item in again)
            if text and score > line['confidence']:
                line.update(text=text, confidence=score, reread=True)
        except Exception:
            continue  # The first-pass reading stays as evidence.


def recognize_image(image):
    """Return recognized lines with confidence, retaining low-confidence evidence."""
    if _is_uniform_image(image):
        return []
    engine = _get_engine()
    lines = _run(engine, image)
    if OCR_RERUN_MAX_LINES and OCR_RERUN_BELOW > 0:
        _reread_low_confidence(engine, image, lines)
    return lines
