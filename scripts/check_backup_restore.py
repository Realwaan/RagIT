"""Cold-copy rehearsal in disposable storage, with fresh processes and signed users.

No user vault or hosted inference calls. Uses real local embeddings and optional
PDF extraction/OCR. This verifies application recovery, not Docker volume tooling.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def phase(args):
    root = args.root.resolve()
    os.environ.update(RAGIT_DATA_DIR=str(root / 'data'), RAGIT_PREVIEWS_DIR=str(root / 'previews'),
                      RAGIT_CROPS_DIR=str(root / 'crops'), RAGIT_AUTH_MODE='clerk',
                      RAGIT_ENV='development', VISION_ENABLED='false',
                      CLERK_SECRET_KEY='test-only-offline-fixture', CLERK_AUTHORIZED_PARTIES='http://testserver')
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from fastapi.testclient import TestClient
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    os.environ['CLERK_JWT_KEY'] = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    from app.main import app

    def headers(owner):
        now = int(time.time())
        token = jwt.encode({'sub': owner, 'sid': 'offline-session', 'iss': 'https://test.clerk.accounts.dev',
                            'azp': 'http://testserver', 'iat': now, 'nbf': now - 1, 'exp': now + 600},
                           private, algorithm='RS256')
        return {'Authorization': 'Bearer ' + token}

    with TestClient(app) as client:
        if args.phase == 'seed':
            contents, name = b'Alpha retains records for 42 days.', 'alpha.txt'
            if args.input:
                from pypdf import PdfReader, PdfWriter
                reader, writer = PdfReader(args.input), PdfWriter()
                for page in reader.pages[:2]:
                    writer.add_page(page)
                buffer = io.BytesIO()
                writer.write(buffer)
                contents, name = buffer.getvalue(), 'alpha.pdf'
            docs = {}
            for owner, filename, body in [('alpha', name, contents), ('beta', 'beta.txt', b'Beta retains records for 91 days.')]:
                response = client.post('/upload', headers=headers(owner), files={'file': (filename, body)})
                assert response.status_code == 200, response.text
                assert response.json()['cache_warning'] is None
                docs[owner] = response.json()['doc_id']
            (root / 'rehearsal.json').write_text(json.dumps({'docs': docs, 'pdf': bool(args.input)}))
        else:
            manifest = json.loads((root / 'rehearsal.json').read_text())
            docs = manifest['docs']
            for owner, doc_id in docs.items():
                response = client.get('/vault', headers=headers(owner))
                assert response.status_code == 200, response.text
                vault = response.json()
                assert [doc['doc_id'] for doc in vault['vault']] == [doc_id], vault
                assert not vault['recovery']['unavailable'], vault
                assert client.get('/api/ast/' + doc_id, headers=headers(owner)).status_code == 200
                other = 'beta' if owner == 'alpha' else 'alpha'
                assert client.get('/api/ast/' + doc_id, headers=headers(other)).status_code == 404
            if manifest['pdf']:
                url = '/api/preview/' + docs['alpha'] + '/1'
                assert client.get(url, headers=headers('alpha')).status_code == 200
                assert client.get(url, headers=headers('beta')).status_code == 404
            assert client.get('/vault').status_code == 401
            response = client.post('/upload', headers=headers('alpha'), files={'file': ('new.txt', b'New records remain writable.')})
            assert response.status_code == 200, response.text
            assert client.delete('/vault/' + response.json()['doc_id'], headers=headers('alpha')).status_code == 200


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['seed', 'verify'])
    parser.add_argument('--root', type=Path)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, default=Path('reports/backup-restore.json'))
    args = parser.parse_args()
    if args.phase:
        assert args.root is not None
        phase(args)
        return
    with tempfile.TemporaryDirectory(prefix='ragit-recovery-') as directory:
        root = Path(directory)
        source, backup, restored = (root / name for name in ('source', 'backup', 'restored'))
        source.mkdir()
        command = [sys.executable, '-m', 'scripts.check_backup_restore']
        subprocess.run(command + ['--phase', 'seed', '--root', str(source)] +
                       (['--input', str(args.input.resolve())] if args.input else []), check=True, timeout=300)
        # Seed process is terminated: no DB, vector, or OCR worker can still write.
        shutil.copytree(source, backup)
        shutil.copytree(backup, restored)
        def hashes(folder):
            result = {}
            for path in folder.rglob('*'):
                if path.is_file():
                    with path.open('rb') as handle:
                        result[str(path.relative_to(folder))] = hashlib.file_digest(handle, 'sha256').hexdigest()
            return result
        original = hashes(source)
        assert original == hashes(backup) == hashes(restored)
        subprocess.run(command + ['--phase', 'verify', '--root', str(restored)], check=True, timeout=300)
        report = {'passed': True, 'files_verified': len(original), 'pdf_included': bool(args.input),
                  'checks': ['cold copy after process exit', 'all restored file hashes match',
                             'fresh-process catalog recovery', 'two signed users remain isolated',
                             'evidence access restored', 'new upload and deletion work'],
                  'scope': 'Local application filesystem rehearsal; no Docker, live Clerk, HTTPS, or hosted answers'}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
