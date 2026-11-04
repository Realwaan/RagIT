"""
Analytical Math Engine for RagIT.

Extracts structured tabular data from Markdown tables, interprets analytical query
intents (sum, average, difference, percentage growth, profit margin, min/max, count),
and executes deterministic, zero-hallucination arithmetic calculations with step-by-step
arithmetic proofs and KaTeX-compatible LaTeX formulas.
"""
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class CellValue:
    raw: str
    num: float              # Scaled numeric value (e.g. $12.5M -> 12,500,000.0)
    raw_num: float          # Unscaled numeric value (e.g. 12.5)
    cur: Optional[str]      # Currency symbol or code (e.g. '$', '€', 'USD')
    suffix: Optional[str]   # Scale suffix or unit (e.g. 'M', 'K', 'B', '%')
    is_neg: bool
    is_percent: bool


@dataclass
class Operand:
    label: str              # Label identifying the source item/column/row
    cell: CellValue


@dataclass
class AnalyticalMathResult:
    operation: str
    summary: str
    proof: str
    latex: str
    formatted_answer: str
    result_value: float


def parse_typed_cell(text: str) -> Optional[CellValue]:
    """Parses currency, scale multipliers (K/M/B/T), accounting negatives, and percentages."""
    clean = text.strip()
    if not clean or '\ufffd' in clean:
        return None
        
    is_neg = False
    # Accounting bracket notation: (100) or ($45.5M)
    if clean.startswith('(') and clean.endswith(')'):
        is_neg = True
        clean = clean[1:-1].strip()
    elif clean.startswith('-'):
        is_neg = True
        clean = clean[1:].strip()
    
    # Matches optional currency symbol/code, numeric value with commas/decimals, and scale suffix
    match = re.match(
        r'^([$€£¥₹]|USD|EUR|GBP|CHF)?\s*([0-9,]+(?:\.[0-9]+)?)\s*([KkMmBbTt]|%|thousand|million|billion|mn|bn)?$', 
        clean, re.I
    )
    if not match:
        return None
        
    cur, num_str, suffix = match.groups()
    try:
        raw_num = float(num_str.replace(',', ''))
    except ValueError:
        return None
        
    mult = 1.0
    is_percent = False
    if suffix:
        s = suffix.lower()
        if s == '%':
            is_percent = True
        elif s in ('k', 'thousand'):
            mult = 1e3
        elif s in ('m', 'million', 'mn'):
            mult = 1e6
        elif s in ('b', 'billion', 'bn'):
            mult = 1e9
        elif s in ('t', 'trillion'):
            mult = 1e12

    val = raw_num * mult
    if is_neg:
        val = -val
        raw_num = -raw_num

    return CellValue(
        raw=text.strip(),
        num=val,
        raw_num=raw_num,
        cur=cur,
        suffix=suffix,
        is_neg=is_neg,
        is_percent=is_percent
    )


def extract_table_blocks(text: str) -> List[str]:
    """Isolates contiguous Markdown table blocks from mixed text."""
    blocks = []
    current_block = []
    for line in text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith('|'):
            current_block.append(trimmed)
        else:
            if len(current_block) >= 3 and re.fullmatch(r'[| :\-]+', current_block[1]):
                blocks.append("\n".join(current_block))
            current_block = []
    if len(current_block) >= 3 and re.fullmatch(r'[| :\-]+', current_block[1]):
        blocks.append("\n".join(current_block))
    return blocks


