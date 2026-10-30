"""Exercise real job ingestion and recovery with isolated storage and local models.

No hosted model calls, fake OCR, fake embeddings, or user-vault mutations.
Use --input PDF to process its first six pages; otherwise use a small text file.
"""
import argparse
import io
import json
import os
import tempfile
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, default=Path('reports/processing-runtime.json'))
    args = parser.parse_args()
    contents, filename = b'The service guarantees 99.9% uptime. Retention lasts 42 days.', 'runtime.txt'
    if args.input:
        from pypdf import PdfReader, PdfWriter
        reader, writer = PdfReader(args.input), PdfWriter()
        for page in reader.pages[:6]:
            writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        contents, filename = output.getvalue(), 'runtime-six-pages.pdf'
    with tempfile.TemporaryDirectory(prefix='ragit-runtime-') as directory:
        root = Path(directory)
        os.environ.update(RAGIT_AUTH_MODE='local', RAGIT_ENV='development', VISION_ENABLED='false',
                          RAGIT_DATA_DIR=str(root / 'data'), RAGIT_PREVIEWS_DIR=str(root / 'previews'),
                          RAGIT_CROPS_DIR=str(root / 'crops'))
        from fastapi.testclient import TestClient
        from app import main as server
        checks, stages = [], set()
        with TestClient(server.app) as client:
            start = time.perf_counter()
            response = client.post('/upload-jobs', files={'file': (filename, contents)})
            accepted_ms = (time.perf_counter() - start) * 1000
            assert response.status_code == 202, response.text
            job = response.json()['id']
            checks.append('upload accepted as a background job')
            assert client.get('/upload-jobs/missing').status_code == 404
            heartbeat = time.perf_counter()
            assert client.get('/health').status_code == 200
            heartbeat_ms = (time.perf_counter() - heartbeat) * 1000
            while time.perf_counter() - start < 180:
                status = client.get('/upload-jobs/' + job)
                assert status.status_code == 200, status.text
                state = status.json()
                if state['status'] == 'ready':
                    result = state['result']
                    break
                assert state['status'] in ('receiving', 'processing'), state
                stages.add(state['stage'])
                time.sleep(0.25)
            else:
                raise AssertionError('Job did not complete within 180 seconds')
            assert result['pages_processed'] == (6 if args.input else 1)
            assert result['cache_warning'] is None
            doc_id = result['doc_id']
            assert any(item['doc_id'] == doc_id for item in client.get('/vault').json()['vault'])
            assert client.get('/api/ast/' + doc_id).status_code == 200
            if args.input:
                assert client.get(f'/api/preview/{doc_id}/6').status_code == 200
            checks.extend(['real extraction and embeddings completed', 'document listed and evidence accessible'])
        # Drop process-local document state; startup must recover from its catalog.
        server.DOCUMENT_VAULT.clear()
        server.DOCUMENT_ASTS.clear()
        server._sync_active('')
        with TestClient(server.app) as client:
            assert any(item['doc_id'] == doc_id for item in client.get('/vault').json()['vault'])
            assert client.get('/upload-jobs/' + job).json()['status'] == 'ready'
            checks.append('catalog and completed job recovered on startup')
            assert client.delete('/vault/' + doc_id).status_code == 200
            assert client.get('/api/ast/' + doc_id).status_code == 404
            assert client.get('/upload-jobs/' + job).json()['status'] == 'failed'
            assert not any(item['doc_id'] == doc_id for item in client.get('/vault').json()['vault'])
            checks.append('deletion removes document access and invalidates completed upload tracking')
            retry = client.post('/upload-jobs', files={'file': (filename, contents)})
            assert retry.status_code == 202, retry.text
            retry_id = retry.json()['id']
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                state = client.get('/upload-jobs/' + retry_id).json()
                if state['status'] == 'ready':
                    break
                assert state['status'] in ('receiving', 'processing'), state
                time.sleep(0.25)
            else:
                raise AssertionError('Reattachment did not complete within 180 seconds')
            assert state['result']['doc_id'] == doc_id
            assert client.get('/api/ast/' + doc_id).status_code == 200
            checks.append('deleted document reattaches with real extraction and usable evidence')
        report = {'passed': True, 'scope': 'Real local models and HTTP ASGI application; local authentication mode. Separate signed-token tests cover account isolation.',
                  'checks': checks, 'observed_stages': sorted(stages), 'accepted_ms': round(accepted_ms, 2),
                  'health_during_processing_ms': round(heartbeat_ms, 2),
                  'attachment_ms': result['attachment_duration_ms'], 'pages': result['pages_processed']}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
