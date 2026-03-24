"""
Stage 2.5: 审查点 Override 层（Audit Point Override Layer）
===========================================================
Phase 4 P1 升级：从"反证校验"升级为"审查点 override 层"

对 Stage 2 的 violation 结果进行二次复核，降低误报：
  1) 配置化 override 规则：基于审查点知识的最终裁决修正
  2) 可执行规则反证：若规则引擎判断 hard_block，则将 violation 纠偏为 compliant
  3) 否定语境反证：若违规词处于明显否定结构中（如"不要退保"），将 violation 纠偏为 compliant

说明：
  - 本阶段为保守纠偏，仅在强反证场景改判
  - 支持配置化 override 规则，便于扩展和维护
  - 输出结构保持 JudgmentResult，不改外部 API 契约
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

from ..ac_matcher import AhocorasickMatcher
from ..audit_trace import trace_event
from ..log import get_logger
from ..rule_engine import evaluate_rule_on_text
from ..schemas import ChunkFactProfile, DocumentState, JudgmentResult, RuleCard
from ..stages.stage1_9_gate import GateResult

logger = get_logger(__name__)


NEGATION_PREFIX = ["不", "未", "无", "非", "别", "勿", "不要", "不可", "不能", "不得"]


# ============================================================
# Phase 4 P1 新增：Override 配置数据结构
# ============================================================

@dataclass
class OverrideConditions:
    """Override 规则的触发条件"""
    rule_claim_type: Optional[List[str]] = None
    rule_keywords_any: Optional[List[str]] = None
    gate_signals: Optional[List[str]] = None
    min_gate_confidence: float = 0.0
    no_sales_pitch: bool = False
    chunk_fact_signals_not_include: Optional[List[str]] = None
    rule_engine_hard_block: bool = False
    has_negated_violation_term: bool = False


@dataclass
class OverrideAction:
    """Override 规则的执行动作"""
    change_verdict_to: str
    reasoning_template: str


@dataclass
class OverrideRule:
    """Override 规则定义"""
    override_id: str
    name: str
    description: str
    enabled: bool
    priority: int
    conditions: OverrideConditions
    action: OverrideAction


def _infer_override_decision_basis(override_rule: OverrideRule, judgment: JudgmentResult) -> str | None:
    if override_rule.override_id == "negation_context":
        return "negation_context"
    if override_rule.override_id == "deterministic_hard_block":
        return judgment.decision_basis or "condition_not_met"
    if override_rule.action.change_verdict_to == "compliant":
        return "exception_applied"
    return judgment.decision_basis


def load_override_rules(config_path: str = "data/override_rules.json") -> List[OverrideRule]:
    """加载 override 规则配置"""
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"Override 配置文件不存在: {config_path}，使用默认规则")
            return []

        with config_file.open("r", encoding="utf-8") as f:
            config = json.load(f)

        rules = []
        for rule_data in config.get("rules", []):
            if not rule_data.get("enabled", True):
                continue

            conditions_data = rule_data.get("conditions", {})
            conditions = OverrideConditions(
                rule_claim_type=conditions_data.get("rule_claim_type"),
                rule_keywords_any=conditions_data.get("rule_keywords_any"),
                gate_signals=conditions_data.get("gate_signals"),
                min_gate_confidence=conditions_data.get("min_gate_confidence", 0.0),
                no_sales_pitch=conditions_data.get("no_sales_pitch", False),
                chunk_fact_signals_not_include=conditions_data.get("chunk_fact_signals_not_include"),
                rule_engine_hard_block=conditions_data.get("rule_engine_hard_block", False),
                has_negated_violation_term=conditions_data.get("has_negated_violation_term", False),
            )

            action_data = rule_data.get("action", {})
            action = OverrideAction(
                change_verdict_to=action_data.get("change_verdict_to", "compliant"),
                reasoning_template=action_data.get("reasoning_template", "Override 改判"),
            )

            rules.append(OverrideRule(
                override_id=rule_data["override_id"],
                name=rule_data["name"],
                description=rule_data["description"],
                enabled=rule_data.get("enabled", True),
                priority=rule_data.get("priority", 100),
                conditions=conditions,
                action=action,
            ))

        # 按优先级排序（优先级数字越小越优先）
        rules.sort(key=lambda r: r.priority)
        logger.info(f"加载了 {len(rules)} 条 override 规则")
        return rules

    except Exception as e:
        logger.error(f"加载 override 配置失败: {e}")
        return []


def _has_negated_violation_term(text: str, rule_card: RuleCard) -> bool:
    """检测明显的否定违规词结构，例如"不要退保""不得误导"。

    策略：
    1. 使用 AC 自动机分别定位否定词和违规词的位置
    2. 检查是否存在"否定词后紧跟违规词"的模式（允许中间有空白字符）
    3. 距离阈值：否定词结束位置 + 5 个字符内出现违规词视为否定语境
    """
    violation_terms = rule_card.violation_terms or rule_card.keywords
    if not violation_terms:
        return False

    # 使用 AC 自动机分别匹配否定词和违规词
    negation_matcher = AhocorasickMatcher(NEGATION_PREFIX)
    violation_matcher = AhocorasickMatcher([t for t in violation_terms if t])

    negation_matches = negation_matcher.find_all(text)
    violation_matches = violation_matcher.find_all(text)

    if not negation_matches or not violation_matches:
        return False

    # 收集所有否定词的结束位置
    negation_end_positions = []
    for neg_term, positions in negation_matches.items():
        neg_len = len(neg_term)
        for pos in positions:
            negation_end_positions.append(pos + neg_len)

    # 收集所有违规词的起始位置
    violation_start_positions = []
    for positions in violation_matches.values():
        violation_start_positions.extend(positions)

    # 检查是否存在"否定词结束后 5 个字符内出现违规词"的模式
    # 这可以容忍多个空格、换行等空白字符
    MAX_GAP = 5
    for neg_end in negation_end_positions:
        for vio_start in violation_start_positions:
            if 0 <= vio_start - neg_end <= MAX_GAP:
                return True

    return False


# ============================================================
# Phase 4 P1 新增：Override 规则匹配逻辑
# ============================================================

def _check_override_conditions(
    override_rule: OverrideRule,
    judgment: JudgmentResult,
    rule_card: RuleCard,
    chunk_text: str,
    chunk_fact: Optional[ChunkFactProfile],
    gate_result: Optional[GateResult],
    rule_engine_report: Optional[any],
) -> tuple[bool, Dict[str, str]]:
    """检查 override 规则的条件是否满足

    返回：(是否满足, 模板变量字典)
    """
    conditions = override_rule.conditions
    template_vars = {}

    # 条件 1：rule_claim_type
    if conditions.rule_claim_type:
        if not rule_card.claim_type or rule_card.claim_type not in conditions.rule_claim_type:
            return False, {}

    # 条件 2：rule_keywords_any
    if conditions.rule_keywords_any:
        rule_keywords = set(rule_card.keywords)
        if not any(kw in rule_keywords for kw in conditions.rule_keywords_any):
            return False, {}

    # 条件 3：gate_signals
    if conditions.gate_signals and gate_result:
        matched_signal = None
        for signal in gate_result.gate_signals:
            if signal.signal_type in conditions.gate_signals:
                if signal.confidence >= conditions.min_gate_confidence:
                    matched_signal = signal
                    break

        if not matched_signal:
            return False, {}

        template_vars["gate_signal_reason"] = matched_signal.reason

    # 条件 4：no_sales_pitch
    if conditions.no_sales_pitch and gate_result:
        has_sales_pitch = any(
            sig.signal_type == "sales_pitch"
            for sig in gate_result.gate_signals
        )
        if has_sales_pitch:
            return False, {}

    # 条件 5：chunk_fact_signals_not_include
    if conditions.chunk_fact_signals_not_include and chunk_fact:
        signal_labels = {s.label for s in chunk_fact.signals}
        if any(label in signal_labels for label in conditions.chunk_fact_signals_not_include):
            return False, {}

    # 条件 6：rule_engine_hard_block
    if conditions.rule_engine_hard_block:
        if not rule_engine_report or not rule_engine_report.hard_block:
            return False, {}
        template_vars["rule_engine_summary"] = rule_engine_report.summary

    # 条件 7：has_negated_violation_term
    if conditions.has_negated_violation_term:
        if not _has_negated_violation_term(chunk_text, rule_card):
            return False, {}

    return True, template_vars


def _apply_override(
    override_rule: OverrideRule,
    judgment: JudgmentResult,
    template_vars: Dict[str, str],
) -> JudgmentResult:
    """应用 override 规则，生成新的 JudgmentResult"""
    reasoning = override_rule.action.reasoning_template.format(**template_vars)

    return JudgmentResult(
        rule_id=judgment.rule_id,
        chunk_id=judgment.chunk_id,
        verdict=override_rule.action.change_verdict_to,
        reasoning_cot=reasoning,
        evidence_span_ids=[],
        evidence_texts=[],
        reason_codes=[],
        decision_basis=_infer_override_decision_basis(override_rule, judgment),
        primary_category=judgment.primary_category,
        secondary_category=judgment.secondary_category,
    )


def run_stage2_5_refute(
    judgments: List[JudgmentResult],
    document: DocumentState,
    rule_cards: Dict[str, RuleCard],
    chunk_facts: Dict[str, ChunkFactProfile] | None = None,
    gate_results: Dict[str, GateResult] | None = None,
    override_config_path: str = "data/override_rules.json",
) -> List[JudgmentResult]:
    """执行审查点 override，返回纠偏后的 JudgmentResult 列表。

    Phase 4 P1 升级：支持配置化 override 规则

    参数：
        judgments: Stage 2 的判定结果
        document: 文档状态
        rule_cards: 规则卡片字典
        chunk_facts: Chunk 事实画像字典（来自 Stage 1.5）
        gate_results: Gate 结果字典（来自 Stage 1.9）
        override_config_path: Override 配置文件路径
    """
    chunk_map = {c.chunk_id: c for c in document.chunks}
    revised: List[JudgmentResult] = []
    revised_count = 0
    override_stats: Dict[str, int] = {}

    # 加载 override 规则
    override_rules = load_override_rules(override_config_path)

    for judgment in judgments:
        if judgment.verdict != "violation":
            revised.append(judgment)
            continue

        rule_card = rule_cards.get(judgment.rule_id)
        chunk = chunk_map.get(judgment.chunk_id)
        if rule_card is None or chunk is None:
            revised.append(judgment)
            continue

        chunk_fact = chunk_facts.get(judgment.chunk_id) if chunk_facts else None
        gate_result = gate_results.get(f"{judgment.chunk_id}_{judgment.rule_id}") if gate_results else None

        # 计算规则引擎报告（用于 deterministic_hard_block override）
        rule_engine_report = evaluate_rule_on_text(chunk.chunk_text, rule_card)

        # 尝试应用 override 规则（按优先级顺序）
        override_applied = False
        for override_rule in override_rules:
            matched, template_vars = _check_override_conditions(
                override_rule=override_rule,
                judgment=judgment,
                rule_card=rule_card,
                chunk_text=chunk.chunk_text,
                chunk_fact=chunk_fact,
                gate_result=gate_result,
                rule_engine_report=rule_engine_report,
            )

            if matched:
                # 应用 override
                new_judgment = _apply_override(override_rule, judgment, template_vars)
                revised.append(new_judgment)
                revised_count += 1
                override_applied = True

                # 统计
                override_stats[override_rule.override_id] = override_stats.get(override_rule.override_id, 0) + 1

                # 审计轨迹
                trace_event(
                    "stage2_5.override_applied",
                    {
                        "chunk_id": judgment.chunk_id,
                        "rule_id": judgment.rule_id,
                        "override_id": override_rule.override_id,
                        "override_name": override_rule.name,
                        "from": "violation",
                        "to": new_judgment.verdict,
                    },
                )

                break  # 只应用第一个匹配的 override

        if not override_applied:
            revised.append(judgment)

    # 日志和审计轨迹
    trace_event(
        "stage2_5.summary",
        {
            "input_count": len(judgments),
            "revised_count": revised_count,
            "output_count": len(revised),
            "override_stats": override_stats,
        },
    )

    if override_stats:
        stats_summary = ", ".join(f"{k}={v}" for k, v in override_stats.items())
        logger.info(f"Stage 2.5 完成: 复核 {len(judgments)} 条判定，改判 {revised_count} 条（{stats_summary}）")
    else:
        logger.info(f"Stage 2.5 完成: 复核 {len(judgments)} 条判定，改判 {revised_count} 条")

    return revised
