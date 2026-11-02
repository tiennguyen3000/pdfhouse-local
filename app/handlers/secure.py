"""Nhóm bảo mật / dung lượng: nén, đặt mật khẩu, gỡ mật khẩu."""
from __future__ import annotations

from pathlib import Path

import pymupdf

from ..context import Ctx
from ..utils import UserError, human_size, open_pdf, opt_bool, opt_str

LEVELS = {
    "light": {"dpi_threshold": 200, "dpi_target": 150, "quality": 85},
    "medium": {"dpi_threshold": 150, "dpi_target": 110, "quality": 75},
    "strong": {"dpi_threshold": 110, "dpi_target": 72, "quality": 60},
}


def compress(ctx: Ctx) -> tuple[list[Path], str]:
    level = opt_str(ctx.options, "level", "medium")
    if level not in LEVELS:
        raise UserError("Mức nén không hợp lệ.")
    cfg = LEVELS[level]
    gray = opt_bool(ctx.options, "grayscale", False)
    src = ctx.first
    before = src.stat().st_size

    doc = open_pdf(src)
    try:
        doc.rewrite_images(
            dpi_threshold=cfg["dpi_threshold"],
            dpi_target=cfg["dpi_target"],
            quality=cfg["quality"],
            lossy=True,
            lossless=True,
            set_to_gray=gray,
        )
        fname = f"{ctx.base}-nen.pdf"
        doc.subset_fonts()
        doc.save(ctx.dest(fname), garbage=4, deflate=True, deflate_images=True, clean=True)
    finally:
        doc.close()

    out = ctx.dest(fname)
    if out.stat().st_size >= before and level == "strong":
        pass  # vẫn trả file, chỉ là không nhỏ hơn
    ctx.options["_saved"] = f"{human_size(before)} → {human_size(out.stat().st_size)}"
    return [out], fname


def protect(ctx: Ctx) -> tuple[list[Path], str]:
    password = opt_str(ctx.options, "password", "")
    if len(password) < 4:
        raise UserError("Mật khẩu phải có ít nhất 4 ký tự.")

    perm = pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ | pymupdf.PDF_PERM_ACCESSIBILITY
    if opt_bool(ctx.options, "allow_copy", False):
        perm |= pymupdf.PDF_PERM_COPY

    doc = open_pdf(ctx.first)
    try:
        fname = f"{ctx.base}-khoa.pdf"
        doc.save(
            ctx.dest(fname),
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw=password,
            user_pw=password,
            permissions=perm,
            garbage=4,
            deflate=True,
        )
    finally:
        doc.close()
    return [ctx.dest(fname)], fname


def unlock(ctx: Ctx) -> tuple[list[Path], str]:
    password = opt_str(ctx.options, "password", "")
    try:
        doc = pymupdf.open(ctx.first)
    except Exception as exc:  # noqa: BLE001
        raise UserError(f"Không mở được PDF: {exc}") from exc

    try:
        if doc.needs_pass and not doc.authenticate(password):
            raise UserError("Mật khẩu không đúng.")
        if doc.page_count == 0:
            raise UserError("PDF không có trang nào.")
        fname = f"{ctx.base}-mo-khoa.pdf"
        doc.save(ctx.dest(fname), garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
    return [ctx.dest(fname)], fname
