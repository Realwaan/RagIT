# 🛡️ RagIT

### Intelligent Document Analysis & Compliance Verification with Retrieval-Augmented Generation

**RagIT** is an AI-powered document intelligence platform built to help users analyze documents, retrieve relevant information, identify discrepancies, and generate evidence-backed answers.

Powered by **Retrieval-Augmented Generation (RAG)**, hierarchical document parsing, hybrid search, and large language models, RagIT transforms complex documents into searchable knowledge while keeping answers grounded in their original sources.

The platform is designed for document-heavy workflows such as compliance verification, policy analysis, contract review, and enterprise knowledge retrieval.

---

## 📖 Overview

Traditional AI chatbots often generate answers without verifying whether the information exists in the supplied documents. This can lead to inaccurate responses, missing context, and unsupported claims.

RagIT addresses these challenges by combining structured document processing with semantic retrieval and evidence verification.

Instead of simply passing an entire document to an LLM, RagIT:

1. Extracts and structures document content.
2. Organizes text and visual elements into a hierarchical document tree.
3. Generates local embeddings for semantic search.
4. Retrieves relevant information using hybrid search.
5. Evaluates whether the retrieved evidence supports the user's question.
6. Generates responses using an LLM configured through supported API providers.
7. Returns source references and supporting document context.

RagIT also includes automated compliance auditing, discrepancy detection, document management, and report generation.

## ✨ Key Features

### 📄 Document Processing

- Supports PDF, TXT, and Markdown documents.
- Extracts and organizes document content.
- Builds a hierarchical document structure.
- Processes paragraphs, sections, tables, and visual elements.
- Generates document previews and visual crops.
- Preserves document context for more accurate retrieval.

### 🧠 Retrieval-Augmented Generation

- Uses local embedding models through FastEmbed.
- Combines semantic vector search with BM25 keyword retrieval.
- Applies Reciprocal Rank Fusion to combine retrieval results.
- Retrieves relevant document sections rather than relying on the entire document.
- Supports context-aware answer generation.
- Provides source references for generated responses.

### 🌳 Hierarchical Document Structure

RagIT organizes extracted content into a document tree.

This hierarchy helps preserve relationships between document sections, paragraphs, and visual content.

It also enables the retrieval pipeline to access additional document context when an individual retrieved chunk is insufficient.

### 🔍 Evidence Verification

RagIT includes retrieval evaluation and answer verification mechanisms.

These mechanisms help:

- Determine whether retrieved information is relevant.
- Expand retrieval to additional page context when necessary.
- Identify questions that cannot be verified using the document.
- Reduce unsupported AI-generated answers.
- Validate generated responses against retrieved sources.

When sufficient evidence cannot be found, the system can refuse to provide an unsupported answer.

### ⚖️ Compliance Auditing

The application provides automated compliance analysis capabilities.

Features include:

- Document-based compliance checks.
- Detection of potential inconsistencies.
- Cross-modal discrepancy analysis.
- Evidence-based findings.
- Synchronous audit execution.
- Retrieval of audit results through document-scoped API endpoints.

### 🗂️ Document Vault

RagIT includes a document vault for managing uploaded and indexed documents.

Users can:

- Upload multiple documents.
- View indexed document information.
- Switch between available documents.
- Inspect document classification.
- View indexing statistics and background processing status.

The currently selected document determines the context used for question answering.

### 📊 Report Generation

RagIT can export findings and generated answers in multiple formats:

- PDF
- Microsoft Word (DOCX)
- CSV
- Markdown
- JSON

Reports can include document classifications, generated answers, evidence references, and evaluation information.

### ⚡ Performance and Caching

The application includes several optimizations for document processing and retrieval:

- Local embedding generation.
- Embedding caching using SQLite.
- Reusable document ingestion caches.
- Content-based document identification.
- Background processing for secondary indexing.
- On-demand document preview rendering.
- Reusable LanceDB indexes.
- Embedding model preloading at application startup.

These mechanisms reduce repeated processing and help make previously indexed content available more efficiently.

