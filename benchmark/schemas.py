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
    # Phase 4 新增：审查点级别的评测字段
    expected_audit_point_id: str = ""  # 期望的审查点 ID
    expected_exception_triggered: bool = False  # 是否应该触发例外
    expected_mitigating_factors: list[str] = field(default_factory=list)  # 缓释因素
    expected_actor_scope: str = ""  # 期望的主体范围（agent/customer/company/third_party/any）
    expected_claim_type: str = ""  # 期望的主张类型（income_promise/risk_downplay/ranking_claim等）
    is_hard_negative: bool = False  # 是否为 hard negative 样本

    def to_dict(self) -> dict:
        return asdict(self)
