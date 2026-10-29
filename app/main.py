import asyncio
import json
import time
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse, Response
from app.schemas import (QueryRequest, ChatRequest, CustomCheckItem,
                         ComplianceAuditRequest, ExportReportRequest)
from app.uploads import read_bounded_upload
from app import auth

import app.config as cfg
from app.config import (
    DOCS_DIR, TOP_K, USE_GOOGLE_GENAI, MAX_UPLOAD_SIZE_BYTES,
    get_active_gemma_model, set_active_gemma_model
)
from app.ingest import get_or_render_page_image
from app.ast_builder import DocumentAST, ASTNodeType, get_or_render_visual_crop
from app.vector_store import LanceVectorStore
from app.discrepancy_scanner import scan_ast_for_discrepancies
from app.embeddings import get_embedding_model
from app.indexing import BackgroundIndexer, prepare_document, load_cached_ast
from app.retriever import HybridRetriever
from app.vision import VISUAL_INDEXER, visual_answer
from app.evaluator import evaluate_relevance, verify_generated_answer
from app.generator import (
    generate_grounded_answer_with_telemetry,
    stream_grounded_answer,
    repair_hallucinated_answer
)
from app.llm import call_plain_gemma_with_telemetry, is_llm_configured
from app.audit_scanner import (
    run_compliance_audit,
    AVAILABLE_FRAMEWORKS,
    DEFAULT_COMPLIANCE_CHECKS,
)
from app.compliance_routes import router as compliance_router
from app.report_routes import router as report_router
from app.vault_catalog import forget_document, remember_document, restore_documents
from app.query_intent import condense_conversational_query

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    global ACTIVE_DOC_ID
    auth.validate_auth_config()
    # Warm up before accepting attachments; a transient model failure remains retryable.
    started = time.perf_counter()
    try:
        await asyncio.to_thread(get_embedding_model)
        app.state.embedding_preload_succeeded = True
    except Exception:
        app.state.embedding_preload_succeeded = False
        logger.exception("Embedding model preload failed; attachment will retry initialization")
    app.state.embedding_preload_ms = round((time.perf_counter() - started) * 1000, 2)
    app.state.vault_recovery = {'restored': 0, 'unavailable': [], 'status': 'ready'}
    try:
        restored, unavailable = await asyncio.to_thread(restore_documents)
        for entry in restored:
            doc_id = entry['doc_id']
            if doc_id in DOCUMENT_VAULT:
                continue
            entry['background_indexing'] = BACKGROUND_INDEXER.submit(entry['ast'])
            VISUAL_INDEXER.submit(entry['ast'])
            DOCUMENT_VAULT[doc_id] = entry
            DOCUMENT_ASTS[doc_id] = entry['ast']
            app.state.vault_recovery['restored'] += 1
        app.state.vault_recovery['unavailable'] = unavailable
        if not auth.enabled() and not ACTIVE_DOC_ID and restored:
            _sync_active(restored[-1]['doc_id'])
    except Exception:
        logger.exception('Document catalog recovery failed; new uploads remain available')
        app.state.vault_recovery['status'] = 'failed'
    try:
        yield
    finally:
        await asyncio.to_thread(VISUAL_INDEXER.shutdown)
        await asyncio.to_thread(BACKGROUND_INDEXER.shutdown)


app = FastAPI(title="AuditGuard RAG • Hierarchical Multimodal Tree-RAG", version="2.0.0", lifespan=lifespan)

app.add_middleware(auth.AuthenticationMiddleware)
app.include_router(report_router)
app.include_router(compliance_router)

