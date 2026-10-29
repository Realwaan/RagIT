"""Clerk session verification and durable, deny-by-default document ownership."""
import asyncio
import logging
import os
import posixpath
import re
import sqlite3
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from threading import Lock

from clerk_backend_api import AuthenticateRequestOptions, authenticate_request
from clerk_backend_api.security.verifytoken import TokenVerificationErrorReason
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import config as cfg

logger = logging.getLogger(__name__)
current_user = ContextVar('current_user', default=None)

DEFAULT_DEV_AUTHORIZED_PARTIES = (
    'http://localhost:8000,http://127.0.0.1:8000,'
    'http://localhost:8001,http://127.0.0.1:8001,'
    'http://localhost:5173,http://127.0.0.1:5173,'
    'http://localhost:3000,http://127.0.0.1:3000'
)


def is_production():
    return os.getenv('RAGIT_ENV', 'development').strip().lower() in ('prod', 'production')


def validate_auth_config():
    """Fail closed at startup if production mode attempts to disable authentication or lacks credentials."""
    if is_production():
        if os.getenv('RAGIT_AUTH_MODE', 'clerk').strip().lower() == 'local':
            raise RuntimeError('RAGIT_AUTH_MODE=local is forbidden when RAGIT_ENV=production.')
        secret = os.getenv('CLERK_SECRET_KEY', '').strip()
        if not secret or secret.startswith('sk_test_'):
            raise RuntimeError('Production deployment requires a live CLERK_SECRET_KEY (sk_live_...).')
        parties = [v.strip() for v in os.getenv('CLERK_AUTHORIZED_PARTIES', '').split(',') if v.strip()]
        if not parties or any(p.startswith('http://') for p in parties):
            raise RuntimeError('Production deployment requires explicit HTTPS CLERK_AUTHORIZED_PARTIES.')


def enabled():
    if is_production() and os.getenv('RAGIT_AUTH_MODE', 'clerk').strip().lower() == 'local':
        raise RuntimeError('RAGIT_AUTH_MODE=local is forbidden when RAGIT_ENV=production.')
    return os.getenv('RAGIT_AUTH_MODE', 'clerk') != 'local'


def user_id():
    user = current_user.get()
    if enabled() and not user:
        raise HTTPException(401, 'Sign in to continue.')
    return user


def connection():
    cfg.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(cfg.INDEX_DIR / 'ownership.sqlite3', timeout=15)
    db.execute('CREATE TABLE IF NOT EXISTS owners (doc_id TEXT PRIMARY KEY, user_id TEXT NOT NULL)')
    return db


def grant(doc_id):
    if not enabled():
        return
    owner = user_id()
    db = connection()
    try:
        with db:
            db.execute('INSERT OR IGNORE INTO owners VALUES (?, ?)', (doc_id, owner))
            if db.execute('SELECT user_id FROM owners WHERE doc_id=?', (doc_id,)).fetchone()[0] != owner:
                raise HTTPException(404, 'Document not found.')
    finally:
        db.close()


def revoke(doc_id):
    """Remove the caller's ownership row after the document has been deleted."""
    if not enabled():
        return
    owner = user_id()
    db = connection()
    try:
        with db:
            db.execute('DELETE FROM owners WHERE doc_id=? AND user_id=?', (doc_id, owner))
    finally:
        db.close()


def owned_ids():
    owner = user_id()
    db = connection()
    try:
        return {row[0] for row in db.execute('SELECT doc_id FROM owners WHERE user_id=?', (owner,))}
    finally:
        db.close()


def all_owned_ids():
    db = connection()
    try:
        return {row[0] for row in db.execute('SELECT doc_id FROM owners')}
    finally:
        db.close()


def require_document(doc_id):
    if enabled() and doc_id not in owned_ids():
        raise HTTPException(404, 'Document not found.')


def verify_session(request):
    secret = os.getenv('CLERK_SECRET_KEY')
    if not secret:
        raise HTTPException(503, 'Authentication is not configured.')
    parties = [v.strip().rstrip('/') for v in os.getenv('CLERK_AUTHORIZED_PARTIES',
               DEFAULT_DEV_AUTHORIZED_PARTIES).split(',') if v.strip()]
    jwt_key = os.getenv('CLERK_JWT_KEY')
    clock_skew_ms = int(os.getenv('CLERK_CLOCK_SKEW_MS', '60000'))
    try:
        state = authenticate_request(request, AuthenticateRequestOptions(
            secret_key=secret, jwt_key=jwt_key,
            authorized_parties=None, clock_skew_in_ms=clock_skew_ms,
            accepts_token=['session_token', 'any']))
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning('Authentication provider error while verifying session: %s', exc)
        raise HTTPException(503, 'Authentication service is temporarily unavailable. Please retry.') from exc
    if state.is_signed_in and state.payload:
        token_azp = state.payload.get('azp')
        if token_azp is not None and str(token_azp).rstrip('/') not in parties:
            logger.warning(
                'Clerk session verification rejected on %s: azp=%s not in authorized_parties=%s',
                getattr(request, 'url', None) and request.url.path, token_azp, parties
            )
            raise HTTPException(401, 'Sign in to continue.')
    if not state.is_signed_in or not state.payload or not state.payload.get('sub'):
        reason = getattr(state, 'reason', None)
        status = getattr(state, 'status', None)
        auth_hdr = request.headers.get('Authorization')
        has_cookie = '__session' in request.cookies
        origin = request.headers.get('origin')
        host = request.headers.get('host')
        logger.warning(
            'Clerk session verification rejected on %s: status=%s reason=%s has_auth_hdr=%s has_cookie=%s origin=%s host=%s',
            getattr(request, 'url', None) and request.url.path, status, reason, bool(auth_hdr), has_cookie, origin, host
        )
        raise HTTPException(401, 'Sign in to continue.')
    return state.payload['sub']


