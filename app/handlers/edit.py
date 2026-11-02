"""Nhóm chỉnh sửa: số trang, watermark, chữ ký, chèn ảnh."""
from __future__ import annotations

from pathlib import Path

import pymupdf

from ..context import Ctx
from ..utils import UserError, open_pdf, opt_bool, opt_float, opt_int, opt_str, page_indices

VN_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def vn_font(size_hint: int = 12) -> pymupdf.Font:
    """Font có dấu tiếng Việt; fallback Helvetica nếu máy không có."""
    for path in VN_FONTS:
        if Path(path).exists():
            try:
                return pymupdf.Font(fontfile=path)
            except Exception:  # noqa: BLE001
                continue
    return pymupdf.Font("helv")


def _save(doc: pymupdf.Document, path: Path) -> Path:
    doc.save(path, garbage=4, deflate=True, clean=True)
    return path


def page_numbers(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    fmt = opt_str(ctx.options, "format", "{n}") or "{n}"
    start = opt_int(ctx.options, "start", 1, 0, 9999)
    size = opt_int(ctx.options, "font_size", 10, 6, 36)
    position = opt_str(ctx.options, "position", "bottom-center")
    margin = 22

    try:
        targets = page_indices(opt_str(ctx.options, "ranges"), doc.page_count)
        total = len(targets)
        for pos, i in enumerate(targets):
            page = doc[i]
            number = start + pos
            text = fmt.replace("{n}", str(number)).replace("{total}", str(total))
            width, height = page.rect.width, page.rect.height

            if position.startswith("bottom"):
                rect = pymupdf.Rect(margin, height - margin - size - 4, width - margin, height - margin + 4)
            else:
                rect = pymupdf.Rect(margin, margin - 4, width - margin, margin + size + 4)

            align = 0 if position.endswith("left") else (2 if position.endswith("right") else 1)
            page.insert_textbox(rect, text, fontsize=size, fontname="helv", align=align, color=(0, 0, 0))

        fname = f"{ctx.base}-so-trang.pdf"
        _save(doc, ctx.dest(fname))
    finally:
        doc.close()
    return [ctx.dest(fname)], fname


def watermark(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    text = opt_str(ctx.options, "text", "BẢN NHÁP").strip() or "BẢN NHÁP"
    size = opt_int(ctx.options, "font_size", 48, 8, 200)
    opacity = opt_float(ctx.options, "opacity", 0.15, 0.02, 1.0)
    rotation = opt_int(ctx.options, "rotation", 45, 0, 90)
    tile = opt_bool(ctx.options, "tile", False)

    try:
        font = vn_font(size)
        for i in page_indices(opt_str(ctx.options, "ranges"), doc.page_count):
            page = doc[i]
            page_w, page_h = page.rect.width, page.rect.height
            text_w = font.text_length(text, fontsize=size)

            if tile:
                step_x = max(text_w + 40, 160)
                step_y = max(size * 3.2, 90)
                y = 40
                while y < page_h:
                    x = 40
                    while x < page_w:
                        _stamp(page, font, text, size, opacity, rotation, pymupdf.Point(x, y))
                        x += step_x
                    y += step_y
            else:
                cx, cy = page_w / 2, page_h / 2
                _stamp(page, font, text, size, opacity, rotation, pymupdf.Point(cx - text_w / 2, cy + size / 3))

        fname = f"{ctx.base}-watermark.pdf"
        doc.subset_fonts()
        _save(doc, ctx.dest(fname))
    finally:
        doc.close()
    return [ctx.dest(fname)], fname


def _stamp(
    page: pymupdf.Page,
    font: pymupdf.Font,
    text: str,
    size: int,
    opacity: float,
    rotation: int,
    point: pymupdf.Point,
) -> None:
    tw = pymupdf.TextWriter(page.rect)
    tw.append(point, text, font=font, fontsize=size)
    morph = (point, pymupdf.Matrix(rotation)) if rotation else None
    tw.write_text(page, color=(0.45, 0.45, 0.5), opacity=opacity, morph=morph)


def _page_for(ctx: Ctx, doc: pymupdf.Document) -> int:
    spec = opt_str(ctx.options, "page", "last").strip().lower()
    if spec in {"last", "cuoi", "cuối"}:
        return doc.page_count - 1
    if spec in {"first", "dau", "đầu"}:
        return 0
    if spec.isdigit():
        idx = int(spec) - 1
        if 0 <= idx < doc.page_count:
            return idx
        raise UserError(f"Trang {spec} không tồn tại (file có {doc.page_count} trang).")
    raise UserError("Trang phải là first, last hoặc số trang.")


def _place_image(ctx: Ctx, default_width_pct: float, default_x: float, default_y: float, suffix: str):
    if not ctx.image or not ctx.image.exists():
        raise UserError("Chưa upload ảnh.")
    doc = open_pdf(ctx.first)
    try:
        idx = _page_for(ctx, doc)
        page = doc[idx]
        pct = opt_float(ctx.options, "width", default_width_pct, 1, 100) / 100
        x = opt_float(ctx.options, "x", default_x, 0, 100) / 100
        y = opt_float(ctx.options, "y", default_y, 0, 100) / 100

        with pymupdf.open(ctx.image) as img_doc:
            iw, ih = img_doc[0].rect.width, img_doc[0].rect.height
        if iw <= 0 or ih <= 0:
            raise UserError("Ảnh không hợp lệ.")

        target_w = page.rect.width * pct
        target_h = target_w * ih / iw
        left = page.rect.width * x
        top = page.rect.height * y
        left = min(max(0, left), max(0, page.rect.width - target_w))
        top = min(max(0, top), max(0, page.rect.height - target_h))

        rect = pymupdf.Rect(left, top, left + target_w, top + target_h)
        page.insert_image(rect, filename=str(ctx.image), overlay=True, keep_proportion=True)

        fname = f"{ctx.base}-{suffix}.pdf"
        _save(doc, ctx.dest(fname))
    finally:
        doc.close()
    return [ctx.dest(fname)], fname


def sign(ctx: Ctx) -> tuple[list[Path], str]:
    return _place_image(ctx, 22, 60, 78, "da-ky")


def add_image(ctx: Ctx) -> tuple[list[Path], str]:
    return _place_image(ctx, 20, 5, 5, "chen-anh")
