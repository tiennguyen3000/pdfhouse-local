"""Trình soạn thảo: áp danh sách thao tác (ops) lên trang PDF.

Mỗi op:
  {"type": "text", "page": 1, "rect": {"x":%, "y":%, "w":%, "h":%}, "text": "...",
   "size": 12, "color": "#111111", "align": "left|center|right"}
  {"type": "image", "page": 1, "rect": {...}, "imageId": "abcd1234.png"}
  {"type": "highlight", "page": 1, "rect": {...}, "color": "#ffe066", "opacity": 0.45}
  {"type": "rect"|"ellipse"|"arrow", "page": 1, "rect": {...}, "color": "#e11d48", "width": 2}
  {"type": "redact", "page": 1, "rect": {...}, "fill": "#ffffff"}
"""
from __future__ import annotations

import math
from pathlib import Path

import pymupdf

from ..utils import UserError

FONT_PATH = None
for _candidate in (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
):
    if Path(_candidate).exists():
        FONT_PATH = _candidate
        break

MAX_OPS = 400


def parse_color(value, default=(0, 0, 0)) -> tuple[float, float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(min(1.0, max(0.0, float(c))) for c in value)  # type: ignore[return-value]
    if isinstance(value, str) and value.startswith("#") and len(value) == 7:
        try:
            return tuple(int(value[i : i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]
        except ValueError:
            return default
    return default


def op_rect(page: pymupdf.Page, spec: dict) -> pymupdf.Rect:
    try:
        x = float(spec.get("x", 0)) / 100 * page.rect.width
        y = float(spec.get("y", 0)) / 100 * page.rect.height
        w = float(spec.get("w", 0)) / 100 * page.rect.width
        h = float(spec.get("h", 0)) / 100 * page.rect.height
    except (TypeError, ValueError, AttributeError) as exc:
        raise UserError("Toạ độ vùng chọn không hợp lệ.") from exc

    rect = pymupdf.Rect(x, y, x + w, y + h)
    rect.normalize()
    rect = rect & page.rect
    if rect.is_empty or rect.width < 2 or rect.height < 2:
        raise UserError("Vùng chọn quá nhỏ, hãy kéo lại.")
    return rect


def _font_name(page: pymupdf.Page) -> str:
    if not FONT_PATH:
        return "helv"
    try:
        page.insert_font(fontname="vnfont", fontfile=FONT_PATH)
    except Exception:  # noqa: BLE001
        return "helv"
    return "vnfont"


def apply_ops(doc: pymupdf.Document, ops: list[dict], src_dir: Path) -> None:
    if not ops:
        raise UserError("Chưa có thao tác nào để áp dụng.")
    if len(ops) > MAX_OPS:
        raise UserError(f"Tối đa {MAX_OPS} thao tác mỗi lần.")

    redact_pages: set[int] = set()
    prepared: list[tuple[int, dict]] = []

    for op in ops:
        try:
            pno = int(op.get("page", 1)) - 1
        except (TypeError, ValueError) as exc:
            raise UserError("Số trang không hợp lệ.") from exc
        if not 0 <= pno < doc.page_count:
            raise UserError(f"Trang {pno + 1} không tồn tại (file có {doc.page_count} trang).")

        kind = str(op.get("type", ""))
        if kind not in {"text", "image", "highlight", "rect", "ellipse", "arrow", "redact"}:
            raise UserError(f"Loại thao tác không hỗ trợ: '{kind}'.")
        prepared.append((pno, op))
        if kind == "redact":
            redact_pages.add(pno)

    # 1) xoá nội dung (redact) trước để không đè lên chữ mới
    for pno in redact_pages:
        page = doc[pno]
        for op_pno, op in prepared:
            if op_pno == pno and op["type"] == "redact":
                page.add_redact_annot(op_rect(page, op.get("rect", {})), fill=parse_color(op.get("fill"), (1, 1, 1)))
        page.apply_redactions()

    # 2) ảnh và hình nền
    for pno, op in prepared:
        if op["type"] not in {"image", "rect", "ellipse", "arrow"}:
            continue
        page = doc[pno]
        rect = op_rect(page, op.get("rect", {}))

        if op["type"] == "image":
            image_id = str(op.get("imageId") or "")
            if not image_id:
                raise UserError("Thiếu ảnh cho thao tác chèn ảnh.")
            path = src_dir / image_id
            if not path.is_file():
                raise UserError("Ảnh đã chọn không còn trong phiên, hãy tải lại.")
            page.insert_image(rect, filename=str(path), keep_proportion=True, overlay=True)
            continue

        color = parse_color(op.get("color"), (0.88, 0.11, 0.28))
        width = min(max(float(op.get("width", 2)), 0.5), 12)

        if op["type"] == "rect":
            page.draw_rect(rect, color=color, width=width)
        elif op["type"] == "ellipse":
            page.draw_oval(rect, color=color, width=width)
        else:  # arrow
            start = pymupdf.Point(rect.x0, rect.y1)
            end = pymupdf.Point(rect.x1, rect.y0)
            page.draw_line(start, end, color=color, width=width)
            angle = math.atan2(end.y - start.y, end.x - start.x)
            size = max(7, width * 3.2)
            for delta in (math.radians(155), math.radians(-155)):
                tip = pymupdf.Point(
                    end.x + size * math.cos(angle + delta),
                    end.y + size * math.sin(angle + delta),
                )
                page.draw_line(end, tip, color=color, width=width)

    # 3) highlight
    for pno, op in prepared:
        if op["type"] != "highlight":
            continue
        page = doc[pno]
        annot = page.add_highlight_annot(op_rect(page, op.get("rect", {})))
        annot.set_colors(stroke=parse_color(op.get("color"), (1.0, 0.88, 0.4)))
        annot.set_opacity(min(max(float(op.get("opacity", 0.45)), 0.05), 1.0))
        annot.update()

    # 4) chữ trên cùng
    for pno, op in prepared:
        if op["type"] != "text":
            continue
        page = doc[pno]
        text = str(op.get("text") or "")
        if not text.strip():
            raise UserError("Có ô chữ rỗng, hãy nhập nội dung.")
        rect = op_rect(page, op.get("rect", {}))
        size = min(max(float(op.get("size", 12)), 5), 96)
        align = {"left": 0, "center": 1, "right": 2}.get(str(op.get("align", "left")), 0)
        fontname = _font_name(page)
        color = parse_color(op.get("color"), (0.06, 0.06, 0.06))

        leftover = page.insert_textbox(
            rect, text, fontsize=size, fontname=fontname, color=color, align=align, lineheight=1.25
        )
        if leftover < 0:
            # vùng quá nhỏ: ghi đè bằng insert_text để không mất nội dung
            page.insert_text(
                pymupdf.Point(rect.x0, rect.y0 + size),
                text,
                fontsize=size,
                fontname=fontname,
                color=color,
            )
