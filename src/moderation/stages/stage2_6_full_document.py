"""
Stage 2.6: 全文审核子流水线（并行于主流程）
===========================================
纯代码信号提取 + LLM 全文级合规检测。

当前检测项：
  - FULLDOC_R001: 引用第三方数据未提供来源
    当文本中出现数据引用（数字+排名/比例/增速等）但没有紧邻的来源说明时触发

设计原则（Strategy A）：
  - 全文级违规通过 evidence_span_ids 指向 span_pool 中真实存在的数据引用 span
  - chunk_id 固定为 "__fulldoc__"，Stage 3 通过普通 span_only 定位路径处理
  - 纯代码信号提取先于 LLM 调用，LLM 只在信号明确时才触发（节省 API 成本）
"""

from __future__ import annotations

import re
import json
from typing import Dict, List, Optional

from .. import config
from ..llm_agent import create_agent, safe_arun
from ..log import get_logger
from ..schemas import DocumentState, JudgmentResult, RuleCard, Span

logger = get_logger(__name__)

# 全文审核专用 chunk_id 标识符
FULLDOC_CHUNK_ID = "__fulldoc__"

# 全文审核规则 ID
FULLDOC_RULE_ID_THIRD_PARTY_SOURCE = "FULLDOC_R001"

# 全文审核规则卡片（注入 state.rule_cards，供 Stage 2.7 / Stage 3 使用）
_FULLDOC_RULE_CARDS: Dict[str, RuleCard] = {
    FULLDOC_RULE_ID_THIRD_PARTY_SOURCE: RuleCard(
        rule_id=FULLDOC_RULE_ID_THIRD_PARTY_SOURCE,
        rule_name="引用第三方数据未提供来源",
        risk_level="medium",
        violation_definition=(
            "文本引用了第三方可验证数据（行业排名、增速、市场份额等）"
            "但未提供数据来源说明"
        ),
        suggestion_template="引用数据时请注明来源，例如：\"（数据来源：XX报告）\"",
        primary_category="data_citation",
    )
}


def get_fulldoc_rule_cards() -> Dict[str, RuleCard]:
    """返回全文审核的合成规则卡片，供 Workflow 注入 state.rule_cards。"""
    return _FULLDOC_RULE_CARDS

# ============================================================
# 数据引用信号提取（纯代码）
# ============================================================

_DATA_CITATION_PATTERNS = [
    r'(?:排名?|排行|位列|位居|首位|第[一二三四五六七八九十\d]+名?)',
    r'\d+(?:\.\d+)?\s*%',
    r'\d+(?:\.\d+)?\s*倍',
    r'\d+(?:\.\d+)?\s*(?:亿|万|千)(?:元|件|份|人|次)',
    r'(?:增长|增速|增幅|同比|环比)\s*\d+(?:\.\d+)?\s*%?',
    r'(?:行业|市场|全国|全球)\s*(?:第[一二三四五六七八九十\d]+|前\d+|领先|最[大高强优])',
]

_SOURCE_INDICATOR_PATTERNS = [
    r'来源[：:]',
    r'数据来源',
    r'资料来源',
    r'据[^，。；]{1,20}(?:报告|数据|统计|调查|发布)',
    r'根据[^，。；]{1,20}(?:报告|数据|统计|调查|发布)',
    r'注[：:].*?(?:数据|来源)',
    r'\([^)]{1,30}(?:报告|数据|年度|年报)[^)]{0,20}\)',
    r'（[^）]{1,30}(?:报告|数据|年度|年报)[^）]{0,20}）',
]

_DATA_RE = re.compile('|'.join(_DATA_CITATION_PATTERNS))
_SOURCE_RE = re.compile('|'.join(_SOURCE_INDICATOR_PATTERNS))

_MAX_SOURCE_DISTANCE = 200


def _find_data_citation_spans(document: DocumentState) -> List[Span]:
    cited: List[Span] = []
    for span in document.span_pool.values():
        if _DATA_RE.search(span.span_text):
            cited.append(span)
    cited.sort(key=lambda s: s.start_index)
    return cited


def _has_nearby_source(document: DocumentState, data_span: Span) -> bool:
    norm_text = document.normalized_text
    start = max(0, data_span.start_index - _MAX_SOURCE_DISTANCE)
    end = min(len(norm_text), data_span.end_index + _MAX_SOURCE_DISTANCE)
    return bool(_SOURCE_RE.search(norm_text[start:end]))


def extract_document_audit_signals(document: DocumentState) -> Dict[str, object]:
    data_spans = _find_data_citation_spans(document)
    if not data_spans:
        return {
            "has_data_citation": False,
            "missing_source_span_ids": [],
            "all_data_span_ids": [],
            "has_source_indicators": False,
        }
    has_any_source = bool(_SOURCE_RE.search(document.normalized_text))
    missing: List[str] = [
        s.span_id for s in data_spans if not _has_nearby_source(document, s)
    ]
    return {
        "has_data_citation": True,
        "missing_source_span_ids": missing,
        "all_data_span_ids": [s.span_id for s in data_spans],
        "has_source_indicators": has_any_source,
    }


