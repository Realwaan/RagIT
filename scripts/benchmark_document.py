"""Measure real cold/warm ingestion without attaching files to a user's vault.

Run as a module: python -m scripts.benchmark_document --input PATH --pages 6
Omit --pages for the full document. Reports contain timings, not document text.
"""
import argparse
import hashlib
import io
import json
import os
import platform
import tempfile
import time
from pathlib import Path


def peak_memory_mib():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
                'peak_working_set', 'working_set', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]
        info = Counters()
        info.cb = ctypes.sizeof(info)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        api = ctypes.WinDLL('psapi', use_last_error=True)
        api.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(info), info.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return round(info.peak_working_set / (1024 ** 2), 2)
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(value / (1024 ** 2 if platform.system() == 'Darwin' else 1024), 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--pages', type=int)
    parser.add_argument('--start-page', type=int, default=1, help='First physical PDF page (1-based)')
    parser.add_argument('--output', type=Path, default=Path('reports/document-performance.json'))
    args = parser.parse_args()
    os.environ['RAGIT_AUTH_MODE'] = 'local'
    from pypdf import PdfReader, PdfWriter
    from app import indexing, ingest, config
    from app.processing import observer
    from app.embeddings import get_embedding_model
    source_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
        Path('app/ingest.py'), Path('app/ocr.py'), Path('app/embeddings.py'), Path('app/indexing.py'))}

    contents = args.input.read_bytes()
    original_pages = len(PdfReader(io.BytesIO(contents)).pages)
    if not 1 <= args.start_page <= original_pages or (args.pages is not None and args.pages < 1):
        parser.error('Choose a valid start page and a positive page count.')
    if args.pages or args.start_page != 1:
        reader, writer = PdfReader(io.BytesIO(contents)), PdfWriter()
        start = args.start_page - 1
        stop = start + args.pages if args.pages else original_pages
        for page in reader.pages[start:stop]:
            writer.add_page(page)
        buffer = io.BytesIO()
        writer.write(buffer)
        contents = buffer.getvalue()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    progress_path = args.output.with_suffix('.progress.json')
    started = time.perf_counter()
    last = [0.0, '']

    def progress(stage, completed=None, total=None):
        now = time.perf_counter()
        if stage != last[1] or now - last[0] > 2:
            progress_path.write_text(json.dumps({'stage': stage, 'completed': completed,
                                                'total': total, 'elapsed_seconds': round(now - started, 2)}))
            last[:] = [now, stage]

    token = observer.set(progress)
    try:
        with tempfile.TemporaryDirectory(prefix='ragit-benchmark-') as directory:
            root = Path(directory)
            indexing.CACHE_DIR = root / 'cache'
            ingest.DOCS_DIR = root / 'docs'
            ingest.PREVIEWS_DIR = root / 'previews'
            config.DOCS_DIR = ingest.DOCS_DIR
            config.PREVIEWS_DIR = ingest.PREVIEWS_DIR
            for folder in (indexing.CACHE_DIR, ingest.DOCS_DIR, ingest.PREVIEWS_DIR):
                folder.mkdir()
            model_started = time.perf_counter()
            get_embedding_model()
            preload = time.perf_counter() - model_started
            cold = indexing.prepare_document(contents, args.input.name)
            cold_metrics = {key: cold[key] for key in ('pages', 'total_chunks', 'indexing_duration_ms', 'stage_timings_ms', 'cache_hit', 'cache_warning')}
            del cold
            warm = indexing.prepare_document(contents, args.input.name)
            report = {'source_filename': args.input.name, 'source_pages': original_pages,
                      'start_page': args.start_page,
                      'input_bytes': len(contents), 'platform': platform.platform(),
                      'cpu_count': os.cpu_count(), 'embedding_threads': config.EMBEDDING_THREADS,
                      'model_preload_seconds': preload, 'cold': cold_metrics,
                      'peak_process_memory_mib': peak_memory_mib(), 'source_sha256': source_hashes,
                      'warm': {key: warm[key] for key in cold_metrics},
                      'scope': 'Real extraction, OCR, embeddings and cache reuse. Excludes hosted answer generation and concurrent-user load.'}
            args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report, indent=2), flush=True)
            progress('complete')
    except Exception as exc:
        args.output.write_text(json.dumps({
            'status': 'failed', 'error': str(exc), 'start_page': args.start_page,
            'requested_pages': args.pages, 'source_pages': original_pages,
            'elapsed_seconds': round(time.perf_counter() - started, 2),
            'peak_process_memory_mib': peak_memory_mib(), 'source_sha256': source_hashes,
        }, indent=2), encoding='utf-8')
        progress('failed')
        raise
    finally:
        observer.reset(token)


if __name__ == '__main__':
    main()
