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

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List

from . import config
from .schemas import RuleCard
from .ac_matcher import AhocorasickMatcher

# 跨 Stage 结果缓存：相同 (chunk_text, rule_id) 只评估一次
# 使用有上限的 LRU，避免长时间运行进程无限增长
# threading.Lock 保证在 run_in_executor 等多线程场景下的安全访问
_eval_cache: OrderedDict[tuple[str, str], "RuleEvalReport"] = OrderedDict()
_eval_cache_lock = threading.Lock()


def clear_eval_cache() -> None:
    with _eval_cache_lock:
        _eval_cache.clear()


def get_eval_cache_size() -> int:
    with _eval_cache_lock:
        return len(_eval_cache)


def _get_cached_report(cache_key: tuple[str, str]) -> "RuleEvalReport" | None:
    with _eval_cache_lock:
        report = _eval_cache.get(cache_key)
        if report is not None:
            _eval_cache.move_to_end(cache_key)
        return report


def _set_cached_report(cache_key: tuple[str, str], report: "RuleEvalReport") -> None:
    max_size = max(0, config.RULE_ENGINE_CACHE_MAX_SIZE)
    if max_size <= 0:
        return
    with _eval_cache_lock:
        _eval_cache[cache_key] = report
        _eval_cache.move_to_end(cache_key)
        while len(_eval_cache) > max_size:
            _eval_cache.popitem(last=False)


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
    prefix_matcher: AhocorasickMatcher | None = None,
    suffix_matcher: AhocorasickMatcher | None = None,
) -> List[int]:
    """
    前缀/后缀不匹配规则：拼接词命中时，该位置不计入违规词命中。
    例：违规词=免税，后缀不匹配=店，命中"免税店"则该次命中剔除。
    """
    blocked_positions = set()

    # 使用 AC 自动机匹配前后缀（如果提供）
    if prefix_matcher:
        all_prefix_matches = prefix_matcher.find_all(text)
        for p in prefixes:
            if p in all_prefix_matches:
                phrase = f"{p}{term}"
                # 创建临时 matcher 查找拼接词
                temp_matcher = AhocorasickMatcher([phrase])
                for idx in temp_matcher.find_positions(text, phrase):
                    blocked_positions.add(idx + len(p))
    else:
        # 回退到逐个查找
        for p in prefixes:
            phrase = f"{p}{term}"
            temp_matcher = AhocorasickMatcher([phrase])
            for idx in temp_matcher.find_positions(text, phrase):
                blocked_positions.add(idx + len(p))

    if suffix_matcher:
        all_suffix_matches = suffix_matcher.find_all(text)
        for s in suffixes:
            if s in all_suffix_matches:
                phrase = f"{term}{s}"
                temp_matcher = AhocorasickMatcher([phrase])
                for idx in temp_matcher.find_positions(text, phrase):
                    blocked_positions.add(idx)
    else:
        # 回退到逐个查找
        for s in suffixes:
            phrase = f"{term}{s}"
            temp_matcher = AhocorasickMatcher([phrase])
            for idx in temp_matcher.find_positions(text, phrase):
                blocked_positions.add(idx)

    return [pos for pos in positions if pos not in blocked_positions]


def evaluate_rule_on_text(text: str, rule_card: RuleCard) -> RuleEvalReport:
    cache_key = (text, rule_card.rule_id)
    cached = _get_cached_report(cache_key)
    if cached is not None:
        return cached

    report = RuleEvalReport(rule_id=rule_card.rule_id)

    violation_terms = rule_card.violation_terms or rule_card.keywords
    condition_terms = rule_card.condition_terms
    exclusion_terms = rule_card.exclusion_terms

    # 构建 AC 自动机
    violation_matcher = AhocorasickMatcher([t for t in violation_terms if t])
    condition_matcher = AhocorasickMatcher([t for t in condition_terms if t]) if condition_terms else None
    exclusion_matcher = AhocorasickMatcher([t for t in exclusion_terms if t]) if exclusion_terms else None
    prefix_matcher = AhocorasickMatcher([t for t in rule_card.prefix_no_match if t]) if rule_card.prefix_no_match else None
    suffix_matcher = AhocorasickMatcher([t for t in rule_card.suffix_no_match if t]) if rule_card.suffix_no_match else None

    # 1) 违规词命中 + 前后缀不匹配过滤
    all_violation_matches = violation_matcher.find_all(text)
    for term in violation_terms:
        if not term:
            continue
        positions = all_violation_matches.get(term, [])
        if positions:
            positions = _filter_positions_by_no_match(
                text=text,
                term=term,
                positions=positions,
                prefixes=rule_card.prefix_no_match,
                suffixes=rule_card.suffix_no_match,
                prefix_matcher=prefix_matcher,
                suffix_matcher=suffix_matcher,
            )
            if positions:
                report.violation_positions[term] = positions

    all_violation_positions = [p for arr in report.violation_positions.values() for p in arr]
    report.has_violation_hit = bool(all_violation_positions)
    if not report.has_violation_hit:
        report.hard_block = True
        report.summary = "无有效违规词命中（或被前后缀不匹配规则过滤）"
        _set_cached_report(cache_key, report)
        return report

    # 2) 条件词约束
    if condition_terms and condition_matcher:
        all_condition_matches = condition_matcher.find_all(text)
        for term in condition_terms:
            if not term:
                continue
            positions = all_condition_matches.get(term, [])
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
            _set_cached_report(cache_key, report)
            return report

    # 3) 排除词约束（命中则硬阻断）
    if exclusion_terms and exclusion_matcher:
        all_exclusion_matches = exclusion_matcher.find_all(text)
        for term in exclusion_terms:
            if not term:
                continue
            positions = all_exclusion_matches.get(term, [])
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
            _set_cached_report(cache_key, report)
            return report

    report.summary = "通过可执行规则前置校验"
    _set_cached_report(cache_key, report)
    return report
