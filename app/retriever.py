import re
import numpy as np
from rank_bm25 import BM25Okapi
from typing import List, Dict, Any
from app.embeddings import embed_query
from app.query_intent import definition_subject, definition_excerpt, function_subject, function_excerpt
from app.table_answers import table_answer

STOP_WORDS = {
    "what", "is", "the", "are", "how", "for", "and", "with", "does", "can",
    "in", "of", "to", "a", "an", "on", "by", "from", "that", "this", "it",
    "be", "or", "as", "at", "if", "who", "which", "when", "where", "why"
}


def tokenize_words(text: str) -> List[str]:
    """Tokenizes text into lowercase alphanumeric words, stripping punctuation."""
    return re.findall(r'[a-z0-9]+(?:\.[0-9]+)?', text.lower())


def requested_pdf_pages(query: str):
    match = re.search(r'\b(?:pdf\s+)?pages?\s+(\d+)(?:\s*[-–]\s*(\d+))?\b', query, re.IGNORECASE)
    if not match:
        return None
    first, last = int(match[1]), int(match[2] or match[1])
    return set(range(first, last + 1)) if 1 <= first <= last <= 5000 else set()


class HybridRetriever:
    """
    Hybrid Retriever combining Sparse Lexical Search (BM25) and Dense Vector Cosine Similarity
    using Reciprocal Rank Fusion (RRF).
    """
    def __init__(self, chunks: List[Dict[str, Any]], embeddings: np.ndarray):
        self.chunks = chunks
        self.embeddings = embeddings  # Shape: (N, 384), pre-normalized unit vectors

        if not chunks:
            self.bm25 = None
            return

        tokenized_corpus = [tokenize_words(c.get("child_text", "")) or [""] for c in chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def retrieve(self, query: str, top_k: int = 4, k_rrf: int = 60) -> List[Dict[str, Any]]:
        if not self.chunks or len(self.chunks) == 0 or self.bm25 is None:
            return []
        requested_pages = requested_pdf_pages(query)
        eligible = np.array([i for i, chunk in enumerate(self.chunks)
                             if requested_pages is None or chunk.get('page') in requested_pages], dtype=int)
        if not len(eligible):
            return []

        # 1. Sparse BM25 Search
        # Question scaffolding must not outrank the actual subject (e.g. a
        # foreword containing 'what' over a textbook's definition of 'cell').
        query_tokens = [token for token in tokenize_words(query) if token not in STOP_WORDS]
        subject = definition_subject(query)
        if subject:
            query_tokens = tokenize_words(subject)
        bm25_scores = self.bm25.get_scores(query_tokens) if query_tokens else np.zeros(len(self.chunks))
        candidate_count = max(top_k * 10, 50)
        bm25_rank_indices = eligible[np.argsort(bm25_scores[eligible])[::-1][:candidate_count]]

        # 2. Dense Vector Dot Product Search
        q_vec = embed_query(query)
        dense_scores = np.dot(self.embeddings, q_vec)
        dense_rank_indices = eligible[np.argsort(dense_scores[eligible])[::-1][:candidate_count]]

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_map: Dict[int, float] = {}

        for rank, idx in enumerate(bm25_rank_indices):
            if bm25_scores[idx] > 0:
                rrf_map[int(idx)] = rrf_map.get(int(idx), 0.0) + (1.0 / (k_rrf + rank))

        for rank, idx in enumerate(dense_rank_indices):
            rrf_map[int(idx)] = rrf_map.get(int(idx), 0.0) + (1.0 / (k_rrf + rank))

        # A heading/contents entry can be a close semantic match but supplies no
        # definition. Prefer an explicit definition without inflating its dense
        # similarity (the relevance gate still sees the actual model score).
        # Definitions may be outside the short candidate lists in a long book.
        # Scan the source sentences for explicit definitions, then score those
        # hits using their already-computed similarities. No reindex is needed.
        definitions = {}
        if subject:
            parent_definitions = {}
            for i in eligible:
                chunk = self.chunks[i]
                parent = chunk.get('parent_text') or chunk.get('child_text', '')
                if parent not in parent_definitions:
                    parent_definitions[parent] = definition_excerpt(query, parent)
                excerpt = parent_definitions[parent]
                if excerpt:
                    definitions[i] = excerpt
                    rrf_map.setdefault(i, 0.0)
        if function_subject(query):
            for i in eligible:
                chunk = self.chunks[i]
                excerpt = function_excerpt(query, chunk.get('child_text', ''))
                if excerpt:
                    definitions[i] = excerpt
                    rrf_map.setdefault(i, 0.0)
        table_matches = {}
        for i in eligible:
            chunk = self.chunks[i]
            parent = chunk.get('parent_text', '')
            if '|' not in parent:
                continue
            if parent not in table_matches:
                table_matches[parent] = table_answer(query, parent)
            if table_matches[parent]:
                definitions[i] = table_matches[parent]
                rrf_map.setdefault(i, 0.0)
        sorted_indices = sorted(
            rrf_map.keys(),
            key=lambda i: (bool(definitions.get(i)), rrf_map[i], float(dense_scores[i])),
            reverse=True
        )

        # Deduplicate parent paragraphs while preserving the best dense/BM25 scores across child hits
        seen_parents: Dict[tuple, Dict[str, Any]] = {}
        results: List[Dict[str, Any]] = []
        citation_num = 1

        for idx in sorted_indices:
            chunk = self.chunks[idx].copy()
            # Identical wording on separate pages can refer to different evidence.
            # Only siblings from the same parent should share a citation.
            parent = (
                chunk.get("filename", ""), chunk.get("page"),
                chunk.get("ast_node_id") or chunk.get("materialized_path") or chunk.get("parent_text", ""),
            )
            d_score = float(dense_scores[idx])
            b_score = float(bm25_scores[idx])
            r_score = float(rrf_map[idx])

            if parent in seen_parents:
                existing = seen_parents[parent]
                if d_score > existing["dense_score"]:
                    existing["dense_score"] = d_score
                if b_score > existing["bm25_score"]:
                    existing["bm25_score"] = b_score
                continue

            if len(results) >= top_k:
                continue

            chunk["citation_id"] = citation_num
            chunk["dense_score"] = d_score
            chunk["bm25_score"] = b_score
            chunk["rrf_score"] = r_score
            if definitions.get(idx):
                chunk["answer_excerpt"] = definitions[idx]
            seen_parents[parent] = chunk
            results.append(chunk)
            citation_num += 1

        return results

    def escalate_page_scan(
        self,
        query: str,
        candidate_pages: List[int],
        ast: Any = None,
        min_threshold: float = 0.50
    ) -> List[Dict[str, Any]]:
        """
        Tier-2 CRAG Hierarchical Tree Escalation:
        When chunk-level confidence falls below threshold, promotes the search
        to Whole-Page scanning across candidate pages to recover multi-paragraph context.
        Computes genuine whole-page dense embedding similarity and whole-word lexical coverage.
        """
        if not self.chunks:
            return []

        pages_to_check = candidate_pages
        if not pages_to_check:
            if ast and hasattr(ast, "get_all_pages"):
                pages_to_check = ast.get_all_pages()
            else:
                pages_to_check = sorted(list({c.get("page", 1) for c in self.chunks}))

        requested_pages = requested_pdf_pages(query)
        if requested_pages is not None:
            pages_to_check = [page for page in pages_to_check if page in requested_pages]

        if not pages_to_check:
            return []

        q_vec = embed_query(query)
        raw_tokens = tokenize_words(query)
        query_tokens = [t for t in raw_tokens if len(t) > 2 and t not in STOP_WORDS]
        if not query_tokens:
            query_tokens = [t for t in raw_tokens if len(t) > 2]

        best_page = None
        best_score = 0.0
        best_lexical = 0.0
        best_text = ""

        for p in pages_to_check:
            if ast and hasattr(ast, "get_page_text"):
                page_text = ast.get_page_text(p)
            else:
                page_chunks = [c["parent_text"] for c in self.chunks if c.get("page") == p]
                page_text = "\n\n".join(dict.fromkeys(page_chunks))

            if not page_text.strip():
                continue

            # 1. Chunk-level dense scores on this page
            page_dense_scores = [
                float(np.dot(self.embeddings[i], q_vec))
                for i, c in enumerate(self.chunks)
                if c.get("page") == p and i < len(self.embeddings)
            ]
            max_chunk_dense = max(page_dense_scores) if page_dense_scores else 0.0

            # 2. Whole-page dense vector similarity (captures multi-paragraph context)
            page_vec = embed_query(page_text[:2000])
            whole_page_dense = float(np.dot(page_vec, q_vec))
            max_dense = max(max_chunk_dense, whole_page_dense)

            # 3. Exact whole-word lexical token coverage across the page
            page_word_set = set(tokenize_words(page_text))
            matching_tokens = sum(1 for t in query_tokens if t in page_word_set)
            lexical_ratio = matching_tokens / max(1, len(query_tokens))

            # Combine whole-page dense similarity and exact multi-paragraph term coverage
            page_score = round(0.65 * max_dense + 0.35 * lexical_ratio, 3) if query_tokens else round(max_dense, 3)
            # If all or nearly all distinct content terms appear as whole words on this page,
            # reflect that multi-paragraph coverage in the page relevance score
            if lexical_ratio >= 0.66 and max_dense >= 0.35:
                page_score = max(page_score, round(0.50 + 0.35 * lexical_ratio, 3))

            if page_score > best_score:
                best_score = page_score
                best_lexical = lexical_ratio
                best_page = p
                best_text = page_text

        if best_page is not None and best_score >= min_threshold:
            filename = ast.title if (ast and hasattr(ast, "title")) else self.chunks[0].get("filename", "Document")
            return [{
                "citation_id": 1,
                "child_text": f"Whole-Page Scan (Page {best_page}): {best_text[:280]}...",
                "parent_text": best_text,
                "filename": filename,
                "page": best_page,
                "dense_score": round(best_score, 3),
                "bm25_score": round(best_lexical, 3),
                "rrf_score": round(best_score, 3),
                "lexical_coverage": round(best_lexical, 3),
                "escalated_from": "whole_page_scan"
            }]

        return []
