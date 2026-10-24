"""Recognize short definition questions and locate explicit source definitions."""
import re


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


def definition_excerpt(query: str, text: str) -> str:
    """Return an exact sentence, never synthesize a definition from a mere mention.

    The subject must begin the sentence: 'a parietal cell' must not answer 'cell'.
    Accept simple singular/plural variants without changing the source wording.
    """
    subject = definition_subject(query)
    if not subject:
        return ""
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
    name = r'\s+'.join(re.escape(word) for word in words[:-1])
    if name:
        name += r'\s+'
    name += '(?:' + '|'.join(re.escape(word) for word in sorted(variants)) + ')'
    start = re.compile(
        r'^(?:(?:a|an|the)\s+)?' + name + r'\s+'
        r'(?:(?:is|are)\s+(?:(?:defined|described)\s+as\s+)?'
        r'(?:a|an|the|basic|fundamental|structural|functional)\b|means?\b|refers?\s+to\b)',
        re.IGNORECASE,
    )
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', text):
        sentence = sentence.strip()
        if start.search(sentence) and len(sentence.split()) >= len(words) + 4:
            return sentence
    return ""