---

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| Web Server | Uvicorn |
| AI Integration | OpenAI-compatible API client |
| Primary LLM Provider | Groq |
| Fallback LLM Provider | Google Gemini |
| Embeddings | FastEmbed (ONNX) |
| Vector Database | LanceDB |
| Vector/Data Processing | NumPy, Apache Arrow |
| Keyword Search | BM25 |
| PDF Processing | pypdf, pypdfium2 |
| Image Processing | Pillow |
| Embedding Cache | SQLite |
| Frontend | Web dashboard, alternate React interface |
| Testing | Pytest |
| Configuration | python-dotenv |

## 🏗️ System Architecture

RagIT uses a modular architecture that separates document ingestion, storage, retrieval, generation, and auditing.

```text
                  ┌──────────────────────┐
                  │   User / Web UI      │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │    FastAPI Backend   │
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │   Document Upload    │
                  │   PDF / TXT / MD     │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Document Processing  │
                  │ Text / PDF / Visuals │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Hierarchical Doc Tree│
                  │ Sections / Paragraphs│
                  │ Tables / Figures     │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Local Embeddings     │
                  │ FastEmbed / ONNX     │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Hybrid Retrieval     │
                  │ Vector Search + BM25 │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Evidence Evaluation  │
                  │ & Context Expansion  │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ LLM Answer Generation│
                  │ Groq / Gemini        │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Verified Response    │
                  │ Sources / Evidence   │
                  └──────────────────────┘
```

Document ingestion also uses local caching and a background worker for additional embeddings and LanceDB indexing.

## 🚀 Getting Started

### Prerequisites

Before running RagIT, make sure you have:

- Python 3.11 or newer.
- Git.
- A modern web browser.
- An internet connection for initial embedding-model downloads and hosted LLM requests.
- A Groq API key and/or a Google Gemini API key for LLM-backed features.

### 1. Clone the Repository

Clone the development branch:

```bash
git clone -b dev-josh https://github.com/Realwaan/RagIT.git
cd RagIT
```

### 2. Create a Virtual Environment

Create a Python virtual environment:

```bash
python -m venv .venv
```

Activate the environment.

**Windows:**

```powershell
.venv\Scripts\activate
```

**macOS / Linux:**

```bash
source .venv/bin/activate
```

### 3. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

The first application startup may download the configured embedding model.

### 4. Configure Environment Variables

Create a `.env` file in the project root.

Example configuration:

```env
# Primary LLM Provider (Groq)
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.1-8b-instant
LLM_API_KEY=your_groq_api_key

# Fallback LLM Provider (Gemini)
FALLBACK_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
FALLBACK_MODEL=gemini-2.5-flash
FALLBACK_API_KEY=your_gemini_api_key

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Retrieval
SIMILARITY_THRESHOLD=0.50
TOP_K=4

# Optional Processing Settings
PDF_PARALLEL_PAGE_THRESHOLD=20
PDF_PROCESS_WORKERS=2
MAX_UPLOAD_SIZE_BYTES=524288000
```

**LLM configuration notes:**

- Groq is the primary LLM provider.
- Gemini serves as the fallback provider.
- The fallback also accepts `GEMINI_API_KEY` as an alternative configuration variable.
- At least one valid LLM API key is needed for hosted generation.
- Embeddings run locally through FastEmbed and do not require a hosted embedding API.
- Keep `.env` and API credentials out of version control.

### 5. Start the Application

Run the FastAPI application:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

On Windows, you can also use the included startup script:

```powershell
run.bat
```

### 6. Open RagIT

Once the server is running, open:

**Main dashboard:**

http://127.0.0.1:8000

**Alternative React interface:**

http://127.0.0.1:8000/assistant

**Interactive API documentation:**

http://127.0.0.1:8000/docs

**Health endpoint:**

http://127.0.0.1:8000/health

---

## 💻 How to Use

### Assistant workspace

The main page uses the existing assistant-ui and Radix components. Open the
document library from the folder button to search loaded files, inspect PDF
pages, and choose a document. Choosing a different file after a conversation has
started opens a new conversation, keeping earlier answers with their original
document. The classic interface remains available at `/classic`.

