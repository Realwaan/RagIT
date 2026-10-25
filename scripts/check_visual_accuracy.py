"""Reproducible 40-question visual benchmark with an explicit human review gate.

python -m scripts.check_visual_accuracy --output reports/visual-accuracy.json
Add --live to compare the configured vision model against text-only answers.
Add --review reviewed.json to evaluate release criteria; see README.
Synthetic illustrations test visible facts, not medical/photo identification.
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def fixtures():
    """Expected facts are authored from drawing commands, independently of models."""
    font = ImageFont.truetype('DejaVuSans.ttf', 30) if Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').exists() else ImageFont.truetype('arial.ttf', 30)
    images, cases = [], []
    for page, kind in enumerate(('pictures', 'diagrams', 'charts', 'tables'), 1):
        image = Image.new('RGB', (1400, 1000), 'white')
        draw = ImageDraw.Draw(image)
        def text(x, y, value):
            draw.text((x, y), value, font=font, fill='black')
        text(60, 30, f'Figure 1: {kind.title()} example')
        if kind == 'pictures':
            draw.ellipse((150, 180, 410, 440), fill='blue')
            draw.rectangle((700, 180, 960, 440), fill='red')
            draw.polygon([(150, 850), (410, 850), (280, 570)], fill='green')
            draw.ellipse((730, 580, 950, 800), fill='yellow', outline='black', width=5)
            qa = [('What shape is blue?', 'circle'), ('What color is the square?', 'red'),
                  ('What shape is green?', 'triangle'), ('What color is the bottom-right circle?', 'yellow'),
                  ('How many shapes are visible?', '4'), ('Which shape is above the green triangle?', 'blue circle'),
                  ('Which shape is right of the blue circle?', 'red square'),
                  ('How many circles are visible?', '2'), ('Which shape has a black outline?', 'yellow circle'),
                  ('What material is the blue object made from?', None)]
        elif kind == 'diagrams':
            for x, label in [(100, 'Tank A'), (550, 'Valve B'), (1000, 'Tank C')]:
                draw.rectangle((x, 300, x+250, 500), outline='black', width=5)
                text(x+20, 370, label)
            draw.line((350, 400, 550, 400), fill='blue', width=12)
            draw.polygon([(550, 400), (510, 375), (510, 425)], fill='blue')
            draw.line((800, 400, 1000, 400), fill='red', width=12)
            draw.polygon([(800, 400), (840, 375), (840, 425)], fill='red')
            text(380, 270, '5 L/min'); text(820, 270, '2 L/min')
            qa = [('Where does the blue arrow start?', 'Tank A'), ('Where does the blue arrow end?', 'Valve B'),
                  ('Where does the red arrow start?', 'Tank C'), ('Where does the red arrow end?', 'Valve B'),
                  ('What is the blue flow rate?', '5 L/min'), ('What is the red flow rate?', '2 L/min'),
                  ('Which component receives both arrows?', 'Valve B'), ('How many tanks are shown?', '2'),
                  ('Does the red arrow point left or right?', 'left'), ('What is the pressure inside Tank A?', None)]
        elif kind == 'charts':
            text(80, 100, 'Output (kg)'); text(500, 860, 'Facility')
            draw.line((150, 200, 150, 800, 1250, 800), fill='black', width=4)
            for x, h, label, value in [(250, 200, 'North', '20'), (600, 500, 'South', '50'), (950, 350, 'West', '35')]:
                draw.rectangle((x, 800-h, x+140, 800), fill='blue')
                text(x, 810, label); text(x+40, 750-h, value)
            text(1000, 120, 'Blue = actual')
            qa = [('What is the output unit?', 'kg'), ('What is North output?', '20'),
                  ('What is South output?', '50'), ('What is West output?', '35'),
                  ('Which facility has the highest output?', 'South'), ('Which has the lowest output?', 'North'),
                  ('What does blue mean?', 'actual'), ('What does the horizontal axis show?', 'Facility'),
                  ('How many facility bars are shown?', '3'), ('What was South output last year?', None)]
        else:
            rows = [['Region', '2024 (kg)', '2025 (kg)'], ['North', '12', '19'], ['South', '12', '27'], ['West', '8', '']]
            for row in range(5):
                draw.line((100, 200+row*140, 1300, 200+row*140), fill='black', width=4)
            for col in range(4):
                draw.line((100+col*400, 200, 100+col*400, 760), fill='black', width=4)
            for r, values in enumerate(rows):
                for c, value in enumerate(values):
                    text(120+c*400, 245+r*140, value)
            qa = [('What is North in 2024?', '12'), ('What is North in 2025?', '19'),
                  ('What is South in 2024?', '12'), ('What is South in 2025?', '27'),
                  ('What is West in 2024?', '8'), ('Which unit is used?', 'kg'),
                  ('Which two regions have the same 2024 value?', 'North and South'),
                  ('Which region has the largest listed 2025 value?', 'South'),
                  ('How many region rows are shown?', '3'), ('What is West in 2025?', None)]
        images.append(image)
        cases.extend({'id': f'{kind}-{i}', 'category': kind, 'page': page,
                      'query': f'In Figure 1 on PDF page {page}: {query}', 'expected': expected}
                     for i, (query, expected) in enumerate(qa, 1))
    return images, cases


def apply_review(report, reviewed):
    required = {'baseline_correct', 'visual_correct', 'citation_correct', 'invented_number'}
    checks = report['checks']
    if len(checks) != 40 or set(reviewed) != {c['id'] for c in checks} or any(
        set(v) != required or any(type(x) is not bool for x in v.values()) for v in reviewed.values()
    ):
        raise ValueError('Review must cover all 40 case IDs with the four boolean fields documented in README.')
    report['review'] = reviewed
    report['baseline_accuracy'] = sum(v['baseline_correct'] for v in reviewed.values()) / len(checks)
    report['visual_accuracy'] = sum(v['visual_correct'] for v in reviewed.values()) / len(checks)
    report['abstentions'] = sum(c['visual']['status'] == 'REFUSE' for c in checks)
    answerable = [c for c in checks if c['expected'] is not None]
    report['answerable_accuracy'] = sum(reviewed[c['id']]['visual_correct'] and c['visual']['status'] == 'SUCCESS'
                                        for c in answerable) / len(answerable)
    passed = (report['visual_accuracy'] >= .9 and report['answerable_accuracy'] >= .9
              and all(v['citation_correct'] for v in reviewed.values())
              and not any(v['invented_number'] for v in reviewed.values())
              and report['visual_accuracy'] > report['baseline_accuracy'])
    report['release_gate'] = 'passed' if passed else 'failed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--review', type=Path)
    parser.add_argument('--output', type=Path, default=Path('reports/visual-accuracy.json'))
    args = parser.parse_args()
    if args.review:
        # Review the exact saved responses, never regenerate answers under a review.
        report = json.loads(args.output.read_text(encoding='utf-8'))
        apply_review(report, json.loads(args.review.read_text(encoding='utf-8')))
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(report['release_gate'])
        return 0 if report['release_gate'] == 'passed' else 1
    root = args.output.parent / 'visual-benchmark'
    root.mkdir(parents=True, exist_ok=True)
    images, cases = fixtures()
    pdf = root / 'visuals.pdf'
    images[0].save(pdf, save_all=True, append_images=images[1:], resolution=100)
    for i, image in enumerate(images, 1):
        image.save(root / f'page-{i}.png')
        image.close()
    (root / 'cases.json').write_text(json.dumps(cases, indent=2), encoding='utf-8')
    from app import vision
    report = {'scope': '40 authored synthetic visual questions; not representative of natural photographs or medical illustrations.',
              'model': vision.cfg.VISION_MODEL, 'vision_configured': vision.configured(),
              'release_gate': 'not_evaluated', 'checks': []}
    if args.live and not vision.configured():
        report['blocked_reason'] = 'No vision credentials configured; no external calls made.'
    elif args.live:
        from fastapi.testclient import TestClient
        import app.main as api
        from app.indexing import prepare_document
        from app.generator import generate_grounded_answer_with_telemetry
        prepared = prepare_document(pdf.read_bytes(), pdf.name)
        ast = prepared['ast']
        vision.VISUAL_INDEXER.submit(ast)
        vision.VISUAL_INDEXER.shutdown()
        api.DOCUMENT_VAULT[ast.doc_id] = prepared
        api.DOCUMENT_ASTS[ast.doc_id] = ast
        client = TestClient(api.app)
        for case in cases:
            hits = prepared['retriever'].retrieve(case['query'])
            baseline, meta = generate_grounded_answer_with_telemetry(case['query'], hits)
            response = client.post('/api/chat', json={'doc_id': ast.doc_id, 'query': case['query']})
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            result = next(e for e in events if e['type'] == 'done')
            report['checks'].append({**case, 'baseline_answer': baseline, 'baseline_telemetry': meta, 'visual': result})
        report['analysis'] = vision.VISUAL_INDEXER.status(ast.doc_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, indent=2))
    return 1 if report.get('blocked_reason') or report['release_gate'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
