"""Recognize short definition questions and locate explicit source definitions."""
import re
from functools import lru_cache


def definition_subject(query: str) -> str:
    match = re.fullmatch(
        r"\s*(?:what\s+(?:is|are)|define|(?:give\s+(?:me\s+)?(?:a|the)\s+)?definition\s+of)"
        r"\s+(?:(?:a|an|the)\s+)?([\w -]+?)\s*[?.!]?\s*",
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
def _definition_pattern(query: str):
    subject = definition_subject(query)
    if not subject:
        return None
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
    return re.compile(
        r'\b(?:(?:a|an|the)\s+)?' + name + r'\b(?:\s+\([\w -]+\))?'
        r'(?:\s+(?:(?:is|are)\s+(?:(?:defined|described)\s+as\s+)?'
        r'(?:(?:a|an|the|one|basic|fundamental|structural|functional)\b|[$€£]?\d)'
        r'|means?\b|refers?\s+to\b)'
        r'|\s*[,—]\s*(?:a|an|the)\s+)',
        re.IGNORECASE,
    )


def definition_excerpt(query: str, text: str) -> str:
    """Extract source wording, allowing headings and appositional definitions.

    Remove only PDF discretionary word-break characters. Never turn a modified
    subject ('parietal cell') into a definition of its generic noun ('cell').
    """
    pattern = _definition_pattern(query)
    if pattern is None:
        return ''
    text = text.replace('\x02', '').replace('\u00ad', '')
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', text):
        sentence = sentence.strip()
        for match in pattern.finditer(sentence):
            prefix = sentence[:match.start()]
            if not prefix.strip():
                return sentence
            # Native extraction frequently attaches an all-caps section heading
            # to the first explanatory sentence. Do not discard that evidence.
            if re.search(r'\b[A-Z][A-Z -]{3,}\s+$', prefix):
                return sentence[match.start():]
            # An appositive can occur inside a complete sentence, e.g. 'and the
            # cytoplasm, a complex aqueous gel'. Retain its full context.
            if re.search(r'(?:\band|[,;:])\s*$', prefix, re.IGNORECASE):
                return sentence
    return ""


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
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', text):
        if action.search(sentence):
            return sentence.strip()
    return ''
