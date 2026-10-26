"""Conservative property lookups from explicit source statements.

This is an extractive path, not a synonym dictionary or a semantic verifier.
Keep source wording and conditions; conflicting matches remain visible.
"""
import re

PROPERTIES = {
    'code', 'identifier', 'id', 'name', 'owner', 'period', 'interval', 'deadline',
    'limit', 'capacity', 'weight', 'frequency', 'rate', 'amount', 'price', 'cost',
    'count', 'version', 'status', 'email', 'phone', 'address', 'load', 'duration',
    'guarantee', 'percentage', 'date', 'time', 'number', 'threshold', 'temperature',
}

# Narrow, explicit paraphrases of generic properties. Full matching prevents
# dropping entity, date, or exception constraints from a longer question.
PROPERTY_PARAPHRASES = (
    (r'how long (?:must|should) (?:records|documents) be (?:kept|retained|stored)', 'retention period'),
    (r'(?:how much weight is (?:permitted|allowed)|what is the (?:maximum permitted weight|weight limit))', 'maximum load'),
    (r'how often (?:is inspection required|must inspections (?:occur|take place))', 'inspection interval'),
    (r'who is responsible for review', 'review owner'),
    (r'which code authorizes access', 'authorization code'),
)


def property_query(query):
    stripped = query.strip().rstrip('?.!').strip()
    for pattern, subject in PROPERTY_PARAPHRASES:
        if re.fullmatch(pattern, stripped, re.I):
            return f'What is the {subject}?'
    return query


def normalize_measurement_spacing(text):
    """Format glued OCR number/unit pairs without changing numbers or units."""
    return re.sub(r'(?<![\w.-])(\d+(?:\.\d+)?)(kg|mg|g|km|cm|mm|ms|ml|mL|kPa|MPa)\b', r'\1 \2', text)


def normalize_fact_spacing(text):
    """Repair numeric property spacing without guessing OCR letters or values.

    Only split a copula immediately after a known property, so identifiers such
    as ``axis20`` and ``IS20`` elsewhere in the sentence remain untouched.
    Original source excerpts are retained separately for citation review.
    """
    properties = '|'.join(sorted(PROPERTIES))
    text = re.sub(r'\b(' + properties + r')\s+(is|are)(?=[+-]?\d)',
                  r'\1 \2 ', text, flags=re.I)
    text = normalize_measurement_spacing(text)
    return re.sub(r'(?<![\w.-])(\d+(?:\.\d+)?)(seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b',
                  r'\1 \2', text, flags=re.I)


def fact_subject(query):
    query = property_query(query)
    query = re.sub(r'\s+(?:on|in|from)\s+(?:the\s+)?(?:pdf\s+)?page\s+\d+\s*[?.!]?$', '', query, flags=re.I)
    match = re.fullmatch(r'\s*(?:what|who)\s+(?:is|are)\s+(?:the\s+)?([\w -]+?)\s*[?.!]?\s*', query, re.I)
    if not match:
        return ''
    subject = match[1].strip()
    words = subject.casefold().split()
    if len(words) > 6 or not words or words[-1] not in PROPERTIES:
        return ''
    return subject


def fact_excerpts(query, text):
    subject = fact_subject(query)
    if not subject:
        return []
    name = r'\s+'.join(re.escape(word) for word in subject.split())
    # Exact noun phrase: "backup authorization code" must not answer a request
    # for "authorization code". An explicit capitalized article can start a
    # sentence after a PDF heading merged without punctuation.
    pattern = re.compile(r'(?<!\w)(?P<article>[Tt]he\s+)?' + name + r'\s+(?:is|are)(?:\s+\S|(?=[+-]?\d))', re.I)
    found = []
    for sentence in re.split(r'(?<=[.!?])\s+', text):
        for match in pattern.finditer(sentence):
            prefix = sentence[:match.start()].strip()
            starts = not prefix or bool(re.fullmatch(r'[\d.)\s]+', prefix))
            # A capitalized article can follow a merged heading. Preserve the
            # ENTIRE sentence in that case, including any attribution/condition;
            # never guess where a heading ends and delete its prefix.
            merged = bool(prefix) and match.group('article') == 'The '
            if not (starts or merged):
                continue
            excerpt = sentence.strip() if merged else sentence[match.start():].strip()
            if excerpt not in found:
                found.append(excerpt)
    return found


def fact_answer(query, chunks):
    matches = []
    for chunk in chunks:
        for excerpt in fact_excerpts(query, chunk.get('parent_text', '')):
            if excerpt not in [text for text, _ in matches]:
                matches.append((excerpt, chunk.get('citation_id', 1)))
    if not matches:
        return None
    if len(matches) == 1:
        text, cid = matches[0]
        return f'{normalize_fact_spacing(text)} [{cid}]'
    return ('The sources contain multiple statements; check their scope and conditions:\n\n' +
            '\n\n'.join(f'{normalize_fact_spacing(text)} [{cid}]' for text, cid in matches))
