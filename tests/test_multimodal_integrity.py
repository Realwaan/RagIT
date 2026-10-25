"""Cross-document regression coverage for table geometry and evidence identity."""
import numpy as np
import pytest

from app.ast_builder import ASTNode, ASTNodeType, DocumentAST, link_cross_modal_symbols
from app.generator import _build_extractive_fallback
from app.ingest import extract_pages_from_pdf
from app.main import _hydrate_ast_siblings
from app.pdf_tables import raster_tables
from app.retriever import HybridRetriever
from app.table_answers import table_answer
from scripts.check_long_pdfs import pdf_fixture, scan_image


def test_long_native_pdf_retains_borderless_and_rotated_table_axes():
    contents, count = pdf_fixture('finance')
    pages = extract_pages_from_pdf(contents, 'independent-finance.pdf')
    assert len(pages) == count == 128
    assert '| Nimbus | 237 | 245 |' in pages[63]['tables'][0]['text']
    assert '| Orion | 431 | 842 |' in pages[89]['tables'][0]['text']
    assert '| Business | Revenue 2024 | Revenue 2025 |' in pages[89]['tables'][0]['text']
    assert '842' in pages[126]['tables'][0]['text']
    assert 'COPPER-918' in pages[127]['text']


def test_raster_grid_retains_repeated_values_and_empty_cells():
    rows = [['Sample', 'Limit', 'Observed'], ['Terra', '12', '9'], ['Lunar', '12', '']]
    image = scan_image(rows=rows)
    lines = []
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if not value:
                continue
            x, y = 90 + c*360, 275 + r*80
            lines.append({'text': value, 'confidence': .94,
                          'box': [[x,y], [x+100,y], [x+100,y+25], [x,y+25]]})
    tables = raster_tables(image, lines)
    assert len(tables) == 1
    assert '| Terra | 12 | 9 |' in tables[0]['text']
    assert '| Lunar | 12 |  |' in tables[0]['text']
    assert tables[0]['ocr_min_confidence'] == .94
    image.close()


def test_repeated_figure_numbers_do_not_cross_chapters():
    ast = DocumentAST('book')
    for index, page in enumerate((1, 101), 1):
        section = ASTNode(f's{index}', ASTNodeType.SECTION, f'Chapter {index}', '', page, f'root/s{index}')
        ast.add_node(section)
        ast.add_node(ASTNode(f'p{index}', ASTNodeType.PARAGRAPH, '', 'See Figure 1 for the threshold.', page,
                            f'root/s{index}/p{index}'), section.id)
        ast.add_node(ASTNode(f'v{index}', ASTNodeType.VISUAL, 'Figure 1: Threshold', 'Threshold diagram', page,
                            f'root/s{index}/v{index}'), section.id)
    link_cross_modal_symbols(ast)
    assert ast.nodes['p1'].linked_node_ids == ['v1']
    assert ast.nodes['p2'].linked_node_ids == ['v2']


def test_explicit_visual_context_has_its_own_page_and_citation():
    ast = DocumentAST('manual')
    ast.add_node(ASTNode('p', ASTNodeType.PARAGRAPH, '', 'See Figure 9.', 3, 'root/p'))
    ast.add_node(ASTNode('v', ASTNodeType.VISUAL, 'Figure 9', 'The pressure setting shown in this diagram is exactly 73 kPa.', 4, 'root/v'))
    link_cross_modal_symbols(ast)
    hits = [{'citation_id': 1, 'ast_node_id': 'p', 'page': 3, 'parent_text': 'See Figure 9.'}]
    _hydrate_ast_siblings(hits, ast)
    assert [(hit['citation_id'], hit['page']) for hit in hits] == [(1, 3), (2, 4)]
    assert hits[1]['retrieved_via'] == 'explicit_visual_reference'
    _hydrate_ast_siblings(hits, ast)
    assert len(hits) == 2


def test_page_filter_applies_before_ranking_and_to_escalation(monkeypatch):
    import app.retriever as module
    monkeypatch.setattr(module, 'embed_query', lambda _: np.array([1., 0.]))
    chunks = [dict(page=page, child_text='The target is a measured limit.', parent_text='The target is a measured limit.')
              for page in (1, 127)]
    retriever = HybridRetriever(chunks, np.array([[.9,.1],[.6,.8]]))
    assert [hit['page'] for hit in retriever.retrieve('What is the target on PDF page 127?')] == [127]
    assert retriever.retrieve('target on PDF page 999') == []
    assert retriever.escalate_page_scan('target on PDF page 999', []) == []


TABLE = '| Business | Revenue 2024 | Revenue 2025 |\n| --- | --- | --- |\n| Orion | 431 | 842 |'


def test_exact_table_cell_uses_both_row_and_column_and_rejects_ambiguity():
    assert table_answer('Orion Revenue 2025', TABLE).endswith('842.')
    assert table_answer('Orion Revenue 2024', TABLE).endswith('431.')
    assert table_answer('Orion Revenue', TABLE) == ''
    assert table_answer('Vega Revenue 2025', TABLE) == ''
    assert table_answer('Orion Revenue 2025', TABLE.replace('842', '\ufffd842')) == ''


def test_table_year_does_not_match_an_unrelated_metric():
    assert table_answer('Orion Expenses 2025', TABLE) == ''


def test_each_table_retains_its_own_column_headers():
    expenses = '| Business | Expenses 2024 | Expenses 2025 |\n| --- | --- | --- |\n| Vega | 120 | 230 |'
    combined = TABLE + '\n\nExpenses:\n' + expenses
    assert table_answer('Vega Revenue 2025', combined) == ''
    assert table_answer('Vega Expenses 2025', combined).endswith('230.')
    assert table_answer('Orion Revenue 2025', combined).endswith('842.')


def test_conflicting_tables_do_not_silently_choose_first_value():
    answer = _build_extractive_fallback('Orion Revenue 2025', [
        {'citation_id': 1, 'parent_text': TABLE},
        {'citation_id': 2, 'parent_text': TABLE.replace('842', '999')},
    ])
    assert 'different values' in answer
    assert '842. [1]' in answer and '999. [2]' in answer


def test_year_section_disambiguates_repeated_table_row_labels():
    text = '| Region | Sales |\n| --- | --- |\n| 2024 | |\n| North | 400 |\n| 2023 | |\n| North | 300 |'
    assert table_answer('North Sales 2024', text).endswith('400.')
    assert table_answer('North Sales 2023', text).endswith('300.')
    assert table_answer('North Sales', text) == ''
