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
