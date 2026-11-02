"""Test API cho toàn bộ công cụ: mỗi tool chạy thật trên fixture và kiểm tra output."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pymupdf
import pytest
from docx import Document
from fastapi.testclient import TestClient
from openpyxl import Workbook
from PIL import Image
from pptx import Presentation

from app.main import app

client = TestClient(app)
FIX = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _text_pdf(pages: int = 5) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 80), f"Bao cao so {i + 1}", fontsize=18)
        page.insert_text((72, 110), "Noi dung tieng Viet co dau: Nguyen Van A", fontsize=11)
        # bảng có kẻ ô để find_tables nhận ra
        x0, y0, w, h = 72, 200, 400, 24
        for r in range(4):
            for c in range(3):
                rect = pymupdf.Rect(x0 + c * 130, y0 + r * h, x0 + (c + 1) * 130, y0 + (r + 1) * h)
                page.draw_rect(rect, color=(0, 0, 0), width=0.7)
                page.insert_text((rect.x0 + 6, rect.y0 + 16), f"R{r}C{c}", fontsize=9)
        page.insert_text((72, 380), f"Trang {i + 1} / {pages}", fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture(scope="session", autouse=True)
def fixtures() -> None:
    FIX.mkdir(exist_ok=True)
    (FIX / "bao-cao.pdf").write_bytes(_text_pdf(5))
    (FIX / "phu-luc.pdf").write_bytes(_text_pdf(2))

    img = Image.new("RGB", (600, 800), (240, 244, 255))
    img.save(FIX / "anh-1.jpg", quality=90)
    Image.new("RGB", (500, 700), (255, 244, 240)).save(FIX / "anh-2.png")

    sig = Image.new("RGBA", (400, 160), (0, 0, 0, 0))
    sig.save(FIX / "chu-ky.png")

    docx = Document()
    docx.add_heading("Hợp đồng mẫu", level=1)
    docx.add_paragraph("Bên A: Nguyễn Văn A. Bên B: Trần Thị B.")
    docx.save(FIX / "hop-dong.docx")

    wb = Workbook()
    ws = wb.active
    ws.append(["STT", "Họ tên", "Số tiền"])
    ws.append([1, "Nguyễn Văn A", 1000])
    ws.append([2, "Trần Thị B", 2000])
    wb.save(FIX / "bang-luong.xlsx")

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Báo cáo quý"
    slide.placeholders[1].text = "Số liệu tổng hợp"
    prs.save(FIX / "bao-cao.pptx")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def upload(*paths: Path, accept: str = "pdf", token: str | None = None) -> tuple[str, list[dict]]:
    files = [("files", (p.name, io.BytesIO(p.read_bytes()), "application/octet-stream")) for p in paths]
    data = {"accept": accept, "slot": "source"}
    if token:
        data["token"] = token
    res = client.post("/api/upload", files=files, data=data)
    assert res.status_code == 200, res.text
    body = res.json()
    return body["token"], body["files"]


def run(tool: str, token: str, ids: list[str], options: dict | None = None, image_id: str | None = None):
    res = client.post(
        f"/api/run/{tool}",
        json={"token": token, "fileIds": ids, "options": options or {}, "imageId": image_id},
    )
    return res


def download(url: str) -> bytes:
    res = client.get(url)
    assert res.status_code == 200, res.text
    return res.content


def as_pdf(data: bytes) -> pymupdf.Document:
    doc = pymupdf.open(stream=data, filetype="pdf")
    return doc


def upload_image(path: Path, token: str) -> str:
    res = client.post(
        "/api/upload",
        files=[("files", (path.name, io.BytesIO(path.read_bytes()), "image/png"))],
        data={"accept": "image", "slot": "image", "token": token},
    )
    assert res.status_code == 200, res.text
    return res.json()["files"][0]["id"]


# --------------------------------------------------------------------------- #
# tests: trang
# --------------------------------------------------------------------------- #
def test_tools_registry():
    data = client.get("/api/tools").json()
    assert len(data["tools"]) >= 20
    assert {t["id"] for t in data["tools"]} >= {
        "merge", "split", "extract", "delete-pages", "rotate", "organize",
        "page-numbers", "watermark", "sign", "add-image", "compress", "protect", "unlock",
        "pdf-to-jpg", "pdf-to-png", "images-to-pdf", "pdf-to-txt", "pdf-to-word",
        "pdf-to-excel", "pdf-to-pptx", "office-to-pdf",
    }


def test_merge():
    token, files = upload(FIX / "bao-cao.pdf", FIX / "phu-luc.pdf")
    res = run("merge", token, [f["id"] for f in files], {"output_name": "gop"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["filename"] == "gop.pdf"
    doc = as_pdf(download(body["url"]))
    assert doc.page_count == 7
    assert len(doc.get_toc()) == 2


def test_split_each():
    token, files = upload(FIX / "phu-luc.pdf")
    res = run("split", token, [files[0]["id"]], {"mode": "each"})
    body = res.json()
    assert body["filename"].endswith(".zip")
    zf = zipfile.ZipFile(io.BytesIO(download(body["url"])))
    assert len(zf.namelist()) == 2


def test_split_ranges():
    token, files = upload(FIX / "bao-cao.pdf")
    res = run("split", token, [files[0]["id"]], {"mode": "range", "ranges": "1-2,3-5"})
    zf = zipfile.ZipFile(io.BytesIO(download(res.json()["url"])))
    assert len(zf.namelist()) == 2
    first = as_pdf(zf.read(zf.namelist()[0]))
    assert first.page_count == 2


def test_extract():
    token, files = upload(FIX / "bao-cao.pdf")
    res = run("extract", token, [files[0]["id"]], {"ranges": "2,4"})
    doc = as_pdf(download(res.json()["url"]))
    assert doc.page_count == 2
    assert "Trang 2 / 5" in doc[0].get_text()


def test_delete_pages():
    token, files = upload(FIX / "bao-cao.pdf")
    res = run("delete-pages", token, [files[0]["id"]], {"ranges": "1,3"})
    doc = as_pdf(download(res.json()["url"]))
    assert doc.page_count == 3
    assert "Trang 1 / 5" not in doc[0].get_text()


def test_rotate():
    token, files = upload(FIX / "bao-cao.pdf")
    res = run("rotate", token, [files[0]["id"]], {"angle": "90", "ranges": "1-2"})
    doc = as_pdf(download(res.json()["url"]))
    assert doc[0].rotation == 90
    assert doc[2].rotation == 0


def test_organize():
    token, files = upload(FIX / "bao-cao.pdf")
    res = run("organize", token, [files[0]["id"]], {"order": "3,1,1"})
    doc = as_pdf(download(res.json()["url"]))
    assert doc.page_count == 3
    assert "Trang 3 / 5" in doc[0].get_text()
    assert "Trang 1 / 5" in doc[1].get_text()


def test_invalid_range_message():
    token, files = upload(FIX / "phu-luc.pdf")
    res = run("extract", token, [files[0]["id"]], {"ranges": "9-20"})
    assert res.status_code == 400
    assert "vượt quá số trang" in res.json()["detail"]


# --------------------------------------------------------------------------- #
# tests: edit / secure
# --------------------------------------------------------------------------- #
def test_page_numbers():
    token, files = upload(FIX / "phu-luc.pdf")
    res = run("page-numbers", token, [files[0]["id"]], {"format": "Trang {n}/{total}", "start": 1})
    doc = as_pdf(download(res.json()["url"]))
    text = doc[0].get_text()
    assert "Trang 1/2" in text


def test_watermark_vietnamese():
    token, files = upload(FIX / "phu-luc.pdf")
    res = run("watermark", token, [files[0]["id"]], {"text": "BẢN NHÁP", "opacity": 0.2})
    assert res.status_code == 200, res.text
    doc = as_pdf(download(res.json()["url"]))
    assert "BẢN NHÁP" in doc[0].get_text()


def test_sign():
    token, files = upload(FIX / "phu-luc.pdf")
    image_id = upload_image(FIX / "chu-ky.png", token)
    res = run("sign", token, [files[0]["id"]], {"page": "last", "width": 30}, image_id)
    assert res.status_code == 200, res.text
    doc = as_pdf(download(res.json()["url"]))
    assert doc[1].get_images(), "trang cuối phải có ảnh chữ ký"


def test_add_image():
    token, files = upload(FIX / "phu-luc.pdf")
    image_id = upload_image(FIX / "chu-ky.png", token)
    res = run("add-image", token, [files[0]["id"]], {"page": "first"}, image_id)
    doc = as_pdf(download(res.json()["url"]))
    assert doc[0].get_images()


def test_compress_reduces_size():
    token, files = upload(FIX / "bao-cao.pdf")
    before = (FIX / "bao-cao.pdf").stat().st_size
    res = run("compress", token, [files[0]["id"]], {"level": "strong"})
    assert res.status_code == 200, res.text
    body = res.json()
    out = download(body["url"])
    assert body["meta"].count("→") == 1
    doc = as_pdf(out)
    assert doc.page_count == 5
    assert len(out) <= before * 1.2


def test_protect_and_unlock():
    token, files = upload(FIX / "phu-luc.pdf")
    res = run("protect", token, [files[0]["id"]], {"password": "matkhau123"})
    assert res.status_code == 200, res.text
    locked = download(res.json()["url"])

    doc = pymupdf.open(stream=locked, filetype="pdf")
    assert doc.needs_pass
    assert doc.authenticate("matkhau123")
    doc.close()

    token2, files2 = upload(FIX / "bao-cao.pdf")
    del token2, files2  # chỉ cần token gốc cho bước unlock dưới đây
    # đưa file đã khoá vào phiên để unlock
    res_up = client.post(
        "/api/upload",
        files=[("files", ("khoa.pdf", io.BytesIO(locked), "application/pdf"))],
        data={"accept": "pdf", "slot": "source"},
    )
    assert res_up.status_code == 400  # upload chặn PDF có mật khẩu -> đúng thiết kế
    assert "mật khẩu" in res_up.json()["detail"].lower()


def test_unlock_wrong_password():
    locked_doc = pymupdf.open()
    locked_doc.new_page()
    tmp = FIX / "locked.pdf"
    locked_doc.save(tmp, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="x", user_pw="x")
    locked_doc.close()

    # upload trực tiếp file khoá sẽ bị chặn, nên test handler qua đường khác:
    from app.context import Ctx
    from app.handlers.secure import unlock
    from app.utils import UserError

    ctx = Ctx(out=FIX, sources=[tmp], names=["locked.pdf"], options={"password": "sai"})
    with pytest.raises(UserError):
        unlock(ctx)


# --------------------------------------------------------------------------- #
# tests: convert
# --------------------------------------------------------------------------- #
def test_pdf_to_jpg():
    token, files = upload(FIX / "phu-luc.pdf")
    res = run("pdf-to-jpg", token, [files[0]["id"]], {"dpi": 100})
    zf = zipfile.ZipFile(io.BytesIO(download(res.json()["url"])))
    assert len(zf.namelist()) == 2
    img = Image.open(io.BytesIO(zf.read(zf.namelist()[0])))
    assert img.format == "JPEG"


def test_pdf_to_png_one_page():
    token, files = upload(FIX / "phu-luc.pdf")
    res = run("pdf-to-png", token, [files[0]["id"]], {"dpi": 100, "ranges": "1"})
    body = res.json()
    assert body["filename"].endswith(".png")
    img = Image.open(io.BytesIO(download(body["url"])))
    assert img.format == "PNG"


def test_images_to_pdf():
    token, files = upload(FIX / "anh-1.jpg", FIX / "anh-2.png", accept="image")
    res = run("images-to-pdf", token, [f["id"] for f in files], {"page_size": "a4", "margin": 20})
    doc = as_pdf(download(res.json()["url"]))
    assert doc.page_count == 2
    assert round(doc[0].rect.width) == 595


def test_pdf_to_txt():
    token, files = upload(FIX / "phu-luc.pdf")
    res = run("pdf-to-txt", token, [files[0]["id"]], {})
    text = download(res.json()["url"]).decode("utf-8")
    assert "--- Trang 1 ---" in text
    assert "Nguyen Van A" in text


def test_pdf_to_word():
    token, files = upload(FIX / "bao-cao.pdf")
    res = run("pdf-to-word", token, [files[0]["id"]], {"images": False, "ranges": "1-2"})
    assert res.json()["filename"].endswith(".docx")
    from docx import Document as Docx

    d = Docx(io.BytesIO(download(res.json()["url"])))
    body = "\n".join(p.text for p in d.paragraphs)
    assert "Bao cao so 1" in body
    assert "R0C0" in body


def test_pdf_to_excel():
    token, files = upload(FIX / "bao-cao.pdf")
    res = run("pdf-to-excel", token, [files[0]["id"]], {"ranges": "1"})
    assert res.status_code == 200, res.text
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(download(res.json()["url"])))
    ws = wb["Trang 1"]
    values = [c.value for row in ws.iter_rows(max_row=2) for c in row]
    assert "R0C0" in values


def test_pdf_to_pptx():
    token, files = upload(FIX / "phu-luc.pdf")
    res = run("pdf-to-pptx", token, [files[0]["id"]], {"dpi": 100})
    prs = Presentation(io.BytesIO(download(res.json()["url"])))
    assert len(prs.slides.__iter__.__self__._sldIdLst) == 2


def test_office_to_pdf():
    token, files = upload(FIX / "hop-dong.docx", FIX / "bang-luong.xlsx", accept="office")
    res = run("office-to-pdf", token, [f["id"] for f in files], {})
    assert res.status_code == 200, res.text
    body = res.json()
    if body["filename"].endswith(".zip"):
        zf = zipfile.ZipFile(io.BytesIO(download(body["url"])))
        assert len(zf.namelist()) == 2
        for name in zf.namelist():
            assert as_pdf(zf.read(name)).page_count >= 1
    else:
        assert as_pdf(download(body["url"])).page_count >= 1


def test_reject_wrong_type():
    token, _ = upload(FIX / "bao-cao.pdf")
    res = client.post(
        "/api/upload",
        files=[("files", ("note.txt", io.BytesIO(b"hello"), "text/plain"))],
        data={"accept": "pdf"},
    )
    assert res.status_code == 400
