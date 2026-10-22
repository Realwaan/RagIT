import io
import re
import hashlib
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from pypdf import PdfReader
import pypdfium2 as pdfium
from app.core.config import PREVIEWS_DIR, DOCS_DIR
from app.auditing.classifier import classify_document
from app.ingestion.pdf_lock import PDF_LOCK
from app.ingestion.pdf_render import render_pdf_image, save_webp
from app.core.config import PDF_PARALLEL_PAGE_THRESHOLD, PDF_PROCESS_WORKERS


def sanitize_doc_id(raw_id: str) -> str:
    """Sanitizes document identifiers to prevent path traversal or injection."""
    cleaned = re.sub(r'[^a-zA-Z0-9_-]', '_', Path(raw_id).stem)
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    return cleaned or "document"


def get_or_render_page_image(doc_prefix: str, page_num: int) -> Path | None:
    """
    On-demand single-page renderer for large documents (e.g. 300-page manuals).
    Renders just the requested page in ~30ms and caches it to disk in compressed WebP format (80% quality).
    Includes strict path traversal guardrails.
    """
    if page_num < 1 or page_num > 5000:
        return None

    safe_prefix = sanitize_doc_id(doc_prefix)
    previews_root = PREVIEWS_DIR.resolve()

    file_name = f"{safe_prefix}_page_{page_num}.webp"
    file_path = (PREVIEWS_DIR / file_name).resolve()
    if not file_path.is_relative_to(previews_root):
        return None

    if file_path.exists():
        return file_path

    png_fallback = (PREVIEWS_DIR / f"{safe_prefix}_page_{page_num}.png").resolve()
    if png_fallback.is_relative_to(previews_root) and png_fallback.exists():
        return png_fallback

    pdf_path = (DOCS_DIR / f"{safe_prefix}.pdf").resolve()
    if not pdf_path.is_relative_to(DOCS_DIR.resolve()) or not pdf_path.exists():
        return None

    try:
        save_webp(render_pdf_image(pdf_path, page_num), file_path)
        return file_path
    except Exception as e:
        print(f"Error on-demand rendering page {page_num}: {e}")
    return None


def render_page_previews(pdf_bytes: bytes, doc_prefix: str) -> Dict[int, str]:
    """
    Save the PDF and render only the first preview. Other pages render on demand.
    """
    safe_prefix = sanitize_doc_id(doc_prefix)
    pdf_save_path = DOCS_DIR / f"{safe_prefix}.pdf"
    # Lazy previews/crops require the original PDF; don't publish broken citations.
    _save_pdf(pdf_save_path, pdf_bytes)
    with PDF_LOCK:
        pdf = pdfium.PdfDocument(str(pdf_save_path))
        try:
            total_pages = len(pdf)
        finally:
            pdf.close()
    page_map = {number: f"/api/preview/{safe_prefix}/{number}" for number in range(1, total_pages + 1)}
    if total_pages:
        file_name = f"{safe_prefix}_page_1.webp"
        save_webp(render_pdf_image(pdf_save_path, 1), PREVIEWS_DIR / file_name)
        page_map[1] = f"/static/previews/{file_name}"
    return page_map


def _save_pdf(path, contents):
    if path.exists() and path.stat().st_size == len(contents) and path.read_bytes() == contents:
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".pdf", delete=False) as stream:
            temporary = stream.name
            stream.write(contents)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def clean_text_to_markdown(raw_text: str) -> str:
    """
    Converts raw extracted document text into clean, structured Markdown
    retaining headings, numbered clauses, lists, and tables.
    """
    lines = raw_text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if re.match(r'^\d+\.\s+[A-Z][A-Z0-9\s&/\-]{3,}$', stripped):
            cleaned.append(f"\n## {stripped}\n")
        elif re.match(r'^\d+\.\d+\s+', stripped):
            cleaned.append(f"\n### {stripped}")
        elif re.match(r'^[•\*\-]\s+', stripped):
            cleaned.append(f"- {stripped.lstrip('•*- ')}")
        else:
            cleaned.append(stripped)
    return "\n".join(cleaned)


