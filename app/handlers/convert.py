"""Nhóm chuyển đổi định dạng."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from docx import Document as Docx
from docx.shared import Pt
from openpyxl import Workbook
from PIL import Image
from pptx import Presentation
from pptx.util import Emu

from ..context import Ctx
from ..utils import UserError, open_pdf, opt_bool, opt_int, opt_str, page_indices

SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    shutil.which("soffice") or "",
    shutil.which("libreoffice") or "",
]
PAGE_SIZES = {"a4": (595.28, 841.89), "letter": (612.0, 792.0)}


def _render_to_images(ctx: Ctx, fmt: str) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    dpi = opt_int(ctx.options, "dpi", 150, 72, 600)
    quality = opt_int(ctx.options, "quality", 90, 40, 100)
    outputs: list[Path] = []
    try:
        for i in page_indices(opt_str(ctx.options, "ranges"), doc.page_count):
            pix = doc[i].get_pixmap(dpi=dpi, alpha=(fmt == "png"))
            path = ctx.dest(f"{ctx.base}-trang-{i + 1}.{fmt}")
            if fmt == "jpg":
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img.save(path, "JPEG", quality=quality, optimize=True)
            else:
                pix.save(path)
            outputs.append(path)
    finally:
        doc.close()
    return outputs, f"{ctx.base}-{fmt}"


def pdf_to_jpg(ctx: Ctx) -> tuple[list[Path], str]:
    return _render_to_images(ctx, "jpg")


def pdf_to_png(ctx: Ctx) -> tuple[list[Path], str]:
    return _render_to_images(ctx, "png")


def images_to_pdf(ctx: Ctx) -> tuple[list[Path], str]:
    size_name = opt_str(ctx.options, "page_size", "fit")
    margin = opt_int(ctx.options, "margin", 0, 0, 200)
    out = pymupdf.open()
    try:
        for src in ctx.sources:
            try:
                with pymupdf.open(src) as img_doc:
                    iw, ih = img_doc[0].rect.width, img_doc[0].rect.height
            except Exception as exc:  # noqa: BLE001
                raise UserError(f"Không đọc được ảnh '{src.name}': {exc}") from exc

            if size_name in PAGE_SIZES:
                pw, ph = PAGE_SIZES[size_name]
                page = out.new_page(width=pw, height=ph)
                avail_w, avail_h = pw - 2 * margin, ph - 2 * margin
                if avail_w <= 10 or avail_h <= 10:
                    raise UserError("Lề quá lớn so với khổ trang.")
                scale = min(avail_w / iw, avail_h / ih)
                w, h = iw * scale, ih * scale
                left, top = (pw - w) / 2, (ph - h) / 2
            else:
                page = out.new_page(width=iw + 2 * margin, height=ih + 2 * margin)
                left = top = margin
                w, h = iw, ih

            page.insert_image(pymupdf.Rect(left, top, left + w, top + h), filename=str(src))

        fname = f"{ctx.base}-anh-ghep.pdf" if len(ctx.sources) > 1 else f"{ctx.base}.pdf"
        out.save(ctx.dest(fname), garbage=4, deflate=True, clean=True)
    finally:
        out.close()
    return [ctx.dest(fname)], fname


def pdf_to_txt(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    keep_layout = opt_bool(ctx.options, "layout", False)
    flags = pymupdf.TEXT_PRESERVE_LIGATURES | pymupdf.TEXT_PRESERVE_WHITESPACE
    chunks: list[str] = []
    try:
        for i in page_indices(opt_str(ctx.options, "ranges"), doc.page_count):
            page = doc[i]
            text = page.get_text("text", flags=flags) if keep_layout else page.get_text("text")
            if len(doc) > 1:
                chunks.append(f"--- Trang {i + 1} ---\n{text.strip()}")
            else:
                chunks.append(text.strip())
    finally:
        doc.close()

    fname = f"{ctx.base}.txt"
    ctx.dest(fname).write_text("\n\n".join(chunks).strip() + "\n", encoding="utf-8")
    return [ctx.dest(fname)], fname


def pdf_to_word(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    with_images = opt_bool(ctx.options, "images", True)
    page_break = opt_bool(ctx.options, "page_break", True)
    targets = page_indices(opt_str(ctx.options, "ranges"), doc.page_count)

    word = Docx()
    normal = word.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)

    try:
        for pos, i in enumerate(targets):
            page = doc[i]
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") == 0:
                    lines = []
                    for line in block["lines"]:
                        lines.append("".join(span["text"] for span in line["spans"]))
                    text = "\n".join(lines).strip()
                    if text:
                        word.add_paragraph(text)
                elif block.get("type") == 1 and with_images:
                    bbox = pymupdf.Rect(block["bbox"])
                    if bbox.width < 8 or bbox.height < 8:
                        continue
                    pix = page.get_pixmap(clip=bbox, dpi=150)
                    tmp = ctx.out / f"_img_{i}_{int(bbox.y0)}.png"
                    pix.save(tmp)
                    word.add_picture(str(tmp), width=Pt(min(bbox.width, page.rect.width - 40)))
                    tmp.unlink(missing_ok=True)

            if page_break and pos < len(targets) - 1:
                word.add_page_break()
    finally:
        doc.close()

    fname = f"{ctx.base}.docx"
    word.save(ctx.dest(fname))
    return [ctx.dest(fname)], fname


def pdf_to_excel(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    wb = Workbook()
    wb.remove(wb.active)
    found_tables = 0
    try:
        for i in page_indices(opt_str(ctx.options, "ranges"), doc.page_count):
            page = doc[i]
            tables = page.find_tables()
            rows_all: list[list] = []
            for table in tables:
                for row in table.extract():
                    rows_all.append(["" if c is None else str(c) for c in row])
                rows_all.append([])
                found_tables += 1
            if not rows_all:
                continue
            ws = wb.create_sheet(title=f"Trang {i + 1}"[:31])
            for row in rows_all:
                ws.append(row)
            widths = {}
            for row in rows_all:
                for col, val in enumerate(row):
                    widths[col] = max(widths.get(col, 8), min(len(val) + 2, 60))
            for col, width in widths.items():
                ws.column_dimensions[ws.cell(row=1, column=col + 1).column_letter].width = width
    finally:
        doc.close()

    if not found_tables:
        raise UserError("Không tìm thấy bảng nào trong PDF. File này có thể là bản scan.")

    fname = f"{ctx.base}.xlsx"
    wb.save(ctx.dest(fname))
    return [ctx.dest(fname)], fname


def pdf_to_pptx(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    dpi = opt_int(ctx.options, "dpi", 150, 72, 300)
    targets = page_indices(opt_str(ctx.options, "ranges"), doc.page_count)

    prs = Presentation()
    first = doc[targets[0]].rect
    prs.slide_width = Emu(int(first.width / 72 * 914400))
    prs.slide_height = Emu(int(first.height / 72 * 914400))
    blank = prs.slide_layouts[6]

    try:
        for i in targets:
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi)
            tmp = ctx.out / f"_slide_{i}.png"
            pix.save(tmp)
            slide = prs.slides.add_slide(blank)
            slide.shapes.add_picture(
                str(tmp), 0, 0, width=prs.slide_width, height=prs.slide_height
            )
            tmp.unlink(missing_ok=True)
    finally:
        doc.close()

    fname = f"{ctx.base}.pptx"
    prs.save(ctx.dest(fname))
    return [ctx.dest(fname)], fname


def office_to_pdf(ctx: Ctx) -> tuple[list[Path], str]:
    soffice = next((p for p in SOFFICE_CANDIDATES if p and Path(p).exists()), None)
    if not soffice:
        raise UserError("Không tìm thấy LibreOffice trên máy. Cài từ libreoffice.org để dùng công cụ này.")

    outputs: list[Path] = []
    with tempfile.TemporaryDirectory() as home:
        env = {**os.environ, "HOME": home}
        for src in ctx.sources:
            cmd = [
                soffice,
                f"-env:UserInstallation=file://{home}/profile",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(ctx.out),
                str(src),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240, env=env)
            produced = ctx.out / f"{src.stem}.pdf"
            if not produced.exists():
                raise UserError(
                    f"LibreOffice không chuyển được '{src.name}'. {proc.stderr.strip()[:200]}"
                )
            outputs.append(produced)

    if not outputs:
        raise UserError("Không có file nào được chuyển.")
    return outputs, f"{ctx.base}-pdf"
