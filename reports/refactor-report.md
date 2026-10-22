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

## Phase 3 verification

Final run: **66 passed, 1 skipped** in 7.66 seconds. All eight requested regression
modules pass. The skipped test is the optional live Gemini integration; no live
provider response was verified. Existing test assertions were preserved. Both
JavaScript bundles pass `node --check`, and `git diff --check` is clean.

Final review found that eager text-table rendering could cache the first page
before continuation stitching. AST construction now defers rendering until all
duplicates and continuations have been merged, then uses the lazy renderer for
eager crops too. Dropped continuation aliases also carry forward their own aliases.
A new test compares eager/lazy stitched image pixels and verifies the old URL's
file. Another test proves table handles are reused and refreshed after overwrite.

The final benchmark was run without the test suite running concurrently. Inputs
and model are identical to baseline. Source JSON: `indexing-before.json` and
`indexing-after.json`; intermediate phase-one results: `indexing-phase1.json`.

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Cold search-ready latency, small text (ms) | 2,367.28 | 1,585.21 | -33.0% |
| Cold search-ready latency, 72-page PDF (ms) | 11,639.16 | 7,350.13 | -36.8% |
| Cold complete including LanceDB, small text (ms) | 2,738.58 | 1,611.13 | -41.2% |
| Cold complete including LanceDB, PDF (ms) | 17,563.90 | 7,369.22 | -58.0% |
| Warm document-cache latency, small text (ms) | 23.35 | 10.47 | -55.2% |
| Warm document-cache latency, PDF (ms) | 60.01 | 31.03 | -48.3% |
| Model embed calls per document, small text | 2 | 1 | -1 |
| Model embed calls per document, PDF | 2 | 6 | +4 bounded batches |
| Embedding cache hit rate, second similar text | 0% | 93.1% | +93.1 percentage points |
| Throughput, small text (child chunks/sec) | 7.18 | 10.72 | +49.3% |
| Throughput, PDF (child chunks/sec) | 24.66 | 39.05 | +58.4% |
| Peak RSS, small text (MiB) | 333.45 | 365.66 | +9.7% |
| Peak RSS, PDF (MiB) | 1,106.24 | 804.26 | -27.3% |
| Mean crop render + encode, small text (ms) | 257.34 | 102.00 | -60.4% |
| Mean crop render + encode, PDF (ms) | 131.80 | 44.44 | -66.3% |

PDF model calls increased because each call is now capped at 64 inputs. Previously,
two large API calls fed child and leaf inputs separately; now six bounded batches
cover distinct inputs once. Calling `index_ast` adds **zero** inference calls in
this final run. API-call count is not the same as the number of embedded strings
or internal ONNX execution batches.

Throughput is `child_chunk_count / cold_ready_seconds` (17 and 287 chunks), not
embedding-only throughput. Warm latency measures `prepare_document` cache reuse;
it does not include an HTTP upload or a fresh background write. The second similar
text is the same SOP plus one added retention clause; hit rate is
`1 - newly_inferred_strings / unique_requested_strings`. It is not a corpus-wide
cache statistic; this metric was not measured for a similar PDF. Crop time averages
the first up to five lazy crops. Peak RSS is the maximum sampled sum of parent and
child RSS across the complete worker workload (cold, warm, crop and similar-document
steps), in bytes / 1024^2; this includes shared pages counted in each process.

Final vector comparison against baseline: SOP (17 x 384) and PDF (287 x 384) both
have minimum and mean cosine **1.0** at measured float32 precision. This verifies
vector equivalence on these inputs, not end-to-end answer accuracy for all documents.

## What indexing and the UI metrics actually measure

The upload path hashes the content and checks the document cache. On a miss it
extracts text, saves the PDF, renders the first preview, builds the AST and visual
links, creates child/parent chunks, embeds exact child and leaf strings, saves the
document cache, and initializes hybrid search. It then publishes the selected
document and queues LanceDB persistence. Remaining previews and crops render when
requested. Classification is regex-based; no LLM runs during attachment.

An observed 20-second attachment can include CPU embedding, parsing, model startup,
cache misses and request/browser overhead. These runs establish costs for the two
fixtures, not the cause of every past 20-second observation. In the final PDF run,
embedding plus model initialization consumed 6,013 ms and extraction 1,049 ms;
those are the remaining dominant measured costs. In the baseline, PDF embedding
alone consumed 9,315 ms, followed by another leaf inference pass during persistence.

