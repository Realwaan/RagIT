"""Select complete source units without inventing an offline paraphrase."""
import re

from app.retriever import STOP_WORDS, tokenize_words


def select_source_units(query, chunks):
    # Restrict this selector to explicit extractive intents. General numeric,
    # visual and explanatory questions keep their existing answer paths.
    if not re.search(r'\b(example|operations|prepared|built|build)\b|\bwhat does .+ mean\b', query, re.I):
        return None
    ignored = {'page', 'shown', 'which', 'what', 'should', 'would', 'could', 'please'}
    terms = {w for w in tokenize_words(query) if w not in STOP_WORDS | ignored and not w.isdigit()}
    wants_example = bool(re.search(r'\bexample\b', query, re.I))
    wants_build = bool(re.search(r'\b(built|build)\b', query, re.I))
    wants_meaning = bool(re.search(r'\bwhat does .+ mean\b', query, re.I))
    candidates = []
    for index, chunk in enumerate(chunks):
        source = chunk.get('parent_text', '')
        source_terms = set(tokenize_words(source))
        # Bullets in extracted slides sometimes arrive as replacement characters.
        units = re.split(r'[\n\r\u2022\ufffd]+|(?<=[a-z)])\.\s+(?=[A-Z])', source)
        for position, unit in enumerate(units):
            unit = unit.strip()
            words = set(tokenize_words(unit))
            overlap = len(words & terms)
            example = wants_example and bool(re.match(r'Example\s*:', unit, re.I)) and bool(source_terms & (terms - {'example', 'illustrates'}))
            construction = wants_build and overlap >= 1 and bool(re.search(r'\b(make|build|construct)\b', unit, re.I))
            meaning = wants_meaning and overlap >= 1 and bool(re.search(r'\bmeans\b', unit, re.I))
            if len(unit.split()) < 4 or (overlap < 2 and not (example or construction or meaning)):
                continue
            # Prefer substantive sentences over recurring title/footer text.
            substantive = bool(re.search(r'\b(is|are|means|have|has|such as|include|operations|make|prepared by)\b', unit, re.I))
            if not substantive and not example:
                continue
            score = overlap + (4 if example or construction or meaning else 0)
            candidates.append((score, -index, -position, unit, chunk.get('citation_id', index + 1)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    best = candidates[0]
    return f'{best[3]} [{best[4]}]'