def _extract_pdf_range(path, start, end):
    """Spawn-safe worker. Only a saved path and page range cross process boundaries."""
    primary, fallback = [], []
    failed = False
    try:
        with open(path, "rb") as source:
            reader = PdfReader(source)
            for idx in range(start, min(end, len(reader.pages))):
                text = reader.pages[idx].extract_text() or ""
                if text.strip():
                    primary.append((idx + 1, text))
    except Exception:
        failed = True
    if not primary:
        with PDF_LOCK:
            pdf = pdfium.PdfDocument(path)
            try:
                for idx in range(start, min(end, len(pdf))):
                    page = pdf[idx]
                    text_page = page.get_textpage()
                    text = text_page.get_text_range() or ""
                    if text.strip():
                        fallback.append((idx + 1, text))
                    text_page.close()
                    page.close()
            finally:
                pdf.close()
    return primary, fallback, failed


def extract_pages_from_pdf(pdf_bytes: bytes, filename: str, saved_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Keep pypdf extraction semantics; shard large PDFs using independent processes."""
    source_path = saved_path or DOCS_DIR / f"source_{hashlib.sha256(pdf_bytes).hexdigest()}.pdf"
    _save_pdf(source_path, pdf_bytes)
    try:
        with PDF_LOCK:
            pdf = pdfium.PdfDocument(str(source_path))
            try:
                total = len(pdf)
            finally:
                pdf.close()
        if total > PDF_PARALLEL_PAGE_THRESHOLD and PDF_PROCESS_WORKERS > 1:
            step = (total + PDF_PROCESS_WORKERS - 1) // PDF_PROCESS_WORKERS
            ranges = [(str(source_path), start, min(total, start + step)) for start in range(0, total, step)]
            try:
                with ProcessPoolExecutor(max_workers=PDF_PROCESS_WORKERS, mp_context=multiprocessing.get_context("spawn")) as pool:
                    results = list(pool.map(_extract_pdf_range_args, ranges))
                if any(row[2] for row in results):
                    results = [_extract_pdf_range(str(source_path), 0, total)]
            except Exception:
                results = [_extract_pdf_range(str(source_path), 0, total)]
        else:
            results = [_extract_pdf_range(str(source_path), 0, total)]
        primary = [page for result in results for page in result[0]]
        raw_pages = primary or [page for result in results for page in result[1]]
        return [{"filename": filename, "page": number, "text": clean_text_to_markdown(text)}
                for number, text in sorted(raw_pages)]
    except Exception as exc:
        print(f"PDF text extraction error: {exc}")
        return []


def _extract_pdf_range_args(args):
    return _extract_pdf_range(*args)


def extract_pages_from_text(raw_text: str, filename: str) -> List[Dict[str, Any]]:
    """Fallback for raw .txt or .md files."""
    chunks = [c.strip() for c in raw_text.split("\n\n\n") if c.strip()]
    if not chunks:
        chunks = [raw_text]
    pages = []
    for idx, c in enumerate(chunks, 1):
        pages.append({
            "filename": filename,
            "page": idx,
            "text": c
        })
    return pages


def _split_into_child_units(para: str) -> List[str]:
    """
    Splits a parent paragraph or table block into fine-grained child search units.
    - For Markdown/pipe tables: pairs header context with each row so individual row lookups retain column names.
    - For prose paragraphs: splits into sentences while preserving bullet items.
    """
    lines = [ln.strip() for ln in para.splitlines() if ln.strip()]
    pipe_lines = [ln for ln in lines if ln.startswith("|")]
    if len(pipe_lines) >= 2:
        title_prefix = lines[0] if not lines[0].startswith("|") else ""
        header_row = pipe_lines[0]
        units = [para]
        for row in pipe_lines[1:]:
            if re.match(r'^\|[\s\-:|]+\|$', row):
                continue
            row_unit = f"{title_prefix} {header_row} {row}".strip()
            units.append(row_unit)
        return units

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n(?=\-\s|\d+\.\s)', para) if len(s.strip()) > 15]
    return sentences if sentences else [para]


def hierarchical_chunk(
    pages: List[Dict[str, Any]],
    page_images: Optional[Dict[int, str]] = None,
    ast: Optional[Any] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Implements Small-to-Big (Parent-Child) chunking synchronized with the Document AST.
    Child sentences/rows are indexed for precise vector + BM25 matching.
    Parent paragraphs are passed to Gemma 4 for rich, coherent context.
    """
    page_images = page_images or {}
    chunks: List[Dict[str, Any]] = []
    chunk_id = 0

    combined_header = " ".join([p.get("text", "")[:1000] for p in pages[:2]])
    classification = classify_document(combined_header)
    default_filename = pages[0].get("filename", "Document") if pages else "Document"

    # When AST is provided, derive chunks directly from AST PARAGRAPH nodes for 100% node ID & path alignment
    if ast is not None and hasattr(ast, "nodes"):
        from app.ingestion.ast_builder import ASTNodeType
        para_nodes = [n for n in ast.nodes.values() if n.type == ASTNodeType.PARAGRAPH]
        if para_nodes:
            for p_node in para_nodes:
                page_num = p_node.page
                para_text = p_node.text.strip()
                if not para_text:
                    continue

                # Determine section title from parent AST node
                sec_title = "Section"
                if p_node.parent_id and p_node.parent_id in ast.nodes:
                    sec_title = ast.nodes[p_node.parent_id].title

                img_url = p_node.image_url or page_images.get(page_num)
                linked_visuals = []
                for lid in p_node.linked_node_ids:
                    v_node = ast.get_node(lid)
                    if v_node and v_node.type == ASTNodeType.VISUAL:
                        linked_visuals.append({
                            "id": v_node.id,
                            "title": v_node.title,
                            "image_url": v_node.image_url or page_images.get(v_node.page),
                            "visual_type": v_node.visual_type,
                            "bbox": v_node.bbox,
                            "page": v_node.page,
                        })
                        if not img_url and v_node.image_url:
                            img_url = v_node.image_url

                child_units = _split_into_child_units(para_text)
                for sent in child_units:
                    chunk_item: Dict[str, Any] = {
                        "id": chunk_id,
                        "filename": default_filename,
                        "page": page_num,
                        "parent_text": para_text,
                        "child_text": sent,
                        "ast_node_id": p_node.id,
                        "section_title": sec_title,
                        "materialized_path": p_node.materialized_path,
                        "image_url": img_url,
                        "has_visual": bool(img_url or linked_visuals),
                    }
                    if linked_visuals:
                        chunk_item["linked_visuals"] = linked_visuals
                    chunks.append(chunk_item)
                    chunk_id += 1
            return chunks, classification

    # Standalone fallback when called without an AST instance
    for page in pages:
        page_num = page["page"]
        img_url = page_images.get(page_num)

        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', page["text"]) if len(p.strip()) > 20]
        if not paragraphs:
            paragraphs = [page["text"].strip()] if page["text"].strip() else []

        for p_idx, para in enumerate(paragraphs, 1):
            sentences = _split_into_child_units(para)
            for sent in sentences:
                chunks.append({
                    "id": chunk_id,
                    "filename": page["filename"],
                    "page": page_num,
                    "parent_text": para,
                    "child_text": sent,
                    "ast_node_id": f"para_{page_num}_{p_idx}",
                    "section_title": f"Page {page_num}",
                    "materialized_path": f"root/page_{page_num}/para_{p_idx}",
                    "image_url": img_url,
                    "has_visual": bool(img_url),
                })
                chunk_id += 1

    return chunks, classification
