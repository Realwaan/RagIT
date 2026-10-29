"""Build/run a versioned, offline-first 150-question synthetic RAG baseline.

python -m scripts.document_baseline --build
python -m scripts.document_baseline --run --split development
python -m scripts.document_baseline --run --split held_out

No model calls unless --live or --live-vision is explicitly supplied. Synthetic template families
are shared across splits; this measures regression, not real-world generalization.
"""
import argparse
import hashlib
import io
import json
import math
import os
import platform
import re
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'tests/fixtures/document_baseline_v1'


def pipeline_sha256():
    digest = hashlib.sha256()
    for path in sorted((ROOT / 'app').glob('*.py')):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def report_freshness(report):
    """Check saved provenance without invoking models or modifying reports."""
    return {
        'pipeline_matches': report.get('pipeline_sha256') == pipeline_sha256(),
        'manifest_matches': report.get('manifest_sha256') == hashlib.sha256((DATA / 'manifest.json').read_bytes()).hexdigest(),
        'runner_matches': report.get('runner_sha256') == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def native_pdf(lines):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')}))
    for content in (['Archive cover. This page contains no operational facts.'], lines):
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        commands = []
        for i, line in enumerate(content):
            escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            commands.append(f'BT /F1 12 Tf 40 {740-i*35} Td ({escaped}) Tj ET')
        stream.set_data('\n'.join(commands).encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def raster_pdf(lines, visual=False, color='blue'):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype('arial.ttf', 30)
    except OSError:
        font = ImageFont.truetype('DejaVuSans.ttf', 30)
    images = [Image.new('RGB', (1224, 1584), 'white') for _ in range(2)]
    ImageDraw.Draw(images[0]).text((70, 80), 'Archive cover', font=font, fill='black')
    draw = ImageDraw.Draw(images[1])
    for i, line in enumerate(lines):
        draw.text((70, 80+i*70), line, font=font, fill='black')
    if visual:
        draw.ellipse((100, 600, 350, 850), fill=color)
        draw.rectangle((700, 600, 950, 850), fill='black')
        draw.line((350, 725, 650, 725), fill='black', width=12)
        draw.polygon([(690, 725), (640, 695), (640, 755)], fill='black')
    output = io.BytesIO()
    images[0].save(output, format='PDF', save_all=True, append_images=images[1:])
    for image in images:
        image.close()
    return output.getvalue()


def build():
    DATA.mkdir(parents=True, exist_ok=True)
    cases, documents = [], []
    for category in ('native', 'scanned', 'tables', 'paraphrase', 'visual', 'unanswerable'):
        for n in range(5):
            doc = f'{category}-{n+1}'
            split = 'development' if n < 3 else 'held_out'
            days, code, owner, unit = 17+n*3, f'RAVEN-{731+n*11}', ['Mira','Owen','Tara','Lena','Ivo'][n], f'Unit {n+1}'
            lines = [f'{unit} operational reference', f'The retention period is {days} days.',
                     f'The authorization code is {code}.', f'The review owner is {owner}.',
                     f'The inspection interval is {n+2} weeks.', f'The maximum load is {40+n*7} kg.']
            qa = [('What is the retention period?', f'{days} days'),
                  ('What is the authorization code?', code), ('Who is the review owner?', owner),
                  ('What is the inspection interval?', f'{n+2} weeks'),
                  ('What is the maximum load?', f'{40+n*7} kg')]
            if category == 'paraphrase':
                qa = list(zip(['How long must records be kept?', 'Which code authorizes access?',
                    'Who is responsible for review?', 'How often is inspection required?',
                    'How much weight is permitted?'], [a for _, a in qa]))
            elif category == 'tables':
                lines = [f'{unit} inventory', 'Table 1: Stock quantities', '| Item | 2024 | 2025 |',
                         '| --- | --- | --- |'] + [f'| Part {c} | {10+i} | {20+n*5+i} |' for i,c in enumerate('ABCDE')]
                qa = [(f'What is the 2025 stock quantity for Part {c}?', str(20+n*5+i)) for i,c in enumerate('ABCDE')]
            elif category == 'unanswerable':
                qa = [(q, None) for q in ['What is the warehouse address?', 'Who founded this organization?',
                    'What was the 2020 revenue?', 'What is the insurance premium?', 'What is the emergency telephone number?']]
            elif category == 'visual':
                color = ['blue','red','green','purple','orange'][n]
                lines = ['Figure 1: Transfer diagram']
                qa = [('What color is the circle in Figure 1?', color),
                      ('What shape is on the right in Figure 1?', 'square'),
                      ('Which direction does the arrow point in Figure 1?', 'right'),
                      ('What color is the square in Figure 1?', 'black'),
                      ('What material is the circle made from?', None)]
            blob = raster_pdf(lines, category == 'visual', color if category == 'visual' else 'blue') if category in ('scanned','visual') else native_pdf(lines)
            path = DATA / f'{doc}.pdf'
            path.write_bytes(blob)
            documents.append({'id': doc, 'path': path.name, 'sha256': hashlib.sha256(blob).hexdigest(),
                              'split': split, 'category': category})
            for i, (query, expected) in enumerate(qa):
                cases.append({'id': f'{doc}-q{i+1}', 'document': doc, 'split': split, 'category': category,
                              'query': query, 'expected_answer': expected, 'answerable': expected is not None,
                              'supporting_pages': [2] if expected is not None else []})
    manifest = {'version': 1, 'scope': 'Authored synthetic documents; shared templates across document-disjoint splits. Not a general accuracy certification.',
                'documents': documents, 'cases': cases}
    (DATA / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def summarize(rows):
    answered = [r for r in rows if r['answerable']]
    unavailable = [r for r in rows if not r['answerable']]
    def mean(values):
        return round(sum(values)/len(values), 4) if values else None
    latencies = sorted(r['latency_ms'] for r in rows)
    return {'count': len(rows), 'supporting_page_recall_at_10': mean([r['page_recall_at_10'] for r in answered]),
            'expected_answer_match_rate': mean([r['expected_answer_match'] for r in rows]),
            'false_refusal_rate': mean([r['refused'] for r in answered]),
            'unanswerable_refusal_rate': mean([r['refused'] for r in unavailable]),
            'citation_page_match_rate': mean([r['citation_page_match'] for r in answered]),
            'answer_correctness': None, 'claim_support_precision': None,
            'human_review_status': 'not_evaluated',
            'latency_p95_ms': latencies[math.ceil(.95*len(latencies))-1] if latencies else None,
            'total_tokens': sum(r['tokens'] for r in rows), 'cost': None}


def apply_review(report, reviews):
    """Bind human judgments to saved answers so stale reviews cannot pass."""
    judgments = []
    for row in report['checks']:
        review = reviews.get(row['id'])
        if review is None:
            raise ValueError(f"Missing review: {row['id']}")
        if review.get('answer_sha256') != row['answer_sha256']:
            raise ValueError(f"Stale review: {row['id']}")
        for key in ('answer_correct', 'citation_correct', 'invented_number'):
            if type(review.get(key)) is not bool:
                raise ValueError(f"{row['id']}: {key} must be boolean")
        counts = [review.get(k) for k in ('supported_claims', 'total_claims')]
        if any(type(n) is not int or n < 0 for n in counts) or counts[0] > counts[1]:
            raise ValueError(f"Invalid claim counts: {row['id']}")
        judgments.append((row, review))
    for category in [None] + list(report['by_category']):
        subset = [(r, v) for r, v in judgments if category is None or r['category'] == category]
        summary = report['summary'] if category is None else report['by_category'][category]
        total = sum(v['total_claims'] for _, v in subset)
        summary.update(human_review_status='reviewed',
            answer_correctness=sum(v['answer_correct'] for _, v in subset)/len(subset) if subset else None,
            citation_correctness=sum(v['citation_correct'] for _, v in subset)/len(subset) if subset else None,
            claim_support_precision=sum(v['supported_claims'] for _, v in subset)/total if total else None,
            invented_number_count=sum(v['invented_number'] for _, v in subset))
    summary = report['summary']
    report['release_gate'] = 'passed' if (
        summary['count'] > 0 and (summary['supporting_page_recall_at_10'] or 0) >= .95
        and (summary['answer_correctness'] or 0) >= .90
        and (summary['claim_support_precision'] or 0) >= .95
        and summary['false_refusal_rate'] is not None and summary['false_refusal_rate'] <= .05
        and summary['citation_correctness'] == 1 and summary['invented_number_count'] == 0
    ) else 'failed'
    report['human_reviews'] = reviews
    return report


def pace_requests(function, requests_per_minute):
    """Pace sequential live calls without retrying or changing their responses."""
    last_started = None
    def call(*args, **kwargs):
        nonlocal last_started
        now = time.monotonic()
        if last_started is not None:
            time.sleep(max(0, 60 / requests_per_minute - (now - last_started)))
        last_started = time.monotonic()
        return function(*args, **kwargs)
    return call


def run(manifest, split, live, output, live_vision=False, vision_rpm=0):
    from fastapi.testclient import TestClient
    import app.main as main
    import app.config as cfg
    from app.indexing import prepare_document
    from app import auth
    if auth.is_production():
        raise ValueError('Run benchmarks in a separate development process, never in production.')
    if live_vision:
        from app.vision import configured
        if not configured():
            raise ValueError('--live-vision requires a configured, enabled vision provider.')
    rows = []
    with ExitStack() as stack:
        # This in-process client has no Clerk session. Scope local mode and the
        # fixture vault to this run, restoring both even when evaluation fails.
        stack.enter_context(patch.dict(os.environ, {'RAGIT_AUTH_MODE': 'local'}))
        stack.enter_context(patch.object(main, 'DOCUMENT_VAULT', {}))
        if vision_rpm:
            from app.vision import call_vision
            stack.enter_context(patch('app.vision.call_vision', pace_requests(call_vision, vision_rpm)))
        if not live:
            stack.enter_context(patch('app.generator.has_valid_primary_key', return_value=False))
            stack.enter_context(patch('app.generator.has_valid_fallback_key', return_value=False))
        if not live and not live_vision:
            stack.enter_context(patch('app.vision.configured', return_value=False))
        client = TestClient(main.app)
        for document in manifest['documents']:
            if document['split'] != split:
                continue
            blob = (DATA / document['path']).read_bytes()
            if hashlib.sha256(blob).hexdigest() != document['sha256']:
                raise ValueError(f"Fixture changed: {document['id']}")
            entry = prepare_document(blob, document['path'])
            main.DOCUMENT_VAULT[entry['doc_id']] = entry
            try:
                for case in [c for c in manifest['cases'] if c['document'] == document['id']]:
                    hits = entry['retriever'].retrieve(case['query'], top_k=10)
                    started = time.perf_counter()
                    response = client.post('/ask', json={'doc_id': entry['doc_id'], 'query': case['query']})
                    response.raise_for_status()
                    result = response.json()
                    answer = result.get('answer', '')
                    refused = result.get('status') == 'REFUSE'
                    cited = {int(x) for x in re.findall(r'\[(\d+)\]', answer)}
                    pages = {s.get('page') for s in result.get('sources', []) if s.get('citation_id') in cited}
                    expected_pages = set(case['supporting_pages'])
                    expected = case['expected_answer']
                    match = refused if expected is None else not refused and bool(re.search(r'(?<!\w)' + re.escape(expected.casefold()) + r'(?!\w)', answer.casefold()))
                    rows.append({**case, 'answer': answer, 'refused': refused, 'expected_answer_match': match,
                        'page_recall_at_10': len(expected_pages & {h.get('page') for h in hits})/len(expected_pages) if expected_pages else None,
                        'citation_page_match': bool(expected_pages) and expected_pages <= pages,
                        'latency_ms': round((time.perf_counter()-started)*1000, 2),
                        'tokens': result.get('estimated_tokens', result.get('token_telemetry', {}).get('total_tokens', 0)),
                        'evaluation': result.get('evaluation', {}),
                        'generation_mode': result.get('generation_mode'), 'cited_pages': sorted(pages),
                        'answer_sha256': hashlib.sha256(answer.encode()).hexdigest()})
                    print(f"{case['id']}: match={match} refusal={refused}", flush=True)
            finally:
                main.DOCUMENT_VAULT.pop(entry['doc_id'], None)
    report = {'benchmark_version': manifest['version'], 'manifest_sha256': hashlib.sha256((DATA/'manifest.json').read_bytes()).hexdigest(),
              'pipeline_sha256': pipeline_sha256(),
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'runtime': {'python': platform.python_version(), 'embedding_model': cfg.DEFAULT_EMBED_MODEL,
                          'similarity_threshold': cfg.SIMILARITY_THRESHOLD, 'answer_top_k': cfg.TOP_K,
                          'text_model': cfg.get_active_gemma_model() if live else None,
                          'vision_model': cfg.VISION_MODEL if live or live_vision else None,
                          'vision_requests_per_minute': vision_rpm or None},
              'scope': manifest['scope'], 'split': split,
              'mode': 'live' if live else 'extractive_with_live_vision' if live_vision else 'offline_extractive',
              'release_gate': 'not_evaluated', 'summary': summarize(rows),
              'by_category': {cat: summarize([r for r in rows if r['category'] == cat]) for cat in sorted({r['category'] for r in rows})},
              'checks': rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-report', type=Path, help='Check saved report provenance without model calls')
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--run', action='store_true')
    providers = parser.add_mutually_exclusive_group()
    providers.add_argument('--live', action='store_true', help='Allow configured hosted-model calls and associated API usage')
    providers.add_argument('--live-vision', action='store_true', help='Allow hosted vision calls while keeping text answers extractive')
    parser.add_argument('--vision-model', help='Override the vision model for this live run only')
    parser.add_argument('--vision-rpm', type=float, default=0, help='Pace vision requests below a provider limit; 0 disables pacing')
    parser.add_argument('--split', choices=['development','held_out'], default='development')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--review', type=Path, help='Review JSON keyed by case ID; requires --output pointing to saved report')
    args = parser.parse_args()
    if args.verify_report:
        if args.build or args.run or args.review:
            parser.error('--verify-report cannot be combined with build, run, or review')
        freshness = report_freshness(json.loads(args.verify_report.read_text(encoding='utf-8')))
        print(json.dumps(freshness, indent=2))
        raise SystemExit(0 if all(freshness.values()) else 1)
    if not math.isfinite(args.vision_rpm) or args.vision_rpm < 0:
        parser.error('--vision-rpm must be a finite non-negative number')
    if args.vision_rpm and not (args.run and (args.live or args.live_vision)):
        parser.error('--vision-rpm requires --run and a live mode')
    if args.vision_model:
        if not args.run or not (args.live or args.live_vision):
            parser.error('--vision-model requires --run and a live mode')
        import app.config as cfg
        cfg.VISION_MODEL = args.vision_model
    if args.review:
        if args.build or args.run or not args.output:
            parser.error('--review requires --output and cannot be combined with --build/--run')
        report = json.loads(args.output.read_text(encoding='utf-8'))
        reviewed = apply_review(report, json.loads(args.review.read_text(encoding='utf-8')))
        args.output.write_text(json.dumps(reviewed, indent=2), encoding='utf-8')
        print(reviewed['release_gate'])
        return
    if args.build:
        build()
    if args.run:
        manifest = json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
        report = run(manifest, args.split, args.live, args.output or ROOT/f'reports/document-baseline-{args.split}.json',
                     live_vision=args.live_vision, vision_rpm=args.vision_rpm)
        print(json.dumps(report['summary'], indent=2))
    if not args.build and not args.run:
        parser.error('Choose --build or --run.')


if __name__ == '__main__':
    main()
