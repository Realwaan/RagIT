"""Conservative, source-preserving lookup of a named row and column."""
import re


def table_answer(query: str, text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith('|')]
    if len(lines) < 3 or not re.fullmatch(r'[| :\-]+', lines[1]):
        return ''
    def cells(line):
        return [cell.strip().replace('\\|', '|') for cell in re.split(r'(?<!\\)\|', line.strip('|'))]
    def words(value):
        return set(re.findall(r'\w+', value.casefold())) - {'the', 'a', 'an', 'of', 'in', 'for', 'and'}
    terms = words(query)
    matches = []
    headers = []
    group = ''
    for line_index, line in enumerate(lines):
        if line_index + 1 < len(lines) and re.fullmatch(r'[| :\-]+', lines[line_index + 1]):
            headers = cells(line)
            group = ''
            continue
        if not headers or re.fullmatch(r'[| :\-]+', line):
            continue
        row = cells(line)
        if len(row) != len(headers):
            continue
        if re.fullmatch(r'(?:FY\s*)?\d{4}', row[0]) and not any(row[1:]):
            group = row[0]
            continue
        label_terms = words(row[0]) | words(group)
        if not label_terms or not label_terms.issubset(terms):
            continue
        for index in range(1, len(headers)):
            header_terms = words(headers[index])
            shared = header_terms & terms
            if not shared or not row[index] or '\ufffd' in row[index]:
                continue
            # A year alone does not identify the requested metric: asking for
            # expenses in 2025 must not return a Revenue 2025 cell.
            metric_terms = {term for term in header_terms if not term.isdigit()}
            if metric_terms and not metric_terms.intersection(terms):
                continue
            # Never confuse 2024 and 2025 merely because both say 'Revenue'.
            numbers = {term for term in header_terms if term.isdigit()}
            if numbers and any(term.isdigit() for term in terms) and not numbers.issubset(terms):
                continue
            label = f'{group} / {row[0]}' if group else row[0]
            matches.append((len(shared), label, headers[index], row[index]))
    if not matches:
        return ''
    best_score = max(match[0] for match in matches)
    best = {match[1:] for match in matches if match[0] == best_score}
    if len(best) != 1:
        return ''
    label, header, value = best.pop()
    return f'{label} — {header}: {value}.'
