"""Recognize short definition questions and locate explicit source definitions."""
import re
from functools import lru_cache


def definition_subject(query: str) -> str:
    # Page qualifiers constrain retrieval, not the subject being defined.
    query = re.sub(r'\s+(?:on|in|from)\s+(?:the\s+)?(?:pdf\s+)?pages?\s+\d+(?:\s*[-–]\s*\d+)?(?=\s*[?.!]?\s*$)', '', query, flags=re.I)
    match = re.fullmatch(
        r"\s*(?:what\s+(?:is|are)|define|(?:give\s+(?:me\s+)?(?:a|the)\s+)?definition\s+of)"
        r"\s+(?:(?:a|an|the)\s+)?([\w -]+?)(?:\s+\([A-Za-z]{2,12}\))?\s*[?.!]?\s*",
        query, re.IGNORECASE,
    )
    if not match:
        return ""
    subject = match[1].strip()
    words = subject.lower().split()
    if len(words) > 6 or set(words) & {"if", "when", "where", "why", "which", "that", "in", "on", "for"}:
        return ""
    return subject


@lru_cache(maxsize=128)
def _subject_name(subject: str):
    words = subject.split()
    last = words[-1]
    variants = {last}
    if last.endswith('ies'):
        variants.add(last[:-3] + 'y')
    elif last.endswith('s') and not last.endswith(('ss', 'us', 'is')):
        variants.add(last[:-1])
    elif last.endswith('y'):
        variants.add(last[:-1] + 'ies')
    else:
        variants.add(last + 's')
    # Articles inside relational questions may be omitted by the user:
    # 'components of protoplasm' also matches 'components of the protoplasm'.
    name = r'\s+'.join(re.escape(word) for word in words[:-1])
    if name:
        name += r'\s+'
    name += '(?:' + '|'.join(re.escape(word) for word in sorted(variants)) + ')'
    name = name.replace(r'of\s+', r'of\s+(?:(?:a|an|the)\s+)?')
    return name


@lru_cache(maxsize=128)
def _definition_pattern(subject: str):
    name = _subject_name(subject)
    # Nominal predicates also occur without an article ("are mathematical
    # abstractions"). Reject location/state descriptions such as "is at the
    # right", rather than requiring a short domain-specific adjective list.
    article_or_value = r'(?:(?:a|an|the|one|basic|fundamental|structural|functional)\b|[$€£]?\d)'
    plural_nominal = (
        r'(?!(?:at|in|on|near|under|above|below|between|behind|not|never|shown|located|visible)\b)'
        r'(?:(?!\b(?:with|from|of|to|by|as|than)\b)[\w-]+\s+){0,4}[\w-]+(?:s|tion|ment|ity|ance|ence)\b'
    )
    return re.compile(
        r'\b(?:(?:a|an|the)\s+)?' + name + r'\b(?:\s+\([\w -]+\))?'
        r'(?:\s+(?:(?:is|are)\s+(?:(?:defined|described)\s+as\s+)?' + article_or_value +
        r'|are\s+' + plural_nominal +
        r'|means?\b|refers?\s+to\b|represents?\b|encompasses?\b|comprises?\b|'
        r'consists?\s+of\b|involves?\b|denotes?\b)'
        r'|\s*[,—]\s*(?:a|an|the)\s+'
        r'|\s*[:–-]\s*(?:' + article_or_value + '|' + plural_nominal + '))',
        re.IGNORECASE,
    )


def _source_sentences(text: str):
    """Keep bullet boundaries while joining PDF line wraps within sentences."""
    text = text.replace('\x02', '').replace('\u00ad', '')
    text = re.sub(r'[•●▪◦‣\uf0b7]', '\n\n', text)
    text = re.sub(r'(?m)^\s*[-*+]\s+', '\n\n', text)
    for block in re.split(r'\n\s*\n', text):
        block = re.sub(r'\s+', ' ', block).strip()
        for sentence in re.split(r'(?<=[.!?])\s+', block):
            if sentence:
                yield sentence


def _definition_subjects(subject: str, text: str):
    """Resolve an acronym only when its expansion is explicit in this source."""
    yield subject
    if not re.fullmatch(r'[A-Za-z]{2,12}', subject):
        return
    acronym = subject.rstrip('s') if subject.endswith('s') else subject
    if not re.search(r'\(' + re.escape(acronym) + r's?\)', text, re.I):
        return
    for match in re.finditer(r'((?:[A-Za-z][\w-]*\s+){1,8})\(' + re.escape(acronym) + r's?\)', text, re.I):
        words = match[1].split()
        for start in range(len(words) - 1):
            expanded = words[start:]
            if ''.join(word[0] for word in expanded).casefold() == acronym.casefold():
                yield ' '.join(expanded)
                break


