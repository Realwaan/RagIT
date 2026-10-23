import io
import re
import hashlib
from collections import OrderedDict
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from pypdf import PdfReader
import pypdfium2 as pdfium
from app.config import PREVIEWS_DIR, DOCS_DIR
from app.classifier import classify_document
from app.pdf_lock import serialized_pdf, PDF_LOCK
from app.ocr import recognize_image
from app.embeddings import split_embedding_text


def sanitize_doc_id(raw_id: str) -> str:
    """Sanitizes document identifiers to prevent path traversal or injection."""
    cleaned = re.sub(r'[^a-zA-Z0-9_-]', '_', Path(raw_id).stem)
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    return cleaned or "document"


@serialized_pdf
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
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            if 1 <= page_num <= len(pdf):
                page = pdf[page_num - 1]
                image = page.render(scale=1.5).to_pil()
                image.save(file_path, "WEBP", quality=80)
                return file_path
        finally:
            pdf.close()
    except Exception as e:
        print(f"Error on-demand rendering page {page_num}: {e}")
    return None


@serialized_pdf
def render_page_previews(pdf_bytes: bytes, doc_prefix: str) -> Dict[int, str]:
    """
    Save the PDF and render only the first preview. Other pages render on demand.
    """
    safe_prefix = sanitize_doc_id(doc_prefix)
    pdf_save_path = DOCS_DIR / f"{safe_prefix}.pdf"
    # Lazy previews/crops require the original PDF; don't publish broken citations.
    pdf_save_path.write_bytes(pdf_bytes)

    page_map: Dict[int, str] = {}
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        try:
            total_pages = len(pdf)
            pages_to_prerender = 1

            for idx in range(total_pages):
                page_num = idx + 1
                file_name = f"{safe_prefix}_page_{page_num}.webp"
                file_path = PREVIEWS_DIR / file_name

                if idx < pages_to_prerender:
                    page = pdf[idx]
                    image = page.render(scale=1.5).to_pil()
                    image.save(file_path, "WEBP", quality=80)
                    page_map[page_num] = f"/static/previews/{file_name}"
                else:
                    page_map[page_num] = f"/api/preview/{safe_prefix}/{page_num}"
        finally:
            pdf.close()
    except Exception as e:
        print(f"Warning: Could not render page preview with pypdfium2: {e}")
    return page_map


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


def extract_pages_from_pdf(pdf_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Fast native extraction plus OCR of raster regions, preserving every page.

    Native text stays authoritative. OCR supplements image text on mixed pages;
    scans use a rendered page. A bounded per-document image cache reuses logos
    and repeated scans without losing their individual page references.
    """
    pages, ocr_cache = [], OrderedDict()
    fallback_reader = None
    try:
        with PDF_LOCK:
            pdf = pdfium.PdfDocument(pdf_bytes)
            page_count = len(pdf)
    except Exception as exc:
        raise ValueError('Could not open PDF. Check that it is valid and not password protected.') from exc
    try:
        for idx in range(page_count):
            images = []
            with PDF_LOCK:
                page = pdf[idx]
                try:
                    try:
                        textpage = page.get_textpage()
                        try:
                            text = textpage.get_text_bounded() or ''
                        finally:
                            textpage.close()
                    except Exception:
                        text = ''
                    if not text.strip() or '\ufffd' in text:
                        try:
                            if fallback_reader is None:
                                fallback_reader = PdfReader(io.BytesIO(pdf_bytes))
                            fallback = fallback_reader.pages[idx].extract_text() or ''
                        except Exception:
                            fallback = ''  # PDFium may still render this page for OCR.
                        if len(fallback.strip()) > len(text.strip()) or ('\ufffd' in text and '\ufffd' not in fallback):
                            text = fallback
                    objects = list(page.get_objects())
                    if not text.strip() and objects:
                        bitmap = page.render(scale=2.0)
                        try:
                            images.append(bitmap.to_pil().copy())
                        finally:
                            bitmap.close()
                    else:
                        for obj in objects:
                            if getattr(obj, 'type', None) == 3:
                                # Decode original pixels, including small table labels.
                                try:
                                    bitmap = obj.get_bitmap(render=True)
                                except Exception:
                                    for image in images:
                                        image.close()
                                    images = []
                                    bitmap = page.render(scale=2.0)
                                    try:
                                        images.append(bitmap.to_pil().copy())
                                    finally:
                                        bitmap.close()
                                    break
                                try:
                                    images.append(bitmap.to_pil().copy())
                                finally:
                                    bitmap.close()
                finally:
                    page.close()
            ocr_lines, confidences = [], []
            native_normalized = re.sub(r'\s+', ' ', text).casefold()
            try:
                for image in images:
                    digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
                    if digest not in ocr_cache:
                        ocr_cache[digest] = recognize_image(image)
                        if len(ocr_cache) > 32:
                            ocr_cache.popitem(last=False)
                    for line in ocr_cache[digest]:
                        value = line['text'].strip()
                        if value and re.sub(r'\s+', ' ', value).casefold() not in native_normalized:
                            ocr_lines.append(value)
                            confidences.append(line['confidence'])
            except Exception as exc:
                raise ValueError(f'OCR failed on page {idx + 1}; indexing stopped to avoid omitting image text. {exc}') from exc
            finally:
                for image in images:
                    image.close()
            # Keep OCR as separate paragraphs so it remains searchable and cited.
            combined = text + ('\n\n' + '\n'.join(dict.fromkeys(ocr_lines)) if ocr_lines else '')
            pages.append({'filename': filename, 'page': idx + 1,
                          'text': clean_text_to_markdown(combined),
                          'extraction': {'native_text': bool(text.strip()), 'ocr_images': len(images),
                                         'ocr_lines': len(ocr_lines),
                                         'ocr_min_confidence': min(confidences) if confidences else None}})
    finally:
        with PDF_LOCK:
            pdf.close()
    return pages


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
        return [window for unit in units for window in split_embedding_text(unit)]

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n(?=\-\s|\d+\.\s)', para) if s.strip()]
    return [window for unit in (sentences or [para]) for window in split_embedding_text(unit)]


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
        from app.ast_builder import ASTNodeType
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

        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', page["text"]) if p.strip()]
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
