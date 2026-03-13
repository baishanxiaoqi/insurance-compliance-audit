"""
Stage 1.9: 轻量 Gate（Lightweight Gate）
=========================================
Phase 3 升级：在 Stage 1.8 和 Stage 2 之间增加检查计划编译逻辑

Gate 的职责：
1. 判断当前规则是否与当前主体匹配（利用 actor_* 锚点）
2. 判断当前规则是否已被明显例外覆盖（利用 time_* 锚点）
3. 判断是否需要外部证据（利用 evidence_need 锚点）
4. 生成简化后的 rule plan 给模型

设计原则：
- 纯代码逻辑，不调用 LLM
- 只处理"明显可判"的场景
- 不确定的场景仍然送入 Stage 2
- Gate 不改变 verdict，只标记 gate_signal
"""

from __future__ import annotations

from typing import Dict, List, Optional
from dataclasses import dataclass

from ..log import get_logger
from ..schemas import ChunkFactProfile, RuleCard, RoutedPair

logger = get_logger(__name__)


@dataclass
class GateSignal:
    """Gate 检测到的信号"""
    signal_type: str  # actor_mismatch / time_context / evidence_missing / exception_likely
    confidence: float  # 0.0-1.0，置信度
    reason: str  # 详细原因
    evidence_labels: List[str]  # 相关的锚点标签


@dataclass
class GateResult:
    """Gate 处理结果"""
    chunk_id: str
    rule_id: str
    gate_signals: List[GateSignal]  # 检测到的信号
    should_skip: bool  # 是否应该跳过 Stage 2（明显不匹配）
    priority: str  # high / medium / low（送入 Stage 2 的优先级）
    rule_plan: Optional[str]  # 简化后的规则计划（给模型看的）


def _check_actor_mismatch(
    rule_card: RuleCard,
    chunk_fact: ChunkFactProfile | None,
) -> Optional[GateSignal]:
    """检查主体是否匹配

    规则：
    - 如果规则要求 actor_scope=agent，但文本中只有 actor_customer，则不匹配
    - 如果规则要求 actor_scope=customer，但文本中只有 actor_agent，则不匹配
    """
    if not rule_card.actor_scope or rule_card.actor_scope == "any":
        return None

    if not chunk_fact or not chunk_fact.signals:
        return None

    # 收集文本中的主体信号
    actor_signals = {s.label for s in chunk_fact.signals if s.label.startswith("actor_")}

    if not actor_signals:
        return None

    # 检查是否匹配
    required_actor = f"actor_{rule_card.actor_scope}"

    # 如果要求的主体不在文本中，但有其他主体
    if required_actor not in actor_signals and actor_signals:
        # 计算置信度：如果只有一个其他主体，置信度高；如果有多个主体，置信度低
        confidence = 0.8 if len(actor_signals) == 1 else 0.5

        return GateSignal(
            signal_type="actor_mismatch",
            confidence=confidence,
            reason=f"规则要求主体为 {rule_card.actor_scope}，但文本中检测到 {', '.join(actor_signals)}",
            evidence_labels=list(actor_signals)
        )

    return None


def _check_time_context(
    rule_card: RuleCard,
    chunk_fact: ChunkFactProfile | None,
) -> Optional[GateSignal]:
    """检查时态语境

    规则：
    - 如果文本中有明确的 time_past 信号，且规则针对当前状态，则可能不匹配
    - 如果文本中有 time_past + actor_third_party，则很可能是历史语境
    """
    if not chunk_fact or not chunk_fact.signals:
        return None

    # 收集时态信号
    time_signals = {s.label for s in chunk_fact.signals if s.label.startswith("time_")}

    if not time_signals:
        return None

    # 检查是否有明确的过去时态
    if "time_past" in time_signals:
        # 如果同时有 actor_third_party，置信度更高
        actor_signals = {s.label for s in chunk_fact.signals if s.label.startswith("actor_")}
        has_third_party = "actor_third_party" in actor_signals

        confidence = 0.8 if has_third_party else 0.5

        return GateSignal(
            signal_type="time_context",
            confidence=confidence,
            reason=f"检测到过去时态信号，可能描述历史语境{'（第三方）' if has_third_party else ''}",
            evidence_labels=list(time_signals | actor_signals)
        )

    return None


def _check_evidence_missing(
    rule_card: RuleCard,
    chunk_fact: ChunkFactProfile | None,
) -> Optional[GateSignal]:
    """检查证据是否缺失

    规则：
    - 如果规则要求 evidence_required=True，但文本中没有数据来源，则证据缺失
    """
    if not rule_card.evidence_required:
        return None

    if not chunk_fact or not chunk_fact.signals:
        # 规则要求证据，但没有任何信号，可能缺失
        return GateSignal(
            signal_type="evidence_missing",
            confidence=0.6,
            reason="规则要求证据支持，但文本中未检测到数据来源或依据",
            evidence_labels=[]
        )

    # 检查是否有 evidence_need 信号但缺少具体数据
    evidence_signals = [s for s in chunk_fact.signals if s.label == "evidence_need"]

    if evidence_signals:
        # 有需要证据的陈述，但需要检查是否有具体数据
        # 这里简化处理：如果有 evidence_need 信号，认为可能缺少证据
        return GateSignal(
            signal_type="evidence_missing",
            confidence=0.5,
            reason="检测到需要证据支持的陈述，但可能缺少具体数据来源",
            evidence_labels=["evidence_need"]
        )

    return None


