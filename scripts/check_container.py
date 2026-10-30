"""Run inside the built image with --network none, as its non-root user."""
import json
import os

assert os.getuid() != 0, 'Container must run as non-root'
os.environ.update(RAGIT_AUTH_MODE='local', RAGIT_ENV='development', VISION_ENABLED='false')

from PIL import Image, ImageDraw, ImageFont
from app.ocr import recognize_image
from app.embeddings import embed_texts
from app.main import app
from fastapi.testclient import TestClient

image = Image.new('RGB', (640, 100), 'white')
ImageDraw.Draw(image).text((20, 20), 'RAGIT OFFLINE TEST 42', fill='black', font=ImageFont.load_default(size=36))
lines = recognize_image(image)
assert '42' in ' '.join(line['text'] for line in lines), lines
vectors = embed_texts(['Offline embedding verification.'])
assert len(vectors) == 1 and len(vectors[0]) == 384
with TestClient(app) as client:
    assert client.get('/ready').status_code == 200
    response = client.post('/upload', files={'file': ('offline.txt', b'The retention period is 42 days.')})
    assert response.status_code == 200, response.text
    doc_id = response.json()['doc_id']
    assert client.get('/api/ast/' + doc_id).status_code == 200
    assert client.delete('/vault/' + doc_id).status_code == 200
print(json.dumps({'passed': True, 'uid': os.getuid(), 'checks': [
    'offline OCR recognized test text', 'offline embeddings', 'readiness',
    'real upload and evidence', 'deletion'], 'scope': 'Isolated non-root container; local auth; no network'}))
