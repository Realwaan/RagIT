from typing import List, Dict, Any, Generator, Tuple, Optional
import base64
import re
import app.config as cfg
from app.llm import (
    get_primary_client,
    get_fallback_client,
    has_valid_primary_key,
    has_valid_fallback_key,
    get_openai_client,
    has_valid_gemini_key,
    has_valid_openai_endpoint,
)
from app.discrepancy_scanner import detect_heuristic_discrepancy
from app.query_intent import (
    definition_subject,
    definition_excerpts,
    function_subject,
    function_excerpt,
    detect_query_modality,
)
from app.table_answers import table_answer
from app.fact_answers import fact_answer

BASE_SYSTEM_PROMPT = """You are AuditGuard, a document intelligence and compliance verification assistant.
Your job is to answer questions strictly and exclusively using the provided numbered source excerpts.

STRICT GROUNDING & FORMATTING RULES:
1. Every factual statement or recommendation MUST cite its supporting excerpt using citation badges like [1], [2], etc.
2. If the provided excerpts do not explicitly contain the answer, reply ONLY with:
   "I cannot verify this information in the provided document excerpts."
3. Do NOT invent, assume, extrapolate, or use outside unverified knowledge.
4. Structure your response so it is effortless to read:
   - Lead with the answer in one or two short sentences, including citations.
   - Keep simple answers brief. For complex questions, use descriptive Markdown headings (###), short paragraphs of at most three sentences, and focused bullet points. Use numbered lists only for ordered steps.
   - Separate paragraphs, headings, and lists with blank lines. Bold only key terms or the decisive result, not entire paragraphs.
   - Use a compact Markdown table only when comparing multiple items with shared attributes. A single number or date does not need a table.
   - Include relevant conditions, exceptions, and uncertainty. Do not repeat the same information in a summary, list, and table, or paste entire source excerpts into the answer.
   - Answer only what was asked, normally within 150-250 words unless the user requests a detailed explanation. Omit filler introductions, technical pipeline commentary, and a separate sources list; citations already link to the evidence.
"""


def build_grounded_prompt(query: str, chunks: List[Dict[str, Any]], persona_addon: str = "") -> str:
    """Builds the context payload with numbered excerpts and linked visual table data."""
    context_lines = []
    for c in chunks:
        cid = c.get("citation_id", 1)
        page = c.get("page", 1)
        doc = c.get("filename", "Document")
        parent = c.get("parent_text", "").strip()
        block = f"[{cid}] (File: {doc}, Page {page}):\n{parent}"
        if c.get("linked_visuals"):
            vis_titles = ", ".join(v.get("title", "Visual") for v in c["linked_visuals"])
            block += f"\n(Linked Visual Evidence: {vis_titles})"
        context_lines.append(block + "\n")

    joined_context = "\n".join(context_lines)

    return f"""=== VERIFIED SOURCE EXCERPTS ===
{joined_context}
================================

USER QUESTION:
{query}

REMINDER: Answer strictly from the excerpts above. Cite [1], [2] for every claim. If unverified, refuse to guess."""