def parse_markdown_table_to_matrix(text: str) -> Optional[Dict[str, Any]]:
    """Parses a single Markdown table into structured rows, headers, and typed cells."""
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith('|')]
    if len(lines) < 3 or not re.fullmatch(r'[| :\-]+', lines[1]):
        return None
    
    def split_cells(line: str) -> List[str]:
        return [c.strip().replace(r'\|', '|') for c in re.split(r'(?<!\\)\|', line.strip('|'))]
    
    headers = split_cells(lines[0])
    data_rows = []
    group = ""
    
    for line in lines[2:]:
        row = split_cells(line)
        if len(row) != len(headers):
            continue
        # Section header row like: | 2024 | | | or | Direct Costs | |
        if row[0] and not any(row[1:]):
            group = row[0]
            continue
        row_label = f"{group} / {row[0]}" if group else row[0]
        cells_dict = {}
        for c_idx, cell_str in enumerate(row[1:], start=1):
            col_name = headers[c_idx]
            val = parse_typed_cell(cell_str)
            cells_dict[col_name] = {
                "raw": cell_str,
                "parsed": val
            }
        data_rows.append({
            "label": row_label,
            "group": group,
            "item": row[0],
            "raw_row": row,
            "cells": cells_dict
        })
        
    return {
        "headers": headers,
        "col_headers": headers[1:],
        "rows": data_rows
    }


def normalize_stem(w: str) -> str:
    """Basic plural/singular normalization."""
    w = w.casefold()
    if w.endswith('ies') and len(w) > 4:
        return w[:-3] + 'y'
    if w.endswith('es') and len(w) > 3:
        return w[:-2]
    if w.endswith('s') and not w.endswith(('ss', 'us', 'is')) and len(w) > 2:
        return w[:-1]
    return w


def query_words(s: str) -> set:
    """Extracts significant query words, stripping stopwords and adding stems."""
    raw = set(re.findall(r'\w+', s.casefold())) - {
        'the', 'a', 'an', 'of', 'in', 'for', 'and', 'to', 'from',
        'is', 'was', 'were', 'what', 'which', 'who', 'how', 'calculate',
        'give', 'find', 'show', 'tell', 'me', 'with', 'by', 'on', 'at'
    }
    result = set(raw)
    for w in raw:
        stemmed = normalize_stem(w)
        if stemmed:
            result.add(stemmed)
    return result


def detect_math_intent(query: str) -> Optional[str]:
    """Recognizes mathematical and analytical operations requested in the query."""
    q = query.casefold()
    if re.search(r'\b(percentage\s+growth|percent\s+growth|percentage\s+change|percent\s+change|growth\s+rate|percentage\s+increase|percentage\s+decrease|rate\s+of\s+growth)\b', q) or re.search(r'\bgrow(?:th)?\s+from\b', q):
        return 'PERCENTAGE_CHANGE'
    if re.search(r'\b(profit\s+margin|operating\s+margin|gross\s+margin|margin)\b', q):
        return 'MARGIN'
    if re.search(r'\b(ratio\s+of|ratio\s+between|proportion\s+of)\b', q):
        return 'RATIO'
    if re.search(r'\b(difference\s+(?:between|of|in)|delta|variance|gap\s+between|how\s+much\s+(?:more|higher|lower|greater|less))\b', q):
        return 'DIFFERENCE'
    if re.search(r'\b(average|mean|avg)\b', q):
        return 'AVERAGE'
    if re.search(r'\b(maximum|max|highest|peak|greatest|largest|top)\b', q):
        return 'MAX'
    if re.search(r'\b(minimum|min|lowest|least|bottom|smallest)\b', q):
        return 'MIN'
    if re.search(r'\b(total\s+count|count\s+of|number\s+of|how\s+many|count)\b', q):
        return 'COUNT'
    if re.search(r'\b(total|sum|combined|aggregate|altogether|overall|add\s+up)\b', q):
        return 'SUM'
    return None


def has_analytical_math_intent(query: str) -> bool:
    """Quick boolean check if query exhibits analytical calculation intent."""
    return detect_math_intent(query) is not None


