# Document RAG priorities — 2026-10-26

## Scope

### Local OCR layout recovery — 2026-10-29

The three remaining real-document development failures now use bounded local
page-image analysis for simple layouts: aligned category/range cards, numbered
side-by-side panels, and stacked fractions. This path reads OCR bounding boxes,
requires high-confidence labels, rejects ambiguous matches, and checks actual
fraction-bar and equals-sign pixels. It does not hardcode document answers,
category names, target numbers, or page numbers. Existing vision/refusal paths
remain available when these checks cannot extract an answer.

The first retrieved page is rendered under the PDF lock; up to eight page OCR
results are cached by path, modification time and page. Answers retain original
image links and are explicitly marked `needs_review` / `local_ocr_layout`, not
semantically verified. Original page images were inspected during development.
Independent review remains outstanding. Diagnostic renders and OCR boxes are
saved under `reports/page-*-diagnostic.*` and `reports/page-*-ocr-diagnostic.json`.

Fresh unchanged 24-case development evaluation: 24/24 term matches, 21/21
answerable citation-page matches, zero false refusals, and 3/3 unanswerable
refusals. These are development proxies, not general accuracy. Full backend suite:
317 passed, including spatial ordering, low-confidence rejection, missing panel
and missing fraction/equals-stroke regressions. Frozen-code synthetic reruns remain
78/90 development and 51/60 held-out. No hosted requests or held-out tuning.
Cold local OCR raised real-document p95 latency to approximately 1.91 seconds.

### Offline source selection improvement — 2026-10-29

Explicit requests for examples, operations, authorship, construction and meanings
now select complete relevant source units instead of blindly using the top child
chunk (which may be a slide footer). Specialized fact/table/definition paths retain
precedence. General questions retain their existing fallback. Selection copies
source text and its citation; it does not establish semantic correctness.

Real-document development proxy matching improved from 16/24 to 21/24 (87.5%).
Citation-page matching remains 20/21; the remaining failures are two OCR-related
questions and one visual refusal with vision disabled. This is development-set
improvement, not independent generalization evidence. Updated v2 report and blank
review template are saved; independent judgments remain pending.

Application code was frozen before rerunning synthetic development and held-out
splits. Results remain 78/90 and 51/60 respectively. The full backend suite passed
312 tests; two additional selection regressions were then added and all five
focused selection tests passed. No hosted requests were made. Separate concurrent
frontend/authentication edits were left intact.

### Real-document development evaluation v2 — 2026-10-29

The real-document runner now labels term/page matches as proxies rather than
answer/citation correctness. The previous runner did not load independent human
judgments; its historical claim of human-reviewed citations must not be treated
as evidence supplied by that runner. Extraction failures are unknown rather than
automatically zero, and missing terms do not imply unsupported claims.

Eight questions were authored from original CS lecture PDF pages before running,
bringing the development set to 24 questions across the same three documents.
Multi-part questions require all expected terms, with word boundaries. This is
expanded development coverage, not new document diversity or a held-out test.
Application code was unchanged. Offline results: 16/24 term matches, 20/21
answerable citation-page matches, 1/21 false refusals, and 3/3 unanswerable
refusals. All answerable cases retrieved an expected page in the top ten.

Saved `reports/real-document-evaluation-v2.json` includes source PDF, case,
application and runner hashes, generated answers and retrieved source excerpts.
The companion `.review-template.json` binds blank reviewer judgments to answer
hashes. Independent answer correctness and claim support remain unevaluated;
the runner does not claim a passed release gate. Original results are preserved.

Failure inspection shows several offline answers selecting slide headers or a
related sentence instead of the requested example/list. One visual refusal is
expected with vision disabled. Next investigate sentence selection and extraction
using these development cases, add general regression examples, then evaluate a
separate frozen document set. Do not tune on existing synthetic held-out failures.
Three new tests cover complete-term matching, state restoration after failure,
and rejection of production execution; all passed. The expanded run made no
hosted requests. Run with `python -m scripts.real_document_eval` in a dedicated
development process.

