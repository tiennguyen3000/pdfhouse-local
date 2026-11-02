"""Tiện ích dùng chung cho các handler."""
from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path

import pymupdf

PAGE_CHARS = "0123456789,-"


class UserError(Exception):
    """Lỗi do người dùng nhập sai — trả về 400 với message thân thiện."""


def parse_ranges(spec: str | None, page_count: int) -> list[tuple[int, int]]:
    """'1-3,5,7-' -> [(0,2),(4,4),(6,page_count-1)] — 0-based, inclusive."""
    if spec is None or not str(spec).strip():
        return [(0, page_count - 1)]

    out: list[tuple[int, int]] = []
    for chunk in str(spec).replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk:
            left, _, right = chunk.partition("-")
            if (not left and not right) or (left and not left.isdigit()) or (right and not right.isdigit()):
                raise UserError(f"Dải trang không hợp lệ: '{chunk}'")
            start = int(left) if left else 1
            end = int(right) if right else page_count
        else:
            if not chunk.isdigit():
                raise UserError(f"Dải trang không hợp lệ: '{chunk}'")
            start = end = int(chunk)
        if start < 1 or end < start or end > page_count:
            raise UserError(f"Dải '{chunk}' vượt quá số trang (file có {page_count} trang).")
        out.append((start - 1, end - 1))

    if not out:
        raise UserError("Không có trang nào được chọn.")
    return out


def page_indices(spec: str | None, page_count: int) -> list[int]:
    """Như parse_ranges nhưng trả list số trang 0-based, đã bỏ trùng, giữ thứ tự."""
    seen: set[int] = set()
    result: list[int] = []
    for first, last in parse_ranges(spec, page_count):
        for i in range(first, last + 1):
            if i not in seen:
                seen.add(i)
                result.append(i)
    return result


def open_pdf(path: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # noqa: BLE001
        raise UserError(f"Không đọc được PDF: {exc}") from exc
    if doc.needs_pass:
        doc.close()
        raise UserError("PDF có mật khẩu. Dùng công cụ 'Gỡ mật khẩu' trước.")
    if doc.page_count == 0:
        doc.close()
        raise UserError("PDF không có trang nào.")
    return doc


def safe_name(name: str, default: str = "document") -> str:
    name = os.path.basename(name or "").strip()
    name = re.sub(r"[^\w\-. ()\[\]]+", "_", name, flags=re.UNICODE).strip(" .")
    return (name or default)[:110]


def stem(name: str) -> str:
    return Path(safe_name(name, "document")).stem or "document"


def human_size(num: float) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def zip_outputs(paths: list[Path], dest: Path, arcname_prefix: str = "") -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            zf.write(p, arcname=f"{arcname_prefix}{p.name}" if arcname_prefix else p.name)
    return dest


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def opt_int(options: dict, key: str, default: int, low: int, high: int) -> int:
    raw = options.get(key, default)
    try:
        return int(clamp(float(raw), low, high))
    except (TypeError, ValueError):
        return default


def opt_float(options: dict, key: str, default: float, low: float, high: float) -> float:
    raw = options.get(key, default)
    try:
        return clamp(float(raw), low, high)
    except (TypeError, ValueError):
        return default


def opt_str(options: dict, key: str, default: str = "") -> str:
    raw = options.get(key, default)
    return str(raw) if raw is not None else default


def opt_bool(options: dict, key: str, default: bool = False) -> bool:
    raw = options.get(key, default)
    if isinstance(raw, bool):
        return raw
    return str(raw).lower() in {"1", "true", "on", "yes"}


def cleanup_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
