# RagIT refactor verification

## Phase 1 audit

Already present: whole-document NPZ reuse, startup model preloading, a locked model
singleton, lazy visual metadata, first-page-only previews, a background LanceDB
worker, and regex-based classification. There are no LLM calls in ingestion; a new
test fails if ingestion touches any LLM client factory.

Implemented: exact-text SQLite + LRU embedding reuse, deduplication and stable
length-bucketed batches of 64, one combined child/leaf request, Arrow fixed-size
vector columns, cached Lance table handles, smaller PDFium critical sections,
process-based extraction above a configurable page threshold, shared clipped
rendering and atomic quality-80/method-1 WebP publication. Duplicate visual evidence
is merged only when text matches and bbox IoU is at least 0.9. Explicitly marked
adjacent table continuations retain all rows, original text paragraphs, and aliases
for prior visual URLs.

The secondary index still asks for its title-prefixed leaf strings, preserving
existing behavior and monkeypatch compatibility; those vectors are already cached,
so there is no second model-inference pass. The `child_embeddings_ms` stage now
includes priming the leaf cache. Public response keys remain unchanged.

No quantization change: the installed FastEmbed catalog contains only one supported
`sentence-transformers/all-MiniLM-L6-v2` entry (384 dimensions, `model.onnx`), without
a separately supported INT8 variant of that same model. `EMBEDDING_MODEL` remains
configurable. No unsupported download or unmeasured quantized default was introduced.
On the baseline SOP and 72-page PDF, before/after child vectors had mean and minimum
cosine similarity 1.0 (float32 measured precision). Pipeline version was bumped
because batching and visual handling changed.

Benchmark inputs are the existing 2,190-byte SOP and 542,083-byte, 72-page
`comporgLesson1_handout.pdf`. Cold measurements use a new process and empty application
caches, with model download excluded; timings include model initialization.
Peak RSS samples the parent plus any child processes every 10 ms. These are single
local runs, not p95 estimates or guarantees. Benchmark artifacts stay in ignored
`data/index/`; JSON summaries are recorded alongside this report.

`PDF_PARALLEL_PAGE_THRESHOLD` defaults to 20 and `PDF_PROCESS_WORKERS` to 2 (capped
at 4). Each worker receives a path and page range, never the PDF bytes. Unsupported
process creation falls back to serial extraction. Output ordering and text match
the serial path in regression coverage. Full-page layout detection remains a
serialized native operation; AST wiring, text normalization, Pillow conversion,
encoding, and file writes are outside the PDF lock.

## Phase 2 audit

Modules moved using `git mv` into ingestion, storage, auditing, and core packages.
Internal imports and test imports now use the package paths. Identity-based legacy
aliases are retained for the benchmark and compatibility checks, including shared
module attributes used by monkeypatch fixtures. Configuration still resolves the
repository root, not the new core package directory.

Uploads did not trigger compliance or discrepancy scans before this refactor and
still do not. New audit-job endpoints use a separate single-worker executor with
lock-protected status/results. Polling and chat remain available during a blocked
audit; duplicate jobs reuse pending/completed results, failed jobs can retry, and
completion never changes the selected document. Jobs and their result cache remain
in-process; server restarts discard job status. Existing synchronous routes and
response keys are unchanged.

Both UIs, model-facing names, API title, reports, launcher, and README now use RagIT.
The Markdown report retains a historical "formerly AuditGuard" attribution to
preserve the explicitly protected legacy export assertion. Browser storage keys
and internal browser events keep their old names to preserve saved chats. The
repository contains only the compiled React bundle, so its display strings were
updated directly while preserving its asset URL. There is no React source build
pipeline in this checkout.

Routing audit: `/` remains the primary UI; `/assistant` is retained. Both `/static`
and `/assets` are used, so neither mount was removed. Tests cover both pages, the
React JavaScript/CSS, primary JavaScript, and RagIT branding.

Generated crops are now ignored, with `.gitkeep` retained. The two named images
were untracked without deleting their local copies; a source-reference search
found no dependencies on their names. `.env` is not tracked and has no entries in
the available `git log --all -- .env` history. This does not audit remote history
that is absent from the local clone.

The root live-model script moved to `tests/test_gemma_integration.py`. It has a
registered integration marker and a no-argument test, skips without GEMINI_API_KEY
or on connection/server-unavailability errors, and fails on reachable endpoint
configuration errors. Offline regression runs explicitly clear provider keys.
