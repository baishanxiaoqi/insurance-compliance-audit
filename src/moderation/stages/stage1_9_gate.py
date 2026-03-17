"""
Stage 1.9: 轻量 Gate（Lightweight Gate）
=========================================
Phase 3 升级：在 Stage 1.8 和 Stage 2 之间增加检查计划编译逻辑

Gate 的职责：
1. 判断当前规则是否与当前主体匹配（利用 actor_* 锚点）
2. 判断当前规则是否已被明显例外覆盖（利用 time_* 锚点）
3. 判断是否需要外部证据（利用 evidence_need 锚点）
4. 生成简化后的 rule plan 给模型

Phase 4 升级（P0 高优先级）：新增 3 个前置场景闸门
5. 非产品/非营销上下文的绝对化表述闸门
6. 规范提示语充分的减保/保单贷款说明闸门
7. 中性知识说明 vs 销售话术闸门

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


# ============================================================
# Phase 4 新增：提示语词库
# ============================================================

# 减保/保单贷款的规范提示语
DISCLAIMER_SURRENDER_TERMS = [
    "降低保障额度",
    "降低保额",
    "影响现金价值",
    "减少现金价值",
    "谨慎选择",
    "请谨慎",
    "根据实际需求",
    "根据自身需求",
]

DISCLAIMER_LOAN_TERMS = [
    "贷款额度",
    "贷款期限",
    "贷款利息",
    "利息限制",
    "还款义务",
    "影响保障",
]

# 中性知识说明的标志词
NEUTRAL_KNOWLEDGE_TERMS = [
    "介绍功能",
    "说明规则",
    "解释条款",
    "客观描述",
    "根据规定",
    "根据法律",
    "根据保险法",
]

# 销售话术的标志词
SALES_PITCH_TERMS = [
    "诱导购买",
    "优势夸大",
    "对比贬损",
    "收益承诺",
    "背书增强",
    "立即购买",
    "限时优惠",
    "不容错过",
]


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


# ============================================================
# Phase 4 新增：3 个前置场景闸门
# ============================================================

def _check_non_marketing_absolute(
    rule_card: RuleCard,
    chunk_fact: ChunkFactProfile | None,
) -> Optional[GateSignal]:
    """闸门 1：非产品/非营销上下文的绝对化表述

    规则：
    - 如果规则是绝对化类（claim_ranking），但文本中没有营销信号
    - 检查是否为历史人物、故事、调侃等非营销语境
    - 检查是否为主观感受（"我觉得""我认为"）

    判断依据：
    - 有 time_past + actor_third_party → 历史语境
    - 有 actor_customer 但无 claim_income_promise/claim_comparison → 非营销
    - 无 actor_agent 且无 claim_* → 非营销
    """
    if not rule_card.claim_type or "ranking" not in rule_card.claim_type.lower():
        return None

    if not chunk_fact or not chunk_fact.signals:
        return None

    signal_labels = {s.label for s in chunk_fact.signals}

    # 检查历史语境
    if "time_past" in signal_labels and "actor_third_party" in signal_labels:
        return GateSignal(
            signal_type="non_marketing_absolute",
            confidence=0.8,
            reason="检测到历史语境（过去时态 + 第三方主体），绝对化表述可能不构成营销违规",
            evidence_labels=["time_past", "actor_third_party"]
        )

    # 检查非营销语境（有客户但无营销主张）
    has_customer = "actor_customer" in signal_labels
    has_marketing_claim = any(
        label in signal_labels
        for label in ["claim_income_promise", "claim_comparison", "claim_ranking"]
    )

    if has_customer and not has_marketing_claim:
        return GateSignal(
            signal_type="non_marketing_absolute",
            confidence=0.6,
            reason="检测到客户主体但无营销主张，绝对化表述可能不构成营销违规",
            evidence_labels=["actor_customer"]
        )

    # 检查完全无营销信号
    has_agent = "actor_agent" in signal_labels
    has_any_claim = any(label.startswith("claim_") for label in signal_labels)

    if not has_agent and not has_any_claim:
        return GateSignal(
            signal_type="non_marketing_absolute",
            confidence=0.5,
            reason="未检测到代理人主体和营销主张，绝对化表述可能不构成营销违规",
            evidence_labels=[]
        )

    return None


def _check_sufficient_disclaimer(
    rule_card: RuleCard,
    chunk_fact: ChunkFactProfile | None,
) -> Optional[GateSignal]:
    """闸门 2：规范提示语充分的减保/保单贷款说明

    规则：
    - 如果规则涉及减保/保单贷款（claim_surrender），检查是否有充分提示语
    - 充分提示语包括：降低保障额度、影响现金价值、谨慎选择等

    判断依据：
    - 文本中包含 2 个以上减保提示语 → 提示充分
    - 文本中包含 2 个以上贷款提示语 → 提示充分
    """
    if not rule_card.claim_type or "surrender" not in rule_card.claim_type.lower():
        # 也检查规则名称和违规定义
        rule_text = f"{rule_card.rule_name} {rule_card.violation_definition}".lower()
        if "减保" not in rule_text and "保单贷款" not in rule_text:
            return None

    if not chunk_fact or not chunk_fact.signals:
        return None

    # 获取文本内容（从 signals 的 value 中提取）
    text_content = " ".join(s.value for s in chunk_fact.signals)

    # 检查减保提示语
    surrender_disclaimer_count = sum(
        1 for term in DISCLAIMER_SURRENDER_TERMS if term in text_content
    )

    if surrender_disclaimer_count >= 2:
        return GateSignal(
            signal_type="sufficient_disclaimer",
            confidence=0.8,
            reason=f"检测到 {surrender_disclaimer_count} 个减保风险提示语，提示充分",
            evidence_labels=["disclaimer_surrender"]
        )

    # 检查保单贷款提示语
    loan_disclaimer_count = sum(
        1 for term in DISCLAIMER_LOAN_TERMS if term in text_content
    )

    if loan_disclaimer_count >= 2:
        return GateSignal(
            signal_type="sufficient_disclaimer",
            confidence=0.8,
            reason=f"检测到 {loan_disclaimer_count} 个保单贷款风险提示语，提示充分",
            evidence_labels=["disclaimer_loan"]
        )

    return None


def _check_neutral_vs_sales(
    rule_card: RuleCard,
    chunk_fact: ChunkFactProfile | None,
) -> Optional[GateSignal]:
    """闸门 3：中性知识说明 vs 销售话术

    规则：
    - 检查文本是否为中性知识说明（介绍功能、说明规则、解释条款）
    - 还是销售话术（诱导购买、优势夸大、对比贬损、收益承诺、背书增强）

    判断依据：
    - 有中性知识标志词 且 无销售话术标志词 → 中性知识说明
    - 有销售话术标志词 → 销售话术
    """
    if not chunk_fact or not chunk_fact.signals:
        return None

    # 获取文本内容
    text_content = " ".join(s.value for s in chunk_fact.signals)

    # 检查中性知识标志词
    neutral_count = sum(1 for term in NEUTRAL_KNOWLEDGE_TERMS if term in text_content)

    # 检查销售话术标志词
    sales_count = sum(1 for term in SALES_PITCH_TERMS if term in text_content)

    # 如果有中性知识标志词且无销售话术标志词
    if neutral_count > 0 and sales_count == 0:
        return GateSignal(
            signal_type="neutral_knowledge",
            confidence=0.7,
            reason=f"检测到 {neutral_count} 个中性知识标志词，无销售话术标志词，可能为客观说明",
            evidence_labels=["neutral_knowledge"]
        )

    # 如果有销售话术标志词
    if sales_count > 0:
        return GateSignal(
            signal_type="sales_pitch",
            confidence=0.7,
            reason=f"检测到 {sales_count} 个销售话术标志词，可能为营销话术",
            evidence_labels=["sales_pitch"]
        )

    # 检查是否缺少诱导性表述（无 claim_income_promise/claim_comparison/claim_ranking）
    signal_labels = {s.label for s in chunk_fact.signals}
    has_inducement = any(
        label in signal_labels
        for label in ["claim_income_promise", "claim_comparison", "claim_ranking", "tone_guarantee"]
    )

    if not has_inducement:
        return GateSignal(
            signal_type="neutral_knowledge",
            confidence=0.5,
            reason="未检测到诱导性表述（收益承诺、对比、排名、保证），可能为客观说明",
            evidence_labels=[]
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

    Phase 4 升级：新增 3 个前置场景闸门检查

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

        # 运行 7 个检查（原有 4 个 + 新增 3 个）
        gate_signals: List[GateSignal] = []

        # 原有 4 个检查
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

        # Phase 4 新增：3 个前置场景闸门
        sig = _check_non_marketing_absolute(rule_card, chunk_fact)
        if sig:
            gate_signals.append(sig)
            signal_counter[sig.signal_type] = signal_counter.get(sig.signal_type, 0) + 1

        sig = _check_sufficient_disclaimer(rule_card, chunk_fact)
        if sig:
            gate_signals.append(sig)
            signal_counter[sig.signal_type] = signal_counter.get(sig.signal_type, 0) + 1

        sig = _check_neutral_vs_sales(rule_card, chunk_fact)
        if sig:
            gate_signals.append(sig)
            signal_counter[sig.signal_type] = signal_counter.get(sig.signal_type, 0) + 1

        # 决定是否跳过 Stage 2
        should_skip = False
        priority = "high"  # 默认高优先级

        # 如果有高置信度的 actor_mismatch，可以跳过
        for sig in gate_signals:
            if sig.signal_type == "actor_mismatch" and sig.confidence >= 0.8:
                should_skip = True
                skip_count += 1
                break

        # Phase 4 新增：如果有高置信度的前置场景闸门信号，降低优先级
        has_gate_signal = False
        for sig in gate_signals:
            if sig.signal_type in ["non_marketing_absolute", "sufficient_disclaimer", "neutral_knowledge"]:
                if sig.confidence >= 0.7:
                    priority = "low"
                    has_gate_signal = True
                    break

        # 如果没有前置场景闸门信号，按信号数量分配优先级
        if not has_gate_signal:
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
