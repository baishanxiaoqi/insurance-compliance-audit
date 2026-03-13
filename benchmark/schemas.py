"""评测模块数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class CaseRecord:
    sample_id: str
    label: str
    text: str
    source_sheet: str
    source_row: int
    source_column: str
    reason_raw: str = ""
    expected_categories: list[str] = field(default_factory=list)
    expected_text_slices: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    quality_status: str = "accepted"
    quality_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
