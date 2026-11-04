"""
Comprehensive test suite for multi-format document support & complex table extraction.
Validates:
1. Standalone Images (.png, .jpg, .webp, .tiff) with OCR, WebP preview, and visual AST nodes.
2. Spreadsheets (.csv, .xlsx) with multi-sheet parsing and merged cell spans.
3. Word Documents (.docx) with Heading-to-Section hierarchy, paragraphs, and native tables.
4. PowerPoint Presentations (.pptx) with slide-to-page mapping, shape text, and slide tables.
5. Complex table header hierarchy, merged cell forward-filling, and deterministic table answers.
6. API upload endpoint format validation.
"""
import io
import uuid
import zipfile
import pytest
from PIL import Image, ImageDraw

from app import config as cfg
from app.ast_builder import ASTNodeType
from app.format_extractors import (
    extract_pages_from_csv,
    extract_pages_from_xlsx,
    extract_pages_from_docx,
    extract_pages_from_pptx,
    extract_pages_from_image,
)
from app.indexing import prepare_document
from app.pdf_tables import normalize_table_headers_and_spans
from app.table_answers import table_answer


def create_mock_csv():
    uid = uuid.uuid4().hex[:6]
    return (
        f"Year,Quarter,Metric,Amount_{uid}\n"
        "2025,Q1,Operating Revenue,$12.5M\n"
        "2025,Q1,Net Profit,$3.2M\n"
        "2025,Q2,Operating Revenue,$15.8M\n"
        "2025,Q2,Net Profit,$4.1M\n"
    ).encode("utf-8")


def create_mock_xlsx():
    uid = uuid.uuid4().hex[:6]
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""")
        zf.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Q1_Summary" sheetId="1" r:id="rId1"/>
    <sheet name="Q2_Summary" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>""")
        zf.writestr("xl/sharedStrings.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="8" uniqueCount="8">
  <si><t>Department_{uid}</t></si>
  <si><t>Budget</t></si>
  <si><t>Spent</t></si>
  <si><t>Engineering</t></si>
  <si><t>$500,000</t></si>
  <si><t>$450,000</t></si>
  <si><t>Marketing</t></si>
  <si><t>$200,000</t></si>
</sst>""")
        zf.writestr("xl/worksheets/sheet1.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
      <c r="C1" t="s"><v>2</v></c>
    </row>
    <row r="2">
      <c r="A2" t="s"><v>3</v></c>
      <c r="B2" t="s"><v>4</v></c>
      <c r="C2" t="s"><v>5</v></c>
    </row>
  </sheetData>
</worksheet>""")
        zf.writestr("xl/worksheets/sheet2.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
    </row>
    <row r="2">
      <c r="A2" t="s"><v>6</v></c>
      <c r="B2" t="s"><v>7</v></c>
    </row>
  </sheetData>
</worksheet>""")
    return bio.getvalue()


def create_mock_docx():
    uid = uuid.uuid4().hex[:6]
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>System Architecture &amp; Latency Specifications {uid}</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>The core engine uses LanceDB for vector storage and FastEmbed for embeddings.</w:t></w:r>
    </w:p>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading2"/></w:pPr>
      <w:r><w:t>Performance Metrics</w:t></w:r>
    </w:p>
    <w:p>
      <w:pPr><w:pStyle w:val="ListBullet"/></w:pPr>
      <w:r><w:t>Sub-100 millisecond retrieval latency</w:t></w:r>
    </w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Component</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Measured Latency</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Hybrid RRF</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>14ms</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>""")
    return bio.getvalue()


