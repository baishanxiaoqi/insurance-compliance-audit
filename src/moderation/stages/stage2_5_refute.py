"""
Stage 2.5: 反证校验（Refute Validator）
=======================================
对 Stage 2 的 violation 结果进行二次复核，降低误报：
  1) 可执行规则反证：若规则引擎判断 hard_block，则将 violation 纠偏为 compliant
  2) 否定语境反证：若违规词处于明显否定结构中（如"不要退保"），将 violation 纠偏为 compliant

说明：
  - 本阶段为保守纠偏，仅在强反证场景改判
  - 输出结构保持 JudgmentResult，不改外部 API 契约
"""

from __future__ import annotations

from typing import Dict, List

from ..ac_matcher import AhocorasickMatcher
from ..audit_trace import trace_event
from ..log import get_logger
from ..rule_engine import evaluate_rule_on_text
from ..schemas import ChunkFactProfile, DocumentState, JudgmentResult, RuleCard

logger = get_logger(__name__)


NEGATION_PREFIX = ["不", "未", "无", "非", "别", "勿", "不要", "不可", "不能", "不得"]


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


def run_stage2_5_refute(
    judgments: List[JudgmentResult],
    document: DocumentState,
    rule_cards: Dict[str, RuleCard],
    chunk_facts: Dict[str, ChunkFactProfile] | None = None,
) -> List[JudgmentResult]:
    """执行反证校验，返回纠偏后的 JudgmentResult 列表。"""
    chunk_map = {c.chunk_id: c for c in document.chunks}
    revised: List[JudgmentResult] = []
    revised_count = 0

    for judgment in judgments:
        if judgment.verdict != "violation":
            revised.append(judgment)
            continue

        rule_card = rule_cards.get(judgment.rule_id)
        chunk = chunk_map.get(judgment.chunk_id)
        if rule_card is None or chunk is None:
            revised.append(judgment)
            continue

        # 反证 1：可执行规则硬阻断
        report = evaluate_rule_on_text(chunk.chunk_text, rule_card)
        if report.hard_block:
            trace_event(
                "stage2_5.refute_rewrite",
                {
                    "chunk_id": judgment.chunk_id,
                    "rule_id": judgment.rule_id,
                    "from": "violation",
                    "to": "compliant",
                    "reason": "deterministic_hard_block",
                    "summary": report.summary,
                },
            )
            revised.append(
                JudgmentResult(
                    rule_id=judgment.rule_id,
                    chunk_id=judgment.chunk_id,
                    verdict="compliant",
                    reasoning_cot=(
                        f"反证校验改判：可执行规则引擎给出硬阻断（{report.summary}），"
                        "当前 violation 与规则约束冲突，改判为 compliant。"
                    ),
                    evidence_span_ids=[],
                    evidence_texts=[],
                    reason_codes=[],
                    draft_suggestion="",
                )
            )
            revised_count += 1
            continue

        # 反证 2：明显否定语境
        if _has_negated_violation_term(chunk.chunk_text, rule_card):
            trace_event(
                "stage2_5.refute_rewrite",
                {
                    "chunk_id": judgment.chunk_id,
                    "rule_id": judgment.rule_id,
                    "from": "violation",
                    "to": "compliant",
                    "reason": "negation_context",
                    "summary": "命中明显否定语境",
                },
            )
            revised.append(
                JudgmentResult(
                    rule_id=judgment.rule_id,
                    chunk_id=judgment.chunk_id,
                    verdict="compliant",
                    reasoning_cot=(
                        "反证校验改判：检测到违规词处于明显否定语境（如'不要/不得+违规词'），"
                        "语义上为禁止或劝阻，不构成违规宣传，改判为 compliant。"
                    ),
                    evidence_span_ids=[],
                    evidence_texts=[],
                    reason_codes=[],
                    draft_suggestion="",
                )
            )
            revised_count += 1
            continue

        revised.append(judgment)

    trace_event(
        "stage2_5.summary",
        {
            "input_count": len(judgments),
            "revised_count": revised_count,
            "output_count": len(revised),
        },
    )
    logger.info(f"Stage 2.5 完成: 复核 {len(judgments)} 条判定，改判 {revised_count} 条")
    return revised

