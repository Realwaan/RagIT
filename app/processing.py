"""Bounded ingestion jobs with private, durable status and cooperative cancellation.

Only one process may serve the vault. A restart marks unfinished jobs interrupted;
it never silently retries a user's upload or claims a partial index is ready.
"""
import asyncio
import json
import logging
import sqlite3
import time
import uuid
from contextvars import ContextVar
from contextlib import contextmanager
from threading import Event, Lock

from fastapi import HTTPException

observer = ContextVar('ingestion_observer', default=None)
logger = logging.getLogger(__name__)


class ProcessingStopped(Exception):
    pass


def report_progress(stage, completed=None, total=None):
    callback = observer.get()
    if callback:
        callback(stage, completed, total)


class ProcessingJobs:
    def __init__(self, path, capacity=1, timeout=1800):
        self.path = path
        self.capacity = capacity
        self.timeout = timeout
        self.lock = Lock()
        self.active = {}
        self.tasks = set()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, updated REAL NOT NULL, payload TEXT NOT NULL)')
                db.execute('CREATE INDEX IF NOT EXISTS jobs_updated ON jobs(updated)')
                yield db
        finally:
            db.close()

    def save(self, job_id, owner, payload):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO jobs VALUES (?, ?, ?, ?)',
                       (job_id, owner, time.time(), json.dumps(payload)))

    def recover(self):
        with self.connect() as db:
            rows = db.execute('SELECT id, owner, payload FROM jobs').fetchall()
            for job_id, owner, raw in rows:
                payload = json.loads(raw)
                if payload['status'] in ('processing', 'receiving'):
                    payload.update(status='interrupted', message='The server restarted during processing. Attach the document again.')
                    db.execute('UPDATE jobs SET payload=?, updated=? WHERE id=?', (json.dumps(payload), time.time(), job_id))
            db.execute('DELETE FROM jobs WHERE updated < ?', (time.time() - 86400,))

    def reserve(self, owner):
        with self.lock:
            if len(self.active) >= self.capacity:
                raise HTTPException(429, 'Document processing is busy. Please retry shortly.', headers={'Retry-After': '10'})
            job_id = uuid.uuid4().hex
            self.active[job_id] = (owner, Event())
        try:
            with self.connect() as db:
                db.execute('DELETE FROM jobs WHERE updated < ?', (time.time() - 86400,))
            self.save(job_id, owner, {'id': job_id, 'status': 'receiving', 'stage': 'receiving'})
        except Exception:
            self.release(job_id)
            raise
        return job_id

    def release(self, job_id):
        with self.lock:
            self.active.pop(job_id, None)

    def get(self, job_id, owner):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM jobs WHERE id=? AND owner=?', (job_id, owner)).fetchone()
        if not row:
            raise HTTPException(404, 'Processing job not found.')
        return json.loads(row[0])

    def cancel(self, job_id, owner):
        payload = self.get(job_id, owner)
        with self.lock:
            active = self.active.get(job_id)
            if active and active[0] == owner:
                active[1].set()
        return payload

    async def run(self, job_id, owner, operation):
        started = time.monotonic()
        cancelled = self.active[job_id][1]
        last_saved = [0.0, None]

        def progress(stage, completed=None, total=None):
            now = time.monotonic()
            if cancelled.is_set():
                raise ProcessingStopped('Processing cancelled. Attach the document again to retry.')
            if now - started > self.timeout:
                raise ProcessingStopped('Processing exceeded the time limit. Try a smaller document or contact the administrator.')
            if stage != last_saved[1] or now - last_saved[0] >= 0.5:
                self.save(job_id, owner, {'id': job_id, 'status': 'processing', 'stage': stage,
                                          'completed': completed, 'total': total,
                                          'elapsed_seconds': round(now - started, 1)})
                last_saved[:] = [now, stage]

        token = observer.set(progress)
        work = None
        try:
            progress('starting')
            work = asyncio.create_task(operation())
            result = await asyncio.shield(work)
            self.save(job_id, owner, {'id': job_id, 'status': 'ready', 'result': result})
        except asyncio.CancelledError:
            # Cancelling an asyncio waiter cannot kill a native OCR/embedding
            # thread. Keep its admission slot until it reaches a checkpoint.
            cancelled.set()
            if work is not None:
                try:
                    await work
                except Exception:
                    pass
            self.save(job_id, owner, {'id': job_id, 'status': 'interrupted', 'message': 'Processing was interrupted. Attach the document again.'})
            raise
        except ProcessingStopped as exc:
            self.save(job_id, owner, {'id': job_id, 'status': 'cancelled' if cancelled.is_set() else 'failed', 'message': str(exc)})
        except (ValueError, HTTPException) as exc:
            self.save(job_id, owner, {'id': job_id, 'status': 'failed', 'message': str(exc.detail) if isinstance(exc, HTTPException) else str(exc)})
        except Exception:
            logger.exception('Ingestion job %s failed', job_id)
            self.save(job_id, owner, {'id': job_id, 'status': 'failed', 'message': 'Document processing failed. Retry or contact the administrator with the job ID.'})
        finally:
            observer.reset(token)
            self.release(job_id)

    def start(self, job_id, owner, operation):
        task = asyncio.create_task(self.run(job_id, owner, operation))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def shutdown(self):
        with self.lock:
            for _, event in self.active.values():
                event.set()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
