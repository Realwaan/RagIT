import asyncio

import pytest
from fastapi import HTTPException

from app.uploads import read_bounded_upload
from app.uploads import UploadAdmissionMiddleware


class RecordingUpload:
    def __init__(self, content):
        self.content = content
        self.offset = 0

    async def read(self, size):
        assert 0 < size <= 1024 * 1024
        chunk = self.content[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


@pytest.mark.parametrize('size', [0, 9, 10])
def test_accepts_up_to_exact_limit(size):
    assert asyncio.run(read_bounded_upload(RecordingUpload(b'x' * size), 10)) == b'x' * size


def test_overflow_stops_reading_before_consuming_entire_file():
    upload = RecordingUpload(b'x' * 1000)
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_bounded_upload(upload, 10))
    assert error.value.status_code == 413
    assert upload.offset == 11


def test_ingress_admission_rejects_before_reading_second_body():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        consumed, responses = [], []

        async def app(scope, receive, send):
            entered.set()
            await release.wait()
            consumed.append(await receive())

        async def receive():
            return {'type': 'http.request', 'body': b'payload'}

        async def send(message):
            responses.append(message)

        middleware = UploadAdmissionMiddleware(app)
        scope = {'type': 'http', 'method': 'POST', 'path': '/upload-jobs'}
        first = asyncio.create_task(middleware(scope, receive, send))
        await entered.wait()
        await middleware(scope, receive, send)
        assert responses[0]['status'] == 429
        assert not consumed
        release.set()
        await first
        await middleware(scope, receive, send)
        assert len(consumed) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize('declared', [False, True])
def test_multipart_body_limit_closes_partial_files(monkeypatch, declared):
    from fastapi import FastAPI, UploadFile
    from starlette.testclient import TestClient
    from starlette import formparsers
    from app import config

    monkeypatch.setattr(config, 'MAX_UPLOAD_SIZE_BYTES', 10)
    opened = []
    original = formparsers.SpooledTemporaryFile

    def track(*args, **kwargs):
        file = original(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(formparsers, 'SpooledTemporaryFile', track)
    app = FastAPI()
    app.add_middleware(UploadAdmissionMiddleware)

    @app.post('/upload-jobs')
    async def upload(file: UploadFile):
        return {'size': file.size}

    prefix = b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n\r\n'
    chunks = [prefix + b'x' * 100, b'x' * (1024 * 1024), b'\r\n--boundary--\r\n']
    headers = {'Content-Type': 'multipart/form-data; boundary=boundary'}
    if declared:
        headers['Content-Length'] = str(sum(map(len, chunks)))
    else:
        async def stream_request():
            pending = iter(chunks)
            messages = []

            async def receive():
                return {'type': 'http.request', 'body': next(pending), 'more_body': True}

            async def send(message):
                messages.append(message)

            await app({'type': 'http', 'method': 'POST', 'path': '/upload-jobs',
                       'query_string': b'', 'headers': [(b'content-type', headers['Content-Type'].encode())]},
                      receive, send)
            assert messages[0]['status'] == 413

        asyncio.run(stream_request())
        assert opened and all(file.closed for file in opened)
    with TestClient(app) as client:
        response = client.post('/upload-jobs', content=iter(chunks), headers=headers)
        assert response.status_code == 413
        assert all(file.closed for file in opened)
        # A rejected body must release admission for the next request.
        assert client.post('/upload-jobs', files={'file': ('ok.txt', b'ok')}).status_code == 200
