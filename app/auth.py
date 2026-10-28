"""Clerk session verification and durable, deny-by-default document ownership."""
import asyncio
import os
import posixpath
import re
import sqlite3
from contextvars import ContextVar

from clerk_backend_api import AuthenticateRequestOptions, authenticate_request
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import config as cfg

current_user = ContextVar('current_user', default=None)


def enabled():
    return os.getenv('RAGIT_AUTH_MODE', 'clerk') != 'local'


def user_id():
    user = current_user.get()
    if enabled() and not user:
        raise HTTPException(401, 'Sign in to continue.')
    return user


def connection():
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


def owned_ids():
    owner = user_id()
    db = connection()
    try:
        return {row[0] for row in db.execute('SELECT doc_id FROM owners WHERE user_id=?', (owner,))}
    finally:
        db.close()


def require_document(doc_id):
    if enabled() and doc_id not in owned_ids():
        raise HTTPException(404, 'Document not found.')


def verify_session(request):
    secret = os.getenv('CLERK_SECRET_KEY')
    if not secret:
        raise HTTPException(503, 'Authentication is not configured.')
    parties = [v.strip() for v in os.getenv('CLERK_AUTHORIZED_PARTIES',
               'http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173').split(',') if v.strip()]
    state = authenticate_request(request, AuthenticateRequestOptions(
        secret_key=secret, jwt_key=os.getenv('CLERK_JWT_KEY'),
        authorized_parties=parties, accepts_token=['session_token']))
    if not state.is_signed_in or not state.payload or not state.payload.get('sub'):
        raise HTTPException(401, 'Sign in to continue.')
    return state.payload['sub']


class AuthenticationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not enabled():
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = posixpath.normpath(request.url.path)
        if path == '/health':
            return await JSONResponse({'status': 'healthy'})(scope, receive, send)
        # Only the app shell and its build assets are public. Document images are not.
        if path in ('/', '/assistant') or path.startswith(('/static/assistant/', '/assets/')):
            return await self.app(scope, receive, send)
        token = None
        try:
            user = await asyncio.to_thread(verify_session, request)
            token = current_user.set(user)
            if path in ('/classic', '/api/model/toggle') or path.startswith('/vault/select/'):
                raise HTTPException(403, 'This legacy operation is unavailable in account mode.')
            if path.startswith('/static/'):
                match = re.fullmatch(r'/static/(?:previews|crops)/(doc_[0-9a-f]{32})_[A-Za-z0-9_]+\.(?:webp|png)', path)
                if not match:
                    raise HTTPException(404, 'Not found.')
                await asyncio.to_thread(require_document, match[1])
            async def private_send(message):
                if message['type'] == 'http.response.start':
                    message['headers'] = list(message.get('headers', [])) + [(b'cache-control', b'private, no-store')]
                await send(message)
            await self.app(scope, receive, private_send)
        except HTTPException as exc:
            await JSONResponse({'detail': exc.detail}, status_code=exc.status_code)(scope, receive, send)
        finally:
            if token is not None:
                current_user.reset(token)