# ============================================================
# 全文审核 LLM Skill
# ============================================================

_FULLDOC_SYSTEM_INSTRUCTIONS = (
    "你是保险营销文本合规审核员，专门检测引用第三方数据未提供来源违规。\n\n"
    "规则定义：当文本中引用了数据（数字、排名、比率、增幅等可验证信息）但没有提供数据来源时，"
    "构成违规。\n\n"
    "判断标准：\n"
    "1. 仅当数据具有外部可验证性（如行业排名、增速、市场份额）时才适用本规则。\n"
    "2. 公司内部数据（自有保单件数、自有客户数）不在此规则范围内。\n"
    "3. 监管文件中的法定数字（等待期天数、保额上限）不在此规则范围内。\n"
    "4. 若数据来源在距离数据引用 200 字符以内已说明，则不构成违规。\n\n"
    "输出要求：严格按 JSON schema 输出，不输出额外文字。"
)


def _build_fulldoc_prompt(
    document: DocumentState,
    missing_span_ids: List[str],
) -> str:
    missing_spans_text = "\n".join(
        f"  {sid}: \"{document.span_pool[sid].span_text}\""
        for sid in missing_span_ids
        if sid in document.span_pool
    )
    all_span_ids_str = "\n".join(
        f"  {sid}" for sid in missing_span_ids
    )
    return (
        f"【全文文本】\n{document.normalized_text[:3000]}\n\n"
        f"【纯代码检测到以下可能缺少来源说明的数据引用 span】\n{missing_spans_text}\n\n"
        f"请判断上述数据引用是否确实缺少数据来源说明，构成违规。\n"
        f"如违规，从上述 span_id 列表中选取最能体现违规的 span_id 填入 evidence_span_ids：\n"
        f"{all_span_ids_str}\n\n"
        f"判断时请注意：\n"
        f"- 仅选有外部可验证性的数据（行业排名、增速、市场份额等）\n"
        f"- 全文若已有来源说明（即使不在 200 字符内），亦可酌情判 compliant\n"
        f"- 若所有数据均有来源，输出 verdict=compliant"
    )


async def _call_fulldoc_llm(
    document: DocumentState,
    missing_span_ids: List[str],
) -> Optional[JudgmentResult]:
    prompt = _build_fulldoc_prompt(document, missing_span_ids)
    agent = create_agent(
        system_instructions=[_FULLDOC_SYSTEM_INSTRUCTIONS],
        output_schema=JudgmentResult,
        model_profile=config.JUDGE_MODEL_PROFILE,
    )
    raw = await safe_arun(agent, prompt)
    if not raw:
        logger.warning("Stage 2.6 LLM 返回空结果")
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        result = JudgmentResult(
            rule_id=FULLDOC_RULE_ID_THIRD_PARTY_SOURCE,
            chunk_id=FULLDOC_CHUNK_ID,
            verdict=data.get("verdict", "compliant"),
            reasoning_cot=data.get("reasoning_cot", ""),
            evidence_span_ids=[
                sid for sid in data.get("evidence_span_ids", [])
                if sid in document.span_pool
            ],
            reason_codes=data.get("reason_codes", []),
            decision_basis=data.get("decision_basis"),
            primary_category="data_citation",
            secondary_category="missing_third_party_source",
        )
        return result
    except Exception as exc:
        logger.warning(f"Stage 2.6 解析 LLM 结果失败: {exc}")
        return None


# ============================================================
# 公开入口
# ============================================================

async def run_stage2_6(
    document: DocumentState,
) -> List[JudgmentResult]:
    """
    执行全文审核子流水线。

    流程：
      1. 纯代码提取数据引用信号
      2. 若无数据引用 → 跳过（返回空列表）
      3. 若有数据引用但均有来源 → 跳过（返回空列表）
      4. 若存在缺少来源的数据引用 → 调用 LLM 精判
      5. LLM 判定为 violation → 返回 JudgmentResult
    """
    signals = extract_document_audit_signals(document)

    if not signals["has_data_citation"]:
        logger.info("Stage 2.6: 无数据引用，跳过全文审核")
        return []

    missing_ids: List[str] = signals["missing_source_span_ids"]  # type: ignore
    if not missing_ids:
        logger.info("Stage 2.6: 所有数据引用均有来源说明，跳过全文审核")
        return []

    logger.info(
        f"Stage 2.6: 检测到 {len(missing_ids)} 个缺少来源的数据引用，调用 LLM 精判"
    )

    result = await _call_fulldoc_llm(document, missing_ids)
    if result is None:
        return []

    logger.info(
        f"Stage 2.6 完成: verdict={result.verdict}, "
        f"evidence_span_ids={result.evidence_span_ids}"
    )
    return [result]

