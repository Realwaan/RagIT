import asyncio

import pytest
from fastapi import HTTPException

from app.processing import ProcessingJobs, report_progress


def test_deletion_invalidates_only_owners_matching_completed_jobs(tmp_path):
    jobs = ProcessingJobs(tmp_path / 'jobs.sqlite3')
    for job, owner, doc in [('one', 'alice', 'deleted'), ('two', 'bob', 'deleted'), ('three', 'alice', 'kept')]:
        jobs.save(job, owner, {'id': job, 'status': 'ready', 'result': {'doc_id': doc}})
    jobs.forget_document('deleted', 'alice')
    recovered = ProcessingJobs(jobs.path)
    assert recovered.get('one', 'alice')['status'] == 'failed'
    assert 'result' not in recovered.get('one', 'alice')
    assert recovered.get('two', 'bob')['status'] == 'ready'
    assert recovered.get('three', 'alice')['status'] == 'ready'


def test_capacity_owner_isolation_and_restart(tmp_path):
    jobs = ProcessingJobs(tmp_path / 'jobs.sqlite3')
    first = jobs.reserve('alice')
    with pytest.raises(HTTPException) as busy:
        jobs.reserve('bob')
    assert busy.value.status_code == 429
    for operation in (jobs.get, jobs.cancel):
        with pytest.raises(HTTPException) as missing:
            operation(first, 'bob')
        assert missing.value.status_code == 404
    restarted = ProcessingJobs(jobs.path)
    restarted.recover()
    assert restarted.get(first, 'alice')['status'] == 'interrupted'
    assert restarted.reserve('bob')


def test_progress_survives_thread_and_result_is_durable(tmp_path):
    jobs = ProcessingJobs(tmp_path / 'jobs.sqlite3')
    job = jobs.reserve('alice')

    async def operation():
        await asyncio.to_thread(report_progress, 'extracting_pages', 5, 20)
        status = jobs.get(job, 'alice')
        assert (status['stage'], status['completed'], status['total']) == ('extracting_pages', 5, 20)
        return {'doc_id': 'example'}

    asyncio.run(jobs.run(job, 'alice', operation))
    assert not jobs.active
    assert ProcessingJobs(jobs.path).get(job, 'alice')['result'] == {'doc_id': 'example'}


@pytest.mark.parametrize('mode', ['cancel', 'timeout', 'error'])
def test_failure_releases_capacity_without_false_ready(tmp_path, mode):
    jobs = ProcessingJobs(tmp_path / 'jobs.sqlite3', timeout=-1 if mode == 'timeout' else 60)
    job = jobs.reserve('alice')
    if mode == 'cancel':
        jobs.cancel(job, 'alice')

    async def operation():
        raise RuntimeError('private diagnostic with server path')

    asyncio.run(jobs.run(job, 'alice', operation))
    result = jobs.get(job, 'alice')
    assert result['status'] == ('cancelled' if mode == 'cancel' else 'failed')
    assert 'private diagnostic' not in result['message']
    assert jobs.reserve('bob')


def test_cancelled_waiter_holds_slot_until_worker_stops(tmp_path):
    jobs = ProcessingJobs(tmp_path / 'jobs.sqlite3')
    job = jobs.reserve('alice')

    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()

        async def operation():
            started.set()
            await finish.wait()
            report_progress('saving')

        task = asyncio.create_task(jobs.run(job, 'alice', operation))
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        with pytest.raises(HTTPException):
            jobs.reserve('bob')
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert not jobs.active
    assert jobs.get(job, 'alice')['status'] == 'interrupted'
