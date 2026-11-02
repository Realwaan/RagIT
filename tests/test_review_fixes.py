import asyncio
import pytest
from fastapi import HTTPException
from app import auth, model_routes
from app.queue import InMemoryTaskQueue
from app.database import PostgreSQLDatabase


def test_postgres_fails_explicitly():
    with pytest.raises(NotImplementedError):
        PostgreSQLDatabase('unused')

@pytest.mark.anyio
async def test_queue_overload_does_not_leak_job():
    queue = InMemoryTaskQueue(max_pending=1)
    await queue.enqueue('test', {})
    with pytest.raises(asyncio.QueueFull):
        await queue.enqueue('test', {})
    assert len(queue.jobs) == 1

@pytest.mark.parametrize('user,allowed', [('ordinary', False), ('admin', True), (None, False)])
def test_model_admin(monkeypatch, user, allowed):
    monkeypatch.setattr(auth, 'enabled', lambda: True)
    monkeypatch.setenv('RAGIT_ADMIN_USER_IDS', 'admin')
    token = auth.current_user.set(user)
    try:
        if allowed:
            model_routes.require_model_admin()
        else:
            with pytest.raises(HTTPException) as exc:
                model_routes.toggle_model()
            assert exc.value.status_code == 403
    finally:
        auth.current_user.reset(token)
