"""Nhóm công cụ tổ chức trang: merge, split, extract, delete, rotate, organize."""
from __future__ import annotations

import math
from pathlib import Path

import pymupdf

from ..context import Ctx
from ..utils import UserError, open_pdf, opt_bool, opt_str, page_indices, parse_ranges


def _save(doc: pymupdf.Document, path: Path) -> Path:
    doc.save(path, garbage=4, deflate=True, clean=True)
    return path


def _copy_pages(doc: pymupdf.Document, indices: list[int]) -> pymupdf.Document:
    out = pymupdf.open()
    for i in indices:
        out.insert_pdf(doc, from_page=i, to_page=i)
    return out


def merge(ctx: Ctx) -> tuple[list[Path], str]:
    out = pymupdf.open()
    toc: list[list] = []
    opened: list[pymupdf.Document] = []

    try:
        for idx, src in enumerate(ctx.sources):
            doc = open_pdf(src)
            opened.append(doc)
            start = out.page_count
            out.insert_pdf(doc)
            if opt_bool(ctx.options, "add_bookmarks", True) and out.page_count > start:
                label = ctx.names[idx] if idx < len(ctx.names) else f"Phần {idx + 1}"
                toc.append([1, label, start + 1])

        if opt_bool(ctx.options, "keep_metadata", True) and opened:
            meta = {k: v for k, v in (opened[0].metadata or {}).items() if v}
            meta.pop("creationDate", None)
            meta.pop("modDate", None)
            out.set_metadata(meta)

        if toc:
            out.set_toc(toc)

        name = opt_str(ctx.options, "output_name").strip()
        fname = f"{Path(name).stem}.pdf" if name else f"{ctx.base}-merged.pdf"
        return [_save(out, ctx.dest(fname))], fname
    finally:
        for doc in opened:
            doc.close()
        out.close()


def split(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    base = ctx.base
    outputs: list[Path] = []
    mode = opt_str(ctx.options, "mode", "range")

    try:
        if mode == "each":
            for i in range(doc.page_count):
                part = _copy_pages(doc, [i])
                outputs.append(_save(part, ctx.dest(f"{base}-trang-{i + 1}.pdf")))
                part.close()
        elif mode == "parts":
            parts = max(2, min(int(ctx.options.get("parts", 2)), doc.page_count))
            size = math.ceil(doc.page_count / parts)
            for p in range(parts):
                first = p * size
                last = min(doc.page_count, first + size) - 1
                if first > last:
                    break
                part = _copy_pages(doc, list(range(first, last + 1)))
                outputs.append(_save(part, ctx.dest(f"{base}-phan-{p + 1}.pdf")))
                part.close()
        else:
            ranges = parse_ranges(opt_str(ctx.options, "ranges"), doc.page_count)
            for n, (first, last) in enumerate(ranges, start=1):
                part = _copy_pages(doc, list(range(first, last + 1)))
                label = f"{first + 1}" if first == last else f"{first + 1}-{last + 1}"
                outputs.append(_save(part, ctx.dest(f"{base}-trang-{label}.pdf")))
                part.close()
    finally:
        doc.close()

    if not outputs:
        raise UserError("Không tạo được file nào.")
    return outputs, f"{base}-split"


def extract(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    try:
        indices = page_indices(opt_str(ctx.options, "ranges"), doc.page_count)
        out = _copy_pages(doc, indices)
        out.set_metadata(doc.metadata or {})
        fname = f"{ctx.base}-trich-xuat.pdf"
        _save(out, ctx.dest(fname))
        out.close()
    finally:
        doc.close()
    return [ctx.dest(fname)], fname


def delete_pages(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    try:
        drop = set(page_indices(opt_str(ctx.options, "ranges"), doc.page_count))
        keep = [i for i in range(doc.page_count) if i not in drop]
        if not keep:
            raise UserError("Không thể xoá toàn bộ trang — file sẽ rỗng.")
        doc.select(keep)
        fname = f"{ctx.base}-da-xoa-trang.pdf"
        _save(doc, ctx.dest(fname))
    finally:
        doc.close()
    return [ctx.dest(fname)], fname


def rotate(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    angle = int(ctx.options.get("angle", 90)) % 360
    if angle % 90:
        raise UserError("Góc xoay phải là bội số của 90.")
    try:
        for i in page_indices(opt_str(ctx.options, "ranges"), doc.page_count):
            page = doc[i]
            page.set_rotation((page.rotation + angle) % 360)
        fname = f"{ctx.base}-xoay.pdf"
        _save(doc, ctx.dest(fname))
    finally:
        doc.close()
    return [ctx.dest(fname)], fname


def organize(ctx: Ctx) -> tuple[list[Path], str]:
    doc = open_pdf(ctx.first)
    order = opt_str(ctx.options, "order", "").strip()
    try:
        if not order:
            indices = list(range(doc.page_count))
        else:
            indices = []
            for chunk in order.replace(" ", "").split(","):
                if not chunk:
                    continue
                if "-" in chunk:
                    left, _, right = chunk.partition("-")
                    if not left.isdigit() or not right.isdigit():
                        raise UserError(f"Dải trang không hợp lệ: '{chunk}'")
                    indices.extend(range(int(left) - 1, int(right)))
                elif chunk.isdigit():
                    indices.append(int(chunk) - 1)
                else:
                    raise UserError(f"Trang không hợp lệ: '{chunk}'")
            if any(i < 0 or i >= doc.page_count for i in indices):
                raise UserError(f"Trang vượt quá số trang (file có {doc.page_count} trang).")

        out = _copy_pages(doc, indices)
        fname = f"{ctx.base}-sap-xep.pdf"
        _save(out, ctx.dest(fname))
        out.close()
    finally:
        doc.close()
    return [ctx.dest(fname)], fname
