"""
Stage 1.1: 语义预检（并行于 Stage 1A 关键词召回）
=================================================
为 financial_confusion 和 absolute_expression 两类语义风险提供补召回。

设计原则：
- 先跑轻量规则检测；只有命中轻量信号才允许调用 LLM
- LLM 只识别风险方向，不做违规判定
- 每个 chunk 最多返回 SEMANTIC_PRESCREEN_MAX_DIRECTIONS 个风险方向
- 每个 chunk 最多补 SEMANTIC_PRESCREEN_MAX_EXTENDED_RULES 条扩展规则
- 降级：LLM 超时/失败时回退到纯轻量规则结果
"""

import asyncio
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .. import config
from ..llm_agent import create_agent, safe_arun
from ..log import get_logger
from ..rule_indexes import select_group_rule_ids_for_text
from ..schemas import Chunk, ChunkCandidates, RuleCard

logger = get_logger(__name__)


# ============================================================
# 数据结构
# ============================================================

class SemanticChunkMetadata(BaseModel):
    """语义预检为某个 chunk 产出的元数据"""
    chunk_id: str
    risk_directions: List[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reasoning: str = ""
    extended_rule_ids: List[str] = Field(default_factory=list)


class _LLMSemanticOutput(BaseModel):
    """LLM 输出的最小 schema（扩展规则由代码完成，不让 LLM 输出）"""
    risk_directions: List[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reasoning: str = ""


# ============================================================
# 轻量信号检测（纯代码，无 LLM）
# ============================================================

# financial_confusion：银行/存款类词 + 保险主体词同时出现
_FC_POSITIVE_BANK = frozenset(["银行", "存款", "储蓄", "理财", "投资", "收益"])
_FC_POSITIVE_INSURANCE = frozenset(["保险", "产品", "保单", "这款产品"])
_FC_NEGATIVE = frozenset([
    "监管规定", "禁止", "不得", "处罚", "说明书",
    "投资策略", "公司投资", "账户配置",
])

# absolute_expression：绝对化词 + 高风险修饰对象
_AE_ABSOLUTE = frozenset(["最", "第一", "唯一", "绝对", "一定", "百分百"])
_AE_HIGH_RISK_OBJECTS = frozenset(["产品", "收益", "保障", "理赔", "代理人", "专家", "顾问"])
_AE_NEGATIVE = frozenset([
    "主观感受", "企业愿景", "服务理念", "文学", "服务介绍",
])


def _detect_financial_confusion_signal(text: str) -> bool:
    """
    轻量正向信号：银行/存款类词 AND 保险主体词同时出现。
    轻量负向排除：排除词出现时降低或取消补召回。
    """
    has_bank = any(w in text for w in _FC_POSITIVE_BANK)
    has_insurance = any(w in text for w in _FC_POSITIVE_INSURANCE)
    if not (has_bank and has_insurance):
        return False
    # 负向排除
    if any(w in text for w in _FC_NEGATIVE):
        return False
    return True


def _detect_absolute_expression_signal(text: str) -> bool:
    """
    轻量正向信号：绝对化词 AND 高风险修饰对象同时出现。
    """
    has_abs = any(w in text for w in _AE_ABSOLUTE)
    has_obj = any(w in text for w in _AE_HIGH_RISK_OBJECTS)
    if not (has_abs and has_obj):
        return False
    if any(w in text for w in _AE_NEGATIVE):
        return False
    return True


def _detect_signals(text: str, enabled_groups: List[str]) -> List[str]:
    """
    返回命中的风险方向列表（轻量规则检测）。
    只检测 enabled_groups 中包含的类别。
    """
    signals: List[str] = []
    if "financial_confusion" in enabled_groups and _detect_financial_confusion_signal(text):
        signals.append("financial_confusion")
    if "absolute_expression" in enabled_groups and _detect_absolute_expression_signal(text):
        signals.append("absolute_expression")
    return signals


# ============================================================
# LLM 语义预检
# ============================================================

def _build_semantic_prescreen_agent():
    """构建语义预检 Agent（轻量，只识别风险方向）"""
    return create_agent(
        output_schema=_LLMSemanticOutput,
        name="semantic_prescreen_agent",
        profile=config.FILTER_MODEL_PROFILE,
        instructions=[
            "你是保险合规预检助手。",
            "你的任务是判断文本片段是否存在指定的语义风险方向。",
            "不要做最终违规判定，只识别风险方向。",
            "必须返回 JSON 对象，格式：{\"risk_directions\": [...], \"confidence\": 0.0-1.0, \"reasoning\": \"...\"}。",
            "risk_directions 只能从给定候选中选择，不要自创方向。",
            "如无风险，返回 {\"risk_directions\": [], \"confidence\": 0.0, \"reasoning\": \"无明显风险\"}。",
        ],
    )


def _build_prescreen_prompt(
    chunk_text: str,
    candidate_directions: List[str],
    max_directions: int,
) -> str:
    directions_str = "\n".join(f"- {d}" for d in candidate_directions)
    direction_defs = {
        "financial_confusion": "将保险产品描述为等同于银行存款/储蓄/理财，混淆产品属性",
        "absolute_expression": "对产品收益/保障/服务使用绝对化夸大词，如'最好''唯一''百分百'",
    }
    defs_str = "\n".join(
        f"- {d}: {direction_defs.get(d, d)}"
        for d in candidate_directions
    )
    return f"""请判断以下保险文本片段是否存在语义风险方向。

【文本片段】
{chunk_text}

【候选风险方向定义】
{defs_str}

要求：
1. 只从候选方向中选择，最多选 {max_directions} 个；
2. confidence 表示整体判断置信度（0.0-1.0）；
3. reasoning 简要说明判断依据（1-2句）；
4. 不要做最终违规判定，只识别风险方向；
5. 返回纯 JSON，不要 markdown 或代码块。

返回格式：
{{"risk_directions": ["方向1"], "confidence": 0.8, "reasoning": "原因"}}"""


# ============================================================
# 规则扩展：由代码完成（不让 LLM 输出 rule_id）
# ============================================================

def _extend_rules_from_directions(
    chunk_text: str,
    directions: List[str],
    category_group_index: Dict[str, List[str]],
    rule_cards: Dict[str, RuleCard],
    max_rules: int,
) -> List[str]:
    extended: List[str] = []
    for direction in directions:
        rule_ids = select_group_rule_ids_for_text(
            text=chunk_text,
            category_group=direction,
            category_group_index=category_group_index,
            rule_cards=rule_cards,
            max_rules=max_rules,
        )
        for rid in rule_ids:
            if rid not in extended:
                extended.append(rid)
            if len(extended) >= max_rules:
                return extended
    return extended


# ============================================================
# 单 chunk 处理
# ============================================================

async def _process_single_chunk(
    chunk: Chunk,
    category_group_index: Dict[str, List[str]],
    rule_cards: Dict[str, RuleCard],
    enabled_groups: List[str],
    max_directions: int,
    max_extended_rules: int,
    enable_llm: bool,
    semaphore: asyncio.Semaphore,
    agent,
) -> Optional[SemanticChunkMetadata]:
    """对单个 chunk 执行语义预检，返回元数据（无信号时返回 None）"""
    text = chunk.chunk_text

    # Step 1: 轻量规则检测
    signals = _detect_signals(text, enabled_groups)
    if not signals:
        return None

    logger.debug(f"  [semantic] Chunk {chunk.chunk_id}: signals={signals}")

    # Step 2: 可选 LLM 风险方向识别
    llm_directions: List[str] = signals  # 默认使用轻量信号结果
    confidence = 0.6
    reasoning = "轻量规则命中"

    if enable_llm and agent is not None:
        async with semaphore:
            try:
                prompt = _build_prescreen_prompt(text, signals, max_directions)
                llm_output: _LLMSemanticOutput = await safe_arun(
                    agent,
                    prompt,
                    max_retries=config.SEMANTIC_PRESCREEN_MAX_RETRIES,
                    timeout_seconds=config.SEMANTIC_PRESCREEN_TIMEOUT_SECONDS,
                )
                # 只保留 enabled_groups 中的方向，过滤 LLM 自创方向
                filtered = [
                    d for d in llm_output.risk_directions
                    if d in enabled_groups
                ][:max_directions]
                if filtered:
                    llm_directions = filtered
                    confidence = llm_output.confidence
                    reasoning = llm_output.reasoning
                else:
                    # LLM 认为无风险，仍尊重轻量规则信号但降低置信度
                    llm_directions = signals
                    confidence = 0.4
                    reasoning = f"LLM 未确认风险方向，轻量规则信号: {signals}"
            except Exception as e:
                logger.warning(
                    f"  [semantic] Chunk {chunk.chunk_id} LLM failed: {e}, "
                    "falling back to lightweight signals"
                )

    # Step 3: 代码扩展规则 ID
    extended_rule_ids = _extend_rules_from_directions(
        chunk_text=text,
        directions=llm_directions,
        category_group_index=category_group_index,
        rule_cards=rule_cards,
        max_rules=max_extended_rules,
    )

    logger.info(
        f"  [semantic] Chunk {chunk.chunk_id}: directions={llm_directions}, "
        f"extended_rules={extended_rule_ids}, confidence={confidence:.2f}"
    )

    return SemanticChunkMetadata(
        chunk_id=chunk.chunk_id,
        risk_directions=llm_directions,
        confidence=confidence,
        reasoning=reasoning,
        extended_rule_ids=extended_rule_ids,
    )


# ============================================================
# Stage 1.1 主函数
# ============================================================

async def run_stage1_1_semantic_prescreen(
    chunks: List[Chunk],
    category_group_index: Dict[str, List[str]],
    rule_cards: Dict[str, RuleCard],
    semaphore: asyncio.Semaphore,
    enabled_groups: Optional[List[str]] = None,
    max_directions: Optional[int] = None,
    max_extended_rules: Optional[int] = None,
    enable_llm: Optional[bool] = None,
) -> Tuple[List[ChunkCandidates], Dict[str, SemanticChunkMetadata]]:
    """
    Stage 1B: 语义预检并行召回。

    与 Stage 1A (run_stage1_raw_recall) 并行执行。
    输出的 ChunkCandidates 包含语义扩展规则 ID，
    需在 Stage 1C/1D（merge + filter）后才能进入后续 Stage。

    Returns:
        (semantic_candidates, semantic_metadata)
        - semantic_candidates: List[ChunkCandidates]，每个 chunk 的语义扩展候选
        - semantic_metadata: Dict[chunk_id, SemanticChunkMetadata]
    """
    # 从 config 读取默认值
    if enabled_groups is None:
        enabled_groups = config.SEMANTIC_PRESCREEN_ENABLED_GROUPS
    if max_directions is None:
        max_directions = config.SEMANTIC_PRESCREEN_MAX_DIRECTIONS
    if max_extended_rules is None:
        max_extended_rules = config.SEMANTIC_PRESCREEN_MAX_EXTENDED_RULES
    if enable_llm is None:
        enable_llm = config.SEMANTIC_PRESCREEN_ENABLE_LLM

    # 只有启用 LLM 时才创建 agent
    agent = _build_semantic_prescreen_agent() if enable_llm else None

    tasks = [
        _process_single_chunk(
            chunk=chunk,
            category_group_index=category_group_index,
            rule_cards=rule_cards,
            enabled_groups=enabled_groups,
            max_directions=max_directions,
            max_extended_rules=max_extended_rules,
            enable_llm=enable_llm,
            semaphore=semaphore,
            agent=agent,
        )
        for chunk in chunks
    ]

    results = await asyncio.gather(*tasks)

    semantic_candidates: List[ChunkCandidates] = []
    semantic_metadata: Dict[str, SemanticChunkMetadata] = {}

    for meta in results:
        if meta is None:
            continue
        semantic_metadata[meta.chunk_id] = meta
        if meta.extended_rule_ids:
            semantic_candidates.append(ChunkCandidates(
                chunk_id=meta.chunk_id,
                candidate_rule_ids=meta.extended_rule_ids,
            ))

    logger.info(
        f"Stage 1.1 完成: {len(semantic_candidates)} chunks 有语义扩展候选, "
        f"{len(semantic_metadata)} chunks 命中语义信号"
    )
    return semantic_candidates, semantic_metadata