**Current verification (2026-10-29):** The dated results below are historical.
References to hashes matching "current files" describe the files at that run,
not the latest checkout. The old live-vision reports do not match today's
application hash. Do not present their scores as current application accuracy.

The benchmark now uses a scoped local-auth fixture vault and restores the
caller's authentication mode and vault afterward. Production runs are rejected.
Use a dedicated development CLI process; this is not a production auth bypass.
New reports record the benchmark runner hash as well as application and manifest
hashes. `--verify-report PATH` checks all three and exits nonzero when stale or
missing provenance is found. It does not certify semantic answer quality.

Fresh offline runs with unchanged application/scoring code between splits:

| Metric | Development | Held-out |
| --- | --- | --- |
| Expected-answer match | 78/90 (86.67%) | 51/60 (85%) |
| Supporting-page recall@10 | 100% | 100% |
| Citation-page match | 83.33% | 83.33% |
| False refusals | 16.67% | 16.67% |
| Unanswerable refusals | 100% | 100% |

Reports: `reports/document-baseline-development-current.json` and
`reports/document-baseline-held_out-current.json`. Both pass all three provenance
checks. Development failures are the 12 answerable visual questions with hosted
vision disabled. Held-out failures are eight such visual questions and the
existing scanned-text mismatch. No held-out tuning was performed. Both human
metrics and release gates remain unevaluated; no hosted requests were made.

Run `scripts/check.ps1 -Baseline` to include both offline splits and provenance
verification in local checks. This checks execution and provenance, not a passing
human-reviewed quality gate. The next accuracy milestone is a fresh live-vision
evaluation followed by independent answer/claim review and broader real-document
coverage; changing retrieval based on these offline visual refusals is unwarranted.

Implement the first three priorities from the repository review: establish a
repeatable baseline, distinguish relevance from evidence support, and pin
questions/audits to explicit documents. Persistence, authentication, reranking,
new formats, and asynchronous audits remain later milestones.

## Delivered design

1. A versioned, authored 150-question synthetic corpus with 30 two-page PDFs.
   Six categories, document-disjoint development/held-out splits (90/60), source
   page labels, fixture hashes, answer hashes, and a review-bound release gate.
   Automated matching and citation-page metrics are explicitly proxies. Human
   correctness and claim-support metrics cannot silently default to passing.
2. Heuristic retrieval scores replace purported NLI probabilities. Citation-ID
   validity and conservative source-sentence support are separate outputs.
   Unsupported and uncertain claim units remain reviewable in the assistant.
   Reports and the classic dashboard no longer call similarity a probability.
3. Explicit document IDs for question, legacy stream, chat, compliance, and
   discrepancy routes. Resolve document state before awaiting work and return
   document identity. Missing/unknown IDs cannot silently use the active file.
   The legacy text stream buffers verified results; the chat SSE route preserves
   incremental generation and reports the final check on completion.

## Validation and limits

- Tests cover wrong numbers with valid citations, missing citations, negation,
  dropped conditions, concurrent questions, switching selection during audits,
  missing/unknown IDs, and document-disjoint benchmark splits.
- Run the backend suite, frontend build/rendering checks, and both offline
  benchmark splits. Keep failures in the baseline; do not tune held-out cases.
- The exact-sentence checker deliberately leaves paraphrases uncertain. It is
  not an NLI implementation and does not assess the truth of source material.
- Synthetic templates are shared across splits. Add independently authored real
  documents before interpreting the results as generalization performance.
- Hosted visual/text correctness and human claim judgments remain unevaluated
  until explicit live runs and independent review are supplied.

## Next iteration

Use development failures to investigate retrieval versus generation/refusal
errors. Freeze those changes before rerunning held-out evaluation. Add a broader
real-document test set, then evaluate a semantic claim checker and reranker
against this baseline. Persist document metadata and jobs in the following phase.

## Recorded implementation checks

- Full backend suite: 173 tests passed. After adding review-gate and stream
  identity tests, the focused trust/scope suite passed all 21 tests.
