"""Test trình soạn thảo: áp ops lên PDF rồi kiểm tra kết quả thật."""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def session_pdf() -> tuple[str, str]:
    path = FIX / "bao-cao.pdf"
    assert path.exists(), "cần fixture từ test_tools (chạy cả bộ)"
    res = client.post(
        "/api/upload",
        files=[("files", ("bao-cao.pdf", io.BytesIO(path.read_bytes()), "application/pdf"))],
        data={"accept": "pdf", "slot": "source"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    return body["token"], body["files"][0]["id"]


def _edit(token: str, file_id: str, ops: list[dict]):
    return client.post("/api/edit", json={"token": token, "fileId": file_id, "ops": ops})


def test_page_image(session_pdf):
    token, file_id = session_pdf
    res = client.get(f"/api/page-image/{token}/{file_id}/1?dpi=100")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_edit_text_and_highlight(session_pdf):
    token, file_id = session_pdf
    ops = [
        {
            "type": "text",
            "page": 1,
            "rect": {"x": 10, "y": 40, "w": 60, "h": 8},
            "text": "Đã duyệt: Nguyễn Thị Khánh",
            "size": 13,
            "color": "#1d4ed8",
        },
        {"type": "highlight", "page": 1, "rect": {"x": 10, "y": 9, "w": 40, "h": 5}},
        {"type": "rect", "page": 2, "rect": {"x": 8, "y": 20, "w": 50, "h": 20}, "color": "#e11d48", "width": 2},
        {"type": "arrow", "page": 2, "rect": {"x": 10, "y": 60, "w": 30, "h": 10}, "color": "#0f766e"},
    ]
    res = _edit(token, file_id, ops)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["filename"].endswith("-edited.pdf")
    assert body["meta"] == "4 thao tác"

    data = client.get(body["url"]).content
    doc = pymupdf.open(stream=data, filetype="pdf")
    assert doc.page_count == 5
    text = doc[0].get_text()
    assert "Đã duyệt: Nguyễn Thị Khánh" in text          # chữ tiếng Việt có dấu
    assert doc[0].annots() is not None                    # highlight tạo annot
    assert "R0C0" in text                                 # nội dung gốc còn nguyên
    doc.close()


def test_edit_image_and_redact(session_pdf):
    token, file_id = session_pdf

    up = client.post(
        "/api/upload",
        files=[("files", ("chu-ky.png", io.BytesIO((FIX / "chu-ky.png").read_bytes()), "image/png"))],
        data={"accept": "image", "slot": "image", "token": token},
    )
    assert up.status_code == 200, up.text
    image_id = up.json()["files"][0]["id"]

    ops = [
        {"type": "image", "page": 1, "rect": {"x": 60, "y": 75, "w": 25, "h": 10}, "imageId": image_id},
        # xoá dòng "Trang 1 / 5" ở gần đáy trang 1
        {"type": "redact", "page": 1, "rect": {"x": 10, "y": 43, "w": 40, "h": 5}, "fill": "#ffffff"},
    ]
    res = _edit(token, file_id, ops)
    assert res.status_code == 200, res.text

    data = client.get(res.json()["url"]).content
    doc = pymupdf.open(stream=data, filetype="pdf")
    page = doc[0]
    assert page.get_images(), "phải có ảnh được chèn"
    assert "Trang 1 / 5" not in page.get_text(), "redact phải xoá được chữ"
    doc.close()


def test_edit_rejects_bad_ops(session_pdf):
    token, file_id = session_pdf

    bad_type = _edit(token, file_id, [{"type": "hack", "page": 1, "rect": {"x": 1, "y": 1, "w": 5, "h": 5}}])
    assert bad_type.status_code == 400

    bad_page = _edit(token, file_id, [{"type": "rect", "page": 99, "rect": {"x": 1, "y": 1, "w": 5, "h": 5}}])
    assert bad_page.status_code == 400
    assert "không tồn tại" in bad_page.json()["detail"]

    tiny = _edit(token, file_id, [{"type": "rect", "page": 1, "rect": {"x": 1, "y": 1, "w": 0.1, "h": 0.1}}])
    assert tiny.status_code == 400

    empty_text = _edit(token, file_id, [{"type": "text", "page": 1, "rect": {"x": 5, "y": 5, "w": 20, "h": 5}, "text": "  "}])
    assert empty_text.status_code == 400

    no_ops = _edit(token, file_id, [])
    assert no_ops.status_code == 400


def test_edit_unknown_file(session_pdf):
    token, _ = session_pdf
    res = _edit(token, "deadbeef.pdf", [{"type": "rect", "page": 1, "rect": {"x": 1, "y": 1, "w": 5, "h": 5}}])
    assert res.status_code == 400
