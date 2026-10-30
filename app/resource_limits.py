"""Validate document expansion before allocating decoded images or model inputs."""
import math
import shutil

from app import config as cfg


def check_storage_headroom(input_bytes):
    """Admission guard, not a filesystem quota or a reservation against other apps."""
    required = cfg.MIN_STORAGE_FREE_BYTES + 2 * input_bytes
    for directory in (cfg.DOCS_DIR, cfg.INDEX_DIR, cfg.PREVIEWS_DIR, cfg.CROPS_DIR):
        if shutil.disk_usage(directory).free < required:
            raise ValueError('The server has insufficient free storage to process this upload. Free space or contact the administrator.')


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


def check_vault_capacity(entries, doc_id, chunk_count):
    """Bound resident documents across accounts; replacing one is not additive."""
    others = [entry for entry in entries if entry['doc_id'] != doc_id]
    if len(others) + 1 > cfg.MAX_VAULT_DOCUMENTS:
        raise ValueError('The server document capacity is full. Delete unused documents or contact the administrator.')
    if sum(entry['total_chunks'] for entry in others) + chunk_count > cfg.MAX_VAULT_CHUNKS:
        raise ValueError('The server search capacity is full. Delete unused documents or contact the administrator.')