def _build_extractive_fallback(query: str, chunks: List[Dict[str, Any]]) -> str:
    """
    Deterministic Extractive Synthesis when no external LLM server is reachable.
    Synthesizes the highest-scoring verified excerpts with exact citation markers [1], [2]
    and highlights any cross-modal discrepancy between cited clauses and linked tables.
    """
    if not chunks:
        return "I cannot verify this information in the provided document excerpts."

    table_matches = [(table_answer(query, chunk.get('parent_text', '')), chunk) for chunk in chunks]
    table_matches = [(answer, chunk) for answer, chunk in table_matches if answer]
    if table_matches and len({answer for answer, _ in table_matches}) == 1:
        answer, chunk = table_matches[0]
        return f"{answer} [{chunk.get('citation_id', 1)}]"
    if table_matches:
        values = list(dict.fromkeys(f"- {answer} [{chunk.get('citation_id', 1)}]" for answer, chunk in table_matches))
        return 'Different source tables report different values:\n\n' + '\n'.join(values) + '\n\nSpecify the PDF page or reporting period to select the intended table.'

    factual = fact_answer(query, chunks)
    if factual:
        return factual

    # Offline definitions must answer the subject, not print a table-of-contents
    # label or an unrelated figure caption and call it a successful answer.
    if definition_subject(query) or function_subject(query):
        for chunk in chunks:
            excerpts = ([function_excerpt(query, chunk.get('parent_text', ''))]
                        if function_subject(query) else definition_excerpts(query, chunk.get('parent_text', '')))
            excerpts = [excerpt for excerpt in excerpts if excerpt]
            if excerpts:
                return '\n\n'.join(f"{excerpt} [{chunk.get('citation_id', 1)}]" for excerpt in excerpts[:2])
        return "I cannot verify this information in the provided document excerpts."

    top_c = chunks[0]
    cid = top_c.get("citation_id", 1)
    excerpt = top_c.get("parent_text", "").strip()

    # The matched child is a source slice, not a generated paraphrase. Keep the
    # complete parent below so conditions remain available in every client/export.
    matched = top_c.get("child_text", "").strip()
    if not matched or matched not in excerpt:
        matched = excerpt
    if len(matched) > 600 and "|" not in matched:
        matched = " ".join(re.split(r"(?<=[.!?])\s+(?=[A-Z])", matched)[:2])
    parts = [f"*Document excerpt*\n\n{matched} [{cid}]"]
    evidence = [f"#### Source [{cid}]\n\n{excerpt}"]

    if len(chunks) > 1 and chunks[1].get("dense_score", 0.0) >= 0.45:
        second_c = chunks[1]
        cid2 = second_c.get("citation_id", 2)
        excerpt2 = second_c.get("parent_text", "").strip()
        if excerpt2 and excerpt2 != excerpt:
            evidence.append(f"#### Source [{cid2}]\n\n{excerpt2}")
            disc = detect_heuristic_discrepancy(excerpt, excerpt2) or detect_heuristic_discrepancy(excerpt2, excerpt)
            if disc and disc.get("status") == "CONTRADICTION":
                parts.append(
                    f"\n\n### Conflicting evidence\n\n{disc.get('discrepancy_delta')} [{cid}][{cid2}]"
                )

    parts.append("\n\n### Source excerpts\n\n" + "\n\n".join(evidence))
    return "".join(parts)


def resolve_crop_bytes(img_url: str) -> Optional[bytes]:
    """Reads binary WebP image data from local static storage."""
    if not img_url:
        return None
    if "/static/crops/" in img_url:
        fname = img_url.split("/static/crops/")[-1].split("?")[0]
        crop_path = cfg.CROPS_DIR / fname
        if crop_path.exists() and crop_path.is_file():
            try:
                return crop_path.read_bytes()
            except Exception:
                return None
    return None


def extract_chunk_images(chunks: List[Dict[str, Any]], max_images: int = 3) -> List[Tuple[str, bytes]]:
    """Extracts binary crops for chunks containing visual evidence (diagrams, tables, figures)."""
    images: List[Tuple[str, bytes]] = []
    seen: set = set()
    for c in chunks:
        if len(images) >= max_images:
            break
        img_url = c.get("image_url")
        if img_url and img_url not in seen:
            data = resolve_crop_bytes(img_url)
            if data:
                seen.add(img_url)
                cid = c.get("citation_id", 1)
                page = c.get("page", 1)
                images.append((f"Visual for Excerpt [{cid}] (Page {page})", data))
        for lv in c.get("linked_visuals", []):
            if len(images) >= max_images:
                break
            lv_url = lv.get("image_url")
            if lv_url and lv_url not in seen:
                data = resolve_crop_bytes(lv_url)
                if data:
                    seen.add(lv_url)
                    cid = c.get("citation_id", 1)
                    title = lv.get("title", "Visual Evidence")
                    images.append((f"Visual '{title}' linked to Excerpt [{cid}] (Page {lv.get('page', 1)})", data))
    return images