Conversations can be searched, renamed, and deleted. The selected conversation,
unsent drafts, response branches, and theme are saved in this browser. If the
backend restarts and a document is no longer loaded, the conversation remains
readable and prompts you to reattach the file or choose another document.

Attach one PDF, TXT, or Markdown file at a time. Upload failures appear on the
attachment; remove it and retry. Removing a processing attachment cancels the
browser request, although work already started on the server may still finish.
Responses can be stopped, regenerated, edited, copied, and exported. Export
errors appear beside the answer so the download can be retried.

Source evidence supports image retry, zoom, fit, and opening the original image.
PDF sources also offer a full-page view. Linked figures keep their own page
numbers. The library and evidence panels support keyboard navigation and small
screens, with light and dark themes.

Frontend verification:

```bash
npm run build
npm test
npm run test:assistant
```

The assistant checks run the production build in Chromium with deterministic
API fixtures. Set `CHROME_PATH` if Chrome or Edge is not in a standard location.
Screenshots and the check summary are written to `reports/frontend/`.
For real-backend integration, set `RAGIT_TEST_URL` to a running local server and
run `node scripts/check_assistant_ui.cjs <chromium-executable>`. An optional
second argument accepts the three-page `preview-fixture.pdf` used by the PDF
acceptance check. Browser checks cover interaction and evidence navigation;
they do not establish the accuracy of an external language or vision model.

### 1. Upload a Document

Open the RagIT dashboard and upload a supported document.

Supported formats:

- `.pdf`
- `.txt`
- `.md`

The backend processes the document and prepares it for retrieval.

The upload response includes information such as:

- Document ID
- Filename
- Number of processed pages
- Total document chunks
- Document tree nodes
- Cross-modal links
- Document classification
- Cache status
- Indexing duration
- Background indexing status

### 2. Ask Questions

After uploading a document, submit a question about its contents.

Example questions:

```text
What are the main requirements described in this document?

Summarize the important compliance policies.

What penalties apply if the service provider fails to
meet the agreed service level?

Are there any inconsistencies between the document's
statements and supporting tables?
```

RagIT retrieves relevant information and uses the available evidence to construct its response.

Where available, the response includes supporting sources and evaluation information.

### 3. Review Evidence

Review the retrieved evidence associated with an answer.

Depending on the document content, this can include:

- Source excerpts.
- Original document page references.
- Hierarchical document paths.
- Linked figures and visual elements.
- Retrieval and evaluation information.

### 4. Run Compliance Checks

Use the compliance audit functionality to examine the active document.

Audits run against an explicit document ID. Durable background audit jobs are planned but not implemented.

### 5. Export Results

Export generated findings and supporting evidence using the available report formats.

---

## 🔌 API Reference

RagIT provides REST endpoints through FastAPI.

The following are some of the main available endpoints.

### Document Management

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/upload` | Upload and process a document |
| `POST` | `/load-sample` | Load the built-in sample document |
| `GET` | `/vault` | List documents in the active vault |
| `POST` | `/vault/select/{doc_id}` | Select an indexed document |
| `GET` | `/api/ast` | Retrieve the active document tree |
| `GET` | `/api/ast/{doc_id}` | Retrieve a document tree by ID |

### Question Answering

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/ask` | Ask a document-grounded question |
| `POST` | `/query` | Alternative question-answering endpoint |
| `GET` | `/ask-stream` | Stream a generated answer |

### Auditing and Verification

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/compliance-audit` | Run a compliance audit |
| `GET` | `/api/discrepancies` | Scan for document discrepancies |
| `GET` | `/api/ast/discrepancies` | Alternative discrepancy endpoint |

### Other Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Check system status |
| `POST` | `/export-report` | Export generated reports |
| `GET` | `/api/crop/{doc_id}/{node_id}` | Retrieve a visual crop |
| `GET` | `/api/preview/{doc_prefix}/{page_num}` | Retrieve a page preview |
| `POST` | `/api/model/toggle` | Toggle the configured active model identifier |

### Example: Upload a Document

```bash
curl -X POST http://127.0.0.1:8000/upload \
  -F "file=@sample.pdf"
