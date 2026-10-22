"""Repeatable local benchmark. Never calls an LLM or modifies input documents.

python scripts/bench_indexing.py --output reports/indexing-before.json
Cold means empty application caches and a fresh process; downloaded model files remain.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker(path):
    import psutil
    import numpy as np
    import app.config as cfg
    import app.embeddings as embeddings
    import app.indexing as indexing
    import app.ingest as ingest
    import app.ast_builder as ast_builder
    from app.vector_store import LanceVectorStore

    work = Path(tempfile.mkdtemp(prefix="benchmark-", dir=ROOT / "data/index"))
    for name, folder in (("DOCS_DIR", "docs"), ("PREVIEWS_DIR", "previews"), ("CROPS_DIR", "crops")):
        target = work / folder
        target.mkdir()
        for module in (cfg, ingest, ast_builder):
            if hasattr(module, name):
                setattr(module, name, target)
    indexing.CACHE_DIR = work / "documents"
    if hasattr(embeddings, "EMBED_CACHE_PATH"):
        embeddings.EMBED_CACHE_PATH = work / "embeddings.sqlite3"
    process = psutil.Process()
    peak = [0]
    stop = threading.Event()

    def sample_rss():
        while not stop.is_set():
            total = 0
            for proc in [process] + process.children(recursive=True):
                try:
                    total += proc.memory_info().rss
                except psutil.Error:
                    pass
            peak[0] = max(peak[0], total)
            stop.wait(0.01)

    monitor = threading.Thread(target=sample_rss, daemon=True)
    monitor.start()
    calls, inferred = [0], [0]
    original_loader = embeddings.get_embedding_model

    class CountedModel:
        def embed(self, texts, **kwargs):
            batch = list(texts)
            calls[0] += 1
            inferred[0] += len(batch)
            return original_loader().embed(batch, **kwargs)

    embeddings.get_embedding_model = lambda: CountedModel()
    contents = path.read_bytes()
    begin = time.perf_counter()
    cold = indexing.prepare_document(contents, path.name)
    ready_ms = (time.perf_counter() - begin) * 1000
    child_calls = calls[0]
    store = LanceVectorStore(work / "lance")
    store.index_ast(cold["ast"])
    complete_ms = (time.perf_counter() - begin) * 1000
    document_calls = calls[0]
    warm_begin = time.perf_counter()
    warm = indexing.prepare_document(contents, path.name)
    warm_ms = (time.perf_counter() - warm_begin) * 1000
    assert warm["cache_hit"]
    np.save(work / "vectors.npy", cold["retriever"].embeddings)
    crop_ms = []
    for node in cold["ast"].get_visual_nodes()[:5]:
        started = time.perf_counter()
        ast_builder.get_or_render_visual_crop(cold["ast"], node)
        crop_ms.append((time.perf_counter() - started) * 1000)
    before_similar = inferred[0]
    similar_requests = None
    if path.suffix.lower() != ".pdf":
        requested = [0]
        original_embed = indexing.embed_texts
        def count_requested(texts):
            requested[0] += len(set(texts))
            return original_embed(texts)
        indexing.embed_texts = count_requested
        similar = indexing.prepare_document(contents + b"\n\nAdditional retention policy requires annual review.", "similar.txt")
        similar_requests = requested[0]
    similar_inferred = inferred[0] - before_similar
    stop.set()
    monitor.join()
    return {
        "file": path.name, "bytes": len(contents), "pages": cold["pages"],
        "chunks": cold["total_chunks"], "model": cfg.DEFAULT_EMBED_MODEL,
        "cold_ready_ms": round(ready_ms, 2), "cold_complete_ms": round(complete_ms, 2),
        "warm_ms": round(warm_ms, 2), "child_model_calls": child_calls,
        "model_calls_per_document": document_calls,
        "second_similar_cache_hit_rate": round(1 - similar_inferred / similar_requests, 4) if similar_requests else None,
        "chunks_per_second": round(cold["total_chunks"] / (ready_ms / 1000), 2),
        "peak_rss_mb": round(peak[0] / 1024**2, 2),
        "crop_render_encode_ms": round(sum(crop_ms) / len(crop_ms), 2) if crop_ms else None,
        "stages_ms": cold["stage_timings_ms"], "artifacts": str(work),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/indexing-benchmark.json")
    parser.add_argument("--pdf", type=Path, default=ROOT / "data/docs/comporgLesson1_handout.pdf")
    parser.add_argument("--worker", type=Path)
    args = parser.parse_args()
    if args.worker:
        print("BENCHMARK_JSON=" + json.dumps(worker(args.worker.resolve())))
        return
    results = []
    for source in (ROOT / "data/docs/sample_enterprise_sop.txt", args.pdf):
        if not source.is_file():
            parser.error(f"Missing benchmark input: {source}. Use --pdf with a real large PDF.")
        output = subprocess.check_output([sys.executable, __file__, "--worker", str(source.resolve())], text=True)
        result = json.loads(next(line.split("=", 1)[1] for line in output.splitlines() if line.startswith("BENCHMARK_JSON=")))
        results.append(result)
        print(json.dumps(result, indent=2), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"cold_definition": "fresh process and empty application caches; model download excluded", "results": results}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
