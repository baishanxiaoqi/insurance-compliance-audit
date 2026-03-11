"""
Stage 3: 确定性定位与 API 组装
================================
纯 Python 工程代码，无 LLM 参与。
负责零幻觉定位、坐标还原、结果聚合。

定位策略：
    - 仅使用 Stage 2 返回的 evidence_span_ids 做确定性定位（span-only）
    - 严禁依赖 evidence_texts 做全文子串匹配，避免重复语句导致错位
"""

from typing import Dict, List, Tuple

from ..log import get_logger
from ..schemas import (
    DocumentState, RuleCard, JudgmentResult,
    ViolationLocation, FinalViolation, AuditResponse
)

logger = get_logger(__name__)

# ============================================================
# span-only 确定性定位
# ============================================================

def _norm_to_raw(document: DocumentState, norm_idx: int, is_end: bool = False) -> int:
    """
    将规范化坐标映射到原始文本坐标（两级映射）

    映射链路：normalized_text → working_text → original_text
    """
    # 第一级：norm → working
    if is_end:
        key = norm_idx - 1 if norm_idx > 0 else 0
        working_idx = document.norm_to_raw_map.get(key, norm_idx)
        if key in document.norm_to_raw_map:
            working_idx += 1
    else:
        working_idx = document.norm_to_raw_map.get(norm_idx, norm_idx)

    # 第二级：working → original
    if is_end:
        key = working_idx - 1 if working_idx > 0 else 0
        original_idx = document.working_to_original_map.get(key, working_idx)
        if key in document.working_to_original_map:
            original_idx += 1
        return original_idx
    else:
        return document.working_to_original_map.get(working_idx, working_idx)


def _trim_punctuation(text: str, start: int, end: int) -> Tuple[int, int]:
    """
    去除违规片段首尾的标点符号，确保输出最小完整语义单元。

    参数:
        text: 原始文本
        start: 起始位置
        end: 结束位置

    返回:
        (trimmed_start, trimmed_end): 去除标点后的位置
    """
    import string
    # 中文标点符号
    chinese_punct = '，。；！？、：""''（）【】《》'
    # 所有标点符号（中英文）
    all_punct = string.punctuation + chinese_punct

    # 去除开头的标点和空白
    while start < end and (text[start] in all_punct or text[start].isspace()):
        start += 1

    # 去除结尾的标点和空白
    while start < end and (text[end-1] in all_punct or text[end-1].isspace()):
        end -= 1

    return start, end


def locate_violation_spans(
    judgment: JudgmentResult,
    document: DocumentState,
) -> List[ViolationLocation]:
    """
    零幻觉定位（span-only 版）：
    仅使用 evidence_span_ids 还原坐标并合并相邻 span。
    """
    locations: List[ViolationLocation] = []

    # span 坐标定位（合并相邻 span，不做边界扩展）
    if not judgment.evidence_span_ids:
        return []

    span_entries: List[Tuple[int, int, str]] = []
    for span_id in judgment.evidence_span_ids:
        span = document.span_pool.get(span_id)
        if not span:
            logger.warning(f"  span_id '{span_id}' 不在 span_pool 中，跳过")
            continue
        span_entries.append((span.start_index, span.end_index, span_id))

    if not span_entries:
        return []

    # 排序 + 合并相邻（优化：只合并紧邻的 span，避免包含无关内容）
    span_entries.sort(key=lambda x: x[0])
    merged_ranges: List[Tuple[int, int, List[str]]] = []
    cur_start, cur_end, cur_ids = span_entries[0][0], span_entries[0][1], [span_entries[0][2]]
    for ns, ne, sid in span_entries[1:]:
        # 阈值从 5 改为 0：只合并完全重叠或紧邻的 span，确保最小完整语义单元
        if ns <= cur_end:
            cur_end = max(cur_end, ne)
            cur_ids.append(sid)
        else:
            merged_ranges.append((cur_start, cur_end, cur_ids))
            cur_start, cur_end, cur_ids = ns, ne, [sid]
    merged_ranges.append((cur_start, cur_end, cur_ids))

    for norm_start, norm_end, span_ids in merged_ranges:
        raw_start = _norm_to_raw(document, norm_start)
        raw_end = _norm_to_raw(document, norm_end, is_end=True)

        # 去除首尾标点符号，确保输出最小完整语义单元
        raw_start, raw_end = _trim_punctuation(
            document.original_text, raw_start, raw_end
        )

        original_slice = document.original_text[raw_start:raw_end]
        locations.append(ViolationLocation(
            span_ids=span_ids,
            original_text_slice=original_slice,
            norm_start=norm_start,
            norm_end=norm_end,
            raw_start=raw_start,
            raw_end=raw_end,
        ))

    return locations


