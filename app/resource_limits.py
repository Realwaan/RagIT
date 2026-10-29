"""Validate document expansion before allocating decoded images or model inputs."""
import math

from app import config as cfg


def checked_pixels(width, height, *, scale=1):
    width, height = float(width) * scale, float(height) * scale
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise ValueError('Document contains invalid image or page dimensions.')
    pixels = math.ceil(width) * math.ceil(height)
    if pixels > cfg.MAX_IMAGE_PIXELS:
        raise ValueError(f'An image or page exceeds the {cfg.MAX_IMAGE_PIXELS:,}-pixel processing limit. Reduce its resolution and retry.')
    return pixels


def check_text_size(size):
    if size > cfg.MAX_EXTRACTED_TEXT_BYTES:
        raise ValueError('Extracted document text exceeds the processing limit. Split the document into smaller files.')


def check_chunk_count(count):
    if count > cfg.MAX_DOCUMENT_CHUNKS:
        raise ValueError(f'Document exceeds the {cfg.MAX_DOCUMENT_CHUNKS:,}-passage processing limit. Split it into smaller files.')
