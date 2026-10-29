from app.generator import _build_extractive_fallback
from app.extractive_answers import select_source_units


def test_example_selected_instead_of_definition():
    chunks = [{'citation_id': 3, 'parent_text': 'Encapsulation means hiding internals.\nExample: a sealed thermostat controller', 'child_text': 'Encapsulation means hiding internals.'}]
    answer = _build_extractive_fallback('Which example illustrates encapsulation?', chunks)
    assert 'sealed thermostat controller' in answer
    assert '[3]' in answer


def test_list_selected_instead_of_slide_footer():
    chunks = [{'citation_id': 2, 'parent_text': 'Training slides\nQueues support operations such as enqueue, peek, and dequeue.\nDepartment of Computing', 'child_text': 'Department of Computing'}]
    answer = _build_extractive_fallback('Which operations do queues support?', chunks)
    assert 'enqueue, peek, and dequeue' in answer
    assert 'Department of Computing' not in answer
    assert '[2]' in answer


def test_selection_keeps_conditions_and_negation():
    source = 'Remote clients must not use write operations unless approval is granted.'
    answer = _build_extractive_fallback('Which write operations may remote clients use?', [{'citation_id': 1, 'parent_text': source, 'child_text': source}])
    assert 'must not' in answer and 'unless approval is granted' in answer


def test_general_question_does_not_select_incidental_keyword_overlap():
    assert select_source_units('What are the two parts of the engine?', [
        {'parent_text': 'Two layers of insulation make up the outer casing.'}]) is None


def test_construction_preserves_complete_source_unit():
    answer = select_source_units('What is built using linked nodes?', [
        {'citation_id': 4, 'parent_text': 'Workshop\nWe use linked nodes to make a queue when ordering matters.'}])
    assert answer == 'We use linked nodes to make a queue when ordering matters. [4]'