# Mount Static Files (Frontend UI, Visual Page Previews & Lossless Crops)
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if (STATIC_DIR / "assistant" / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assistant" / "assets")), name="assets")

# In-Memory State & Multi-Document Knowledge Vault (Protected by Async Lock)
STATE_LOCK = asyncio.Lock()
ACTIVE_DOC_ID: str = ""
ACTIVE_RETRIEVER: HybridRetriever | None = None
ACTIVE_CHUNKS: list = []
DOCUMENT_VAULT: dict = {}
DOCUMENT_ASTS: dict[str, DocumentAST] = {}
LANCE_STORE = LanceVectorStore()
BACKGROUND_INDEXER = BackgroundIndexer(LANCE_STORE)

NO_DOCUMENT_CLASSIFICATION: dict = {
    "type": "NONE",
    "label": "No Document Loaded",
    "icon": "📁",
    "confidence": 0.0,
    "prompt_addon": ""
}
ACTIVE_CLASSIFICATION: dict = NO_DOCUMENT_CLASSIFICATION


def _sync_active(doc_id: str = ""):
    global ACTIVE_DOC_ID, ACTIVE_RETRIEVER, ACTIVE_CHUNKS, ACTIVE_CLASSIFICATION
    ACTIVE_DOC_ID = doc_id or ""
    entry = DOCUMENT_VAULT.get(ACTIVE_DOC_ID) if ACTIVE_DOC_ID else None
    if entry:
        ACTIVE_RETRIEVER = entry.get("retriever")
        ACTIVE_CHUNKS = entry.get("chunks", [])
        ACTIVE_CLASSIFICATION = entry.get("classification", NO_DOCUMENT_CLASSIFICATION)
    else:
        ACTIVE_RETRIEVER = None
        ACTIVE_CHUNKS = []
        ACTIVE_CLASSIFICATION = NO_DOCUMENT_CLASSIFICATION


def active_entry() -> dict | None:
    """Local-mode selection, derived from the vault."""
    return DOCUMENT_VAULT.get(ACTIVE_DOC_ID) if ACTIVE_DOC_ID else None


def document_snapshot(doc_id: str):
    """Resolve once, before any await; never fall back to another document."""
    auth.require_document(doc_id)
    entry = DOCUMENT_VAULT.get(doc_id)
    if not doc_id.strip() or entry is None:
        raise HTTPException(status_code=404, detail="Document not loaded. Attach this document again.")
    return dict(entry)


async def _attach_document(contents: bytes, filename: str, request_started: float) -> dict:
    """Publish search-ready state before the optional LanceDB embedding pass."""
    global ACTIVE_DOC_ID
    try:
        entry = await asyncio.to_thread(prepare_document, contents, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    doc_id = entry["doc_id"]
    await asyncio.to_thread(auth.grant, doc_id)
    entry["uploaded_at"] = datetime.now().isoformat(timespec='seconds')
    try:
        await asyncio.to_thread(remember_document, entry)
    except Exception:
        logger.exception('Could not persist document catalog entry')
        entry['cache_warning'] = 'Search is ready, but this document may need reattachment after restart.'
    entry["background_indexing"] = BACKGROUND_INDEXER.submit(entry["ast"])
    entry["visual_analysis"] = VISUAL_INDEXER.submit(entry["ast"])
    async with STATE_LOCK:
        DOCUMENT_ASTS[doc_id] = entry["ast"]
        DOCUMENT_VAULT[doc_id] = entry
        if not auth.enabled():
            _sync_active(doc_id)
    entry["attachment_duration_ms"] = round((time.perf_counter() - request_started) * 1000, 2)
    return {
        "ok": True, "status": "ready", "filename": filename, "doc_id": doc_id,
        "pages_processed": entry["pages"], "total_chunks": entry["total_chunks"],
        "total_ast_nodes": entry["total_ast_nodes"], "cross_modal_links": entry["cross_modal_links"],
        "indexing_duration_ms": entry["indexing_duration_ms"],
        "attachment_duration_ms": entry["attachment_duration_ms"],
        "stage_timings_ms": entry["stage_timings_ms"], "cache_hit": entry["cache_hit"],
        "cache_warning": entry["cache_warning"], "classification": entry["classification"],
        "extraction": entry.get("extraction", {}),
        "visual_analysis": VISUAL_INDEXER.status(doc_id),
        "background_indexing": BACKGROUND_INDEXER.snapshot(entry["background_indexing"]),
    }


def _hydrate_ast_siblings(retrieved: list[dict], ast: DocumentAST | None) -> None:
    """Attaches linked visual sibling nodes from the AST onto retrieved text chunks."""
    if not ast:
        return
    linked_sources = []
    included_ids = {chunk.get('ast_node_id') for chunk in retrieved}
    for chunk in list(retrieved):
        ast_id = chunk.get("ast_node_id")
        if not ast_id:
            continue
        node = ast.get_node(ast_id)
        if not node or not node.linked_node_ids:
            continue
        linked_visuals = []
        for lid in node.linked_node_ids:
            v_node = ast.get_node(lid)
            if v_node and v_node.type == ASTNodeType.VISUAL:
                linked_visuals.append({
                    "id": v_node.id,
                    "title": v_node.title,
                    "image_url": v_node.image_url,
                    "visual_type": v_node.visual_type,
                    "page": v_node.page,
                    "link_tier": node.metadata.get('edge_meta', {}).get(lid, {}).get('tier', 3),
                })
                tier = node.metadata.get('edge_meta', {}).get(lid, {}).get('tier', 3)
                if tier == 1 and lid not in included_ids and len(v_node.text.split()) > 8 and len(linked_sources) < 8:
                    included_ids.add(lid)
                    linked_sources.append({'citation_id': len(retrieved) + len(linked_sources) + 1,
                                           'ast_node_id': lid, 'filename': ast.title, 'page': v_node.page,
                                           'parent_text': v_node.text, 'child_text': v_node.text,
                                           'image_url': v_node.image_url, 'has_visual': True,
                                           'evidence_type': v_node.visual_type, 'retrieved_via': 'explicit_visual_reference'})
        if linked_visuals:
            chunk["linked_visuals"] = linked_visuals
            if not chunk.get("image_url") and linked_visuals[0].get("image_url"):
                chunk["image_url"] = linked_visuals[0]["image_url"]
            chunk["has_visual"] = True
    retrieved.extend(linked_sources)


@app.get("/health")
def health_check():
    active_model = get_active_gemma_model()
    active = active_entry()
    return {
        "status": "healthy",
        "embedding_preload_succeeded": getattr(app.state, "embedding_preload_succeeded", False),
        "embedding_preload_ms": getattr(app.state, "embedding_preload_ms", None),
        "vault_recovery": getattr(app.state, 'vault_recovery', {'status': 'not_started'}),
        "doc_loaded": bool(active and active["chunks"]),
        "classification": (active["classification"] if active else NO_DOCUMENT_CLASSIFICATION).get("label"),
        "chunk_count": len(active["chunks"]) if active else 0,
        "ast_loaded": ACTIVE_DOC_ID in DOCUMENT_ASTS,
        "lancedb_ready": LANCE_STORE.is_ready(),
        "llm_configured": is_llm_configured(),
        "model": active_model,
        "engine": "Google GenAI (Native)" if USE_GOOGLE_GENAI else "OpenAI-Compatible (ALMA)",
        "use_google_genai": USE_GOOGLE_GENAI
    }


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Local Document Ingestion:
    Validates file size & extension, extracts pages, builds the 3-Tier Document AST,
    detects visual bounds and prepares HybridRetriever. LanceDB runs in the background.
    """
    request_started = time.perf_counter()
    filename = (file.filename or "uploaded_doc.pdf").strip()
    allowed_exts = (".pdf", ".txt", ".md")
    if not filename.lower().endswith(allowed_exts):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Please upload {', '.join(allowed_exts)}."
        )

    contents = await read_bounded_upload(file, cfg.MAX_UPLOAD_SIZE_BYTES)
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(contents) > cfg.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {cfg.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB."
        )

    return await _attach_document(contents, filename, request_started)


@app.post("/ask")
@app.post("/query")
async def ask_question(payload: QueryRequest):
    """
    Standard JSON endpoint for AuditGuard Q&A.
    Returns Grounded Answer, Proof Drawer sources with linked visual crops,
    CRAG Evaluation, Plain Gemma Baseline, genuine token telemetry, and exact latency.
    """
    doc_id = payload.doc_id
    doc_entry = document_snapshot(doc_id)
    retriever = doc_entry["retriever"]
    ast = doc_entry.get("ast")
    classification = doc_entry.get("classification", {})

    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    t_total_start = time.perf_counter()

    # 1. Hybrid RRF Retrieval with Microsecond Benchmarking
    t0 = time.perf_counter()
    retrieved = await asyncio.to_thread(retriever.retrieve, query, TOP_K)
    retrieval_ms = round((time.perf_counter() - t0) * 1000, 2)

    # 2. AST Cross-Modal Sibling Hydration
    _hydrate_ast_siblings(retrieved, ast)

    # 3. CRAG Relevance Gatekeeper (Tier 1: Chunk-Level Evaluation)
    visual = await asyncio.to_thread(visual_answer, ast, query, retrieved)
    if visual is not None:
        return {**visual, "query": query, "doc_id": doc_id, "classification": classification,
                "retrieval_ms": retrieval_ms, "baseline": ""}
    eval_result = evaluate_relevance(retrieved, query=query)

    # Tier 2 AST Whole-Page Escalation:
    if eval_result["status"] == "REFUSE":
        candidate_pages = [c.get("page") for c in retrieved if c.get("page")]
        escalated_chunks = await asyncio.to_thread(
            retriever.escalate_page_scan, query, candidate_pages, ast
        )
        if escalated_chunks:
            escalated_eval = evaluate_relevance(escalated_chunks, query=query)
            if escalated_eval["status"] != "REFUSE":
                retrieved = escalated_chunks
                _hydrate_ast_siblings(retrieved, ast)
                eval_result = escalated_eval

    # 4. Check for Defense Refusal
    total_ast_nodes = len(ast.nodes) if ast else doc_entry.get("total_ast_nodes", 0)
    cross_modal_links = len(ast.get_cross_modal_links()) if ast else doc_entry.get("cross_modal_links", 0)
    indexing_duration_ms = doc_entry.get("indexing_duration_ms", 0.0)

    if eval_result["status"] == "REFUSE":
        plain_baseline = ""
        baseline_tokens = 0
        if payload.include_baseline:
            plain_baseline, base_meta = await asyncio.to_thread(call_plain_gemma_with_telemetry, query)
            baseline_tokens = base_meta.get("baseline_tokens", 0)

        total_ms = round((time.perf_counter() - t_total_start) * 1000, 2)
        return {
            "query": query, "doc_id": doc_id,
            "status": "REFUSE",
            "evaluation": eval_result,
            "answer": eval_result["reason"],
            "sources": [],
            "baseline": plain_baseline,
            "classification": classification,
            "retrieval_ms": retrieval_ms,
            "total_ms": total_ms,
            "estimated_tokens": baseline_tokens,
            "token_telemetry": {
                "grounded_prompt_tokens": 0,
                "grounded_completion_tokens": 0,
                "grounded_total_tokens": 0,
                "baseline_tokens": baseline_tokens,
                "total_tokens": baseline_tokens,
                "generation_mode": "refusal_gatekeeper",
                "model_used": get_active_gemma_model(),
                "total_ast_nodes": total_ast_nodes,
                "cross_modal_links": cross_modal_links,
                "indexing_duration_ms": indexing_duration_ms,
            },
            "generation_mode": "refusal_gatekeeper",
        }

    # 5. Synthesize Grounded Answer
    persona = classification.get("prompt_addon", "")

    async def _fetch_grounded():
        return await asyncio.to_thread(generate_grounded_answer_with_telemetry, query, retrieved, persona)

    async def _fetch_baseline():
        if payload.include_baseline:
            return await asyncio.to_thread(call_plain_gemma_with_telemetry, query)
        return "", {"baseline_tokens": 0, "baseline_mode": "disabled"}

    (grounded_answer, gen_meta), (plain_baseline, base_meta) = await asyncio.gather(
        _fetch_grounded(), _fetch_baseline()
    )

    # 6. Post-Generation Guardrail Verification (audits inline citations and LLM-level refusals)
    eval_result = verify_generated_answer(grounded_answer, retrieved, eval_result)
    if eval_result.get("invalid_citations") or (
        eval_result.get("status") == "SYNTHESIZE"
        and any(c.get("status") == "unsupported" for c in eval_result.get("claims", []))
    ):
        grounded_answer, eval_result, repaired = repair_hallucinated_answer(
            query, grounded_answer, retrieved, eval_result
        )
        if repaired:
            gen_meta["self_rag_repaired"] = True

    final_status = "REFUSE" if eval_result["status"] == "REFUSE" else "SUCCESS"
    total_tokens = int(gen_meta.get("total_tokens", 0) + base_meta.get("baseline_tokens", 0))
    total_ms = round((time.perf_counter() - t_total_start) * 1000, 2)

    return {
        "query": query, "doc_id": doc_id,
        "status": final_status,
        "evaluation": eval_result,
        "answer": grounded_answer,
        "sources": [] if final_status == "REFUSE" else retrieved,
        "baseline": plain_baseline,
        "classification": classification,
        "retrieval_ms": retrieval_ms,
        "total_ms": total_ms,
        "estimated_tokens": total_tokens,
        "token_telemetry": {
            "grounded_prompt_tokens": gen_meta.get("prompt_tokens", 0),
            "grounded_completion_tokens": gen_meta.get("completion_tokens", 0),
            "grounded_total_tokens": gen_meta.get("total_tokens", 0),
            "baseline_tokens": base_meta.get("baseline_tokens", 0),
            "total_tokens": total_tokens,
            "generation_mode": gen_meta.get("generation_mode", "unknown"),
            "model_used": gen_meta.get("model_used", ""),
            "total_ast_nodes": total_ast_nodes,
            "cross_modal_links": cross_modal_links,
            "indexing_duration_ms": indexing_duration_ms,
        },
        "generation_mode": gen_meta.get("generation_mode", "unknown"),
    }


@app.get("/ask-stream")
async def ask_stream(query: str, doc_id: str):
    """Legacy text stream uses the same generation and verification as /ask."""
    result = await ask_question(QueryRequest(query=query, doc_id=doc_id))
    answer = result["answer"]
    if result.get("evaluation", {}).get("claim_support") == "needs_review":
        answer += "\n\nSome claims need source review; citation links alone do not verify them."
    return StreamingResponse(iter([answer]), media_type="text/event-stream",
                             headers={"X-Document-ID": doc_id})


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    """Document-pinned streaming for the React chat; sources belong to each turn."""
    from starlette.concurrency import iterate_in_threadpool

    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Enter a question first.")
    entry = document_snapshot(payload.doc_id)
    retriever, ast = entry["retriever"], entry.get("ast")
    classification = entry.get("classification", {})

    def event(kind, **values):
        return "data: " + json.dumps({"type": kind, "doc_id": payload.doc_id, **values}) + "\n\n"

    async def events():
        started = time.perf_counter()
        try:
            yield event("activity", label="Finding relevant passages")
            # Prior questions disambiguate short follow-ups; they are not evidence.
            previous = payload.previous_question.strip()[:1000]
            retrieval_query = await asyncio.to_thread(
                condense_conversational_query,
                query,
                history=payload.history,
                previous_question=previous,
            )
            # Prior questions and conversation history condensed above
            # Ready for retrieval
            retrieved = await asyncio.to_thread(retriever.retrieve, retrieval_query, TOP_K)
            _hydrate_ast_siblings(retrieved, ast)
            yield event("activity", label="Checking relevant image evidence")
            visual = await asyncio.to_thread(visual_answer, ast, retrieval_query, retrieved)
            if visual is not None:
                yield event("sources", sources=visual['sources'], label=visual['evaluation']['badge'])
                ans_text = visual['answer']
                step = 25
                for i in range(0, len(ans_text), step):
                    yield event("delta", text=ans_text[i:i + step])
                yield event("done", **{**visual, 'query': query, 'classification': classification,
                                       'total_ms': round((time.perf_counter() - started) * 1000, 2)})
                return
            evaluation = evaluate_relevance(retrieved, query=query)
            if evaluation["status"] == "REFUSE":
                pages = [c.get("page") for c in retrieved if c.get("page")]
                expanded = await asyncio.to_thread(retriever.escalate_page_scan, retrieval_query, pages, ast)
                if expanded:
                    expanded_eval = evaluate_relevance(expanded, query=query)
                    if expanded_eval["status"] != "REFUSE":
                        retrieved, evaluation = expanded, expanded_eval
                        _hydrate_ast_siblings(retrieved, ast)
            if evaluation["status"] == "REFUSE":
                yield event("done", query=query, answer=evaluation["reason"], status="REFUSE",
                            evaluation=evaluation, sources=[], classification=classification)
                return
            yield event("sources", sources=retrieved, label="Writing answer")
            answer = ""
            async for delta in iterate_in_threadpool(stream_grounded_answer(
                query, retrieved, classification.get("prompt_addon", ""), previous_question=previous
            )):
                answer += delta
                yield event("delta", text=delta)
            evaluation = verify_generated_answer(answer, retrieved, evaluation)
            if evaluation.get("invalid_citations") or (
                evaluation.get("status") == "SYNTHESIZE"
                and any(c.get("status") == "unsupported" for c in evaluation.get("claims", []))
            ):
                answer, evaluation, repaired = repair_hallucinated_answer(
                    query, answer, retrieved, evaluation
                )
            refused = evaluation["status"] == "REFUSE"
            yield event("done", query=query, answer=answer, status="REFUSE" if refused else "SUCCESS",
                        evaluation=evaluation, sources=[] if refused else retrieved,
                        classification=classification, total_ms=round((time.perf_counter() - started) * 1000, 2))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Chat stream failed")
            yield event("error", message="The response was interrupted. Please retry.")

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/ast")
def get_active_document_ast(doc_id: str = ""):
    if auth.enabled():
        return document_snapshot(doc_id)["ast"].to_dict()
    """Returns the complete Document AST for visual graph rendering."""
    if not ACTIVE_DOC_ID or ACTIVE_DOC_ID not in DOCUMENT_ASTS:
        raise HTTPException(status_code=404, detail="No active Document AST available.")
    return DOCUMENT_ASTS[ACTIVE_DOC_ID].to_dict()


@app.get("/api/ast/{doc_id}")
def get_document_ast_by_id(doc_id: str):
    """Returns the Document AST for a specific vault document."""
    auth.require_document(doc_id)
    if doc_id not in DOCUMENT_ASTS:
        raise HTTPException(status_code=404, detail=f"Document AST for '{doc_id}' not found.")
    return DOCUMENT_ASTS[doc_id].to_dict()


@app.get("/api/crop/{doc_id}/{node_id}")
async def get_visual_crop(doc_id: str, node_id: str):
    await asyncio.to_thread(auth.require_document, doc_id)
    ast = DOCUMENT_ASTS.get(doc_id) or await asyncio.to_thread(load_cached_ast, doc_id)
    node = ast.get_node(node_id) if ast else None
    if node is None or node.type != ASTNodeType.VISUAL:
        raise HTTPException(status_code=404, detail="Visual not found.")
    image_path = await asyncio.to_thread(get_or_render_visual_crop, ast, node)
    if image_path and image_path.exists():
        return FileResponse(str(image_path), media_type="image/webp")
    raise HTTPException(status_code=404, detail="Visual image unavailable.")


@app.get("/api/preview/{doc_prefix}/{page_num}")
async def get_preview_image(doc_prefix: str, page_num: int):
    """
    On-Demand Visual Audit Proof Renderer:
    Renders and serves high-res single page previews for 300-page PDFs in ~30ms.
    """
    await asyncio.to_thread(auth.require_document, doc_prefix)
    img_path = await asyncio.to_thread(get_or_render_page_image, doc_prefix, page_num)
    if img_path and img_path.exists():
        media_type = "image/webp" if img_path.suffix.lower() == ".webp" else "image/png"
        return FileResponse(str(img_path), media_type=media_type)
    raise HTTPException(status_code=404, detail="Page preview could not be generated.")


SAMPLE_SOP_CONTENT = """# GLOBAL VIRTUAL ASSISTANT SERVICE LEVEL AGREEMENT & ESCALATION SOP

1. PURPOSE & SCOPE OF ENGAGEMENT
This Agreement governs all remote virtual assistant, administrative, and data verification operations provided by ALMA Talent Solutions. All remote personnel must maintain compliance with enterprise data security protocols (ISO 27001).

2. SYSTEM UPTIME & RESPONSE TIME SLA
2.1 Uptime Guarantee: The service provider guarantees 99.9% availability during standard client business hours (08:00 to 18:00 EST).
2.2 Penalty Credit: In the event that service availability drops below 99.5% in any calendar billing month, the client shall be entitled to an immediate 15% billing credit applied to the next invoice cycle.
Table 1: Q3 Historical Availability & Outage Log:
| Month | Target SLA | Actual Uptime | Outage Minutes | Penalty Credit Due |
| July | 99.9% | 99.95% | 12 min | 0% |
| August | 99.9% | 99.80% | 45 min | 0% |
| September | 99.9% | 98.20% | 420 min | 15% Penalty Due (Breach) |

3. DATA PROTECTION & ZERO-TRUST SECURITY
3.1 Access Control: Remote virtual assistants shall never store client credentials on personal local drives. All authentication must occur through hardware-enforced MFA or enterprise SSO.
3.2 Incident Escalation Flowchart (Figure 1):
- Step 1: Any unauthorized data access alert must be logged within 15 minutes of occurrence.
- Step 2: Immediate written notice must be submitted to the Client Security Officer within 1 hour.
- Step 3: All active VPN sessions for the affected contractor account must be terminated immediately.

4. WIRE TRANSFERS & FINANCIAL AUTHORIZATION
4.1 Dual Authorization: Wire transfers or account disbursements exceeding $50,000 require written sign-off from both the Chief Financial Officer (CFO) and the Managing Director.
4.2 Audit Retention: All wire transfer authorization records must be archived in encrypted cold storage for a minimum period of 7 years.

5. TERMINATION FOR CONVENIENCE
Either party may terminate this agreement without cause by providing at least 30 business days prior written notice. Early termination fees are explicitly waived after the initial 6-month contract anniversary."""


@app.post("/load-sample")
async def load_sample_document():
    """
    1-Click Stage Demo Mode:
    Passes sample_enterprise_sop.txt through the exact same AST, visual table extraction,
    and LanceDB indexing pipeline used for uploaded documents (zero hardcoded AST node overrides).
    """
    request_started = time.perf_counter()
    sample_filename = "sample_enterprise_sop.txt"
    sample_path = DOCS_DIR / sample_filename
    if not sample_path.exists():
        sample_path.write_text(SAMPLE_SOP_CONTENT, encoding="utf-8")
    sample_content = sample_path.read_text(encoding="utf-8")

    return await _attach_document(sample_content.encode("utf-8"), sample_filename, request_started)



@app.get("/vault")
def get_vault():
    """Returns all active indexed documents in the enterprise knowledge vault."""
    allowed = auth.owned_ids() if auth.enabled() else None
    items = []
    for k, v in list(DOCUMENT_VAULT.items()):
        if allowed is not None and k not in allowed:
            continue
        items.append({
            "doc_id": v["doc_id"],
            "filename": v["filename"],
            "pages": v["pages"],
            "total_chunks": v["total_chunks"],
            "total_ast_nodes": v.get("total_ast_nodes", 0),
            "cross_modal_links": v.get("cross_modal_links", 0),
            "indexing_duration_ms": v.get("indexing_duration_ms", 0),
            "attachment_duration_ms": v.get("attachment_duration_ms", 0),
            "stage_timings_ms": v.get("stage_timings_ms", {}),
            "cache_hit": v.get("cache_hit", False),
            "cache_warning": v.get("cache_warning"),
            "restored": v.get('restored', False),
            "background_indexing": BACKGROUND_INDEXER.snapshot(v.get("background_indexing", {})),
            "visual_analysis": VISUAL_INDEXER.status(v['doc_id']),
            "classification": v["classification"],
            "uploaded_at": v["uploaded_at"],
            "is_active": (not auth.enabled() and v["doc_id"] == ACTIVE_DOC_ID)
        })
    raw_recovery = getattr(app.state, 'vault_recovery', {'status': 'not_started'})
    if auth.enabled():
        owned_unavailable = [
            item for item in raw_recovery.get('unavailable', [])
            if item.get('doc_id') in allowed
        ]
        recovery = {
            "status": raw_recovery.get("status", "ready"),
            "restored": len(items),
            "unavailable": owned_unavailable,
        }
    else:
        recovery = raw_recovery
    return {"vault": items, "active_doc_id": "" if auth.enabled() else ACTIVE_DOC_ID,
            "recovery": recovery}


@app.post("/vault/select/{doc_id}")
async def select_vault_document(doc_id: str):
    """Switch active document from the vault atomically."""
    global ACTIVE_DOC_ID
    if doc_id not in DOCUMENT_VAULT:
        raise HTTPException(status_code=404, detail="Document not found in vault.")

    async with STATE_LOCK:
        doc = DOCUMENT_VAULT[doc_id]
        _sync_active(doc_id)

    return {
        "ok": True,
        "active_doc_id": doc_id,
        "filename": doc["filename"],
        "classification": doc["classification"]
    }


@app.delete("/vault/{doc_id}")
async def delete_vault_document(doc_id: str):
    """Remove a document the caller owns: memory, catalog, ownership, and derived files."""
    global ACTIVE_DOC_ID
    await asyncio.to_thread(auth.require_document, doc_id)
    async with STATE_LOCK:
        entry = DOCUMENT_VAULT.pop(doc_id, None)
        DOCUMENT_ASTS.pop(doc_id, None)
        if ACTIVE_DOC_ID == doc_id:
            _sync_active("")
    removed = await asyncio.to_thread(forget_document, doc_id, entry, LANCE_STORE)
    if entry is None and not removed:
        raise HTTPException(status_code=404, detail="Document not found.")
    await asyncio.to_thread(auth.revoke, doc_id)
    return {"ok": True, "doc_id": doc_id}


@app.post("/api/model/toggle")
def toggle_model():
    """Toggle between high-speed Gemma 4 MoE (26b-a4b-it) and dense Gemma 4 (31b-it)."""
    current = get_active_gemma_model()
    if current == "gemma-4-26b-a4b-it":
        updated = set_active_gemma_model("gemma-4-31b-it")
    else:
        updated = set_active_gemma_model("gemma-4-26b-a4b-it")
    return {
        "ok": True,
        "model": updated,
        "label": "Gemma 4 MoE (~3s)" if updated == "gemma-4-26b-a4b-it" else "Gemma 4 Dense 31B (~28s)"
    }


@app.get("/classic", response_class=HTMLResponse)
async def serve_ui():
    """Serve the single-page dashboard."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>AuditGuard UI Loading...</h1>")


@app.get("/", response_class=HTMLResponse)
@app.get("/assistant", response_class=HTMLResponse)
async def serve_assistant_ui():
    """Serve the modern React Assistant-UI frontend."""
    html_path = STATIC_DIR / "assistant" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Assistant UI not found.</h1>", status_code=404)
