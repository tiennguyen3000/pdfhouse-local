"""Bảng tra handler theo id công cụ."""
from __future__ import annotations

from . import convert, edit, pages, secure

HANDLERS = {
    "merge": pages.merge,
    "split": pages.split,
    "extract": pages.extract,
    "delete-pages": pages.delete_pages,
    "rotate": pages.rotate,
    "organize": pages.organize,
    "page-numbers": edit.page_numbers,
    "watermark": edit.watermark,
    "sign": edit.sign,
    "add-image": edit.add_image,
    "compress": secure.compress,
    "protect": secure.protect,
    "unlock": secure.unlock,
    "pdf-to-jpg": convert.pdf_to_jpg,
    "pdf-to-png": convert.pdf_to_png,
    "images-to-pdf": convert.images_to_pdf,
    "pdf-to-txt": convert.pdf_to_txt,
    "pdf-to-word": convert.pdf_to_word,
    "pdf-to-excel": convert.pdf_to_excel,
    "pdf-to-pptx": convert.pdf_to_pptx,
    "office-to-pdf": convert.office_to_pdf,
}
