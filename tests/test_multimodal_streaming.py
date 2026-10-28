import pytest
from pathlib import Path
from unittest.mock import MagicMock
import app.generator as generator
import app.config as cfg


def test_resolve_crop_bytes_existing(tmp_path, monkeypatch):
    test_crops_dir = tmp_path / "crops"
    test_crops_dir.mkdir()
    fake_crop = test_crops_dir / "sample_crop.webp"
    fake_crop.write_bytes(b"WEBP_DATA_HEADER_12345")

    monkeypatch.setattr(cfg, "CROPS_DIR", test_crops_dir)

    result = generator.resolve_crop_bytes("/static/crops/sample_crop.webp")
    assert result == b"WEBP_DATA_HEADER_12345"

    # Query params stripped correctly
    result_with_param = generator.resolve_crop_bytes("/static/crops/sample_crop.webp?v=123")
    assert result_with_param == b"WEBP_DATA_HEADER_12345"


def test_resolve_crop_bytes_missing_or_invalid():
    assert generator.resolve_crop_bytes("") is None
    assert generator.resolve_crop_bytes(None) is None
    assert generator.resolve_crop_bytes("/other/path/image.png") is None
    assert generator.resolve_crop_bytes("/static/crops/nonexistent_file_xyz123.webp") is None


def test_extract_chunk_images(monkeypatch):
    monkeypatch.setattr(generator, "resolve_crop_bytes", lambda url: b"IMAGE_BYTES" if "valid" in url else None)

    chunks = [
        {
            "citation_id": 1,
            "page": 2,
            "image_url": "/static/crops/valid_1.webp",
            "linked_visuals": [
                {"title": "Chart A", "image_url": "/static/crops/valid_2.webp", "page": 2}
            ]
        },
        {
            "citation_id": 2,
            "page": 3,
            "image_url": "/static/crops/valid_1.webp",  # Duplicate, should be deduplicated
            "linked_visuals": [
                {"title": "Diagram B", "image_url": "/static/crops/valid_3.webp", "page": 3}
            ]
        }
    ]

    images = generator.extract_chunk_images(chunks, max_images=3)
    assert len(images) == 3
    labels = [label for label, data in images]
    assert any("Excerpt [1]" in l for l in labels)
    assert any("Chart A" in l for l in labels)
    assert any("Diagram B" in l for l in labels)
    for label, data in images:
        assert data == b"IMAGE_BYTES"


def test_build_multimodal_payload():
    images = [
        ("Figure 1", b"TEST_IMAGE_BYTES_1"),
        ("Table 2", b"TEST_IMAGE_BYTES_2"),
    ]
    payload = generator.build_multimodal_payload("Explain this diagram.", images)
    assert len(payload) == 5  # 1 base prompt + (1 label text + 1 image_url) * 2
    assert payload[0]["type"] == "text"
    assert payload[0]["text"] == "Explain this diagram."
    assert payload[1]["type"] == "text"
    assert "Figure 1" in payload[1]["text"]
    assert payload[2]["type"] == "image_url"
    assert payload[2]["image_url"]["url"].startswith("data:image/webp;base64,")


def test_stream_multimodal_gemini_routing(monkeypatch):
    # Setup mock Gemini client
    mock_chunk_1 = MagicMock()
    mock_chunk_1.choices = [MagicMock()]
    mock_chunk_1.choices[0].delta.content = "The diagram shows "
    mock_chunk_2 = MagicMock()
    mock_chunk_2.choices = [MagicMock()]
    mock_chunk_2.choices[0].delta.content = "a blue circle [1]."

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = [mock_chunk_1, mock_chunk_2]

    monkeypatch.setattr(generator, "has_valid_fallback_key", lambda: True)
    monkeypatch.setattr(generator, "get_fallback_client", lambda **kw: mock_client)
    monkeypatch.setattr(generator, "resolve_crop_bytes", lambda url: b"FAKE_WEBP")

    chunks = [
        {"citation_id": 1, "page": 1, "parent_text": "Overview of system.", "image_url": "/static/crops/diagram.webp"}
    ]

    # Visual query targeting the diagram
    tokens = list(generator.stream_grounded_answer("What does the diagram show?", chunks))
    assert tokens == ["The diagram shows ", "a blue circle [1]."]

    # Verify that mock_client was called with multimodal message format
    assert mock_client.chat.completions.create.called
    call_args = mock_client.chat.completions.create.call_args[1]
    user_msg = next(m for m in call_args["messages"] if m["role"] == "user")
    assert isinstance(user_msg["content"], list)
    assert any(part.get("type") == "image_url" for part in user_msg["content"])
