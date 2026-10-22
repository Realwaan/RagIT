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
- Synchronous and asynchronous audit execution.
- Retrieval of audit results through API endpoints.

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

Audits can be executed directly or submitted as background jobs.

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
| `POST` | `/api/jobs/audit` | Submit an asynchronous audit |
| `GET` | `/api/jobs/{job_id}` | Retrieve audit job status and results |

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
    "include_baseline": false
  }'
```

The response includes the generated answer, retrieval evaluation, source evidence, and execution telemetry.

Set `include_baseline` to `true` to request a comparison against an answer generated without retrieved document context.

### Example: Load Sample Document

```bash
curl -X POST http://127.0.0.1:8000/load-sample
```

### Example: Submit an Audit Job

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/audit \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "your_document_id"
  }'
```

The endpoint returns an audit job identifier.

Check its progress using:

```bash
curl http://127.0.0.1:8000/api/jobs/YOUR_JOB_ID
```

Audit jobs can report `queued`, `running`, `completed`, or `failed` states.

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

The active in-memory document vault and audit jobs are scoped to the running server process. Cached ingestion artifacts can persist across restarts.

---

## 🧪 Testing

RagIT uses Pytest for automated testing.

Run the test suite:

```bash
python -m pytest tests -v
```

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

## 📁 Source Code Organization

The backend is organized into separate functional modules.

```text
RagIT/
│
├── app/
│   ├── main.py                 # FastAPI application and routes
│   │
│   ├── core/                   # Configuration and LLM generation
│   │
│   ├── ingestion/              # Document extraction and indexing
│   │
│   ├── storage/                # Embeddings and retrieval
│   │
│   ├── auditing/               # Verification and compliance audits
│   │
│   └── static/                 # Web UI and generated assets
│
├── data/                       # Local documents and indexes
│
├── scripts/                    # Development and benchmark tools
│
├── tests/                      # Automated tests
│
├── requirements.txt            # Python dependencies
├── requirements-dev.txt        # Development dependencies
├── run.bat                     # Windows startup script
└── README.md                   # Project documentation
```

### Core Modules

**`app/core/`**

Handles application configuration, LLM integration, and answer generation.

**`app/ingestion/`**

Handles document extraction, structural parsing, visual processing, and ingestion workflows.

**`app/storage/`**

Manages embedding generation, local vector storage, and hybrid retrieval.

**`app/auditing/`**

Contains document verification, discrepancy scanning, compliance auditing, audit jobs, and report export functionality.

**`app/main.py`**

Defines the FastAPI application, manages active document state, and exposes application endpoints.

---

## 🔐 Security and Limitations

RagIT is intended to support document analysis and verification workflows.

Keep the following considerations in mind:

- Generated answers should be reviewed before making important compliance, legal, or financial decisions.
- Retrieval and answer verification reduce unsupported responses but do not guarantee perfect accuracy.
- Third-party LLM providers may receive retrieved document excerpts during answer generation.
- Uploaded documents and generated caches are stored locally.
- API keys should be stored securely and never committed to the repository.
- The current API implementation does not provide a complete authentication and authorization layer for public deployment.
- Additional access controls, storage security, deployment configuration, and data handling policies are recommended before production use.

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