- TypeScript/Vite production build and all six rendering tests passed.
- Chromium fixture checks passed, including opening the uncertain-claims review
  panel. These browser checks do not assess hosted model accuracy.
- Offline development set: 90 questions, 64.44% expected-answer match.
- Offline held-out set: 60 questions, 61.67% expected-answer match.
- Both splits: 100% supporting-page recall@10, 25% false refusals, and 100%
  refusal on the authored unanswerable questions. The two-page fixtures make
  page recall an easy test; it must not be interpreted as large-corpus retrieval
  accuracy. Scanned text and offline visual answers expose additional failures.
- Reports remain `not_evaluated` for human correctness and the release gate.
  No hosted-model benchmark or independent human review was performed.

API migration is intentional: callers must now send `doc_id` on question and
audit routes. Consumers of the removed text-evaluation confidence/NLI fields
must use `retrieval_score`, `citation_verified`, and `claim_support` separately.

## Resumed implementation and validation — 2026-10-27

The follow-up adds conservative property extraction and narrow question
paraphrases, preserving source conditions and displaying conflicting statements.
OCR measurement spacing is normalized without changing values. Visual questions
refuse when the visual provider is unavailable rather than treating captions as
successful visual answers.

The SQLite document catalog now restores explicitly attached documents from
compatible ingestion caches at startup and resubmits background indexing. It
preserves document identity and renamed citations, excludes unregistered caches,
and reports missing, corrupt, and incompatible entries. A damaged search entry
does not prevent other documents from recovering. Catalog write failures leave
uploads searchable with a warning. This does not persist browser conversations,
the user's last selected document, or in-flight job execution state; startup
selects the latest registered document and resubmits work.

Validation:

- `python -m pytest tests -q -p no:cacheprovider`: 208 passed, including ten new
  catalog/restart tests.
- `npm test`: six rendering tests passed. `npm run build`: passed with existing
  Vite configuration and bundle-size warnings.
- `git diff --check`: passed.
- Offline development: 84.44% expected-answer match (previous baseline 64.44%).
- Offline held-out: 80.00% expected-answer match (previous baseline 61.67%).
  Code was unchanged between the development and held-out runs.
- Both splits: 16.67% false refusals, 100% unanswerable refusals, and 83.33%
  citation-page match. Remaining failures include OCR errors and visual questions
  refused with hosted vision disabled. Results are synthetic matching proxies;
  human correctness and release gates remain `not_evaluated`.
- Updated reports: `reports/document-baseline-development-improved.json` and
  `reports/document-baseline-held_out-improved.json`; original baselines retained.

An unrestricted discovery run (`python -m pytest -q`) also collected the separate
root-level `test_gemma4.py` live smoke script. Its Google API call failed with 404
because the active model name was `llama-3.1-8b-instant`. The application test suite
above passed; hosted-model correctness remains unvalidated.

The smoke-script mismatch was subsequently fixed: `test_gemma4.py` now accepts
`--provider primary|fallback` and uses that provider's configured endpoint,
credentials, and model together. Ordinary pytest discovery no longer executes
the live check. Six mocked regression cases cover provider selection, missing
credentials, empty streams, and safe failure reporting. Full root-level discovery
now passes all 214 tests (`python -m pytest -q -p no:cacheprovider`). The CLI help
and whitespace checks pass. No live hosted request was made for this follow-up;
the application pipeline and benchmark hashes are unchanged.

## OCR spacing improvement — 2026-10-27

Development failures showed correct numeric values glued to the preceding copula
(`is20 days`), which hurt readability and failed the benchmark's word-boundary
match. Property answers now insert the missing space after `is`/`are` before
numeric values and between numbers and time units. Signed values, conditions,
and original citation excerpts are preserved. The conservative source checker
uses the same spacing normalization; changed values still require review.
Identifiers and negation are not guessed or corrected.

The benchmark fixtures and scoring logic are unchanged. This is a formatting
and exact-match improvement, not evidence of improved semantic reasoning.
Code was frozen after development validation and before the held-out rerun.