def format_number_output(
    val: float,
    cur: Optional[str] = None,
    suffix: Optional[str] = None,
    is_percent: bool = False
) -> str:
    """Formats numeric values preserving source currency, scale suffixes (M/K/B), or %."""
    sign = "-" if val < 0 else ""
    abs_val = abs(val)
    prefix_str = cur or ""
    
    if is_percent:
        return f"{val:+.2f}%" if val != 0 else "0.00%"
        
    if suffix in ('M', 'm', 'million', 'mn'):
        if abs_val >= 1e6:
            s_val = abs_val / 1e6
            formatted = f"{s_val:,.2f}".rstrip('0').rstrip('.')
            return f"{sign}{prefix_str}{formatted}M"
    elif suffix in ('B', 'b', 'billion', 'bn'):
        if abs_val >= 1e9:
            s_val = abs_val / 1e9
            formatted = f"{s_val:,.2f}".rstrip('0').rstrip('.')
            return f"{sign}{prefix_str}{formatted}B"
    elif suffix in ('K', 'k', 'thousand'):
        if abs_val >= 1e3:
            s_val = abs_val / 1e3
            formatted = f"{s_val:,.2f}".rstrip('0').rstrip('.')
            return f"{sign}{prefix_str}{formatted}K"
            
    if abs_val == int(abs_val):
        formatted = f"{int(abs_val):,}"
    else:
        formatted = f"{abs_val:,.2f}".rstrip('0').rstrip('.')
    return f"{sign}{prefix_str}{formatted}"


