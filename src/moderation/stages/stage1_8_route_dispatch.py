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


def _has_semantic_constraints(rule_card: RuleCard) -> bool:
    """判断规则是否包含超出纯关键词/距离约束的语义限制。"""
    return bool(
        (rule_card.actor_scope and rule_card.actor_scope != "any")
        or (rule_card.claim_type and rule_card.claim_type != "other")
        or rule_card.exception_group
        or rule_card.evidence_required
        or rule_card.mutual_exclusion_group
    )


def decide_route(
    rule_card: RuleCard,
    chunk_fact: ChunkFactProfile | None = None,
) -> tuple[str, str, str | None]:
    """
    返回 (strategy, reason, skill_type)。
    strategy: "base" | "skill"
    skill_type: 复杂场景类型（仅 skill 轨有效）
    """
    inferred_skill_type = classify_complex_scenario(rule_card)
    has_structured_constraints = bool(
        rule_card.exceptions or rule_card.condition_terms or rule_card.exclusion_terms
    )
    has_semantic_constraints = _has_semantic_constraints(rule_card)
    has_complex_signals = _has_complex_signals(chunk_fact)

    # 显式路由策略
    if rule_card.route_strategy == "base":
        return "base", "rule_route_strategy=base", None
    if rule_card.route_strategy == "skill":
        return "skill", "rule_route_strategy=skill", inferred_skill_type

    # 路由提示（优先级低于显式路由，高于自动推断）
    if rule_card.route_hint == "prefer_base" and not has_complex_signals:
        return "base", "rule_route_hint=prefer_base", None
    if rule_card.route_hint == "prefer_skill":
        return "skill", "rule_route_hint=prefer_skill", inferred_skill_type

    # 复杂度标记
    if rule_card.complexity_level == "complex":
        return "skill", "rule_complexity=complex", inferred_skill_type
    if rule_card.complexity_level == "simple" and not has_complex_signals and not inferred_skill_type:
        return "base", "rule_complexity=simple", None

    # 复杂场景分类器优先：真正把 complex classifier 的结果用于分流
    if inferred_skill_type:
        return "skill", "inferred_complex_skill", inferred_skill_type

    # 复杂信号 + 语义/结构化约束：需要 LLM 处理
    if has_complex_signals and (has_structured_constraints or has_semantic_constraints):
        return "skill", "complex_signals_with_constraints", None

    # 只有存在语义性约束时，才默认走 skill；纯结构化约束优先交给 base 轨
    if has_semantic_constraints:
        return "skill", "semantic_rule_constraints", None

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
