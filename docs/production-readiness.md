# Production readiness work

Status: in progress. Do not describe the application as production-ready yet.

External deployment prerequisite: the user confirmed they do not yet have a production hostname or hosting machine. Continue local/container validation; live HTTPS and production sign-in cannot be verified until a target exists. Operational and cold-backup/restore guidance is in `docs/operations.md`; a restore rehearsal remains required.

Production authentication now requires a nonempty `sk_live_` secret format, rejecting arbitrary placeholders and publishable keys at startup. Authentication subset: 35 passed. Format validation does not prove the credential is valid with Clerk.

## Implemented in the current worktree

- Removed ALMA project references from source, sample content, launcher, and setup documentation.
- Added an authenticated background upload API: POST `/upload-jobs`, GET and DELETE `/upload-jobs/{id}`.
- Status is scoped to the submitting account and stored in SQLite. Restart recovery marks unfinished jobs interrupted. The user can reattach; incomplete work is not advertised as ready.
- One ingestion slot bounds concurrent document processing, including legacy uploads and the sample. Busy requests receive 429. This still assumes a single server worker.
- Progress reports extraction page counts, embedding passage counts, stages, and elapsed time.
- Cancellation and a 30-minute deadline are cooperative at processing checkpoints. They do not kill a native OCR call mid-execution. Admission is held until the worker stops.
- The UI uploads once, polls status, shows progress, and requests cancellation on removal.
- Upload ingress now caps actual multipart body bytes before spooling (file limit plus 1 MiB for multipart overhead), including absent or dishonest Content-Length. Oversized bodies return 413; partial spool files close and admission is released. Seven focused upload tests cover bounded file reads, concurrent admission, declared-size rejection, and streaming overflow cleanup.
- Vector deletion invalidates queued background indexing and cleans up writes that finish after deletion. Reattachment receives a fresh job; the serial worker removes stale writes before running it. Indexing/catalog subset: 29 passed, including controlled deletion/write and deletion/reattachment races.
- Visual deletion removes resident snapshots and invalidates worker identity; old workers cannot publish over a reattachment. Visual/auth subset: 52 passed. Completed upload records for the deleted document and owner become failed records without a result, including across restart; processing/auth subset: 36 passed. Deletion and ingestion now share admission to prevent concurrent artifact/ownership mutations; 37 processing/auth tests pass, including both overlap directions. Persistent visual-cache retention still requires review.

## Verification so far

- Latest full Python regression after failure cleanup: 362 passed in 35.67s (`pytest -q -p no:cacheprovider`).

- Failed preparation now cleans newly created source/preview/crop/cache artifacts in the same worker after its writes stop. Existing files and unrelated document identities are preserved. Passage-capacity rejection and cancellation at the saving checkpoint also clean new preparation artifacts. Indexing/catalog/job subset: 41 passed. Hard process termination and successful native work whose legacy HTTP waiter disappears remain outside this cleanup guarantee; crash-orphan retention is still outstanding.

- Latest full Python regression after storage admission changes: 359 passed in 41.34s (`pytest -q -p no:cacheprovider`).

- Document-count admission now runs before preparation, so a full vault rejects a new document without generating another ingestion cache. Uploads also check free space at all artifact locations before processing, requiring `RAGIT_MIN_STORAGE_FREE_BYTES` (default 512 MiB) plus twice the input size; insufficient capacity returns 507. The resource/catalog/indexing/job subset passed 49 tests. This is a free-space admission guard, not a disk quota or a reservation against other processes. Later extraction/chunk-limit failures can still leave artifacts; cleanup and platform quotas remain outstanding.

- Cold backup/restore rehearsal passed using real PDF extraction/local embeddings and fresh source/restore processes. All 16 file hashes matched; signed fixture users retained separate vaults, cross-account evidence was denied, PDF previews worked, and new upload/deletion succeeded. Report: `reports/backup-restore.json`; script: `scripts/check_backup_restore.py`. Docker-volume tooling and live Clerk remain outside this check.
- Browser component regression rerun passed (`npm run test:assistant`); report and screenshots are in `reports/frontend`. Its API responses are fixtures, so it does not establish live browser upload/authentication behavior.