```

### Example: Ask a Question

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the main compliance requirements?",
    "doc_id": "YOUR_DOCUMENT_ID",
    "include_baseline": false
  }'
```

The response includes the generated answer, retrieval evaluation, source evidence, and execution telemetry.

Set `include_baseline` to `true` to request a comparison against an answer generated without retrieved document context.

### Example: Load Sample Document

```bash
curl -X POST http://127.0.0.1:8000/load-sample
```

### Example: Run a Document Audit

```bash
curl "http://127.0.0.1:8000/compliance-audit?doc_id=YOUR_DOCUMENT_ID"
```

`/ask`, `/query`, and `/api/chat` require `doc_id` in the JSON body.
`/ask-stream`, `/compliance-audit`, `/api/discrepancies`, and
`/api/ast/discrepancies` require it as a query parameter. Missing IDs return
422; unknown IDs return 404. Requests never fall back to the selected document.
Responses identify the requested document; changing selection does not retarget
an in-flight request. The classic and React interfaces supply the document ID.
The legacy `/ask-stream` response is buffered through the same verification path
as `/ask`; `/api/chat` retains incremental SSE events and final verification metadata.


---

## 🔄 Document Indexing and Caching

RagIT uses a staged document preparation pipeline.

### Initial Processing

When a document is uploaded, the application:

1. Validates the file.
2. Extracts text and document structure.
3. Builds the hierarchical document tree.
4. Prepares searchable text chunks.
5. Generates embeddings needed for initial retrieval.
6. Initializes the hybrid retriever.
7. Makes the document available for questions and audits.

### Background Indexing

Additional paragraph and visual embeddings can be processed by a background indexing worker.

This separates initial search readiness from secondary index completion.

The system can begin answering document questions without waiting for every background indexing operation to finish.

### Persistent Caching

RagIT stores processed document information locally to avoid unnecessary recomputation.

Important storage locations include:

| Location | Purpose |
|---|---|
| `data/docs/` | Original and locally stored documents |
| `data/index/` | Indexes and processed document data |
| `data/index/embeddings.sqlite3` | Cached embeddings |
| `data/index/ingestion-cache/` | Reusable ingestion cache |
| `app/static/previews/` | Generated page previews |
| `app/static/crops/` | Visual crops |

The ingestion cache uses document content and pipeline configuration to determine whether existing processed data can be reused.

Identical document content can reuse previously prepared data even when the uploaded filename changes.

The SQLite catalog at `data/index/vault.sqlite3` records explicitly attached
documents. On startup, compatible ingestion caches restore those documents and
their search indexes, and background indexing resumes. Unregistered cache files
are not added to the vault. Missing, damaged, or incompatible caches are reported
by `/vault` and `/health`; reattach the affected document to rebuild it. Catalog
write failures leave the current upload searchable and return a recovery warning.

---

## 🧪 Testing

RagIT uses Pytest for automated testing.

Run the test suite:

```bash
python -m pytest tests -v
```

Normal test discovery does not run the root-level live provider smoke script.
To explicitly check a configured hosted endpoint (uses API quota), run:

```bash
python test_gemma4.py --provider fallback
python test_gemma4.py --provider primary
```

The script uses the selected provider's endpoint, credentials, and model together.
It exits unsuccessfully on provider errors or empty responses, without silently
switching providers. The historical filename is retained; it can check either
configured text provider.

To check answers against an existing local PDF ingestion cache through the streaming
API, run:

```bash
python -m scripts.check_document_answers --cache data/index/ingestion-cache/<key>.npz --cases tests/fixtures/histology_questions.json --output reports/document-answer-regression.json
```

The included cases target the cached 538-page Netter histology edition and check
answer text plus cited PDF pages. The original PDF and its ingestion cache must be
present locally. This check explicitly disables external LLM calls and exercises
local retrieval and source extraction; it does not measure general answer accuracy.

### Visual evidence and accuracy checks

