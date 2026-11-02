"""PDF House Local — bộ công cụ PDF chạy hoàn toàn trên máy.

Chạy: ./run.sh  (mặc định http://127.0.0.1:8077)
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

import pymupdf
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .context import Ctx
from .handlers import HANDLERS
from .handlers.editor import apply_ops
from .registry import GROUPS, TOOL_MAP, TOOLS
from .utils import UserError, human_size, open_pdf, safe_name, stem, zip_outputs

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
SESSIONS_DIR = BASE_DIR / "data" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILES = 30
MAX_FILE_MB = 100
MAX_TOTAL_MB = 400
SESSION_TTL = 7200

PDF_EXT = {".pdf"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
OFFICE_EXT = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".rtf", ".txt", ".csv"}

app = FastAPI(title="PDF House Local", docs_url="/api/docs", redoc_url=None)


@app.exception_handler(UserError)
def _user_error(_request, exc: UserError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=400)


# --------------------------------------------------------------------------- #
# session helpers
# --------------------------------------------------------------------------- #
def purge_expired() -> None:
    cutoff = time.time() - SESSION_TTL
    for d in SESSIONS_DIR.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            continue


def _session(token: str, create: bool = False) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", token or ""):
        raise HTTPException(400, "Token không hợp lệ.")
    path = SESSIONS_DIR / token
    if create:
        (path / "src").mkdir(parents=True, exist_ok=True)
        (path / "out").mkdir(parents=True, exist_ok=True)
    elif not path.is_dir():
        raise HTTPException(404, "Phiên đã hết hạn, hãy tải file lại.")
    return path


def _manifest(session: Path) -> dict:
    path = session / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _save_manifest(session: Path, manifest: dict) -> None:
    (session / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def _check_ext(name: str, accept: str) -> None:
    ext = Path(name).suffix.lower()
    allowed = {"pdf": PDF_EXT, "image": IMAGE_EXT, "office": OFFICE_EXT}.get(accept, PDF_EXT)
    if ext not in allowed:
        raise UserError(f"'{name}' không đúng định dạng cho công cụ này ({', '.join(sorted(allowed))}).")


def _thumb(doc: pymupdf.Document, width: int = 150) -> str:
    page = doc[0]
    zoom = width / max(page.rect.width, 1)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()


def _image_thumb(path: Path, width: int = 150) -> str:
    with pymupdf.open(path) as doc:
        page = doc[0]
        zoom = width / max(page.rect.width, 1)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()


# --------------------------------------------------------------------------- #
# API models
# --------------------------------------------------------------------------- #
class RunRequest(BaseModel):
    token: str
    fileIds: list[str] = Field(default_factory=list)
    options: dict = Field(default_factory=dict)
    imageId: str | None = None


class EditRequest(BaseModel):
    token: str
    fileId: str
    ops: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "engine": f"pymupdf {pymupdf.__version__}",
        "tools": len(TOOLS),
        "limits": {"max_files": MAX_FILES, "max_file_mb": MAX_FILE_MB, "max_total_mb": MAX_TOTAL_MB},
    }


@app.get("/api/tools")
def tools() -> dict:
    return {"groups": GROUPS, "tools": TOOLS}


@app.post("/api/upload")
async def upload(
    files: list[UploadFile] = File(default_factory=list),
    token: str | None = Form(None),
    slot: str = Form("source"),
    accept: str = Form("pdf"),
) -> dict:
    purge_expired()
    if not files:
        raise UserError("Chưa chọn file nào.")
    if len(files) > MAX_FILES:
        raise UserError(f"Tối đa {MAX_FILES} file mỗi lần.")

    created = not token
    if token:
        session = _session(token)
    else:
        token = uuid.uuid4().hex
        session = _session(token, create=True)

    manifest = _manifest(session)
    src_dir = session / "src"
    src_dir.mkdir(exist_ok=True)
    items: list[dict] = []
    total = 0

    try:
        for uf in files:
            raw = await uf.read()
            name = safe_name(uf.filename or "file", "file")
            _check_ext(name, accept)
            if accept == "pdf" and not raw.startswith(b"%PDF-"):
                raise UserError(f"'{name}' không phải file PDF.")
            mb = len(raw) / 1048576
            if mb > MAX_FILE_MB:
                raise UserError(f"'{name}' vượt quá {MAX_FILE_MB} MB.")
            total += len(raw)
            if total / 1048576 > MAX_TOTAL_MB:
                raise UserError(f"Tổng dung lượng vượt quá {MAX_TOTAL_MB} MB.")

            file_id = f"{uuid.uuid4().hex[:8]}{Path(name).suffix.lower()}"
            dest = src_dir / file_id
            dest.write_bytes(raw)

            item = {
                "id": file_id,
                "name": name,
                "size": human_size(len(raw)),
                "bytes": len(raw),
                "slot": slot,
                "pages": None,
                "thumb": None,
            }
            try:
                with pymupdf.open(dest) as doc:
                    if doc.page_count:
                        item["pages"] = doc.page_count
                        item["thumb"] = _image_thumb(dest) if accept == "image" else _thumb(doc)
            except Exception:  # noqa: BLE001
                if accept == "pdf":
                    raise UserError(f"'{name}' là PDF hỏng hoặc có mật khẩu.")

            manifest[file_id] = {"name": name, "pages": item["pages"], "slot": slot}
            items.append(item)
    except UserError:
        if created:
            shutil.rmtree(session, ignore_errors=True)
        raise

    _save_manifest(session, manifest)
    return {"token": token, "files": items}


@app.get("/api/preview/{token}/{file_id}")
def preview(token: str, file_id: str) -> FileResponse:
    session = _session(token)
    if not re.fullmatch(r"[0-9a-f]{8}\.[a-z0-9]{2,5}", file_id):
        raise HTTPException(400, "Tham số không hợp lệ.")
    path = session / "src" / file_id
    if not path.is_file():
        raise HTTPException(404, "Không tìm thấy file.")
    return FileResponse(path)


@app.get("/api/page-image/{token}/{file_id}/{page}")
def page_image(token: str, file_id: str, page: int, dpi: int = 110) -> Response:
    session = _session(token)
    if not re.fullmatch(r"[0-9a-f]{8}\.[a-z0-9]{2,5}", file_id):
        raise HTTPException(400, "Tham số không hợp lệ.")
    path = session / "src" / file_id
    if not path.is_file():
        raise HTTPException(404, "Không tìm thấy file.")
    with pymupdf.open(path) as doc:
        if page < 1 or page > doc.page_count:
            raise HTTPException(404, "Trang không tồn tại.")
        pix = doc[page - 1].get_pixmap(dpi=min(max(dpi, 60), 200))
        return Response(content=pix.tobytes("png"), media_type="image/png")


@app.post("/api/edit")
def edit(req: EditRequest) -> dict:
    session = _session(req.token)
    manifest = _manifest(session)
    src = session / "src" / req.fileId
    if not src.is_file():
        raise UserError("File nguồn không còn trong phiên, hãy tải lại.")

    started = time.time()
    doc = open_pdf(src)
    out_dir = session / "out" / uuid.uuid4().hex[:10]
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        apply_ops(doc, req.ops, session / "src")
        doc.subset_fonts()
        base = stem(manifest.get(req.fileId, {}).get("name", "document"))
        fname = f"{base}-edited.pdf"
        doc.save(out_dir / fname, garbage=4, deflate=True, clean=True)
    except UserError:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(out_dir, ignore_errors=True)
        raise HTTPException(500, f"Áp thao tác lỗi: {exc}") from exc
    finally:
        doc.close()

    target = out_dir / fname
    return {
        "url": f"/api/download/{req.token}/out/{out_dir.name}/{target.name}",
        "filename": target.name,
        "size": human_size(target.stat().st_size),
        "count": 1,
        "elapsed": round(time.time() - started, 2),
        "meta": f"{len(req.ops)} thao tác",
    }


@app.post("/api/run/{tool_id}")
def run(tool_id: str, req: RunRequest) -> dict:
    tool = TOOL_MAP.get(tool_id)
    if not tool:
        raise HTTPException(404, "Công cụ không tồn tại.")
    handler = HANDLERS.get(tool_id)
    if not handler:
        raise HTTPException(501, "Công cụ chưa được cài đặt.")

    session = _session(req.token)
    manifest = _manifest(session)
    src_dir = session / "src"

    ids = req.fileIds or [k for k, v in manifest.items() if v.get("slot") == "source"]
    if not ids:
        raise UserError("Chưa có file nguồn.")
    if not tool.get("multi") and len(ids) > 1:
        ids = ids[:1]

    sources: list[Path] = []
    names: list[str] = []
    for fid in ids:
        path = src_dir / fid
        if not path.is_file():
            raise UserError("File nguồn không còn trong phiên, hãy tải lại.")
        sources.append(path)
        names.append(manifest.get(fid, {}).get("name", path.name))

    image_path = None
    if req.imageId:
        image_path = src_dir / req.imageId
        if not image_path.is_file():
            raise UserError("Không tìm thấy ảnh đã upload.")

    out_dir = session / "out" / uuid.uuid4().hex[:10]
    out_dir.mkdir(parents=True, exist_ok=True)

    ctx = Ctx(
        out=out_dir,
        sources=sources,
        names=names,
        image=image_path,
        options={k: v for k, v in req.options.items() if not k.startswith("_")},
        tool=tool_id,
    )

    started = time.time()
    try:
        outputs, base = handler(ctx)
    except UserError as exc:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(out_dir, ignore_errors=True)
        raise HTTPException(500, f"Xử lý lỗi: {exc}") from exc

    if not outputs:
        raise HTTPException(500, "Không có file kết quả.")

    if len(outputs) > 1:
        zip_name = f"{base}.zip"
        final = zip_outputs(outputs, out_dir / zip_name)
        for p in outputs:
            p.unlink(missing_ok=True)
        files_out = [final]
    else:
        files_out = outputs

    target = files_out[0]
    rel = f"{req.token}/out/{out_dir.name}/{target.name}"
    return {
        "url": f"/api/download/{rel}",
        "filename": target.name,
        "size": human_size(target.stat().st_size),
        "count": len(files_out),
        "elapsed": round(time.time() - started, 2),
        "meta": ctx.options.get("_saved", ""),
    }


@app.get("/api/download/{token}/out/{folder}/{name}")
def download(token: str, folder: str, name: str) -> FileResponse:
    session = _session(token)
    if not re.fullmatch(r"[0-9a-f]{10}", folder) or not re.fullmatch(r"[\w\-. ()]{1,120}", name):
        raise HTTPException(400, "Tham số không hợp lệ.")
    path = session / "out" / folder / name
    if not path.is_file():
        raise HTTPException(404, "File kết quả không còn (đã quá hạn).")
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@app.delete("/api/session/{token}")
def drop_session(token: str) -> dict:
    session = _session(token)
    shutil.rmtree(session, ignore_errors=True)
    return {"ok": True}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
