"""In-process audit jobs, isolated from upload and chat request handling."""
import logging
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock
from uuid import uuid4

from app.auditing.audit_scanner import run_compliance_audit
from app.auditing.discrepancy_scanner import scan_ast_for_discrepancies

logger = logging.getLogger(__name__)


class AuditJobManager:
    def __init__(self, compliance=None, discrepancies=None):
        self._compliance = compliance or run_compliance_audit
        self._discrepancies = discrepancies or scan_ast_for_discrepancies
        self._lock = Lock()
        self._executor = None
        self._jobs = {}
        self._by_document = {}

    def submit(self, doc_id, retriever, ast):
        with self._lock:
            previous = self._jobs.get(self._by_document.get(doc_id))
            if previous and previous["status"] != "failed":
                return deepcopy(previous)
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audit-job")
            job_id = uuid4().hex
            job = {"job_id": job_id, "doc_id": doc_id, "status": "queued", "progress": 0,
                   "result": None, "error": None}
            self._jobs[job_id] = job
            self._by_document[doc_id] = job_id
            self._executor.submit(self._run, job_id, retriever, ast)
            return deepcopy(job)

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None

    def _update(self, job_id, **fields):
        with self._lock:
            self._jobs[job_id].update(fields)

    def _run(self, job_id, retriever, ast):
        self._update(job_id, status="running", progress=10)
        try:
            compliance = self._compliance(retriever)
            self._update(job_id, progress=60)
            discrepancies = self._discrepancies(ast, use_llm=False)
            self._update(job_id, status="completed", progress=100,
                         result={"compliance": compliance, "discrepancies": discrepancies})
        except Exception:
            logger.exception("Audit job %s failed", job_id)
            self._update(job_id, status="failed", error="Audit failed; submit again to retry.")

    def shutdown(self):
        with self._lock:
            executor, self._executor = self._executor, None
        if executor:
            executor.shutdown(wait=True)