PDF pictures, diagrams, charts, and tables can be analyzed with a vision-capable
service. Set `VISION_API_KEY` (or the existing Gemini fallback key); optional
`VISION_MODEL` and `VISION_BASE_URL` default to the Gemini fallback configuration.
`VISION_ENABLED=false` disables image requests. Original image crops and page
overviews are sent to that service. Text search is available immediately, while
two background workers build searchable visual descriptions. Progress appears
above the composer. Reattaching a document resumes analysis using cached results.
After an application restart, registered documents with valid ingestion caches
resume automatically; unavailable documents require reattachment.

Visual questions inspect up to four relevant images, expanding to eight when
needed. An additional model pass checks individual claims against the originals
before any answer text is displayed. Unreadable or unsupported details are omitted
or refused. Exact structured-table lookups retain their deterministic path.
The evidence drawer distinguishes extracted text from AI interpretations. A
`model_checked` result is not a guarantee of correctness, and citation validity
does not measure visual accuracy. Without vision credentials, extracted text/OCR
remains usable and image interpretation is reported as unavailable.

Analysis caches live in `data/index/visual-analysis` and include image bytes,
context, region, model, and analysis version in their keys. Failed images can be
retried by reattaching. Document status adds `visual_analysis` counts; answer
sources add optional visual IDs, bounds, captions, origin, and verification status.
Extraction version 5 rebuilds older ingestion caches on reattachment.

Generate the 40-question benchmark and inspect its four source images:

```bash
python -m scripts.check_visual_accuracy --output reports/visual-accuracy.json
python -m scripts.check_visual_accuracy --live --output reports/visual-accuracy.json
```

The live command compares text-only answers with the actual chat endpoint and
records model, tokens, latency, answers, and citations. It needs vision credentials
and incurs API usage. These authored synthetic illustrations test colors, shapes,
arrow directions, labels, chart units, table cells, and unanswerable questions;
they do not establish accuracy on natural photographs or medical illustrations.
Additional regression tests cover rotation, conflicting tables, repeated figure
numbers, blank cells, cache failures, and streaming parity.

A reviewer must inspect each saved answer against the images before the release
gate is evaluated. A review JSON object maps each case ID (for example,
`pictures-1`) to four booleans: `baseline_correct`, `visual_correct`,
`citation_correct`, and `invented_number`. Count unnecessary abstentions as
incorrect; count an appropriate refusal on an unanswerable question as correct.
Mark citation correctness true for an appropriate refusal with no citations.

For the 150-question document baseline, enable hosted vision while retaining
extractive text answers with:

```bash
python -m scripts.document_baseline --run --split development --live-vision --output reports/document-baseline-development-live-vision.json
```

This uses the configured vision service and API quota. If the configured model
is unavailable, `--vision-model <model-id>` overrides it for that run only.
Use `--vision-rpm 4` to pace calls at four requests per minute when needed;
each visual answer normally uses one generation and one verification request.
Pacing does not increase the provider's daily allowance.
Reports label this mode `extractive_with_live_vision` and record the vision model
and token usage; compare it separately from the fully offline baseline. Omitting
both `--live` and `--live-vision` disables hosted calls. The fixtures, expected
answers, and matching rules remain the same in all modes.

```bash
python -m scripts.check_visual_accuracy --review reviewed.json --output reports/visual-accuracy.json
```

Review applies to saved responses without rerunning models. Passing requires at
least 90% overall and answerable-question accuracy, improvement over the baseline,
correct citations for every case, and zero invented numbers. Reports remain
`not_evaluated` until this review is supplied; offline tests cannot certify model
accuracy. Existing document-answer reports remain text/OCR-only evaluations.

The main dashboard presents a concise answer first, with expandable source excerpts,
long-answer details, charts, and earlier messages. Citations remain available inside
expanded sections. Tables retain their column headers on small screens.

Run the answer-rendering tests with Node.js:

```bash
npm ci
npm test
```

The React assistant is composed from `frontend/src/components/`, including the
workspace navigation and header, chat session, composer, attachments, messages,
welcome screen, source drawer, and conversation deletion dialog.

Build it and run its browser regression checks:

```bash
npm run build
npm run test:assistant -- /path/to/chrome
```

The browser executable argument is optional when Chrome or Edge is installed in a
standard location; `CHROME_PATH` is also supported. This check serves the built UI
locally and uses API fixtures to verify loading and retry states, message actions,
source viewing, conversation persistence, and mobile navigation without a model API.