`indexing_duration_ms` uses `time.perf_counter` inside `prepare_document`; it ends
at search readiness. `attachment_duration_ms` measures the server handler through
document publication and queue submission. Neither measures the browser's full
file-selection-to-ready experience or completed background persistence. The UI
"index speed" value is a duration, not a rate. `retrieval_ms` times initial hybrid
retrieval (including query embedding and thread scheduling), excluding later
whole-page escalation. `total_ms` covers the answer handler's retrieval,
verification, generation and baseline comparison, excluding client/network time.
Token counts come from provider usage when available; zero in offline mode does
not mean local embedding computation was free.

The timings are measured, but **confidence and entailment are heuristic scores**.
`evaluate_relevance` takes the maximum dense score, sometimes multiplies it by
0.65 when query coverage is zero, and displays it times 100 as confidence. Its
`nli_entailment_prob` is a weighted formula using dense score and lexical coverage;
there is no NLI model or calibration dataset here. Whole-page escalation can itself
put a blended lexical/dense score in the `dense_score` field. "ENTAILED" and
"Verified" therefore overstate what these checks prove. Citation verification
checks valid marker IDs; it does not establish that each cited excerpt supports
each generated claim. These semantics were left unchanged under the requested
public-contract and existing-assertion constraints.

## Document-RAG fit and remaining priorities

RagIT fits the broad **document-RAG** category: it ingests user documents, retrieves
hybrid semantic/keyword evidence, injects excerpts into generation, and returns
source/page citations with visual links. No official hackathon rubric was supplied,
so this is category fit, not confirmation of every judging criterion.

Strengths compared with a basic vector-only demo: parent/child context, BM25 plus
dense rank fusion, linked visual evidence, explicit refusal paths, deterministic
audit checks, offline extractive fallback, persistent content reuse, and measured
pipeline stages. These are useful design choices, not evidence that it outperforms
an enterprise system on answer quality.

There is no single enterprise-standard stack. Microsoft's guidance separates
ingestion, retrieval and generation evaluation, and its search service documents
document-level permission filtering. Those are useful comparison points here:
[RAG design and evaluation](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-solution-design-and-evaluation-guide),
[RAG search and security](https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview).

| Gap in this checkout | Recommended next change |
|---|---|
| Confidence/entailment labels imply proven correctness | Label current values as retrieval heuristics; build a labeled question/evidence set and report recall@k, answer correctness, claim support and refusal precision separately. |
| Citation checks only validate IDs | Check claim-to-excerpt support; keep retrieval relevance distinct from answer faithfulness. [Ragas faithfulness](https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/faithfulness.md) evaluates response consistency with context. |
| Text parsing and caption heuristics cannot reliably read scanned pages or chart values | Add OCR/layout extraction selectively for low-text pages, then test tables, rotated scans and charts with human-labeled evidence. |
| Active document and vault are process-global; routes lack tenant/document authorization | Introduce authenticated sessions, document ownership and permission filtering before retrieval and before serving source/crop URLs. |
| In-memory job status, unbounded result/disk caches and local process state | Add retention/eviction and durable jobs with retry/cancellation if deploying multiple workers; keep audit-policy/model versions in result-cache keys. |
| Main hybrid retrieval scans the active document in memory; no learned reranker | Benchmark larger corpora first; use indexed filtered candidate retrieval and test a reranker only if it improves labeled retrieval results within latency limits. |
| Uploaded text is placed in prompts without a tested injection defense | Explicitly mark excerpts as untrusted data and test adversarial documents; enforce authorization independently of prompts. [OWASP RAG security](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html) covers source, retrieval and generation boundaries. |
| One local latency sample per input, no concurrency or tail latency study | Repeat cold/warm runs, report p50/p95 with hardware/model/cache state, and measure client attachment time separately from server readiness and persistence. |

For more speed, retain startup model warmup and persistent caches, benchmark worker
counts/page thresholds on the deployment CPU, and profile the remaining embedding
cost before adding concurrency. Large-file uploads still wait for searchable
embeddings; immediate upload acknowledgment would need a separate ingestion job
contract and UI progress flow. This refactor intentionally preserves `/upload`.

Already done: document-level caching, startup warmup, background persistence, lazy
visuals and no ingestion LLM. Changed: exact-text reuse, batching, bulk writes,
PDF processing/rendering, package boundaries, audit jobs, hygiene and RagIT branding.
Accepted limits: small-document peak RSS rose 9.7%; job state is in-process;
embedding inference shares a lock and may contend under load; cached crops and
SQLite need a future retention policy; the React source is unavailable. Left alone:
model default/quantization, retrieval scoring and refusal thresholds, provider
configuration, old HTTP contracts and both UI routes. No production deployment,
external-model evaluation or enterprise-readiness certification was performed.
