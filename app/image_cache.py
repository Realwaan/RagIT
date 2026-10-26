"""Validate cached image artifacts and publish complete files atomically."""
import os
import tempfile

from PIL import Image


def valid_image(path):
    try:
        with Image.open(path) as image:
            image.load()
        return True
    except (OSError, ValueError, SyntaxError):
        return False


def save_image(image, path, **options):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.webp', delete=False) as handle:
            temporary = handle.name
        image.save(temporary, 'WEBP', **options)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