def create_mock_pptx():
    uid = uuid.uuid4().hex[:6]
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/slides/slide1.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Executive Briefing {uid}</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>RagIT delivers sub-second grounded answers with verified visual proof.</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>""")
        zf.writestr("ppt/slides/slide2.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Cost &amp; Scaling</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
      <p:graphicFrame>
        <a:graphic>
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">
            <a:tbl>
              <a:tr>
                <a:tc><a:txBody><a:p><a:r><a:t>Metric</a:t></a:r></a:p></a:txBody></a:tc>
                <a:tc><a:txBody><a:p><a:r><a:t>Value</a:t></a:r></a:p></a:txBody></a:tc>
              </a:tr>
              <a:tr>
                <a:tc><a:txBody><a:p><a:r><a:t>API Burn</a:t></a:r></a:p></a:txBody></a:tc>
                <a:tc><a:txBody><a:p><a:r><a:t>$0.00 Local</a:t></a:r></a:p></a:txBody></a:tc>
              </a:tr>
            </a:tbl>
          </a:graphicData>
        </a:graphic>
      </p:graphicFrame>
    </p:spTree>
  </p:cSld>
</p:sld>""")
    return bio.getvalue()


def create_mock_image():
    uid = uuid.uuid4().hex[:6]
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 30), f"SERVICE LEVEL AGREEMENT {uid}", fill=(0, 0, 0))
    draw.text((20, 80), "Uptime Guarantee: 99.99 percent availability", fill=(0, 0, 0))
    draw.text((20, 130), "Penalty Credit: 15 percent invoice rebate", fill=(0, 0, 0))
    draw.rectangle([15, 20, 580, 280], outline=(0, 0, 0), width=2)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


def test_csv_extraction_and_indexing():
    csv_bytes = create_mock_csv()
    fname = f"financials_{uuid.uuid4().hex[:6]}.csv"
    pages = extract_pages_from_csv(csv_bytes, fname)
    assert len(pages) == 1
    assert "Operating Revenue" in pages[0]["text"]
    assert pages[0]["tables"] is not None

    # End-to-end indexing
    result = prepare_document(csv_bytes, fname)
    assert result["doc_id"].startswith("doc_")
    assert result["pages"] == 1
    ast = result["ast"]
    assert ast.root_id in ast.nodes

    # Verify retrieval
    retriever = result["retriever"]
    results = retriever.retrieve("What was the Net Profit for Q1?", top_k=2)
    assert len(results) > 0
    text_content = (results[0].get("parent_text") or "") + " " + (results[0].get("child_text") or "")
    assert "3.2M" in text_content or "Net Profit" in text_content


def test_xlsx_multi_sheet_and_indexing():
    xlsx_bytes = create_mock_xlsx()
    fname = f"quarterly_budget_{uuid.uuid4().hex[:6]}.xlsx"
    pages = extract_pages_from_xlsx(xlsx_bytes, fname)
    assert len(pages) == 2
    assert "Q1_Summary" in pages[0]["text"]
    assert "Engineering" in pages[0]["text"]
    assert "Q2_Summary" in pages[1]["text"]
    assert "Marketing" in pages[1]["text"]

    # End-to-end indexing
    result = prepare_document(xlsx_bytes, fname)
    assert result["pages"] == 2
    retriever = result["retriever"]
    results = retriever.retrieve("Engineering Budget", top_k=2)
    assert len(results) > 0
    text_content = (results[0].get("parent_text") or "") + " " + (results[0].get("child_text") or "")
    assert "$500,000" in text_content or "Engineering" in text_content


def test_docx_headings_and_tables_indexing():
    docx_bytes = create_mock_docx()
    fname = f"architecture_{uuid.uuid4().hex[:6]}.docx"
    pages = extract_pages_from_docx(docx_bytes, fname)
    assert len(pages) == 1
    text = pages[0]["text"]
    assert "System Architecture" in text
    assert "## Performance Metrics" in text
    assert "Hybrid RRF" in text

    # End-to-end indexing
    result = prepare_document(docx_bytes, fname)
    ast = result["ast"]
    section_nodes = [n for n in ast.nodes.values() if n.type == ASTNodeType.SECTION]
    assert len(section_nodes) >= 1
    titles = [n.title for n in section_nodes]
    assert any("Performance" in t for t in titles)

    retriever = result["retriever"]
    results = retriever.retrieve("Hybrid RRF latency", top_k=2)
    assert len(results) > 0
    text_content = (results[0].get("parent_text") or "") + " " + (results[0].get("child_text") or "")
    assert "14ms" in text_content or "Hybrid RRF" in text_content


