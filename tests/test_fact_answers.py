import pytest
from app.fact_answers import fact_answer, fact_excerpts
from app.generator import _build_extractive_fallback


@pytest.mark.parametrize('query,text', [
    ('What is the activation code?', 'The activation code is ZEBRA-258.'),
    ('What is the retention period?', 'Archive instructions The retention period is 46 days.'),
    ('Who is the review owner?', 'The review owner is Salma.'),
    ('What is the maximum load?', 'The maximum load is 62 kg only if both supports are locked.'),
    ('What is the authorization code?', 'The authorization code is not assigned.'),
    ('What is the deadline?', 'The deadline is Friday\nunless the office is closed.'),
    ('What is the activation code?', 'The manual says The activation code is provisional.'),
])
def test_property_lookups_preserve_complete_source(query, text):
    assert fact_answer(query, [{'parent_text': text, 'citation_id': 4}]) == text + ' [4]'
    assert _build_extractive_fallback(query, [{'parent_text': text, 'citation_id': 4}]) == text + ' [4]'


@pytest.mark.parametrize('text', [
    'The backup activation code is OTHER-992.',
    'A secondary activation code is OTHER-992.',
    'Activation code',
    'No activation code is available.',
])
def test_different_subject_and_heading_do_not_become_answers(text):
    assert fact_answer('What is the activation code?', [{'parent_text': text}]) is None


def test_different_values_are_not_silently_discarded():
    answer = fact_answer('What is the deadline?', [
        {'parent_text': 'The deadline is Monday.', 'citation_id': 1},
        {'parent_text': 'The deadline is Friday.', 'citation_id': 2}])
    assert 'Monday. [1]' in answer and 'Friday. [2]' in answer
    assert 'scope and conditions' in answer


def test_dictionary_definitions_use_existing_path():
    assert fact_excerpts('What is a cell?', 'A cell is a biological unit.') == []


def test_ocr_glued_spaces_do_not_change_values():
    from app.fact_answers import normalize_measurement_spacing
    from app.evaluator import verify_generated_answer
    chunk = {'parent_text': 'The maximum load is 83kg.', 'citation_id': 1}
    answer = fact_answer('What is the maximum load?', [chunk])
    assert answer == 'The maximum load is 83 kg. [1]'
    assert verify_generated_answer(answer, [chunk], {})['claim_support'] == 'supported'
    assert fact_answer('What is the retention period?', [{'parent_text': 'The retention period is46 days.'}]) == 'The retention period is 46 days. [1]'
    assert normalize_measurement_spacing('Part A83kg and version 8.3kg') == 'Part A83kg and version 8.3 kg'


@pytest.mark.parametrize('query,source,expected', [
    ('What is the retention period?', 'The retention period is57days unless a hold applies.',
     'The retention period is 57 days unless a hold applies.'),
    ('What is the inspection interval?', 'The inspection interval is6weeks.',
     'The inspection interval is 6 weeks.'),
    ('What is the temperature?', 'The temperature is-12.5 degrees.',
     'The temperature is -12.5 degrees.'),
    ('What is the maximum load?', 'The maximum load is+81kg only when locked.',
     'The maximum load is +81 kg only when locked.'),
])
def test_glued_numeric_properties_preserve_values_conditions_and_support(query, source, expected):
    from app.evaluator import verify_generated_answer
    chunks = [{'parent_text': source, 'citation_id': 3}]
    answer = fact_answer(query, chunks)
    assert answer == expected + ' [3]'
    assert chunks[0]['parent_text'] == source
    assert verify_generated_answer(answer, chunks, {})['claim_support'] == 'supported'
    changed = answer.replace('57', '58').replace('6 weeks', '9 weeks').replace('-12.5', '12.5').replace('+81', '+82')
    assert verify_generated_answer(changed, chunks, {})['claim_support'] == 'needs_review'


@pytest.mark.parametrize('text', [
    'The authorization code is IS57.',
    'The owner is axis57.',
    'Part A57days and code X81kg are identifiers.',
    'The retention period is unknown.',
    'The retention period is not57 days.',
])
def test_spacing_repair_does_not_guess_identifiers_or_negation(text):
    from app.fact_answers import normalize_fact_spacing
    assert normalize_fact_spacing(text) == text


@pytest.mark.parametrize('query,source', [
    ('How long should documents be stored?', 'The retention period is 83 days.'),
    ('What is the weight limit?', 'The maximum load is 76 kg.'),
    ('How often must inspections occur?', 'The inspection interval is 9 months.'),
])
def test_generic_property_paraphrases_keep_evidence(query, source):
    assert fact_answer(query, [{'parent_text': source}]) == source + ' [1]'


@pytest.mark.parametrize('query', [
    'How long must tax records be kept?',
    'How much weight is allowed if the support is broken?',
    'Who is responsible for review in 2020?',
    'How long must records be kept on page 12?',
])
def test_rewrite_does_not_drop_extra_constraints(query):
    from app.fact_answers import property_query
    assert property_query(query) == query


@pytest.mark.parametrize('query,expected_canonical', [
    ('How long can the files be kept?', 'What is the retention period?'),
    ('How long should records be preserved?', 'What is the retention period?'),
    ('What is the load limit?', 'What is the maximum load?'),
    ('How often must an inspection take place?', 'What is the inspection interval?'),
    ('Who is in charge of review?', 'What is the review owner?'),
])
def test_generalized_property_inquiries(query, expected_canonical):
    from app.fact_answers import property_query
    assert property_query(query) == expected_canonical


def test_visual_caption_is_not_success_when_provider_unavailable(monkeypatch):
    from types import SimpleNamespace
    import app.vision as vision
    monkeypatch.setattr(vision, 'configured', lambda: False)
    monkeypatch.setattr(vision, 'select_visuals', lambda *args: [SimpleNamespace()])
    result = vision.visual_answer(None, 'What color is the circle in Figure 1?',
                                  [{'citation_id': 1, 'parent_text': 'Figure 1: Transfer diagram'}])
    assert result['status'] == 'REFUSE'
    assert result['sources'] == []
    assert result['evaluation']['visual_support'] == 'unavailable'