For desktop/mobile browser checks, start the local server on port 8000, then run:

```bash
node scripts/check_answer_ui.cjs /path/to/chrome
```

This check loads the built-in sample document, asks questions through the dashboard,
checks keyboard disclosure controls and citation drawers, and saves screenshots to
`reports/`. Its structured-answer example is a UI test fixture, not a generated answer.

For a development environment with additional testing and benchmarking dependencies:

```bash
pip install -r requirements-dev.txt
```

Run the indexing benchmark:

```bash
python scripts/bench_indexing.py --output reports/indexing-benchmark.json
```

To benchmark a different PDF:

```bash
python scripts/bench_indexing.py \
  --pdf path/to/document.pdf \
  --output reports/indexing-benchmark.json
```

The benchmark can be used to evaluate document preparation, caching, and indexing behavior under local test conditions.

Performance results depend on hardware, model caching, document complexity, and file size.

---

## Source Code Organization

Backend modules live directly under `app/`: `main.py` contains routes and lifecycle;
`schemas.py` defines API requests; `uploads.py` bounds upload reads;
`ingest.py`, `ast_builder.py`, and `indexing.py` process documents;
`retriever.py`, `embeddings.py`, and `vector_store.py` handle retrieval;
`generator.py`, `evaluator.py`, and `vision.py` generate and check answers.
`vault_catalog.py` restores registered documents. Audit and export modules also
live directly in `app/`. React source lives in `frontend/src/`.

