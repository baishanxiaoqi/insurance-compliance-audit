"""
Stage 1.5: 事实抽取（Fact Extraction）
=====================================
当前版本采用纯代码的确定性抽取，用于搭建事实层框架：
  - 从 chunk 的 spans 中抽取否定/确定性/比较/时间/动作等事实信号
  - 输出 ChunkFactProfile，供 Stage 2 提示增强与后续可执行规则引擎使用

说明：
  - 本阶段不改变对外 API 输出
  - 后续可平滑替换为 LLM 结构化抽取（Schema 保持不变）
"""

from __future__ import annotations

import re
from typing import Dict, List, Set

from ..log import get_logger
from ..schemas import ChunkFactProfile, ChunkCandidates, DocumentState, FactSignal

logger = get_logger(__name__)


NEGATION_TERMS = ["不", "无", "非", "未", "不要", "不得", "不能"]
CERTAINTY_TERMS = ["保证", "一定", "稳赚", "必然", "无条件", "全额", "肯定"]
COMPARISON_TERMS = ["比", "高于", "低于", "远超", "优于", "不如", "超过"]
TIME_TERMS = ["之前", "后来", "目前", "曾", "过去", "未来", "即将", "最后", "限时"]
ACTION_TERMS = ["建议", "推荐", "退保", "购买", "停售", "抢购", "转购", "投保"]

PERCENT_PATTERN = re.compile(r"\d+(?:\.\d+)?%")
MONEY_PATTERN = re.compile(r"(?:\d+(?:\.\d+)?)(?:万|亿|元|块|w)")


def _extract_span_signals(span_text: str) -> List[tuple[str, str]]:
    """从单个 span 文本抽取信号（label, value）。"""
    signals: List[tuple[str, str]] = []

    for term in NEGATION_TERMS:
        if term in span_text:
            signals.append(("negation", term))

    for term in CERTAINTY_TERMS:
        if term in span_text:
            signals.append(("certainty", term))

    for term in COMPARISON_TERMS:
        if term in span_text:
            signals.append(("comparison", term))

    for term in TIME_TERMS:
        if term in span_text:
            signals.append(("time", term))

    for term in ACTION_TERMS:
        if term in span_text:
            signals.append(("action", term))

    for m in PERCENT_PATTERN.findall(span_text):
        signals.append(("number_percent", m))

    for m in MONEY_PATTERN.findall(span_text):
        signals.append(("number_money", m))

    return signals


def _build_summary(signals: List[FactSignal]) -> str:
    if not signals:
        return ""
    labels: Dict[str, Set[str]] = {}
    for s in signals:
        labels.setdefault(s.label, set()).add(s.value)

    parts = []
    for label in ["negation", "certainty", "comparison", "time", "action", "number_percent", "number_money"]:
        values = sorted(labels.get(label, set()))
        if values:
            parts.append(f"{label}: {'/'.join(values[:5])}")
    return "; ".join(parts)


def run_stage1_5(
    document: DocumentState,
    candidates: List[ChunkCandidates],
) -> Dict[str, ChunkFactProfile]:
    """
    仅对 Stage 1 有候选规则的 chunk 进行事实抽取，减少无效计算。
    返回：chunk_id -> ChunkFactProfile
    """
    chunk_ids = {c.chunk_id for c in candidates}
    chunk_map = {c.chunk_id: c for c in document.chunks}

    profiles: Dict[str, ChunkFactProfile] = {}

    for chunk_id in chunk_ids:
        chunk = chunk_map.get(chunk_id)
        if chunk is None:
            continue

        merged: Dict[tuple[str, str], Set[str]] = {}
        for span in chunk.spans:
            raw_signals = _extract_span_signals(span.span_text)
            for label, value in raw_signals:
                key = (label, value)
                merged.setdefault(key, set()).add(span.span_id)

        signals: List[FactSignal] = []
        for (label, value), span_ids in merged.items():
            signals.append(
                FactSignal(
                    label=label,
                    value=value,
                    evidence_span_ids=sorted(span_ids),
                )
            )

        signals.sort(key=lambda s: (s.label, s.value))
        profiles[chunk_id] = ChunkFactProfile(
            chunk_id=chunk_id,
            signals=signals,
            summary=_build_summary(signals),
        )

    logger.info(f"Stage 1.5 完成: 生成 {len(profiles)} 个 chunk 事实画像")
    return profiles
