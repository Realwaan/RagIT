# Production readiness work

Status: in progress. Do not describe the application as production-ready yet.

## Implemented in the current worktree

- Removed ALMA project references from source, sample content, launcher, and setup documentation.
- Added an authenticated background upload API: POST `/upload-jobs`, GET and DELETE `/upload-jobs/{id}`.
- Status is scoped to the submitting account and stored in SQLite. Restart recovery marks unfinished jobs interrupted. The user can reattach; incomplete work is not advertised as ready.
- One ingestion slot bounds concurrent document processing, including legacy uploads and the sample. Busy requests receive 429. This still assumes a single server worker.
- Progress reports extraction page counts, embedding passage counts, stages, and elapsed time.
- Cancellation and a 30-minute deadline are cooperative at processing checkpoints. They do not kill a native OCR call mid-execution. Admission is held until the worker stops.
- The UI uploads once, polls status, shows progress, and requests cancellation on removal.

## Verification so far

- Python suite rerun on October 30: 340 passed. Pytest emitted a nonfatal cache-write permission warning.
- TypeScript/Vite build passed; a large dependency chunk warning remains.
- Six Node tests passed again on October 30; TypeScript/Vite build also passed. Browser fixture suite previously passed with the job API fixture; it was not rerun in this verification pass.
- Real-document benchmark script added. First six pages: cold ingestion 18.22s (17.51s extraction), cached ingestion 15.79ms. Report: `reports/netter-small-performance.json`. These are local ingestion timings, not answer latency.
- First full 538-page benchmark completed: cold indexing 607.52s (534.69s extraction, 61.68s embeddings), cached indexing 1.36s, 17,350 passages. Report: `reports/netter-full-performance.json`. This historical run does not establish reliability of subsequent changes.
- Subsequent full-book run failed in OCR on physical page 173 with ONNX Runtime `bad allocation`. Its progress file stops at 171/538; it must not be treated as a running or successful benchmark. Log: `reports/netter-full-performance-v2.log`. Peak memory and a successful repeat remain outstanding.
- Real local HTTP application check passed for six PDF pages: background acceptance 65.74ms, health response during processing 3.8ms, attachment 18.37s; document evidence and startup recovery checked. Report: `reports/processing-runtime.json`. This does not establish production authentication or concurrent-user performance.

## Required next work

Active diagnosis: physical page 173 succeeds in isolation (3.79s cold indexing, 856.9 MiB peak process working set including source loading). Report: `reports/netter-page173-diagnostic.json`. This suggests the full-run context matters; it does not establish the cause. A new full run with failure and peak-memory reporting is underway in exec session `32944`, output `reports/netter-full-performance-v3.json`.

1. Diagnose the full-book OCR allocation failure and complete a successful repeat with peak-memory measurements. The supplied PDF contains 538 physical pages; printed page numbering differs. Do not extrapolate a six-page result to the whole book.
2. Improve measured extraction bottlenecks without silently dropping image text or tables; verify evidence fidelity.
3. Bound decoded image/page/chunk resources, concurrent request bodies, resident vault memory, and storage usage. Add explicit limits and useful rejection behavior.
4. Exercise the real background upload API, concurrent users, retries, cancellation, restart, and UI progress beyond mocked browser responses. Handle polling/network interruption and recover job tracking across reloads.
5. Review job retention and document deletion interactions, background index races, backup/restore, logging, health/readiness, and operational instructions.
6. Review the existing untracked Docker files and produce a reproducible deployment build, persistent storage, HTTPS, and production authentication setup.
7. Independently inspect real answers/citations and complex visual questions. Existing expected-term matching does not establish answer accuracy.
8. Run final regression/build/browser checks and an actual production configuration smoke test. Hosting/domain choice is pending user input.

The running user application has not been restarted by this work. Existing uploads must not be interrupted without inspecting their live state.

