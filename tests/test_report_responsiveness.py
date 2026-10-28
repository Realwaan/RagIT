"""A slow export must not prevent the same event loop serving health requests."""
import asyncio
import threading

import httpx

import app.main as main
import app.report_routes as reports


def test_slow_pdf_export_keeps_api_responsive(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_pdf(**kwargs):
        started.set()
        assert release.wait(5), 'Export blocked the API event loop'
        return b'%PDF-test'

    monkeypatch.setattr(reports, 'build_pdf_bytes', slow_pdf)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                    base_url='http://test') as client:
            export = asyncio.create_task(client.post('/export-report', json={
                'query': 'Example', 'answer': 'Example answer', 'format': 'pdf',
            }))
            try:
                assert await asyncio.to_thread(started.wait, 2)
                health = await asyncio.wait_for(client.get('/health'), timeout=2)
                assert health.status_code == 200
            finally:
                release.set()
                result = await export
            assert result.content == b'%PDF-test'

    asyncio.run(exercise())
