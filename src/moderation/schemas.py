"""
核心数据结构定义 (Pydantic Schema)
===================================
贯穿整个 Workflow 的强类型数据结构，严格定义并校验。
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ============================================================
# 1.1 文本底座结构 (Text Assets)
# ============================================================

class Span(BaseModel):
    """最小语义单元 —— 按标点切分后的原子文本片段"""
    span_id: str = Field(..., description="唯一标识，例如 'S_chunk001_01'")
    span_text: str = Field(..., description="最小语义单元的文本内容")
    start_index: int = Field(..., description="在规范化文本中的绝对起始位置")
    end_index: int = Field(..., description="在规范化文本中的绝对结束位置")
    chunk_id: str = Field(..., description="所属 Chunk 的 ID")


class Chunk(BaseModel):
    """文本块 —— 按字数切分的中间粒度单元"""
    chunk_id: str
    chunk_text: str
    spans: List[Span] = Field(default_factory=list, description="该 Chunk 包含的所有 Span")


class DocumentState(BaseModel):
    """文档预处理状态 —— Stage 0 的完整输出"""
    doc_id: str
    original_text: str = Field(..., description="用户输入的原始文本（未经任何处理）")
    working_text: str = Field(..., description="经过 OCR 修复后的工作文本（用于审核处理）")
    normalized_text: str = Field(..., description="规范化后的文本（用于分块和 span 切分）")
    norm_to_raw_map: Dict[int, int] = Field(
        default_factory=dict,
        description="规范化坐标 -> working_text 坐标的映射表"
    )
    working_to_original_map: Dict[int, int] = Field(
        default_factory=dict,
        description="working_text 坐标 -> original_text 坐标的映射表"
    )
    chunks: List[Chunk] = Field(default_factory=list)
    span_pool: Dict[str, Span] = Field(
        default_factory=dict,
        description="全局 span_id 索引池，用于 O(1) 查找"
    )


# ============================================================
# 1.2 规则底座结构 (Rule Card)
# ============================================================

class RuleCard(BaseModel):
    """规则卡片 —— 单条合规规则的完整描述"""
    rule_id: str
    rule_name: str
    risk_level: Literal["high", "medium", "low"]
    violation_definition: str = Field(..., description="违规定义：什么情况下算违规")
    exceptions: List[str] = Field(default_factory=list, description="例外情况（什么情况下合规）")
    keywords: List[str] = Field(default_factory=list, description="关键词列表（用于关键词召回）")
    reason_codes: List[str] = Field(default_factory=list, description="允许输出的理由码枚举")
    suggestion_template: str = Field("", description="合规建议模板（带槽位）")
    violation_terms: List[str] = Field(default_factory=list, description="违规词列表（Excel: 违规词）")
    condition_terms: List[str] = Field(default_factory=list, description="条件词列表：需与违规词同时出现")
    condition_distance: Optional[int] = Field(default=None, description="条件词限定距离（字符）")
    exclusion_terms: List[str] = Field(default_factory=list, description="排除词列表：与违规词同时出现则不违规")
    exclusion_distance: Optional[int] = Field(default=None, description="排除词限定距离（字符）")
    prefix_no_match: List[str] = Field(default_factory=list, description="前缀不匹配词：与违规词拼接后视为非违规")
    suffix_no_match: List[str] = Field(default_factory=list, description="后缀不匹配词：与违规词拼接后视为非违规")
    compliant_basis: str = Field("", description="合规依据")
    compliant_case: str = Field("", description="合规案例")
    violation_basis: str = Field("", description="违规依据")
    violation_case: str = Field("", description="违规案例")
    complexity_level: Literal["simple", "complex"] = Field(
        "simple",
        description="规则复杂度标签：simple 走基础策略，complex 走技能策略",
    )
    route_strategy: Literal["auto", "base", "skill"] = Field(
        "auto",
        description="路由策略：auto 自动分发，base 基础策略，skill 复杂策略",
    )


# ============================================================
# Stage 1 过滤输出结构
# ============================================================

class FilterResult(BaseModel):
    """Stage 1 Agent 过滤结果"""
    relevant_rule_ids: List[str] = Field(
        ...,
        description="最相关的 rule_id 列表（最多返回指定数量）"
    )


# ============================================================
# Stage 2 判定结果结构
# ============================================================

class JudgmentResult(BaseModel):
    """Stage 2 深度精判输出 —— 单个 (chunk, rule) 对的判定结果"""
    rule_id: str
    chunk_id: str
    verdict: Literal["violation", "compliant", "unsure"]
    reasoning_cot: str = Field(
        ...,
        description="必须大于50字的逻辑推演（结合例外条款分析）"
    )
    evidence_span_ids: List[str] = Field(
        default_factory=list,
        description="如果违规，必须从 span 字典中选择 ID 填入。严禁捏造。"
    )
    evidence_texts: List[str] = Field(
        default_factory=list,
        description="如果违规，提取原文中最短的违规片段文本（只保留核心违规语义，不要整句），例如'收益比存银行高出好几倍'而非整个句子。"
    )
    reason_codes: List[str] = Field(
        default_factory=list,
        description="必须从 RuleCard 中提取的理由码"
    )
    draft_suggestion: str = Field(
        "",
        description="结合 RuleCard 模板直接生成的合规修改建议"
    )


# ============================================================
# Stage 1.5 事实抽取结构
# ============================================================

class FactSignal(BaseModel):
    """事实信号 —— 为后续可执行推理提供结构化输入"""
    label: str = Field(..., description="信号标签，如 negation/certainty/comparison/time/action")
    value: str = Field(..., description="信号文本值")
    evidence_span_ids: List[str] = Field(default_factory=list, description="关联的证据 span_id 列表")


class ChunkFactProfile(BaseModel):
    """单个 chunk 的事实画像"""
    chunk_id: str
    signals: List[FactSignal] = Field(default_factory=list)
    summary: str = Field("", description="规则无关的简要事实摘要")


# ============================================================
# Stage 3 最终输出结构
# ============================================================

class ViolationLocation(BaseModel):
    """违规位置信息 —— 精确到原始文本坐标（最短违规片段）"""
    span_ids: List[str] = Field(..., description="关联的证据 span_id 列表")
    original_text_slice: str = Field(..., description="原始文本中的最短违规片段")
    norm_start: int = Field(..., description="规范化文本中的起始位置（去除\\r后的坐标）")
    norm_end: int = Field(..., description="规范化文本中的结束位置（去除\\r后的坐标）")
    raw_start: int = Field(..., description="原始文本中的起始位置（包含所有原始字符的坐标）")
    raw_end: int = Field(..., description="原始文本中的结束位置（包含所有原始字符的坐标）")


class FinalViolation(BaseModel):
    """最终违规结果 —— 面向 API 输出的结构"""
    rule_id: str
    rule_name: str
    risk_level: str
    verdict: str
    reasoning: str
    locations: List[ViolationLocation]
    reason_codes: List[str]
    suggestion: str


class AuditResponse(BaseModel):
    """API 最终响应体"""
    doc_id: str
    total_violations: int
    violations: List[FinalViolation]
    processing_time_seconds: float


# ============================================================
# 工作流状态 (Workflow State)
# ============================================================

class ChunkCandidates(BaseModel):
    """Stage 1 输出：chunk 与候选规则的映射"""
    chunk_id: str
    candidate_rule_ids: List[str]


class RoutedPair(BaseModel):
    """Stage 1.8 输出：每个 (chunk, rule) 对的审核策略路由"""
    chunk_id: str
    rule_id: str
    strategy: Literal["base", "skill"]
    reason: str = ""
    skill_type: str | None = Field(
        None,
        description="复杂场景类型：temporal_context/subject_switch/commitment_strength/cross_paragraph",
    )


class WorkflowState(BaseModel):
    """
    贯穿整个 Workflow 的状态对象
    各 Stage 之间通过此对象传递数据，避免参数乱传
    """
    document: Optional[DocumentState] = None
    rule_cards: Dict[str, RuleCard] = Field(default_factory=dict)
    stage1_candidates: List[ChunkCandidates] = Field(default_factory=list)
    stage15_facts: Dict[str, ChunkFactProfile] = Field(default_factory=dict)
    stage18_routes: List[RoutedPair] = Field(default_factory=list)
    stage2_judgments: List[JudgmentResult] = Field(default_factory=list)
    final_response: Optional[AuditResponse] = None