def _check_exception_likely(
    rule_card: RuleCard,
    chunk_fact: ChunkFactProfile | None,
) -> Optional[GateSignal]:
    """检查是否可能触发例外

    规则：
    - 如果文本中有 negation 信号，可能触发否定例外
    - 如果文本中有 time_past + actor_third_party，可能触发历史语境例外
    """
    if not chunk_fact or not chunk_fact.signals:
        return None

    signal_labels = {s.label for s in chunk_fact.signals}

    # 检查否定信号
    if "negation" in signal_labels:
        return GateSignal(
            signal_type="exception_likely",
            confidence=0.7,
            reason="检测到否定信号，可能触发否定例外",
            evidence_labels=["negation"]
        )

    # 检查历史语境
    if "time_past" in signal_labels and "actor_third_party" in signal_labels:
        return GateSignal(
            signal_type="exception_likely",
            confidence=0.7,
            reason="检测到过去时态 + 第三方主体，可能触发历史语境例外",
            evidence_labels=["time_past", "actor_third_party"]
        )

    return None


def _generate_rule_plan(
    rule_card: RuleCard,
    chunk_fact: ChunkFactProfile | None,
    gate_signals: List[GateSignal],
) -> str:
    """生成简化的规则计划

    目标：给模型一个更清晰、更结构化的输入，而不是完整的规则卡片
    """
    plan_parts = []

    # 1. 规则基本信息
    plan_parts.append(f"规则ID: {rule_card.rule_id}")
    plan_parts.append(f"规则名称: {rule_card.rule_name}")
    plan_parts.append(f"风险等级: {rule_card.risk_level}")

    # 2. 主体要求
    if rule_card.actor_scope and rule_card.actor_scope != "any":
        plan_parts.append(f"主体要求: {rule_card.actor_scope}")

    # 3. 主张类型
    if rule_card.claim_type:
        plan_parts.append(f"主张类型: {rule_card.claim_type}")

    # 4. 证据要求
    if rule_card.evidence_required:
        plan_parts.append("证据要求: 必须有数据来源或外部依据")

    # 5. Gate 检测到的信号
    if gate_signals:
        signal_summary = []
        for sig in gate_signals:
            signal_summary.append(f"{sig.signal_type} (置信度: {sig.confidence:.1f})")
        plan_parts.append(f"Gate 信号: {', '.join(signal_summary)}")

    # 6. 核心违规定义（简化）
    plan_parts.append(f"违规定义: {rule_card.violation_definition[:100]}...")

    return "\n".join(plan_parts)


def run_gate(
    routed_pairs: List[RoutedPair],
    rule_cards: Dict[str, RuleCard],
    chunk_facts: Dict[str, ChunkFactProfile] | None = None,
) -> List[GateResult]:
    """运行轻量 Gate

    返回：GateResult 列表，包含 gate_signals 和 should_skip 标记
    """
    results: List[GateResult] = []
    skip_count = 0
    signal_counter: Dict[str, int] = {}

    for pair in routed_pairs:
        rule_card = rule_cards.get(pair.rule_id)
        if not rule_card:
            continue

        chunk_fact = chunk_facts.get(pair.chunk_id) if chunk_facts else None

        # 运行 4 个检查
        gate_signals: List[GateSignal] = []

        sig = _check_actor_mismatch(rule_card, chunk_fact)
        if sig:
            gate_signals.append(sig)
            signal_counter[sig.signal_type] = signal_counter.get(sig.signal_type, 0) + 1

        sig = _check_time_context(rule_card, chunk_fact)
        if sig:
            gate_signals.append(sig)
            signal_counter[sig.signal_type] = signal_counter.get(sig.signal_type, 0) + 1

        sig = _check_evidence_missing(rule_card, chunk_fact)
        if sig:
            gate_signals.append(sig)
            signal_counter[sig.signal_type] = signal_counter.get(sig.signal_type, 0) + 1

        sig = _check_exception_likely(rule_card, chunk_fact)
        if sig:
            gate_signals.append(sig)
            signal_counter[sig.signal_type] = signal_counter.get(sig.signal_type, 0) + 1

        # 决定是否跳过 Stage 2
        should_skip = False
        priority = "medium"

        # 如果有高置信度的 actor_mismatch，可以跳过
        for sig in gate_signals:
            if sig.signal_type == "actor_mismatch" and sig.confidence >= 0.8:
                should_skip = True
                skip_count += 1
                break

        # 如果有多个信号，降低优先级
        if len(gate_signals) >= 2:
            priority = "low"
        elif len(gate_signals) == 1:
            priority = "medium"
        else:
            priority = "high"

        # 生成规则计划
        rule_plan = _generate_rule_plan(rule_card, chunk_fact, gate_signals)

        results.append(
            GateResult(
                chunk_id=pair.chunk_id,
                rule_id=pair.rule_id,
                gate_signals=gate_signals,
                should_skip=should_skip,
                priority=priority,
                rule_plan=rule_plan,
            )
        )

    logger.info(
        f"Gate 完成: 共 {len(results)} 个组合, 跳过 {skip_count} 个 ({skip_count/len(results)*100:.1f}%)"
    )

    if signal_counter:
        signal_summary = ", ".join(f"{k}={v}" for k, v in signal_counter.items())
        logger.info(f"Gate 信号分布: {signal_summary}")

    return results