def test_pptx_slide_mapping_and_indexing():
    pptx_bytes = create_mock_pptx()
    fname = f"briefing_{uuid.uuid4().hex[:6]}.pptx"
    pages = extract_pages_from_pptx(pptx_bytes, fname)
    assert len(pages) == 2
    assert pages[0]["page"] == 1
    assert "Executive Briefing" in pages[0]["text"]
    assert pages[1]["page"] == 2
    assert "Cost & Scaling" in pages[1]["text"]
    assert "API Burn" in pages[1]["text"]

    # End-to-end indexing
    result = prepare_document(pptx_bytes, fname)
    assert result["pages"] == 2
    retriever = result["retriever"]
    results = retriever.retrieve("API Burn local cost", top_k=2)
    assert len(results) > 0
    text_content = (results[0].get("parent_text") or "") + " " + (results[0].get("child_text") or "")
    assert "$0.00" in text_content or "Local" in text_content


def test_standalone_image_extraction_and_previews(tmp_path):
    img_bytes = create_mock_image()
    fname = f"sla_scan_{uuid.uuid4().hex[:6]}.png"
    doc_id = f"doc_{uuid.uuid4().hex}"
    pages, previews = extract_pages_from_image(img_bytes, fname, doc_id)
    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert "extraction" in pages[0]
    assert pages[0]["extraction"]["has_visual_objects"] is True

    # Check that preview WebP file was generated
    preview_file = cfg.PREVIEWS_DIR / f"{doc_id}_page_1.webp"
    assert preview_file.exists()

    # End-to-end indexing
    result = prepare_document(img_bytes, fname)
    ast = result["ast"]
    visual_nodes = [n for n in ast.nodes.values() if n.type == ASTNodeType.VISUAL]
    assert len(visual_nodes) >= 1
    assert visual_nodes[0].image_url == f"/api/preview/{result['doc_id']}/1"


def test_complex_table_hierarchical_headers_and_spans():
    # Multi-level hierarchical header test
    raw_rows = [
        ["Region", "2024", ""],
        ["", "Revenue", "Profit"],
        ["North America", "$50M", "$12M"],
        ["EMEA", "$35M", "$8M"]
    ]
    normalized = normalize_table_headers_and_spans(raw_rows)
    assert normalized[0] == ["Region", "2024 > Revenue", "2024 > Profit"]
    assert normalized[1] == ["North America", "$50M", "$12M"]
    assert normalized[2] == ["EMEA", "$35M", "$8M"]

    # Convert to Markdown table and verify deterministic table_answer
    md_table = (
        "| Region | 2024 > Revenue | 2024 > Profit |\n"
        "| --- | --- | --- |\n"
        "| North America | $50M | $12M |\n"
        "| EMEA | $35M | $8M |\n"
    )
    ans = table_answer("What was the 2024 Revenue for EMEA?", md_table)
    assert ans != ""
    assert "$35M" in ans

    profit_ans = table_answer("What was the 2024 Profit for North America?", md_table)
    assert profit_ans != ""
    assert "$12M" in profit_ans


def test_supported_extensions_validation():
    assert ".pdf" in cfg.SUPPORTED_EXTENSIONS
    assert ".docx" in cfg.SUPPORTED_EXTENSIONS
    assert ".xlsx" in cfg.SUPPORTED_EXTENSIONS
    assert ".csv" in cfg.SUPPORTED_EXTENSIONS
    assert ".pptx" in cfg.SUPPORTED_EXTENSIONS
    assert ".png" in cfg.SUPPORTED_EXTENSIONS
    assert ".jpg" in cfg.SUPPORTED_EXTENSIONS
    assert ".webp" in cfg.SUPPORTED_EXTENSIONS


def test_upload_endpoint_extension_validation():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    bad_res = client.post("/upload-jobs", files={"file": ("malware.exe", b"test", "application/octet-stream")})
    assert bad_res.status_code == 400
    assert "Unsupported file format" in bad_res.json()["detail"]

    good_csv = client.post("/upload-jobs", files={"file": ("sheet.csv", b"a,b\n1,2\n", "text/csv")})
    assert good_csv.status_code == 202
    assert good_csv.json()["status"] == "processing"