def build_multimodal_payload(prompt_text: str, images: List[Tuple[str, bytes]]) -> List[Dict[str, Any]]:
    """Constructs OpenAI/Gemini compatible multimodal message content with base64 image_urls."""
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt_text}]
    for label, img_data in images:
        b64 = base64.b64encode(img_data).decode("ascii")
        content.append({"type": "text", "text": f"\n[Visual Reference: {label}]"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/webp;base64,{b64}"}
        })
    return content


def generate_grounded_answer_with_telemetry(
    query: str,
    chunks: List[Dict[str, Any]],
    persona_addon: str = ""
) -> Tuple[str, Dict[str, Any]]:
    """
    Synchronous grounded generation returning (answer_text, telemetry_dict).
    Executes Primary Fast API (Groq) first, with seamless fallback to Google Gemini.
    """
    system_content = BASE_SYSTEM_PROMPT
    if persona_addon:
        system_content += f"\n\nSPECIALIZED AUDIT PERSONA:\n{persona_addon}"

    user_content = build_grounded_prompt(query, chunks, persona_addon)
    visual_images = extract_chunk_images(chunks)
    is_visual = detect_query_modality(query) == "visual"

    # Direct multimodal path (Gemini) when query is visual and visual crops are present
    if is_visual and visual_images and has_valid_fallback_key():
        client = get_fallback_client(timeout=cfg.VISION_TIMEOUT_SECONDS)
        gemini_content = build_multimodal_payload(user_content, visual_images)
        try:
            response = client.chat.completions.create(
                model=cfg.FALLBACK_MODEL,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": gemini_content}
                ],
                temperature=0.2,
                max_tokens=800
            )
            text = response.choices[0].message.content or "No response from Gemini multimodal."
            usage = getattr(response, "usage", None)
            prompt_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
            comp_tok = int(getattr(usage, "completion_tokens", 0) or 0)
            total_tok = int(getattr(usage, "total_tokens", 0) or (prompt_tok + comp_tok))
            return text, {
                "prompt_tokens": prompt_tok,
                "completion_tokens": comp_tok,
                "total_tokens": total_tok,
                "generation_mode": "gemini_multimodal",
                "model_used": cfg.FALLBACK_MODEL,
            }
        except Exception as e:
            print(f"Direct multimodal Gemini warning, attempting fallback: {e}")

    # 1. Try Primary Fast API (Groq)
    if has_valid_primary_key():
        client = get_primary_client()
        try:
            response = client.chat.completions.create(
                model=cfg.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2,
                max_tokens=800
            )
            text = response.choices[0].message.content or "No response from Groq."
            usage = getattr(response, "usage", None)
            prompt_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
            comp_tok = int(getattr(usage, "completion_tokens", 0) or 0)
            total_tok = int(getattr(usage, "total_tokens", 0) or (prompt_tok + comp_tok))
            return text, {
                "prompt_tokens": prompt_tok,
                "completion_tokens": comp_tok,
                "total_tokens": total_tok,
                "generation_mode": "groq_primary",
                "model_used": cfg.LLM_MODEL,
            }
        except Exception as e:
            print(f"Primary Fast API (Groq) warning, attempting fallback: {e}")

    # 2. Try Fallback (Google Gemini OpenAI-compatible endpoint)
    if has_valid_fallback_key():
        client = get_fallback_client(timeout=cfg.VISION_TIMEOUT_SECONDS if visual_images else None)
        gemini_content = build_multimodal_payload(user_content, visual_images) if visual_images else user_content
        try:
            response = client.chat.completions.create(
                model=cfg.FALLBACK_MODEL,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": gemini_content}
                ],
                temperature=0.2,
                max_tokens=800
            )
            text = response.choices[0].message.content or "No response from Gemini fallback."
            usage = getattr(response, "usage", None)
            prompt_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
            comp_tok = int(getattr(usage, "completion_tokens", 0) or 0)
            total_tok = int(getattr(usage, "total_tokens", 0) or (prompt_tok + comp_tok))
            return text, {
                "prompt_tokens": prompt_tok,
                "completion_tokens": comp_tok,
                "total_tokens": total_tok,
                "generation_mode": "gemini_multimodal" if visual_images else "gemini_fallback",
                "model_used": cfg.FALLBACK_MODEL,
            }
        except Exception as e:
            print(f"Fallback API (Gemini) warning, attempting extractive fallback: {e}")

    # 3. Transparent Extractive AST Fallback (Offline Mode)
    fallback_text = _build_extractive_fallback(query, chunks)
    return fallback_text, {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "generation_mode": "extractive_fallback",
        "model_used": "extractive-ast-engine",
    }