- Lifecycle regression suite: 351 passed before aggregate vault limits were added. The updated catalog/capacity subset then passed all 12 tests. Full final regression remains required after remaining changes.
- Aggregate resident vault limits default to 50 documents and 150,000 searchable passages, configurable with `RAGIT_MAX_VAULT_DOCUMENTS` and `RAGIT_MAX_VAULT_CHUNKS`. Attachment rejects excess with 507; recovery reports `server_capacity` without deleting durable records. One document may be prepared before rejection. These bounds do not replace a measured process/container memory ceiling or storage quota.
- The first Linux image build completed with dependency checks passing (`ragit:readiness-check`, placeholder frontend key), but inspection found OCR initialization was lazy. The Dockerfile now pins resolved base-image digests and explicitly runs detection/classification/recognition to preload every OCR model. Rebuild session `2178` initialized all models then failed with Docker RPC EOF; subsequent engine inspection returned `Docker Desktop is unable to start`. The corrected image is not verified. `scripts/check_container.py` is prepared to check non-root offline OCR, embeddings, readiness, upload/evidence, and deletion with `--network none`; it has not run. Docker engine recovery is an external blocker for container validation, while other readiness work can continue.
- Expanded real-PDF HTTP lifecycle verification passed: `reports/processing-runtime-v2.json`. Six pages with real OCR/embeddings survived startup recovery, deletion revoked evidence access and invalidated upload tracking, and reattachment restored usable evidence. Acceptance 129.52ms, health during processing 891.85ms, first attachment 30.11s while the Docker build was also running. This is local-mode ASGI verification, not production browser/authentication or a clean latency benchmark.

- Python suite rerun on October 30: 340 passed. Pytest emitted a nonfatal cache-write permission warning.
- TypeScript/Vite build passed; a large dependency chunk warning remains.
- Six Node tests passed again on October 30; TypeScript/Vite build also passed. Browser fixture suite previously passed with the job API fixture; it was not rerun in this verification pass.
- Real-document benchmark script added. First six pages: cold ingestion 18.22s (17.51s extraction), cached ingestion 15.79ms. Report: `reports/netter-small-performance.json`. These are local ingestion timings, not answer latency.
- First full 538-page benchmark completed: cold indexing 607.52s (534.69s extraction, 61.68s embeddings), cached indexing 1.36s, 17,350 passages. Report: `reports/netter-full-performance.json`. This historical run does not establish reliability of subsequent changes.
- Subsequent full-book run failed in OCR on physical page 173 with ONNX Runtime `bad allocation`. Its progress file stops at 171/538; it must not be treated as a running or successful benchmark. Log: `reports/netter-full-performance-v2.log`. Peak memory and a successful repeat remain outstanding.
- Real local HTTP application check passed for six PDF pages: background acceptance 65.74ms, health response during processing 3.8ms, attachment 18.37s; document evidence and startup recovery checked. Report: `reports/processing-runtime.json`. This does not establish production authentication or concurrent-user performance.

## Required next work

Active diagnosis: physical page 173 succeeds in isolation (3.79s cold indexing, 856.9 MiB peak process working set including source loading). Report: `reports/netter-page173-diagnostic.json`. Run v3 failed on page 116 during a full-image pixel copy for hashing, at 1302.07 MiB peak working set. Image hashing now uses 128-row strips, preserving the digest while avoiding a full-image temporary allocation; ten resource-limit tests pass. Run v4 completed all 538 pages: 627.15s cold, 1.12s warm, 17,350 passages, 2142.14 MiB peak working set. Report: `reports/netter-full-performance-v4.json`; its progress report also records Windows commit/system telemetry. At page 1, available RAM was 506.67 MiB and available commit capacity 748.99 MiB, so host memory pressure is a material confounder. No user applications have been closed. This validates one full ingestion after the hashing change; host memory availability also improved, so the original failure cause is not isolated. Hosted answers, concurrent-user load, and container memory behavior are not covered.

1. Diagnose the full-book OCR allocation failure and complete a successful repeat with peak-memory measurements. The supplied PDF contains 538 physical pages; printed page numbering differs. Do not extrapolate a six-page result to the whole book.
2. Improve measured extraction bottlenecks without silently dropping image text or tables; verify evidence fidelity.
3. Bound decoded image/page/chunk resources, concurrent request bodies, resident vault memory, and storage usage. Add explicit limits and useful rejection behavior.
4. Exercise the real background upload API, concurrent users, retries, cancellation, restart, and UI progress beyond mocked browser responses. Handle polling/network interruption and recover job tracking across reloads.
5. Review job retention and document deletion interactions, background index races, backup/restore, logging, health/readiness, and operational instructions.
6. Review the existing untracked Docker files and produce a reproducible deployment build, persistent storage, HTTPS, and production authentication setup.
7. Independently inspect real answers/citations and complex visual questions. Existing expected-term matching does not establish answer accuracy.
8. Run final regression/build/browser checks and an actual production configuration smoke test. Hosting/domain choice is pending user input.

The running user application has not been restarted by this work. Existing uploads must not be interrupted without inspecting their live state.
