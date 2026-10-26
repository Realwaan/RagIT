"""Relevance scores are heuristics, not entailment probabilities."""
import re
from app.config import SIMILARITY_THRESHOLD
from app.retriever import tokenize_words, STOP_WORDS
from app.fact_answers import property_query, normalize_fact_spacing


def _compute_lexical_overlap(query, chunks):
    tokens = [t for t in tokenize_words(query) if len(t) > 2 and t not in STOP_WORDS]
    tokens = tokens or tokenize_words(query)
    words = set(tokenize_words(' '.join(
        f"{c.get('parent_text', '')} {c.get('child_text', '')}" for c in chunks)))
    return round(sum(t in words for t in tokens) / len(tokens), 3) if tokens else 0.0


def evaluate_relevance(retrieved_chunks, query=''):
    original_query = query
    query = property_query(query)
    dense = max((float(c.get('dense_score', 0)) for c in retrieved_chunks), default=0.0)
    overlap = _compute_lexical_overlap(query, retrieved_chunks) if query else dense
    score = dense
    terms = [t for t in tokenize_words(query) if len(t) > 2 and t not in STOP_WORDS]
    if len(terms) >= 2 and overlap == 0 and dense < .72:
        score = round(dense * .65, 3)
    accepted = bool(retrieved_chunks) and score >= SIMILARITY_THRESHOLD
    promoted = any(c.get('escalated_from') == 'whole_page_scan' for c in retrieved_chunks)
    return {
        'status': 'SYNTHESIZE' if accepted else 'REFUSE',
        'retrieval_score': round(max(0., min(1., score)), 4),
        'retrieval_score_kind': 'heuristic_similarity_not_probability',
        'relevance_query': query, 'query_rewritten': query != original_query,
        'lexical_overlap': overlap,
        'claim_support': 'not_checked', 'citation_verified': False,
        'badge': ('RELEVANT PASSAGES' + (' - PROMOTED TO PAGE SCAN' if promoted else '')) if accepted else 'INSUFFICIENT EVIDENCE',
        'reason': 'Relevant passages found; answer claims have not been checked.' if accepted else
                  'I could not find enough supporting evidence in the retrieved passages to answer this question. Try rephrasing it or specifying a PDF page.',
    }


def _normalize(text):
    text = normalize_fact_spacing(text)
    return re.sub(r'\s+', ' ', re.sub(r'[*_`]', '', text)).strip().casefold()


def check_claim_support(answer, chunks):
    """Conservative sentence/line checks, not a semantic entailment model.

    Only complete source sentences receive extractive support. Paraphrases,
    compound clauses and tables remain uncertain unless matched in full.
    """
    evidence = {int(c.get('citation_id', i + 1)): c for i, c in enumerate(chunks)}
    claims = []
    for unit in re.split(r'\n+|(?<=[.!?])\s+(?=[A-Z])', answer):
        if not unit.strip() or re.fullmatch(r'[\s|:\-]+', unit):
            continue
        ids = sorted({int(x) for x in re.findall(r'\[(\d+)\]', unit)})
        text = re.sub(r'\[\d+\]', '', unit)
        text = re.sub(r'^\s*(?:[-*+]\s+|\d+\.\s+)', '', text).strip()
        if not text:
            continue
        normalized = _normalize(text).rstrip('.!?')
        matched = []
        for cid in ids:
            source = evidence.get(cid, {})
            source_text = source.get('parent_text') or source.get('child_text', '')
            sentences = re.split(r'\n+|(?<=[.!?])\s+', source_text)
            if any(normalized == _normalize(s).rstrip('.!?') for s in sentences):
                matched.append(cid)
        if not ids or any(cid not in evidence for cid in ids):
            status, reason = 'unsupported', 'Missing or invalid source citation.'
        elif matched:
            status, reason = 'supported', 'Exact source sentence match; semantic paraphrases are not evaluated.'
        else:
            status, reason = 'uncertain', 'Citation exists, but local checks cannot establish claim support.'
        claims.append({'text': text, 'citation_ids': ids, 'supporting_citation_ids': matched,
                       'status': status, 'reason': reason})
    return claims


def verify_generated_answer(answer, retrieved_chunks, eval_result):
    updated = dict(eval_result)
    for key in ('confidence', 'nli_verdict', 'nli_entailment_prob'):
        updated.pop(key, None)
    valid = {int(c.get('citation_id', i + 1)) for i, c in enumerate(retrieved_chunks)}
    cited = {int(x) for x in re.findall(r'\[(\d+)\]', answer)}
    updated.update(verified_citations=sorted(cited & valid), invalid_citations=sorted(cited - valid),
                   citation_verified=bool(cited) and cited <= valid)
    if not answer.strip() or 'i cannot verify this information in the provided document excerpts' in answer.casefold():
        updated.update(status='REFUSE', claim_support='not_applicable', claims=[],
                       badge='INSUFFICIENT EVIDENCE', reason='No supported answer was provided.')
        return updated
    claims = check_claim_support(answer, retrieved_chunks)
    supported = bool(claims) and all(c['status'] == 'supported' for c in claims)
    updated.update(claims=claims, claim_support='supported' if supported else 'needs_review',
                   verification_method='conservative_exact_sentence_match',
                   badge='EXTRACTIVE SUPPORT CHECKED' if supported else 'ANSWER NEEDS SOURCE REVIEW',
                   reason='Exact source sentences matched.' if supported else
                          'Some answer claims are unsupported or uncertain; review the cited evidence.')
    return updated
