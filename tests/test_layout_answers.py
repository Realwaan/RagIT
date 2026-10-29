from PIL import Image, ImageDraw

from app.layout_answers import range_cards, numbered_panels, fraction_formula


def line(text, x, y, w=80, h=20, confidence=1):
    return {'text': text, 'confidence': confidence, 'box': [[x,y],[x+w,y],[x+w,y+h],[x,y+h]]}


def test_ranges_follow_columns_not_ocr_reading_order():
    rows = [line('Basic', 10, 10), line('Advanced', 110, 10),
            line('plans', 10, 30), line('plans', 110, 30),
            line('3-7', 10, 50), line('20-40', 110, 50),
            line('users', 10, 75), line('users', 110, 75)]
    query = 'How many users do Basic and Advanced plans have by category?'
    answer = range_cards(query, list(reversed(rows)))
    assert 'Basic: 3-7 users' in answer
    assert 'Advanced: 20-40 users' in answer
    rows[4]['confidence'] = .5
    assert range_cards(query, rows) is None


def test_numbered_panels_do_not_interleave_columns():
    rows = [line('3.1', 0, 40, h=40), line('4.2', 300, 40, h=40),
            line('Keep the doors', 100, 20), line('Open the windows', 400, 20),
            line('closed during storms.', 100, 50), line('only after inspection.', 400, 50)]
    answer = numbered_panels('Explain policies 3.1 and 4.2.', rows)
    assert '3.1: Keep the doors closed during storms.' in answer
    assert '4.2: Open the windows only after inspection.' in answer
    assert numbered_panels('Explain policies 3.1 and 9.8.', rows) is None


def test_fraction_requires_visible_divider_and_equals_sign():
    rows = [line('Rate', 10, 50, 50, 30), line('Distance', 100, 30, 80, 20),
            line('Time', 100, 75, 80, 20)]
    image = Image.new('RGB', (220, 120), 'white')
    draw = ImageDraw.Draw(image)
    draw.line((100, 65, 180, 65), fill='black', width=2)
    assert fraction_formula('What is the rate formula?', rows, image) is None
    draw.line((65, 60, 95, 60), fill='black', width=2)
    draw.line((65, 70, 95, 70), fill='black', width=2)
    assert fraction_formula('What is the rate formula?', rows, image) == 'Rate = Distance / Time.'
    rows[1]['confidence'] = .7
    assert fraction_formula('What is the rate formula?', rows, image) is None