Run backend tests, frontend tests, and the production build locally:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```

No GitHub Actions subscription or workflow is required. Install development
Python and npm dependencies first using the setup instructions above.
Upload reads stop at the configured limit plus one byte. Multipart parsing may
spool requests before the handler runs; public deployments still need a proxy
request-body limit. Accepted documents are materialized in memory for extraction.

---

## 🔐 Security and Limitations

RagIT is intended to support document analysis and verification workflows.

Keep the following considerations in mind:

- Generated answers should be reviewed before making important compliance, legal, or financial decisions.
- Retrieval and answer verification reduce unsupported responses but do not guarantee perfect accuracy.
- Third-party LLM providers may receive retrieved document excerpts during answer generation.
- Uploaded documents and generated caches are stored locally.
- API keys should be stored securely and never committed to the repository.
- Clerk authentication (`@clerk/react` on the frontend and `clerk-backend-api` in `app/auth.py`) enforces per-account session verification and durable SQLite document ownership (`data/index/ownership.sqlite3`) by default (`RAGIT_AUTH_MODE=clerk`).
- Setting `RAGIT_ENV=production` fails closed at startup if `RAGIT_AUTH_MODE=local`, if `CLERK_SECRET_KEY` is a development `sk_test_` key, or if `CLERK_AUTHORIZED_PARTIES` does not enforce HTTPS origins.
- Single-worker deployment (`uvicorn app.main:app --workers 1`) is required while active document indexes (`DOCUMENT_VAULT` / `DOCUMENT_ASTS`) are held in process memory alongside SQLite catalog persistence.

## 🛣️ Future Improvements

Potential areas for continued development include:

- User authentication and role-based access control.
- Persistent multi-user document workspaces.
- Expanded support for document formats.
- More advanced table and visual understanding.
- Improved compliance rule customization.
- Automated evaluation of retrieval and answer quality.
- Deployment and containerization support.
- Enhanced reporting and audit history.

---

## 🤝 Contributing

Contributions, suggestions, and bug reports are welcome.

To contribute:

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Run the relevant tests.
5. Commit your changes.
6. Open a pull request explaining the changes.

For bugs and feature requests, open an issue in the GitHub repository.

## 🔗 Relevant Links

**GitHub:** https://github.com/Realwaan/RagIT

**Business Plan:** https://docs.google.com/document/d/1-fl5HdMup8CPJnZoWCDj8LOMirwX5HjuyMB9A5Fg59g/edit?tab=t.0

**Video Demo:** https://drive.google.com/file/d/1zEAHLUBQRsciH8jUzL3Y6cntQAPC_rIy/view?usp=sharing

**Slides:** https://ragit-astrag-jit.lovable.app/?utm_id=97757_v0_s00_e0_tv0

---

**RagIT — Turning documents into searchable, verifiable knowledge.**


## Document RAG baseline and verification semantics

The priority implementation is tracked in [docs/document-rag-priorities.md](docs/document-rag-priorities.md).
Text evaluations return `retrieval_score` (a heuristic in 0?1),
`citation_verified` (citation IDs exist), and `claim_support` independently.
The former `confidence`, `nli_verdict`, and `nli_entailment_prob` fields have been
removed from text evaluations. No entailment model or calibrated probability is
implied. Compliance checklist entries now expose `retrieval_score` as well.

`claims` contains conservative sentence/line checks: `supported` for complete
source sentence matches, `unsupported` for missing/invalid citations, and
`uncertain` for other wording. Paraphrases and structured-table answers can be
correct while remaining uncertain. The UI exposes claims needing review.
Extractive support establishes textual correspondence, not factual truth of the
source or completeness of the answer. Visual model checks remain separately labeled.

The versioned synthetic benchmark has 150 questions across native PDFs, scans,
tables, paraphrases, visuals, and unanswerable questions. Development (90) and
held-out (60) questions use disjoint documents but shared template families.
It is a regression baseline, not representative real-document accuracy.

```bash
python -m scripts.document_baseline --run --split development
python -m scripts.document_baseline --run --split held_out
```

Committed fixtures are hash-checked. `--build` regenerates them and changes the
manifest; do not rebuild during comparisons. Default runs disable hosted text
and vision calls. `--live` explicitly enables configured providers and API usage.
Reports contain per-category page recall@10, expected-answer match, citation-page
match, false refusals, latency, and tokens. Expected-answer matching is only an
automated proxy; human answer correctness and claim-support precision stay null
until reviewed. Monetary cost stays null because provider pricing is not configured.

A review JSON maps each case ID to `answer_sha256` from the saved report,
`answer_correct`, `citation_correct`, `invented_number` (booleans), and
`supported_claims`, `total_claims` (nonnegative integer counts). Review each answer
against its original PDF. Appropriate refusals may have zero claims; count an
unnecessary refusal as incorrect. Apply a complete review without rerunning models:

```bash
python -m scripts.document_baseline --review reviewed.json --output reports/document-baseline-held_out.json
```

Missing or stale reviews are rejected. The reviewed synthetic gate requires 95%
page recall@10, 90% answer correctness, 95% claim support, at most 5% false
refusals, correct citations for every answer, and no invented numbers. It does
not certify real-world or visual accuracy. Live representative documents and
independent review remain necessary before making those claims.

## Reproducible local development

The tested Windows/Python 3.13 dependency snapshot is in
`constraints-windows-py313.txt`. Install required development packages with:

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt -c constraints-windows-py313.txt
npm ci
```

This snapshot has no artifact hashes and has not been validated on other platforms
or by a clean installation. Update it deliberately after dependency checks and tests.
The local check script runs `pip check` before tests; no GitHub workflows are used.

Chat requests accept up to 16,000 characters per question and 20 history messages
with up to 32,000 characters each. History roles must be `user` or `assistant`;
malformed history is rejected before document lookup or provider calls. Custom
compliance requests allow up to 100 checks. These are application validation
limits, not substitutes for deployment-level request limits or authentication.

Report routes live in `app/report_routes.py`. Synchronous report construction runs
in FastAPI's worker pool so a PDF export does not block the API event loop.
Run the complete local check including installed Chrome/Edge browser fixtures with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1 -Browser
```

Browser fixtures check interface behavior without hosted model calls. This does
not replace document-answer accuracy review. By default, `RAGIT_AUTH_MODE=clerk`
requires a verified Clerk session token on all document, query, preview, crop,
and export endpoints, scoping ingestion caches and document ownership per account.
Local unauthenticated mode (`RAGIT_AUTH_MODE=local`) is reserved for local fixture
tests and is rejected when `RAGIT_ENV=production`.
