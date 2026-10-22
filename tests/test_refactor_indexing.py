import sqlite3
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pytest

import app.storage.embeddings as embeddings
import app.ingestion.indexing as indexing
import app.ingestion.ingest as ingest
import app.ingestion.ast_builder as ast_module
from app.ingestion.pdf_lock import PDF_LOCK
from tests.test_indexing_performance import isolated, small_pdf, TEXT


@pytest.fixture
def cached_model(monkeypatch, tmp_path):
    monkeypatch.setattr(embeddings, "EMBED_CACHE_PATH", tmp_path / "vectors.sqlite3")
    monkeypatch.setattr(embeddings, "_memory_cache", __import__("collections").OrderedDict())
    calls = []
    class Model:
        def embed(self, texts, batch_size):
            assert batch_size == 64
            calls.append(list(texts))
            for text in texts:
                vector = np.zeros(384, dtype=np.float32)
                vector[0] = len(text)
                vector[1] = sum(map(ord, text)) % 97 + 1
                yield vector
    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: Model())
    return calls


def test_bucketing_scatter_dedup_and_persistent_cache(cached_model):
    texts = ["Longest example sentence", "Short", "Longest example sentence", "Case", "case"]
    vectors = embeddings.embed_texts(texts)
    assert cached_model == [sorted(dict.fromkeys(texts), key=len)]
    np.testing.assert_array_equal(vectors[0], vectors[2])
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6)
    assert not np.array_equal(vectors[3], vectors[4])
    embeddings._memory_cache.clear()
    np.testing.assert_array_equal(vectors, embeddings.embed_texts(texts))
    assert len(cached_model) == 1


def test_second_document_boilerplate_needs_no_inference(isolated, cached_model, monkeypatch):
    monkeypatch.setattr(indexing, "embed_texts", embeddings.embed_texts)
    boilerplate = "The standard service agreement requires annual review."
    indexing.prepare_document((boilerplate + "\n\nFirst client requires monthly billing.").encode(), "first.txt")
    indexing.prepare_document((boilerplate + "\n\nSecond client requires quarterly billing.").encode(), "second.txt")
    assert sum(batch.count(boilerplate) for batch in cached_model) == 1
    assert sum(batch.count("Paragraph 1 (Page 1): " + boilerplate) for batch in cached_model) == 1


def test_corrupt_embedding_and_concurrent_requests(cached_model):
    embeddings.embed_texts(["A shared clause"])
    embeddings._memory_cache.clear()
    with sqlite3.connect(embeddings.EMBED_CACHE_PATH) as db:
        db.execute("UPDATE embeddings SET vector=?", (b"broken",))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: embeddings.embed_texts(["A shared clause"]), range(4)))
    assert len(cached_model) == 2
    for vector in results:
        np.testing.assert_array_equal(vector, results[0])


def test_parallel_pdf_extraction_matches_serial(isolated, monkeypatch):
    contents = small_pdf(3)
    monkeypatch.setattr(ingest, "PDF_PROCESS_WORKERS", 1)
    serial = ingest.extract_pages_from_pdf(contents, "pages.pdf")
    monkeypatch.setattr(ingest, "PDF_PROCESS_WORKERS", 2)
    monkeypatch.setattr(ingest, "PDF_PARALLEL_PAGE_THRESHOLD", 1)
    parallel = ingest.extract_pages_from_pdf(contents, "pages.pdf")
    assert parallel == serial
    assert [page["page"] for page in parallel] == [1, 2, 3]


def test_rendering_is_clipped_but_conversion_and_encoding_are_unlocked(isolated, monkeypatch):
    from app.ingestion.pdf_render import render_pdf_image, save_webp
    from PIL import Image
    original_to_pil = ingest.pdfium.PdfBitmap.to_pil
    original_save = Image.Image.save
    def to_pil(bitmap):
        assert not PDF_LOCK._is_owned()
        return original_to_pil(bitmap)
    def save(image, *args, **kwargs):
        assert not PDF_LOCK._is_owned()
        assert kwargs["method"] == 1 and kwargs["quality"] == 80
        return original_save(image, *args, **kwargs)
    monkeypatch.setattr(ingest.pdfium.PdfBitmap, "to_pil", to_pil)
    monkeypatch.setattr(Image.Image, "save", save)
    image = render_pdf_image(small_pdf(), 1, scale=2, bbox=(30, 200, 130, 280))
    assert image.size == (200, 160)
    save_webp(image, ast_module.CROPS_DIR / "clipped.webp")


