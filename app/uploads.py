"""Bound application memory while reading multipart upload spool files."""
from fastapi import HTTPException, UploadFile
from threading import BoundedSemaphore
from starlette.responses import JSONResponse
from starlette.formparsers import MultiPartException
from app import config as cfg


class UploadAdmissionMiddleware:
    """Bound simultaneous multipart parsing before FastAPI consumes the body."""
    def __init__(self, app):
        self.app = app
        self.slot = BoundedSemaphore(1)

    async def __call__(self, scope, receive, send):
        upload = scope['type'] == 'http' and scope.get('method') == 'POST' and scope.get('path', '').rstrip('/') in ('/upload', '/upload-jobs')
        if not upload:
            return await self.app(scope, receive, send)
        # Allow multipart headers in addition to the file limit. Count actual
        # bytes too: Content-Length can be absent or dishonest.
        limit = cfg.MAX_UPLOAD_SIZE_BYTES + 1024 * 1024
        headers = dict(scope.get('headers', []))
        try:
            declared = int(headers.get(b'content-length', b'0'))
            if declared < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)(scope, receive, send)
        if declared > limit:
            return await JSONResponse({'detail': 'Upload request exceeds the size limit.'}, status_code=413)(scope, receive, send)
        if not self.slot.acquire(blocking=False):
            return await JSONResponse({'detail': 'Another document is being uploaded. Please retry shortly.'},
                                      status_code=429, headers={'Retry-After': '10'})(scope, receive, send)
        received = 0
        exceeded = False

        async def bounded_receive():
            nonlocal received, exceeded
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > limit:
                    exceeded = True
                    # Starlette closes partial multipart spool files when
                    # this exception interrupts its parsing loop.
                    raise MultiPartException('Upload request exceeds the size limit.')
            return message

        async def bounded_send(message):
            if exceeded and message['type'] == 'http.response.start':
                message = {**message, 'status': 413}
            await send(message)

        try:
            await self.app(scope, bounded_receive, bounded_send)
        finally:
            self.slot.release()


async def read_bounded_upload(file: UploadFile, limit: int) -> bytes:
    """Read at most limit + 1 bytes, rejecting overflow before ingestion."""
    contents = bytearray()
    while True:
        chunk = await file.read(min(1024 * 1024, limit - len(contents) + 1))
        if not chunk:
            return bytes(contents)
        contents.extend(chunk)
        if len(contents) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size of {limit // (1024 * 1024)} MB.",
            )
