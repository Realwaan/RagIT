"""Report downloads run in FastAPI's worker pool, keeping the event loop free."""
import json
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import Response
from app.config import get_active_gemma_model
from app.exporter import build_pdf_bytes, build_docx_bytes, build_csv_string
from app.schemas import ExportReportRequest

router = APIRouter()


@router.post("/export-report")
def export_report(payload: ExportReportRequest):
    """
    Exports an audited compliance finding as a downloadable PDF (.pdf), Word (.docx),
    CSV (.csv), Markdown (.md), or JSON (.json) report.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    doc_label = payload.classification.get("label", "General Enterprise Document")
    doc_type = payload.classification.get("type", "GENERAL_SPECIFICATION")
    eval_badge = payload.evaluation.get("badge", "Not checked")
    confidence = payload.evaluation.get("retrieval_score", "not measured")
    fmt = payload.format.lower().strip()

    if fmt == "json":
        report_obj = {
            "generated_at": timestamp,
            "engine": "AuditGuard Tree-RAG v2.0",
            "model": get_active_gemma_model(),
            "classification": payload.classification,
            "evaluation": payload.evaluation,
            "query": payload.query,
            "grounded_answer": payload.answer,
            "baseline_comparison": payload.baseline,
            "sources": payload.sources,
        }
        return Response(
            content=json.dumps(report_obj, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="audit_trail_{file_timestamp}.json"'}
        )

    if fmt == "pdf":
        pdf_bytes = build_pdf_bytes(
            title="AuditGuard Verification Report",
            timestamp=timestamp,
            doc_label=doc_label,
            confidence=confidence,
            query=payload.query,
            answer=payload.answer,
            sources=payload.sources,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="audit_report_{file_timestamp}.pdf"'}
        )

    if fmt in ("docx", "word", "doc"):
        docx_bytes = build_docx_bytes(
            title="AuditGuard Verification Report",
            timestamp=timestamp,
            doc_label=doc_label,
            confidence=confidence,
            query=payload.query,
            answer=payload.answer,
            sources=payload.sources,
        )
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="audit_report_{file_timestamp}.docx"'}
        )

    if fmt == "csv":
        csv_text = build_csv_string(
            timestamp=timestamp,
            query=payload.query,
            answer=payload.answer,
            sources=payload.sources,
        )
        return Response(
            content=csv_text.encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="audit_report_{file_timestamp}.csv"'}
        )

    md_lines = [
        "# 🛡️ AuditGuard RAG — Compliance Verification Report",
        f"**Generated At:** {timestamp}  ",
        f"**Document Classification:** {doc_label} (`{doc_type}`)  ",
        f"**Evidence check:** {eval_badge} (retrieval score: `{confidence}`; not a probability)  ",
        f"**Active Model:** `{get_active_gemma_model()}`  ",
        "",
        "---",
        "",
        "## 1. Compliance Audit Query",
        f"> {payload.query}",
        "",
        "## 2. Document Answer",
        f"{payload.answer}",
        "",
    ]

    if payload.baseline:
        md_lines.extend([
            "## 3. Hallucination Radar (Ungrounded Baseline Comparison)",
            "**Plain Gemma 4 (Zero AST Context):**",
            f"> {payload.baseline}",
            "",
        ])

    md_lines.extend([
        "## 4. Source Evidence & AST Provenance Trail",
        "| Citation | Document | Page | AST Path | Similarity | Clause Excerpt |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |"
    ])

    for s in payload.sources:
        cid = s.get("citation_id", 1)
        doc = s.get("filename", "Document")
        page = s.get("page", 1)
        ast_path = s.get("materialized_path", f"root/page_{page}")
        score = round(float(s.get("dense_score", 0.0)) * 100, 1)
        excerpt = s.get("parent_text", s.get("child_text", "")).replace("\n", " ").strip()
        if len(excerpt) > 120:
            excerpt = excerpt[:117] + "..."
        excerpt = excerpt.replace("|", "\\|")
        md_lines.append(f"| `[{cid}]` | {doc} | Page {page} | `{ast_path}` | {score}% | {excerpt} |")

    md_lines.extend([
        "",
        "---",
        "*Generated by AuditGuard Tree-RAG Verification Engine*"
    ])

    md_content = "\n".join(md_lines)
    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="audit_report_{file_timestamp}.md"'}
    )