def test_ingestion_never_touches_llm_clients(isolated, monkeypatch):
    import app.core.llm as llm
    def forbidden(*args, **kwargs):
        pytest.fail("Ingestion called an LLM client")
    for name in ("get_primary_client", "get_fallback_client", "get_openai_client", "get_genai_client"):
        monkeypatch.setattr(llm, name, forbidden)
    assert indexing.prepare_document(TEXT, "no-llm.txt")["total_chunks"] > 0


def test_visual_overlap_dedup_keeps_alias(isolated):
    box = {"bbox": (30, 200, 130, 280), "title": "Figure 1", "text": "Identical evidence"}
    nodes = ast_module.extract_halo_crops("alias_test", small_pdf(), {1: [box, box]}, render_crops=False)
    first_page = [node for node in nodes if node.page == 1]
    assert len(first_page) == 1
    ast = ast_module.DocumentAST("alias_test")
    ast.add_node(first_page[0])
    assert ast.get_node("alias_test_vis_p1_2") is first_page[0]


def test_explicit_table_continuations_preserve_rows_and_old_urls(isolated):
    pages = [
        {"page": 1, "text": "Table 1: Results\n| Region | Actual |\n| North | 90% |"},
        {"page": 2, "text": "Table 1: Results (continued)\n| Region | Actual |\n| South | 95% |"},
    ]
    ast = ast_module.build_document_ast("continued", pages, lazy_visuals=True)
    visuals = ast.get_visual_nodes()
    assert len(visuals) == 1
    assert "North" in visuals[0].text and "South" in visuals[0].text
    assert ast.get_node("continued_vis_tbl_2") is visuals[0]
    assert ast_module.get_or_render_visual_crop(ast, visuals[0]).exists()
    assert any(node.page == 2 and "South" in node.text for node in ast.get_leaves())


def test_eager_continuation_renders_all_parts_and_preserves_aliases(isolated):
    from PIL import Image
    pages = [
        {"page": 1, "text": "Table 1: Results\n| Region | Actual |\n| North | 90% |"},
        {"page": 2, "text": "Table 1: Results (continued)\n| Region | Actual |\n| South | 95% |"},
    ]
    eager = ast_module.build_document_ast("eager_continued", pages)
    lazy = ast_module.build_document_ast("lazy_continued", pages, lazy_visuals=True)
    eager_crop = ast_module.get_or_render_visual_crop(eager, eager.get_visual_nodes()[0])
    lazy_crop = ast_module.get_or_render_visual_crop(lazy, lazy.get_visual_nodes()[0])
    with Image.open(eager_crop) as left, Image.open(lazy_crop) as right:
        assert left.size == right.size
        assert left.tobytes() == right.tobytes()
    assert (ast_module.CROPS_DIR / "eager_continued_vis_tbl_2.webp").read_bytes() == eager_crop.read_bytes()
    assert eager.get_visual_nodes()[0].image_url.startswith("/static/crops/")


def test_lance_table_handle_cache_refreshes_on_overwrite(tmp_path, monkeypatch):
    from app.storage.vector_store import LanceVectorStore
    store = LanceVectorStore(tmp_path / "lance")
    ast = ast_module.DocumentAST("replace")
    ast.add_node(ast_module.ASTNode("old", ast_module.ASTNodeType.PARAGRAPH, "Old", "Old content", 1, "root/old"))
    vector = np.ones((1, 384), dtype=np.float32) / np.sqrt(384)
    store.index_ast(ast, vector)
    store._tables.clear()
    opened = []
    original = store.db.open_table
    def open_table(name):
        opened.append(name)
        return original(name)
    monkeypatch.setattr(store.db, "open_table", open_table)
    assert store.has_document(ast.doc_id)
    assert store.search(ast.doc_id, vector[0])[0]["text"] == "Old content"
    assert len(opened) == 1
    ast.get_node("old").text = "New content"
    store.index_ast(ast, vector)
    assert store.has_document(ast.doc_id)
    assert store.search(ast.doc_id, vector[0])[0]["text"] == "New content"
    assert len(opened) == 1
