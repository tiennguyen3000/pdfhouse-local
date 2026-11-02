"""Ngữ cảnh xử lý: mọi handler nhận đúng một Ctx và trả (danh sách file ra, tên gợi ý)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Ctx:
    out: Path
    sources: list[Path]
    names: list[str] = field(default_factory=list)
    image: Path | None = None
    options: dict = field(default_factory=dict)
    tool: str = ""

    @property
    def first(self) -> Path:
        if not self.sources:
            raise ValueError("Chưa có file nguồn")
        return self.sources[0]

    @property
    def base(self) -> str:
        from .utils import stem

        return stem(self.names[0]) if self.names else "document"

    def dest(self, name: str) -> Path:
        return self.out / name
