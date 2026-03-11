"""
可执行规则判定器（最小版）
=========================
在 LLM 判定前提供确定性约束判断：
  1) 违规词命中（含前后缀不匹配过滤）
  2) 条件词距离约束
  3) 排除词距离约束（命中则硬阻断）

输出用于：
  - Stage2 前置短路（硬阻断/无命中直接 compliant）
  - 向 LLM 注入可执行规则证据，减少逻辑漂移
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from .schemas import RuleCard


@dataclass
class RuleEvalReport:
    rule_id: str
    violation_positions: Dict[str, List[int]] = field(default_factory=dict)
    condition_positions: Dict[str, List[int]] = field(default_factory=dict)
    exclusion_positions: Dict[str, List[int]] = field(default_factory=dict)
    condition_pass: bool = True
    exclusion_blocked: bool = False
    hard_block: bool = False
    has_violation_hit: bool = False
    summary: str = ""


def _find_positions(text: str, term: str) -> List[int]:
    if not term:
        return []
    return [m.start() for m in re.finditer(re.escape(term), text, re.IGNORECASE)]


def _has_near_pair(a_positions: List[int], b_positions: List[int], distance: int | None) -> bool:
    if not a_positions or not b_positions:
        return False
    if distance is None:
        return True
    for a in a_positions:
        for b in b_positions:
            if abs(a - b) <= distance:
                return True
    return False


def _filter_positions_by_no_match(
    text: str,
    term: str,
    positions: List[int],
    prefixes: List[str],
    suffixes: List[str],
) -> List[int]:
    blocked_positions = set()

    for p in prefixes:
        phrase = f"{p}{term}"
        for idx in _find_positions(text, phrase):
            blocked_positions.add(idx + len(p))

    for s in suffixes:
        phrase = f"{term}{s}"
        for idx in _find_positions(text, phrase):
            blocked_positions.add(idx)

    return [pos for pos in positions if pos not in blocked_positions]


def evaluate_rule_on_text(text: str, rule_card: RuleCard) -> RuleEvalReport:
    report = RuleEvalReport(rule_id=rule_card.rule_id)

    violation_terms = rule_card.violation_terms or rule_card.keywords
    condition_terms = rule_card.condition_terms
    exclusion_terms = rule_card.exclusion_terms

    # 1) 违规词命中 + 前后缀不匹配过滤
    for term in violation_terms:
        positions = _find_positions(text, term)
        positions = _filter_positions_by_no_match(
            text=text,
            term=term,
            positions=positions,
            prefixes=rule_card.prefix_no_match,
            suffixes=rule_card.suffix_no_match,
        )
        if positions:
            report.violation_positions[term] = positions

    all_violation_positions = [p for arr in report.violation_positions.values() for p in arr]
    report.has_violation_hit = bool(all_violation_positions)
    if not report.has_violation_hit:
        report.hard_block = True
        report.summary = "无有效违规词命中（或被前后缀不匹配规则过滤）"
        return report

    # 2) 条件词约束
    if condition_terms:
        for term in condition_terms:
            positions = _find_positions(text, term)
            if positions:
                report.condition_positions[term] = positions

        all_condition_positions = [p for arr in report.condition_positions.values() for p in arr]
        report.condition_pass = _has_near_pair(
            all_violation_positions,
            all_condition_positions,
            rule_card.condition_distance,
        )
        if not report.condition_pass:
            report.hard_block = True
            report.summary = "条件词未满足距离约束"
            return report

    # 3) 排除词约束（命中则硬阻断）
    if exclusion_terms:
        for term in exclusion_terms:
            positions = _find_positions(text, term)
            if positions:
                report.exclusion_positions[term] = positions

        all_exclusion_positions = [p for arr in report.exclusion_positions.values() for p in arr]
        report.exclusion_blocked = _has_near_pair(
            all_violation_positions,
            all_exclusion_positions,
            rule_card.exclusion_distance,
        )
        if report.exclusion_blocked:
            report.hard_block = True
            report.summary = "命中排除词距离约束，判定为例外"
            return report

    report.summary = "通过可执行规则前置校验"
    return report
