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


# =====================================================================
# Conversational Query Condensation (Harvard HBS RAG Pattern)
# =====================================================================

_ANAPHORIC_PRONOUNS = re.compile(
    r"\b(it|its|they|them|their|this|that|these|those|he|she|him|her)\b",
    re.IGNORECASE
)
_TRANSITION_STARTERS = re.compile(
    r"^(and\b|also\b|what about\b|how about\b|why\b|where\b|which one\b|what else\b|what if\b|same\b|other\b)",
    re.IGNORECASE
)
_VERB_FOLLOWUPS = re.compile(
    r"^(does|can|is|did|will|would|could|should|are|was|were)\s+(it|that|this|they|there)\b",
    re.IGNORECASE
)


def is_context_dependent_query(query: str) -> bool:
    """Detect whether a query refers to prior conversation context."""
    q = query.strip()
    if not q:
        return False
    return bool(
        _ANAPHORIC_PRONOUNS.search(q)
        or _TRANSITION_STARTERS.search(q)
        or _VERB_FOLLOWUPS.search(q)
    )


def _call_fast_llm_for_condensation(prompt: str, timeout: float = 4.0) -> str:
    """Invokes the fast primary (Groq) or fallback (Gemini) endpoint for query reformulation."""
    from app.llm import has_valid_primary_key, get_primary_client, has_valid_fallback_key, get_fallback_client
    import app.config as cfg

    if has_valid_primary_key():
        try:
            client = get_primary_client(timeout=timeout)
            resp = client.chat.completions.create(
                model=cfg.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a concise search query reformulation assistant. Output ONLY the standalone question."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=60,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception:
            pass

    if has_valid_fallback_key():
        try:
            client = get_fallback_client(timeout=timeout)
            resp = client.chat.completions.create(
                model=cfg.FALLBACK_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a concise search query reformulation assistant. Output ONLY the standalone question."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=60,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception:
            pass

    return ""


def condense_conversational_query(
    query: str,
    history: list[dict] | None = None,
    previous_question: str = "",
    timeout: float = 4.0,
) -> str:
    """Reformulates multi-turn conversational follow-ups into standalone retrieval queries.

    Follows the Harvard HBS conversational RAG pattern:
    - If the query is already standalone, keeps it unchanged (zero latency overhead).
    - If it refers back to conversation context, synthesizes a self-contained search query.
    - Gracefully falls back to deterministic heuristic concatenation when offline or on failure.
    """
    clean_query = query.strip()
    if not clean_query:
        return ""

    has_history = bool(history and any(isinstance(m, dict) and m.get("content") for m in history))
    has_previous = bool(previous_question and previous_question.strip())

    if not has_history and not has_previous:
        return clean_query

    # Fast path: standalone queries with no anaphora or transition words do not need condensation
    if not is_context_dependent_query(clean_query):
        return clean_query

    # Format recent history (up to last 4 turns)
    history_turns = []
    if has_history:
        for m in (history or [])[-4:]:
            role = str(m.get("role", "user")).capitalize()
            content = str(m.get("content", "")).strip()
            if role.lower() == "assistant" and len(content) > 150:
                content = content.split("\n")[0][:150] + "..."
            if content:
                history_turns.append(f"{role}: {content}")
    elif has_previous:
        history_turns.append(f"User: {previous_question.strip()}")

    if not history_turns:
        return clean_query

    history_text = "\n".join(history_turns)
    prompt = (
        f"Conversation History:\n{history_text}\n\n"
        f"Follow-up Question: {clean_query}\n"
        "Rephrase this follow-up question as a single, self-contained search query for document retrieval. "
        "Do NOT answer it. Return ONLY the standalone question:"
    )

    llm_condensed = _call_fast_llm_for_condensation(prompt, timeout=timeout)
    if llm_condensed:
        cleaned = re.sub(
            r"^(Standalone Query|Rephrased Question|Search Query):\s*",
            "",
            llm_condensed,
            flags=re.I
        ).strip("\"' \n")
        if cleaned and len(cleaned) > 3:
            return cleaned

    # Deterministic offline fallback (preserving previous RagIT behavior)
    last_context = previous_question.strip()
    if not last_context and has_history:
        for m in reversed(history or []):
            if m.get("role") == "user" and m.get("content"):
                last_context = str(m["content"]).strip()
                break

    if last_context:
        if re.match(r"(?i)^(and\b|what about\b|how about\b|why\b|does (it|that)\b|can (it|that)\b)", clean_query):
            return f"{last_context}\n{clean_query}"
        return f"{last_context} - {clean_query}"

    return clean_query
