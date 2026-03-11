"""
Stage 1.8: 路由分发（Dual Strategy Router）
============================================
将 Stage 1 候选的 (chunk, rule) 组合分发到两套策略：
  - base : 现有基础审核策略（快速、低成本）
  - skill: 复杂审核策略（Skills/子 Agent，适合上下文依赖和复杂逻辑）

方案3增强：
  - 自动识别复杂场景类型（temporal_context/subject_switch等）
  - 为 skill 轨添加 skill_type 标记
"""

from __future__ import annotations

from typing import Dict, List, Set

from ..log import get_logger
from ..schemas import ChunkCandidates, ChunkFactProfile, RoutedPair, RuleCard
from ..complex_classifier import classify_complex_scenario

logger = get_logger(__name__)

_COMPLEX_SIGNAL_LABELS: Set[str] = {"negation", "time", "comparison"}


def _has_complex_signals(chunk_fact: ChunkFactProfile | None) -> bool:
    if chunk_fact is None:
        return False
    labels = {s.label for s in chunk_fact.signals}
    return bool(labels & _COMPLEX_SIGNAL_LABELS)


def decide_route(
    rule_card: RuleCard,
    chunk_fact: ChunkFactProfile | None = None,
) -> tuple[str, str, str | None]:
    """
    返回 (strategy, reason, skill_type)。
    strategy: "base" | "skill"
    skill_type: 复杂场景类型（仅 skill 轨有效）
    """
    # 显式路由策略
    if rule_card.route_strategy == "base":
        return "base", "rule_route_strategy=base", None
    if rule_card.route_strategy == "skill":
        skill_type = classify_complex_scenario(rule_card)
        return "skill", "rule_route_strategy=skill", skill_type

    # 复杂度标记
    if rule_card.complexity_level == "complex":
        skill_type = classify_complex_scenario(rule_card)
        return "skill", "rule_complexity=complex", skill_type

    # 高风险 + 结构化约束
    has_structured_constraints = bool(
        rule_card.exceptions or rule_card.condition_terms or rule_card.exclusion_terms
    )
    if rule_card.risk_level == "high" and has_structured_constraints:
        skill_type = classify_complex_scenario(rule_card)
        return "skill", "high_risk_with_constraints", skill_type

    # 复杂信号 + 结构化约束
    if has_structured_constraints and _has_complex_signals(chunk_fact):
        skill_type = classify_complex_scenario(rule_card)
        return "skill", "complex_signals_with_constraints", skill_type

    return "base", "default_base", None


def run_stage1_8(
    candidates: List[ChunkCandidates],
    rule_cards: Dict[str, RuleCard],
    chunk_facts: Dict[str, ChunkFactProfile] | None = None,
) -> List[RoutedPair]:
    """为 Stage 1 候选对生成路由结果。"""
    routes: List[RoutedPair] = []
    strategy_counter = {"base": 0, "skill": 0}
    skill_type_counter: Dict[str, int] = {}

    for chunk_candidate in candidates:
        chunk_fact = chunk_facts.get(chunk_candidate.chunk_id) if chunk_facts else None
        for rule_id in chunk_candidate.candidate_rule_ids:
            rule_card = rule_cards.get(rule_id)
            if rule_card is None:
                continue

            strategy, reason, skill_type = decide_route(rule_card, chunk_fact)
            strategy_counter[strategy] = strategy_counter.get(strategy, 0) + 1

            if skill_type:
                skill_type_counter[skill_type] = skill_type_counter.get(skill_type, 0) + 1

            routes.append(
                RoutedPair(
                    chunk_id=chunk_candidate.chunk_id,
                    rule_id=rule_id,
                    strategy=strategy,
                    reason=reason,
                    skill_type=skill_type,
                )
            )

    logger.info(
        "Stage 1.8 完成: 共 %d 个组合, base=%d, skill=%d",
        len(routes),
        strategy_counter.get("base", 0),
        strategy_counter.get("skill", 0),
    )

    if skill_type_counter:
        skill_type_summary = ", ".join(f"{k}={v}" for k, v in skill_type_counter.items())
        logger.info(f"复杂场景分布: {skill_type_summary}")

    return routes