def execute_analytical_math(query: str, table_text: str) -> Optional[AnalyticalMathResult]:
    """
    Evaluates an analytical mathematical operation over a Markdown table string.
    Returns None if the query is not a calculation or if operands cannot be safely resolved.
    """
    parsed = parse_markdown_table_to_matrix(table_text)
    if not parsed:
        return None
        
    op = detect_math_intent(query)
    if not op:
        return None
        
    q_words = query_words(query)
    
    # 1. Match rows: check complete label, item name, or section group
    matched_rows = []
    for r in parsed["rows"]:
        lbl_terms = query_words(r["label"])
        item_terms = query_words(r["item"])
        grp_terms = query_words(r["group"]) if r["group"] else set()
        
        # Check if terms are contained in query words
        if (lbl_terms and lbl_terms.issubset(q_words)) or \
           (item_terms and item_terms.issubset(q_words)) or \
           (grp_terms and grp_terms.issubset(q_words)):
            matched_rows.append(r)
            
    # 2. Match columns with metric protection (prevent Year 2024 matching unrelated metrics)
    matched_cols = []
    for col in parsed["col_headers"]:
        c_terms = query_words(col)
        shared = c_terms & q_words
        if not shared:
            continue
        metric_terms = {t for t in c_terms if not t.isdigit()}
        if metric_terms and not metric_terms.intersection(q_words):
            continue
        col_numbers = {t for t in c_terms if t.isdigit()}
        query_numbers = {t for t in q_words if t.isdigit()}
        if col_numbers and query_numbers and not col_numbers.issubset(query_numbers):
            continue
        matched_cols.append(col)

    # Fallback 1: user asked across all rows ("across all regions", "overall", or no specific row mentioned)
    if not matched_rows:
        if matched_cols:
            matched_rows = [r for r in parsed["rows"] if any(r["cells"].get(c, {}).get("parsed") for c in matched_cols)]
            
    # Fallback 2: row was specified (e.g. Orion), and query mentions metrics/numbers or user wants all matching cols
    if matched_rows and not matched_cols:
        for col in parsed["col_headers"]:
            c_terms = query_words(col)
            if c_terms & q_words:
                matched_cols.append(col)
        # If table only has 1 data column (e.g. Metric | Cost), that's our column!
        if not matched_cols and len(parsed["col_headers"]) == 1:
            matched_cols = [parsed["col_headers"][0]]
        elif not matched_cols and len(matched_rows) == 1:
            r = matched_rows[0]
            matched_cols = [c for c in parsed["col_headers"] if r["cells"].get(c, {}).get("parsed")]

    if not matched_rows or not matched_cols:
        return None

    # Handle operands
    operands: List[Operand] = []
    entity_name = ""
    
    if len(matched_rows) == 1 and len(matched_cols) > 1:
        r = matched_rows[0]
        for col in matched_cols:
            cell_data = r["cells"].get(col)
            if cell_data and cell_data["parsed"]:
                operands.append(Operand(label=f"{col}", cell=cell_data["parsed"]))
        entity_name = f"{r['label']}"
    elif len(matched_rows) > 1 and len(matched_cols) == 1:
        col = matched_cols[0]
        for r in matched_rows:
            cell_data = r["cells"].get(col)
            if cell_data and cell_data["parsed"]:
                operands.append(Operand(label=f"{r['label']}", cell=cell_data["parsed"]))
        entity_name = f"{matched_rows[0].get('group') or col}"
    elif len(matched_rows) == 1 and len(matched_cols) == 1:
        if op == 'COUNT':
            operands.append(Operand(label=matched_rows[0]["label"], cell=matched_rows[0]["cells"][matched_cols[0]]["parsed"]))
            entity_name = matched_cols[0]
        elif op in ('MARGIN', 'RATIO'):
            pass  # Handled below
        else:
            return None
            
    if op in ('MARGIN', 'RATIO') and (not operands or len(operands) < 2):
        r = matched_rows[0] if matched_rows else parsed["rows"][0]
        num_cell = None
        den_cell = None
        for col in parsed["col_headers"]:
            cw = query_words(col)
            if cw & {'profit', 'income', 'net', 'operating', 'gross'}:
                num_cell = (col, r["cells"][col]["parsed"])
            elif cw & {'revenue', 'sales', 'turnover'}:
                den_cell = (col, r["cells"][col]["parsed"])
        if num_cell and den_cell and num_cell[1] and den_cell[1]:
            operands = [
                Operand(label=num_cell[0], cell=num_cell[1]),
                Operand(label=den_cell[0], cell=den_cell[1])
            ]
            entity_name = r["label"]

    if not operands:
        return None

    # For difference or percentage change, discriminate operand ordering
    if op in ('DIFFERENCE', 'PERCENTAGE_CHANGE') and len(operands) >= 2:
        op1_label = operands[0].label
        op2_label = operands[1].label
        d1 = query_words(op1_label) - query_words(op2_label)
        d2 = query_words(op2_label) - query_words(op1_label)
        q_lower = query.casefold()
        pos1 = min((q_lower.find(w) for w in d1 if q_lower.find(w) != -1), default=9999)
        pos2 = min((q_lower.find(w) for w in d2 if q_lower.find(w) != -1), default=9999)
        
        # If op2 appears earlier in query, order it first (e.g. difference between 2025 and 2024)
        if pos2 < pos1:
            operands[0], operands[1] = operands[1], operands[0]

    cur = next((opnd.cell.cur for opnd in operands if opnd.cell.cur), None)
    suffix = next((opnd.cell.suffix for opnd in operands if opnd.cell.suffix), None)

    # 1. SUM
    if op == 'SUM':
        total = sum(opnd.cell.num for opnd in operands)
        res_str = format_number_output(total, cur=cur, suffix=suffix)
        proof_parts = [f"{opnd.cell.raw} ({opnd.label})" for opnd in operands]
        proof = f"{' + '.join(proof_parts)} = {res_str}"
        summary = f"Total {entity_name} is {res_str}."
        latex = f"$$\\text{{Total}} = {' + '.join(opnd.cell.raw.replace('$', '\\$') for opnd in operands)} = {res_str.replace('$', '\\$')}$$"
        return AnalyticalMathResult(
            operation='SUM',
            summary=summary,
            proof=proof,
            latex=latex,
            formatted_answer=f"{summary}\n\n**Arithmetic Proof:** {proof}\n\n{latex}",
            result_value=total
        )

    # 2. AVERAGE
    elif op == 'AVERAGE':
        n = len(operands)
        total = sum(opnd.cell.num for opnd in operands)
        avg = total / n
        res_str = format_number_output(avg, cur=cur, suffix=suffix)
        proof_parts = [f"{opnd.cell.raw} ({opnd.label})" for opnd in operands]
        proof = f"({' + '.join(proof_parts)}) / {n} = {res_str}"
        summary = f"Average {entity_name} across {n} items is {res_str}."
        latex = f"$$\\text{{Average}} = \\frac{{{' + '.join(opnd.cell.raw.replace('$', '\\$') for opnd in operands)}}}{{{n}}} = {res_str.replace('$', '\\$')}$$"
        return AnalyticalMathResult(
            operation='AVERAGE',
            summary=summary,
            proof=proof,
            latex=latex,
            formatted_answer=f"{summary}\n\n**Arithmetic Proof:** {proof}\n\n{latex}",
            result_value=avg
        )

    # 3. MAX
    elif op == 'MAX':
        best = max(operands, key=lambda x: x.cell.num)
        res_str = format_number_output(best.cell.num, cur=cur, suffix=suffix)
        summary = f"Highest {entity_name} is {best.label} with {res_str}."
        proof = f"Max of [{', '.join(f'{opnd.label}: {opnd.cell.raw}' for opnd in operands)}] = {best.label} ({res_str})"
        latex = f"$$\\max = {res_str.replace('$', '\\$')} \\quad (\\text{{{best.label}}})$$"
        return AnalyticalMathResult(
            operation='MAX',
            summary=summary,
            proof=proof,
            latex=latex,
            formatted_answer=f"{summary}\n\n**Arithmetic Proof:** {proof}\n\n{latex}",
            result_value=best.cell.num
        )

    # 4. MIN
    elif op == 'MIN':
        best = min(operands, key=lambda x: x.cell.num)
        res_str = format_number_output(best.cell.num, cur=cur, suffix=suffix)
        summary = f"Lowest {entity_name} is {best.label} with {res_str}."
        proof = f"Min of [{', '.join(f'{opnd.label}: {opnd.cell.raw}' for opnd in operands)}] = {best.label} ({res_str})"
        latex = f"$$\\min = {res_str.replace('$', '\\$')} \\quad (\\text{{{best.label}}})$$"
        return AnalyticalMathResult(
            operation='MIN',
            summary=summary,
            proof=proof,
            latex=latex,
            formatted_answer=f"{summary}\n\n**Arithmetic Proof:** {proof}\n\n{latex}",
            result_value=best.cell.num
        )

    # 5. COUNT
    elif op == 'COUNT':
        n = len(operands)
        summary = f"Total count of {entity_name} entries is {n}."
        proof = f"Counted {n} records: {', '.join(opnd.label for opnd in operands)}."
        latex = f"$$\\text{{Count}} = {n}$$"
        return AnalyticalMathResult(
            operation='COUNT',
            summary=summary,
            proof=proof,
            latex=latex,
            formatted_answer=f"{summary}\n\n**Arithmetic Proof:** {proof}\n\n{latex}",
            result_value=float(n)
        )

    # 6. DIFFERENCE
    elif op == 'DIFFERENCE':
        if len(operands) < 2:
            return None
        op1, op2 = operands[0], operands[1]
        diff = op1.cell.num - op2.cell.num
        res_str = format_number_output(diff, cur=cur, suffix=suffix)
        summary = f"Difference between {op1.label} and {op2.label} is {res_str}."
        proof = f"{op1.cell.raw} ({op1.label}) - {op2.cell.raw} ({op2.label}) = {res_str}"
        latex = f"$$\\text{{Difference}} = {op1.cell.raw.replace('$', '\\$')} - {op2.cell.raw.replace('$', '\\$')} = {res_str.replace('$', '\\$')}$$"
        return AnalyticalMathResult(
            operation='DIFFERENCE',
            summary=summary,
            proof=proof,
            latex=latex,
            formatted_answer=f"{summary}\n\n**Arithmetic Proof:** {proof}\n\n{latex}",
            result_value=diff
        )

    # 7. PERCENTAGE_CHANGE
    elif op == 'PERCENTAGE_CHANGE':
        if len(operands) < 2:
            return None
        from_match = re.search(r'\bfrom\s+(\w+)', query, re.I)
        op_start, op_end = operands[0], operands[1]
        if from_match:
            from_term = from_match.group(1).lower()
            if from_term in op_end.label.lower():
                op_start, op_end = operands[1], operands[0]
        else:
            y_start = re.findall(r'\d+', op_start.label)
            y_end = re.findall(r'\d+', op_end.label)
            if y_start and y_end and int(y_start[0]) > int(y_end[0]):
                op_start, op_end = op_end, op_start

        base = op_start.cell.num
        if base == 0:
            return None
        growth_pct = ((op_end.cell.num - base) / abs(base)) * 100.0
        res_str = f"{growth_pct:+.2f}%"
        summary = f"Percentage growth of {entity_name} from {op_start.label} to {op_end.label} is {res_str}."
        proof = f"(({op_end.cell.raw} [{op_end.label}] - {op_start.cell.raw} [{op_start.label}]) / {op_start.cell.raw} [{op_start.label}]) * 100% = {res_str}"
        latex = f"$$\\text{{Growth}} = \\frac{{{op_end.cell.raw.replace('$', '\\$')} - {op_start.cell.raw.replace('$', '\\$')}}}{{{op_start.cell.raw.replace('$', '\\$')}}} \\times 100\\% = {res_str}$$"
        return AnalyticalMathResult(
            operation='PERCENTAGE_CHANGE',
            summary=summary,
            proof=proof,
            latex=latex,
            formatted_answer=f"{summary}\n\n**Arithmetic Proof:** {proof}\n\n{latex}",
            result_value=growth_pct
        )

    # 8. MARGIN & RATIO
    elif op in ('MARGIN', 'RATIO'):
        if len(operands) < 2:
            return None
        num_op, den_op = operands[0], operands[1]
        if den_op.cell.num == 0:
            return None
        if op == 'MARGIN':
            margin_pct = (num_op.cell.num / den_op.cell.num) * 100.0
            res_str = f"{margin_pct:.2f}%"
            summary = f"Profit margin for {entity_name} is {res_str}."
            proof = f"({num_op.cell.raw} [{num_op.label}] / {den_op.cell.raw} [{den_op.label}]) * 100% = {res_str}"
            latex = f"$$\\text{{Margin}} = \\frac{{{num_op.cell.raw.replace('$', '\\$')}}}{{{den_op.cell.raw.replace('$', '\\$')}}} \\times 100\\% = {res_str}$$"
            val = margin_pct
        else:
            ratio = num_op.cell.num / den_op.cell.num
            res_str = f"{ratio:.2f}"
            summary = f"Ratio of {num_op.label} to {den_op.label} for {entity_name} is {res_str}."
            proof = f"{num_op.cell.raw} [{num_op.label}] / {den_op.cell.raw} [{den_op.label}] = {res_str}"
            latex = f"$$\\text{{Ratio}} = \\frac{{{num_op.cell.raw.replace('$', '\\$')}}}{{{den_op.cell.raw.replace('$', '\\$')}}} = {res_str}$$"
            val = ratio
        return AnalyticalMathResult(
            operation=op,
            summary=summary,
            proof=proof,
            latex=latex,
            formatted_answer=f"{summary}\n\n**Arithmetic Proof:** {proof}\n\n{latex}",
            result_value=val
        )

    return None


def analytical_math_answer(query: str, text: str) -> Optional[AnalyticalMathResult]:
    """
    Main entry point: scans text for Markdown tables, evaluates analytical math on each,
    and returns the first valid calculation result.
    """
    if not has_analytical_math_intent(query) or '|' not in text:
        return None
        
    tables = extract_table_blocks(text)
    for table_block in tables:
        result = execute_analytical_math(query, table_block)
        if result:
            return result
            
    return None