def generate_grounded_answer(
    query: str,
    chunks: List[Dict[str, Any]],
    persona_addon: str = ""
) -> str:
    """Synchronous grounded generation returning the answer string."""
    answer, _ = generate_grounded_answer_with_telemetry(query, chunks, persona_addon)
    return answer


def stream_grounded_answer(
    query: str,
    chunks: List[Dict[str, Any]],
    persona_addon: str = "",
    previous_question: str = "",
) -> Generator[str, None, None]:
    """
    Streams tokens in real-time from Primary Fast API (Groq) or Fallback (Gemini).
    When visual crops are present and the query relates to visual artifacts, streams
    multimodally directly from Gemini.
    """
    system_content = BASE_SYSTEM_PROMPT
    if persona_addon:
        system_content += f"\n\nSPECIALIZED AUDIT PERSONA:\n{persona_addon}"

    prompt_query = query if not previous_question else (
        f"Previous user question (context only, not evidence): {previous_question}\nCurrent question: {query}"
    )
    user_content = build_grounded_prompt(prompt_query, chunks, persona_addon)
    visual_images = extract_chunk_images(chunks)
    is_visual = detect_query_modality(query) == "visual"

    # Multimodal Direct Route (Gemini) when query is visual and visual crops are present
    if is_visual and visual_images and has_valid_fallback_key():
        client = get_fallback_client(timeout=cfg.VISION_TIMEOUT_SECONDS)
        gemini_content = build_multimodal_payload(user_content, visual_images)
        streamed_any = False
        try:
            stream = client.chat.completions.create(
                model=cfg.FALLBACK_MODEL,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": gemini_content}
                ],
                temperature=0.2,
                max_tokens=800,
                stream=True
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    streamed_any = True
                    yield delta
            if streamed_any:
                return
        except Exception as e:
            if streamed_any:
                raise RuntimeError("The response stream was interrupted.") from e
            print(f"Multimodal Gemini direct stream warning: {e}")

    # 1. Try Primary Fast API (Groq) Streaming
    if has_valid_primary_key():
        client = get_primary_client()
        streamed_any = False
        try:
            stream = client.chat.completions.create(
                model=cfg.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2,
                max_tokens=800,
                stream=True
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    streamed_any = True
                    yield delta
            if streamed_any:
                return
        except Exception as e:
            if streamed_any:
                raise RuntimeError("The response stream was interrupted.") from e
            print(f"Primary Fast API (Groq) stream warning: {e}")

    # 2. Try Fallback (Gemini OpenAI-compatible) Streaming
    if has_valid_fallback_key():
        client = get_fallback_client(timeout=cfg.VISION_TIMEOUT_SECONDS if visual_images else None)
        gemini_content = build_multimodal_payload(user_content, visual_images) if visual_images else user_content
        streamed_any = False
        try:
            stream = client.chat.completions.create(
                model=cfg.FALLBACK_MODEL,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": gemini_content}
                ],
                temperature=0.2,
                max_tokens=800,
                stream=True
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    streamed_any = True
                    yield delta
            if streamed_any:
                return
        except Exception as e:
            if streamed_any:
                raise RuntimeError("The response stream was interrupted.") from e
            print(f"Fallback API (Gemini) stream warning: {e}")

    # 3. Offline streaming fallback
    yield _build_extractive_fallback(query, chunks)


def repair_hallucinated_answer(
    query: str,
    answer: str,
    chunks: List[Dict[str, Any]],
    eval_result: Dict[str, Any],
) -> Tuple[str, Dict[str, Any], bool]:
    """
    Self-RAG Phase 3 Repair Loop:
    When an answer contains invalid citations or unsupported claims, triggers
    a targeted repair pass to excise hallucinations and restore strict grounding.
    Returns (repaired_answer, updated_eval_result, was_repaired).
    """
    from app.evaluator import verify_generated_answer

    invalid_cids = eval_result.get("invalid_citations", [])
    claims = eval_result.get("claims", [])
    has_unsupported = any(c.get("status") == "unsupported" for c in claims)

    if not invalid_cids and not has_unsupported:
        return answer, eval_result, False

    valid_cids = {int(c.get("citation_id", i + 1)) for i, c in enumerate(chunks)}

    # 1. Deterministic sentence-level excision of unsupported or hallucinated citation units
    units = re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n\n+", answer)
    repaired_units = []
    for unit in units:
        unit_cids = {int(x) for x in re.findall(r"\[(\d+)\]", unit)}
        # If the unit cites non-existent citations, drop it
        if unit_cids and not unit_cids <= valid_cids:
            continue
        # If the unit has no citation but makes factual assertions, drop it
        if not unit_cids and len(unit.split()) > 6 and not unit.strip().startswith(("#", "*", "-")):
            continue
        repaired_units.append(unit)

    candidate = " ".join(repaired_units).strip() if "\n" not in answer else "\n\n".join(repaired_units).strip()

    # 2. If deterministic excision leaves valid claims, re-verify
    if candidate:
        re_eval = verify_generated_answer(candidate, chunks, eval_result)
        if re_eval.get("citation_verified", False) and not re_eval.get("invalid_citations"):
            re_eval["badge"] = re_eval.get("badge", "") + " • SELF-RAG REPAIRED"
            re_eval["self_rag_repaired"] = True
            return candidate, re_eval, True

    # 3. If LLM is reachable, try targeted single-turn correction
    if has_valid_primary_key() or has_valid_fallback_key():
        repair_prompt = f"""You are a compliance editor. The following answer draft contains unsupported claims or hallucinated citations.
Rewrite the answer strictly keeping ONLY verified statements supported by the numbered source excerpts below.
Every claim must cite [1], [2] matching the source excerpts. Remove any unsupported sentences or invalid citations.
Do not introduce outside information.

=== SOURCE EXCERPTS ===
{build_grounded_prompt(query, chunks)}
=======================

DRAFT WITH ERRORS:
{answer}

REWRITTEN VERIFIED ANSWER:"""

        try:
            client = get_primary_client() if has_valid_primary_key() else get_fallback_client()
            model = cfg.LLM_MODEL if has_valid_primary_key() else cfg.FALLBACK_MODEL
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Rewrite the draft to remove hallucinations and strictly ground every claim in the provided source excerpts."},
                    {"role": "user", "content": repair_prompt}
                ],
                temperature=0.1,
                max_tokens=600
            )
            repaired_text = resp.choices[0].message.content or ""
            if repaired_text:
                re_eval = verify_generated_answer(repaired_text, chunks, eval_result)
                if re_eval.get("citation_verified", False) and not re_eval.get("invalid_citations"):
                    re_eval["badge"] = re_eval.get("badge", "") + " • SELF-RAG REPAIRED"
                    re_eval["self_rag_repaired"] = True
                    return repaired_text, re_eval, True
        except Exception as e:
            print(f"Self-RAG repair LLM warning: {e}")

    # 4. Fallback to transparent extractive synthesis
    extractive = _build_extractive_fallback(query, chunks)
    re_eval = verify_generated_answer(extractive, chunks, eval_result)
    re_eval["badge"] = "EXTRACTIVE SYNTHESIS • RECOVERED"
    re_eval["self_rag_repaired"] = True
    return extractive, re_eval, True
