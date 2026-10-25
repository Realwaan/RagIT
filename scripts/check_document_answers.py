"""Check an existing PDF cache through the real streaming API, with LLMs disabled.

Run from the project root with python -m scripts.check_document_answers
--cache <ingestion-cache.npz> --cases <questions.json> --output <report.json>.
Cases contain source-checked expected text and PDF page numbers.
"""
import argparse
import json
import re
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.indexing import _load_cache
from app.retriever import HybridRetriever


def main_check():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cached = _load_cache(args.cache.stem) if args.cache.is_file() else None
    if cached is None:
        parser.error('The ingestion cache and its original PDF/preview must exist locally.')
    ast, chunks, classification, vectors, pages = cached
    main.DOCUMENT_VAULT[ast.doc_id] = {
        'retriever': HybridRetriever(chunks, vectors), 'ast': ast, 'classification': classification,
    }
    client = TestClient(main.app)
    checks = []
    with patch('app.generator.has_valid_primary_key', return_value=False), patch('app.generator.has_valid_fallback_key', return_value=False), patch('app.vision.configured', return_value=False):
        for case in json.loads(args.cases.read_text(encoding='utf-8')):
            response = client.post('/api/chat', json={
                'doc_id': ast.doc_id, 'query': case['query'],
                'previous_question': case.get('previous_question', ''),
            })
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            done = next((event for event in events if event['type'] == 'done'), {})
            answer = done.get('answer', '')
            cited_ids = {int(value) for value in re.findall(r'\[(\d+)\]', answer)}
            cited_pages = {source['page'] for source in done.get('sources', []) if source['citation_id'] in cited_ids}
            passed = (
                response.status_code == 200 and done.get('status') == 'SUCCESS'
                and case['expected_text'] in answer
                and set(case['expected_pages']).issubset(cited_pages)
                and done.get('evaluation', {}).get('citation_verified', False)
            )
            checks.append({**case, 'passed': bool(passed), 'answer': answer,
                           'cited_pages': sorted(cited_pages), 'total_ms': done.get('total_ms')})
            print(f"{'PASS' if passed else 'FAIL'}: {case['query']} (cited pages: {sorted(cited_pages)})", flush=True)
    report = {'document_title': ast.title, 'pdf_pages': pages,
              'mode': 'actual PDF cache, local embeddings, streaming API, offline extraction',
              'passed': all(check['passed'] for check in checks), 'checks': checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main_check())