def _subject_heading(prefix: str, subject: str) -> bool:
    """Recognize a title merged with its explanation, not a noun modifier."""
    words = re.findall(r'[A-Za-z]+', prefix)
    if not words or words[0].lower() in {'a', 'an'}:
        return False
    connectors = {'and', 'of', 'the', 'in', 'to', 'for', 'vs'}
    if any(not word[0].isupper() and word not in connectors for word in words):
        return False
    def stem(word):
        word = word.casefold()
        if word.endswith('ies'):
            return word[:-3] + 'y'
        return word[:-1] if word.endswith('s') and not word.endswith(('ss', 'us', 'is')) else word
    terms = {stem(word) for word in re.findall(r'[A-Za-z]+', subject) if word.casefold() not in connectors}
    return bool(terms) and terms.issubset({stem(word) for word in words})


def definition_excerpts(query: str, text: str) -> list[str]:
    """Return explicit definitions in source order, without inventing wording."""
    subject = definition_subject(query)
    if not subject:
        return []
    normalized = text.replace('\x02', '').replace('\u00ad', '')
    patterns = [_definition_pattern(name) for name in _definition_subjects(subject, normalized)]
    found = []
    for sentence in _source_sentences(normalized):
        for pattern in patterns:
            for match in pattern.finditer(sentence):
                prefix = sentence[:match.start()]
                # Bullet/list formatting and repeated headings are not noun
                # modifiers. "A parietal cell" is still a different subject.
                starts_here = not prefix.strip() or bool(re.fullmatch(r'(?:\d+[.)]?\s*)+', prefix))
                heading = sentence[match.start()].isupper() and (
                    re.search(r'\b[A-Z][A-Z -]{3,}\s+$', prefix) or _subject_heading(prefix, subject)
                )
                repeated_heading = re.fullmatch(_subject_name(subject) + r'\s*[:–—-]?\s*', prefix, re.I)
                appositive = (re.search(r'\band\s*$', prefix, re.I) or
                              (re.search(r'[,;:]\s*$', prefix) and re.search(r'[,—]', match[0])))
                definition_label = re.search(r'\b(?:definition|meaning|distinction)\s*:\s*$', prefix, re.I)
                if starts_here or heading or repeated_heading or definition_label:
                    excerpt = sentence[match.start():]
                elif appositive:
                    excerpt = sentence
                else:
                    continue
                label = re.match(r'(?:(?:a|an|the)\s+)?' + _subject_name(subject) + r'\s*[:–-]\s*(.*)', excerpt, re.I)
                if label and len(re.findall(r'\w+', label[1])) < 3 and not re.match(r'[$€£]?\d', label[1]):
                    continue
                # A label or a title alone cannot establish a definition.
                if not re.search(r'\w', sentence[match.end():]) and re.search(
                    r'\b(?:a|an|the|one|basic|fundamental|structural|functional|means?|to)\s*$', match[0], re.I
                ):
                    continue
                if excerpt not in found:
                    found.append(excerpt)
    return found


def definition_excerpt(query: str, text: str) -> str:
    """Extract source wording, allowing headings and appositional definitions.

    Remove only PDF discretionary word-break characters. Never turn a modified
    subject ('parietal cell') into a definition of its generic noun ('cell').
    """
    return next(iter(definition_excerpts(query, text)), '')


def function_subject(query: str) -> str:
    match = re.fullmatch(
        r'\s*what\s+(?:is|are)\s+(?:the\s+)?(?:functions?|roles?|purpose)\s+of\s+'
        r'(?:the\s+)?([\w -]+?)\s*[?.!]?\s*', query, re.IGNORECASE,
    )
    return match[1].strip() if match else ''


def function_excerpt(query: str, text: str) -> str:
    """Extract an explicit subject/action sentence, not just a function heading."""
    subject = function_subject(query)
    if not subject:
        return ''
    text = text.replace('\x02', '').replace('\u00ad', '')
    action = re.compile(
        r'\b' + re.escape(subject) + r'\b(?:\s+\([^)]{1,30}\))?'
        r'(?:,?\s+which|\s+that)?\s+'
        r'(?:provides?|produces?|supplies|supply|generates?|transports?|'
        r'synthesi[sz]es?|secretes?|absorbs?|protects?|regulates?|stores?|'
        r'filters?|supports?|enables?|converts?|maintains?)\b',
        re.IGNORECASE,
    )
    for sentence in _source_sentences(text):
        if action.search(sentence):
            return sentence.strip()
    return ''