def assemble_violations(
    judgments: List[JudgmentResult],
    document: DocumentState,
    rule_cards: Dict[str, RuleCard],
) -> List[FinalViolation]:
    """
    结果聚合：
    1. 筛选 verdict == "violation" 的判定结果
    2. 对每个违规判定进行定位和坐标还原
    3. 基于 span 坐标范围重叠进行智能去重（处理 chunk overlap 导致的重复）
    4. 组装为 FinalViolation 列表
    """
    violations: List[FinalViolation] = []

    # 只处理 violation 判定
    violation_judgments = [j for j in judgments if j.verdict == "violation"]
    logger.info(f"Stage 3: 共 {len(violation_judgments)} 个违规判定需要定位")

    # 收集所有候选违规（按 rule_id 分组）
    raw_violations: Dict[str, List[FinalViolation]] = {}

    for judgment in violation_judgments:
        rule_card = rule_cards.get(judgment.rule_id)
        if not rule_card:
            logger.warning(f"  RuleCard {judgment.rule_id} 未找到，跳过")
            continue

        # 零幻觉定位
        locations = locate_violation_spans(judgment, document)

        if not locations:
            logger.warning(
                f"  [{judgment.chunk_id} x {judgment.rule_id}] "
                f"无有效违规位置，跳过"
            )
            continue

        violation = FinalViolation(
            rule_id=judgment.rule_id,
            rule_name=rule_card.rule_name,
            risk_level=rule_card.risk_level,
            verdict=judgment.verdict,
            reasoning=judgment.reasoning_cot,
            locations=locations,
            reason_codes=judgment.reason_codes,
            suggestion=judgment.draft_suggestion,
        )

        if judgment.rule_id not in raw_violations:
            raw_violations[judgment.rule_id] = []
        raw_violations[judgment.rule_id].append(violation)

    # 按 rule_id 分组去重：同一规则下，如果两条违规的 span 坐标范围有重叠，则合并
    for rule_id, group in raw_violations.items():
        merged = _merge_overlapping_violations(group)
        violations.extend(merged)

    # 按 raw_start 排序，使输出有序
    violations.sort(key=lambda v: v.locations[0].raw_start if v.locations else 0)

    logger.info(f"Stage 3 完成: 共 {len(violations)} 个去重后的违规结果")
    return violations


def _merge_overlapping_violations(
    violations: List[FinalViolation],
) -> List[FinalViolation]:
    """
    对同一 rule_id 下的违规结果进行基于坐标重叠的去重合并。
    两条违规的 span 坐标范围有交集时，保留最短语义的违规片段（文本长度最短）。
    """
    if len(violations) <= 1:
        return violations

    # 计算每条违规的坐标范围和总文本长度
    def _get_range(v: FinalViolation) -> tuple:
        starts = [loc.norm_start for loc in v.locations]
        ends = [loc.norm_end for loc in v.locations]
        return (min(starts), max(ends))

    def _get_total_length(v: FinalViolation) -> int:
        """计算所有 locations 的总文本长度"""
        return sum(len(loc.original_text_slice) for loc in v.locations)

    # 按起始位置排序
    sorted_v = sorted(violations, key=lambda v: _get_range(v)[0])

    merged: List[FinalViolation] = []
    current = sorted_v[0]
    current_range = _get_range(current)

    for v in sorted_v[1:]:
        v_range = _get_range(v)

        # 判断是否有坐标重叠
        if v_range[0] < current_range[1]:
            # 重叠 → 保留最短语义的违规片段（文本长度最短）
            current_len = _get_total_length(current)
            v_len = _get_total_length(v)

            if v_len < current_len:
                current = v
                current_range = v_range
            elif v_len == current_len:
                # 长度相同，保留 locations 数量更少的（更精确）
                if len(v.locations) < len(current.locations):
                    current = v
                    current_range = v_range
            # 否则保留 current
        else:
            # 无重叠 → current 已完结，加入结果
            merged.append(current)
            current = v
            current_range = v_range

    merged.append(current)
    return merged


def run_stage3(
    judgments: List[JudgmentResult],
    document: DocumentState,
    rule_cards: Dict[str, RuleCard],
    processing_time: float,
) -> AuditResponse:
    """
    Stage 3 主函数：
    1. 筛选 violation 判定
    2. 零幻觉定位 + 坐标还原
    3. 结果聚合 + 去重
    4. 组装最终 API 响应体
    """
    violations = assemble_violations(judgments, document, rule_cards)

    return AuditResponse(
        doc_id=document.doc_id,
        total_violations=len(violations),
        violations=violations,
        processing_time_seconds=round(processing_time, 2),
    )