_RATE_LOCK = Lock()
_USER_REQUEST_TIMES: dict[str, deque] = defaultdict(deque)
_USER_UPLOAD_TIMES: dict[str, deque] = defaultdict(deque)
_USER_INFLIGHT: dict[str, int] = defaultdict(int)


def _check_rate_limit(user: str, path: str) -> None:
    now = time.monotonic()
    req_limit = int(os.getenv('RAGIT_RATE_LIMIT_PER_MIN', '120'))
    upload_limit = int(os.getenv('RAGIT_UPLOAD_LIMIT_PER_HOUR', '30'))
    with _RATE_LOCK:
        q = _USER_REQUEST_TIMES[user]
        while q and now - q[0] > 60.0:
            q.popleft()
        if len(q) >= req_limit:
            raise HTTPException(429, 'Too many requests. Please wait a moment and try again.')
        q.append(now)
        if path == '/upload':
            uq = _USER_UPLOAD_TIMES[user]
            while uq and now - uq[0] > 3600.0:
                uq.popleft()
            if len(uq) >= upload_limit:
                raise HTTPException(429, 'Hourly upload quota reached. Please try again later.')
            uq.append(now)


def _acquire_concurrency(user: str) -> bool:
    max_concurrent = int(os.getenv('RAGIT_MAX_CONCURRENT_JOBS', '4'))
    with _RATE_LOCK:
        if _USER_INFLIGHT[user] >= max_concurrent:
            raise HTTPException(429, 'Too many concurrent operations in progress for this account.')
        _USER_INFLIGHT[user] += 1
        return True


def _release_concurrency(user: str) -> None:
    with _RATE_LOCK:
        if _USER_INFLIGHT[user] > 0:
            _USER_INFLIGHT[user] -= 1


class AuthenticationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = posixpath.normpath(request.url.path)

        # Ingress body size limit before multipart/JSON parsing
        max_ingress = cfg.MAX_UPLOAD_SIZE_BYTES + (2 * 1024 * 1024)
        content_length = request.headers.get('content-length')
        if content_length:
            try:
                if int(content_length) > max_ingress:
                    return await JSONResponse(
                        {'detail': f'Request body exceeds maximum allowed size of {cfg.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.'},
                        status_code=413,
                    )(scope, receive, send)
            except ValueError:
                return await JSONResponse({'detail': 'Invalid Content-Length header.'}, status_code=400)(scope, receive, send)

        received_bytes = 0

        async def bounded_receive():
            nonlocal received_bytes
            message = await receive()
            if message['type'] == 'http.request':
                received_bytes += len(message.get('body', b''))
                if received_bytes > max_ingress:
                    raise HTTPException(
                        413,
                        f'Request body exceeds maximum allowed size of {cfg.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.',
                    )
            return message

        if not enabled():
            try:
                return await self.app(scope, bounded_receive, send)
            except HTTPException as exc:
                return await JSONResponse({'detail': exc.detail}, status_code=exc.status_code)(scope, receive, send)

        if path == '/health':
            return await JSONResponse({'status': 'healthy'})(scope, receive, send)
        if path == '/favicon.ico':
            return await JSONResponse({}, status_code=204)(scope, receive, send)
        # Only the app shell and its build assets are public. Document images are not.
        if path in ('/', '/assistant', '/classic') or path.startswith(('/static/assistant/', '/static/marked.min.js', '/assets/')):
            return await self.app(scope, bounded_receive, send)
        token = None
        acquired_user = None
        heavy_paths = ('/upload', '/ask', '/query', '/api/chat', '/compliance-audit')
        try:
            user = await asyncio.to_thread(verify_session, request)
            _check_rate_limit(user, path)
            if path in heavy_paths:
                _acquire_concurrency(user)
                acquired_user = user
            token = current_user.set(user)
            if path.startswith('/static/'):
                match = re.fullmatch(r'/static/(?:previews|crops)/(doc_[0-9a-f]{32})_[A-Za-z0-9_]+\.(?:webp|png)', path)
                if not match:
                    raise HTTPException(404, 'Not found.')
                await asyncio.to_thread(require_document, match[1])
            async def private_send(message):
                if message['type'] == 'http.response.start':
                    message['headers'] = list(message.get('headers', [])) + [(b'cache-control', b'private, no-store')]
                await send(message)
            await self.app(scope, bounded_receive, private_send)
        except HTTPException as exc:
            await JSONResponse({'detail': exc.detail}, status_code=exc.status_code)(scope, receive, send)
        finally:
            if acquired_user is not None:
                _release_concurrency(acquired_user)
            if token is not None:
                current_user.reset(token)