| Offline synthetic metric | Previous | Current |
| --- | --- | --- |
| Development expected-answer match | 84.44% | 86.67% (78/90) |
| Held-out expected-answer match | 80.00% | 85.00% (51/60) |
| Unanswerable refusal, both splits | 100% | 100% |
| False refusal, both splits | 16.67% | 16.67% |
| Citation-page match, both splits | 83.33% | 83.33% |

Full root-level test discovery: 223 passed. Whitespace checks passed. Reports
`reports/document-baseline-development-ocr-spacing.json` and
`reports/document-baseline-held_out-ocr-spacing.json` both match the current
pipeline hash. Previous reports are retained for comparison.

Remaining held-out failures are eight visual questions with vision disabled and
one scanned-text answer. No held-out-specific corrections were made. Hosted
vision and human-reviewed correctness remain unevaluated; all release gates
remain `not_evaluated`.

## Live vision and image-cache recovery — 2026-10-27

The development run can now enable vision independently of hosted text generation
with `--live-vision`, select an available model with `--vision-model`, and pace
requests with `--vision-rpm`. The report records the distinct
`extractive_with_live_vision` mode, model, request limit, and visual token usage.
Questions, expected answers, fixtures, and matching rules are unchanged.

Live evaluation exposed an empty cached visual crop. Crops and page previews now
validate cached images and regenerate unreadable artifacts from the source PDF.
New images are written to temporary files and atomically replaced, preserving
the previous artifact if a write fails. Empty and corrupt cache recovery and
failed-write preservation have regression coverage.

Full root-level test discovery after these changes: 231 passed. Benchmark-mode
tests also cover provider isolation, visual token accounting, and request pacing.

Provider availability affected the initial attempts: the configured Gemini 2.5
Flash returned 404, Gemini 3.8 Flash returned overload/timeouts, and Gemini 3.6
Flash reached 86/90 matches (95.56%) before the bad crop and request limits caused
four failures. Its report is retained as
`reports/document-baseline-development-vision-3.6.json`. The subsequent paced
3.6 attempt was stopped when the API reported its daily free allowance exhausted.
No billing settings were changed.

The final paced development run with `gemini-3.5-flash-lite` completed after the
session interruption. Its report was recovered and checked on resume: all 90
questions match their expected answers, including all 15 visual-category cases.
The report's pipeline and manifest hashes match the current files.

- Expected-answer match: 100% (90/90).
- Citation-page match and unanswerable refusal: 100%; false refusal: 0%.
- Request pacing: 4 vision requests per minute; hosted text generation disabled.
- Reported p95 latency: 45.93 seconds; total tokens: 59,166; cost not calculated.
- Report: `reports/document-baseline-development-vision-lite.json`.

These are development-set synthetic matching results, not independently reviewed
accuracy. Human correctness, claim-support precision, and the release gate remain
unevaluated. No held-out live-vision run has been completed; the last offline
held-out score remains 85% (51/60). This resume verified the completed report and
recorded its results without rerunning hosted requests or changing application code.

## Held-out live vision validation — 2026-10-27

The follow-up held-out run used the same `gemini-3.5-flash-lite` model and four
vision requests per minute, with hosted text generation disabled. Pipeline and
manifest hashes match the development report and current files. No application,
fixture, or scoring changes were made between runs.

- Expected-answer match: 98.33% (59/60), including all ten visual-category cases.
- Citation-page match and unanswerable refusal: 100%; false refusal: 0%.
- The only mismatch is the existing scanned-text case `scanned-5-q3`; no
  held-out-specific correction was made.
- Reported p95 latency: 28.39 seconds; total tokens: 39,429; cost not calculated.
- Report: `reports/document-baseline-held_out-vision-lite-live.json`.
- Full root-level test discovery: 231 passed.

The initial sandboxed attempt was interrupted after socket access was blocked
(WinError 10013); the completed report comes from the network-enabled rerun.
These remain synthetic expected-answer matching results. Human correctness,
claim-support precision, and the release gate remain `not_evaluated`.
