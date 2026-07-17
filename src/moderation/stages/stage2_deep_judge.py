"""
Stage 2: 深度精判与对齐（双策略混合架构）
==========================================
方案3实现：
  策略A（base 轨）：确定性规则引擎（快速、低成本）
  策略B（skill 轨）：Skills/子Agent（复杂逻辑、高准确率）
    - 基础 Skills：5个专业领域 Skill
    - 复杂 Skills：4个复杂场景 Skill（时态/主体/承诺/跨段落）

工作流程：
  1. 根据 Stage 1.8 的路由结果分发到不同策略
  2. base 轨：直接执行规则引擎，硬阻断则输出 compliant
  3. skill 轨：
     - 如果有 skill_type，使用复杂 Skill
     - 否则使用基础 Skill（按规则自动路由）
  4. 并发处理所有任务，控制并发上限
  5. unsure 高风险二次审查
"""

from __future__ import annotations

import asyncio
import re
from typing import Dict, List

from .. import config
from ..audit_trace import trace_event
from ..llm_agent import create_agent, safe_arun
from ..log import get_logger
from ..rule_engine import evaluate_rule_on_text
from ..schemas import (
    Chunk,
    ChunkCandidates,
    ChunkFactProfile,
    DocumentState,
    JudgmentResult,
    RoutedPair,
    RuleCard,
)
from ..skills import get_skill_for_rule
from ..complex_skills import get_complex_skill

logger = get_logger(__name__)

_GENERIC_RISK_ANCHORS = (
    "金融产品", "投资", "理财", "存款", "存钱", "储蓄", "收益", "回报",
    "锁定", "保证", "第一", "最好", "唯一", "转嫁风险", "赠送", "礼品",
    "温馨服务", "退休金", "教育金", "养老金", "传承", "避税", "法律",
    "监管", "顾问", "招募", "岗位", "平安保险", "集团", "中国平安",
)
_GENERIC_NEUTRAL_PHRASES = (
    "可以提供", "财务保障", "风险管理", "帮助缓解", "间接保障", "长期保障",
    "功能", "规划", "稳定性", "信誉", "补偿或保障",
)

_BASE_VERIFY_SYSTEM_INSTRUCTIONS = (
    "你是保险营销文本合规分类器（轻量版）。\n"
    "规则引擎已经在文本中找到了词面命中的证据，你的任务是判断这些证据是否构成规则所定义的直接违规宣传。\n"
    "不要只看词面是否命中，要判断语义是否真的构成违规。\n"
    "\n"
    "判断顺序（严格按序）：\n"
    "1. 规则引擎给出的命中词/片段，是否出现在文本中且语义成立\n"
    "2. 命中片段的主体是否直接指向保险产品或代理人（而非客户、监管机构、泛指）\n"
    "3. 该片段是否属于负面说明、禁令说明、培训材料、监管解读、客观背景介绍\n"
    "4. 综合以上，是否达到该规则定义的'直接违规宣传'门槛\n"
    "\n"
    "verdict 取值：\n"
    "- violation：确认违规\n"
    "- compliant：证据不成立或属于例外场景\n"
    "- unsure：无法确认，需要更多上下文\n"
    "\n"
    "输出格式严格遵循 JSON schema，不要输出额外文字。"
)


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _trim_fragment(text: str) -> str:
    return (text or "").strip(" \t\r\n，。；！？、：:,.!?'\"“”‘’（）()[]【】《》")


def _normalize_fragment(text: str) -> str:
    return "".join(_trim_fragment(text).split())


def _clip_for_context(text: str, max_chars: int, from_tail: bool = False) -> str:
    cleaned = (text or "").strip()
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned
    if from_tail:
        return "…" + cleaned[-max_chars:]
    return cleaned[:max_chars] + "…"


def _build_longdoc_context_bundle(
    document: DocumentState,
    chunk: Chunk,
) -> str | None:
    if len(document.normalized_text) < config.LONGDOC_THRESHOLD or len(document.chunks) <= 1:
        return None

    max_chars = max(0, config.LONGDOC_CONTEXT_CHARS)
    if max_chars <= 0:
        return None

    chunk_index = next(
        (index for index, item in enumerate(document.chunks) if item.chunk_id == chunk.chunk_id),
        None,
    )
    if chunk_index is None:
        return None

    sections: list[str] = []
    if chunk_index > 0:
        prev_text = _clip_for_context(document.chunks[chunk_index - 1].chunk_text, max_chars, from_tail=True)
        if prev_text:
            sections.append(f"前文审核块摘要：\n{prev_text}")
    if chunk_index + 1 < len(document.chunks):
        next_text = _clip_for_context(document.chunks[chunk_index + 1].chunk_text, max_chars, from_tail=False)
        if next_text:
            sections.append(f"后文审核块摘要：\n{next_text}")

    return "\n\n".join(sections) if sections else None


def _collect_rule_anchor_terms(rule_card: RuleCard) -> List[str]:
    candidates: List[str] = []
    candidates.extend(rule_card.keywords)
    candidates.extend(rule_card.violation_terms)
    candidates.extend(
        part
        for part in re.split(r"[\\/\\-\\s（）()，,：:]+", rule_card.rule_name)
        if len(_normalize_fragment(part)) >= 2 and "知识库规则" not in part
    )

    reference_text = " ".join(
        text for text in [
            rule_card.rule_name,
            rule_card.violation_definition,
            rule_card.violation_basis,
        ] if text
    )
    for term in _GENERIC_RISK_ANCHORS:
        if term in reference_text:
            candidates.append(term)

    return _dedupe_preserve_order([
        _trim_fragment(term)
        for term in candidates
        if len(_normalize_fragment(term)) >= 2
    ])


def _score_span_text(
    span_text: str,
    anchor_terms: List[str],
    evidence_texts: List[str],
) -> int:
    normalized_span = _normalize_fragment(span_text)
    score = 0

    if any(
        normalized_evidence
        and (normalized_evidence in normalized_span or normalized_span in normalized_evidence)
        for normalized_evidence in (_normalize_fragment(text) for text in evidence_texts)
    ):
        score += 4

    anchor_hits = [
        term for term in anchor_terms
        if _normalize_fragment(term) and _normalize_fragment(term) in normalized_span
    ]
    score += min(len(anchor_hits), 2) * 3

    if any(phrase in span_text for phrase in _GENERIC_NEUTRAL_PHRASES) and not anchor_hits:
        score -= 3

    if len(normalized_span) <= 16:
        score += 1

    return score


def _map_evidence_texts_to_span_ids(
    evidence_texts: List[str],
    chunk: Chunk,
) -> List[str]:
    if not evidence_texts:
        return []

    mapped_ids: List[str] = []
    normalized_texts = [_normalize_fragment(text) for text in evidence_texts if _normalize_fragment(text)]
    for span in chunk.spans:
        normalized_span = _normalize_fragment(span.span_text)
        if any(
            normalized_text in normalized_span or normalized_span in normalized_text
            for normalized_text in normalized_texts
        ):
            mapped_ids.append(span.span_id)
    return _dedupe_preserve_order(mapped_ids)


def _refine_violation_evidence(
    result: JudgmentResult,
    chunk: Chunk,
    rule_card: RuleCard,
) -> JudgmentResult:
    if result.verdict != "violation":
        result.evidence_span_ids = []
        result.evidence_texts = []
        return result

    result.evidence_texts = _dedupe_preserve_order([
        _trim_fragment(text)
        for text in result.evidence_texts
        if _normalize_fragment(text)
    ])[:3]
    result.evidence_span_ids = _dedupe_preserve_order(result.evidence_span_ids)[:5]

    if not result.evidence_span_ids and result.evidence_texts:
        result.evidence_span_ids = _map_evidence_texts_to_span_ids(result.evidence_texts, chunk)[:5]

    selected_spans = [span for span in chunk.spans if span.span_id in result.evidence_span_ids]
    if len(selected_spans) > 1:
        anchor_terms = _collect_rule_anchor_terms(rule_card)
        scores = {
            span.span_id: _score_span_text(span.span_text, anchor_terms, result.evidence_texts)
            for span in selected_spans
        }
        if any(score > 0 for score in scores.values()):
            best_score = max(scores.values())
            keep_ids = [
                span.span_id
                for span in selected_spans
                if scores[span.span_id] == best_score
            ]
        else:
            keep_ids = [
                min(
                    selected_spans,
                    key=lambda span: len(_normalize_fragment(span.span_text)),
                ).span_id
            ]
        result.evidence_span_ids = _dedupe_preserve_order(keep_ids)
        selected_spans = [span for span in chunk.spans if span.span_id in result.evidence_span_ids]

    if selected_spans:
        selected_span_texts = [_normalize_fragment(span.span_text) for span in selected_spans]
        selected_span_fragments = [
            _trim_fragment(span.span_text)
            for span in selected_spans[:3]
            if _normalize_fragment(span.span_text)
        ]
        overlapping_evidence = [
            text for text in result.evidence_texts
            if any(
                normalized_text and (
                    normalized_text in selected_span_text
                    or selected_span_text in normalized_text
                )
                for normalized_text in [_normalize_fragment(text)]
                for selected_span_text in selected_span_texts
            )
        ]
        if overlapping_evidence and not any(
            len(_normalize_fragment(text)) > len(selected_span_text)
            and selected_span_text
            and selected_span_text in _normalize_fragment(text)
            for text in overlapping_evidence
            for selected_span_text in selected_span_texts
        ):
            result.evidence_texts = _dedupe_preserve_order(overlapping_evidence)[:3]
        elif result.evidence_texts or result.evidence_span_ids:
            result.evidence_texts = selected_span_fragments

    if not result.decision_basis:
        result.decision_basis = "explicit_violation"

    return result


def _infer_base_decision_basis(report) -> str | None:
    if report.exclusion_blocked:
        return "exclusion_triggered"
    if not report.condition_pass:
        return "condition_not_met"
    if report.has_violation_hit:
        return "explicit_violation"
    return None


def _infer_override_decision_basis(override_id: str, judgment: JudgmentResult) -> str | None:
    if override_id == "negation_context":
        return "negation_context"
    if override_id == "deterministic_hard_block":
        return judgment.decision_basis or "condition_not_met"
    if override_id in {
        "absolute_low_risk_exception",
        "surrender_disclaimer_sufficient",
        "regulatory_objective_description",
        "background_comparison_context",
        "non_recruitment_context",
    }:
        return "exception_applied"
    return judgment.decision_basis


def _apply_rule_card_defaults(
    result: JudgmentResult,
    rule_card: RuleCard,
) -> JudgmentResult:
    """用 RuleCard 的结构化元数据补齐输出口径。"""
    if not result.primary_category and rule_card.primary_category:
        result.primary_category = rule_card.primary_category
    if not result.secondary_category and rule_card.secondary_category:
        result.secondary_category = rule_card.secondary_category
    return result

# ============================================================
# 策略A：base 轨（确定性规则引擎）
# ============================================================


def judge_with_base_strategy(
    chunk: Chunk,
    rule_card: RuleCard,
    document: DocumentState,
) -> JudgmentResult:
    """
    策略A：使用确定性规则引擎判定。

    适用场景：
      - 简单关键词违规
      - 明确的条件词/排除词约束
      - 无需上下文理解的规则

    优势：
      - 零成本（无 LLM 调用）
      - 确定性输出（无幻觉）
      - 毫秒级响应
    """
    report = evaluate_rule_on_text(chunk.chunk_text, rule_card)

    # 记录审计轨迹
    trace_event(
        "stage2.base_strategy",
        {
            "chunk_id": chunk.chunk_id,
            "rule_id": rule_card.rule_id,
            "has_violation_hit": report.has_violation_hit,
            "condition_pass": report.condition_pass,
            "exclusion_blocked": report.exclusion_blocked,
            "hard_block": report.hard_block,
            "summary": report.summary,
        },
    )

    # 硬阻断：直接判定为 compliant
    if report.hard_block:
        return JudgmentResult(
            rule_id=rule_card.rule_id,
            chunk_id=chunk.chunk_id,
            verdict="compliant",
            reasoning_cot=f"规则引擎判定：{report.summary}",
            evidence_span_ids=[],
            evidence_texts=[],
            reason_codes=[],
            decision_basis=_infer_base_decision_basis(report),
        )

    # 通过规则引擎前置校验：判定为 violation
    # 提取证据 span_ids
    evidence_span_ids = []
    for span in chunk.spans:
        # 检查 span 是否包含违规词
        for term, positions in report.violation_positions.items():
            if term in span.span_text:
                evidence_span_ids.append(span.span_id)
                break

    # 提取违规片段
    evidence_texts = list(report.violation_positions.keys())

    return JudgmentResult(
        rule_id=rule_card.rule_id,
        chunk_id=chunk.chunk_id,
        verdict="violation",
        reasoning_cot=f"规则引擎判定：命中违规词 {', '.join(report.violation_positions.keys())}，"
                      f"条件词约束{'满足' if report.condition_pass else '不满足'}，"
                      f"排除词{'未命中' if not report.exclusion_blocked else '命中'}。",
        evidence_span_ids=evidence_span_ids[:5],  # 最多5个
        evidence_texts=evidence_texts[:3],  # 最多3个
        reason_codes=rule_card.reason_codes[:1] if rule_card.reason_codes else [],
        decision_basis="explicit_violation",
    )


# ============================================================
# 策略A 升级：base_verify_llm（歧义类别轻量 LLM 最终裁决）
# ============================================================


async def judge_with_base_verify_llm(
    chunk: Chunk,
    rule_card: RuleCard,
    document: DocumentState,
    base_result: JudgmentResult,
    semaphore: asyncio.Semaphore | None = None,
) -> JudgmentResult:
    """
    base_verify_llm：对 base 轨输出的 violation 做轻量 LLM 最终语义裁决。

    规则引擎已提证，LLM 只判断这些证据是否构成直接违规，不重新召回。
    """
    # 构建轻量 Prompt：规则 + chunk 文本 + 规则引擎证据
    violation_hits = ", ".join(base_result.evidence_texts) if base_result.evidence_texts else "（无词面命中片段）"
    spans_summary = "\n".join(
        f"  {s.span_id}: {s.span_text}"
        for s in chunk.spans[:10]
    )
    context_bundle = _build_longdoc_context_bundle(document, chunk)
    context_section = (
        f"\n【邻近上下文（辅助判断，不直接作为定位证据）】\n{context_bundle}\n"
        if context_bundle
        else ""
    )
    prompt = (
        f"【规则 ID】{rule_card.rule_id}\n"
        f"【规则名称】{rule_card.rule_name}\n"
        f"【违规定义】{rule_card.violation_definition}\n"
        f"【类别分组】{rule_card.category_group}\n"
        f"\n"
        f"【待审文本 chunk_id={chunk.chunk_id}】\n"
        f"{chunk.chunk_text}\n"
        f"{context_section}"
        f"\n"
        f"【规则引擎命中的违规词/片段】\n"
        f"{violation_hits}\n"
        f"\n"
        f"【文本 Span 列表（用于填写 evidence_span_ids）】\n"
        f"{spans_summary}\n"
        f"\n"
        f"请严格按判断顺序裁决：这些证据是否构成本规则定义的直接违规宣传？"
    )

    agent = create_agent(
        output_schema=JudgmentResult,
        instructions=_BASE_VERIFY_SYSTEM_INSTRUCTIONS,
        name="base_verify_llm",
        temperature=0.1,
        profile=config.JUDGE_MODEL_PROFILE,
    )

    try:
        if semaphore:
            async with semaphore:
                result = await safe_arun(
                    agent,
                    prompt,
                    max_retries=config.JUDGE_MODEL_PROFILE.max_retries,
                    timeout_seconds=config.JUDGE_MODEL_PROFILE.timeout_seconds,
                )
        else:
            result = await safe_arun(
                agent,
                prompt,
                max_retries=config.JUDGE_MODEL_PROFILE.max_retries,
                timeout_seconds=config.JUDGE_MODEL_PROFILE.timeout_seconds,
            )
    except Exception as e:
        logger.warning(
            f"base_verify_llm 调用失败 [{chunk.chunk_id} x {rule_card.rule_id}]: {e}，"
            f"降级为 unsure（避免误判）"
        )
        return JudgmentResult(
            chunk_id=base_result.chunk_id,
            rule_id=base_result.rule_id,
            verdict="unsure",
            reasoning_cot=f"base_verify_llm 调用失败，降级为 unsure: {e}",
            evidence_span_ids=base_result.evidence_span_ids,
            strategy="base_verify_llm_error",
        )

    # 后验证：过滤幻觉 span_id
    valid_span_ids = {s.span_id for s in chunk.spans}
    result.evidence_span_ids = [
        sid for sid in result.evidence_span_ids if sid in valid_span_ids
    ]

    # 若 LLM 未返回证据但 violation，保留规则引擎的证据
    if result.verdict == "violation" and not result.evidence_span_ids:
        result.evidence_span_ids = base_result.evidence_span_ids
    if result.verdict == "violation" and not result.evidence_texts:
        result.evidence_texts = base_result.evidence_texts

    # 补全 rule_id / chunk_id（LLM 有时不填）
    result.rule_id = rule_card.rule_id
    result.chunk_id = chunk.chunk_id

    result = _refine_violation_evidence(result, chunk, rule_card)
    result = _apply_rule_card_defaults(result, rule_card)

    trace_event(
        "stage2.base_verify_llm",
        {
            "chunk_id": chunk.chunk_id,
            "rule_id": rule_card.rule_id,
            "category_group": rule_card.category_group,
            "base_verdict": "violation",
            "verify_verdict": result.verdict,
            "evidence_hits": violation_hits,
        },
    )

    return result


# ============================================================
# 策略B：skill 轨（LLM Agent + Skills）
# ============================================================


def _select_prompt_deterministic_report(report):
    """为 skill Prompt 选择可注入的规则引擎辅助信息。

    只在规则引擎已经发现了正向词面证据或明确例外/排除证据时注入，
    避免“无命中”结果对 skill 轨造成负向锚定。
    """
    if report.has_violation_hit:
        return report
    if report.exclusion_blocked:
        return report
    if report.condition_positions or report.exclusion_positions:
        return report
    return None


async def judge_with_skill_strategy(
    chunk: Chunk,
    rule_card: RuleCard,
    document: DocumentState,
    chunk_fact: ChunkFactProfile | None = None,
    skill_type: str | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> JudgmentResult:
    """
    策略B：使用 Skills/LLM Agent 判定。

    适用场景：
      - 语境歧义（如"薪资"的时态判断）
      - 跨句逻辑（需要上下文）
      - 复杂例外条款
      - 主体切换识别

    优势：
      - 语义理解能力强
      - 专业 Skill + Few-shot 提升准确率
      - 可处理复杂逻辑

    参数：
      skill_type: 复杂场景类型（temporal_context/subject_switch等）
                  如果提供，优先使用复杂 Skill；否则使用基础 Skill
    """
    # 选择 Skill：复杂 Skill 优先
    if skill_type:
        skill = get_complex_skill(skill_type)
        if skill:
            logger.debug(
                f"使用复杂 Skill: {skill.name} (rule={rule_card.rule_id}, "
                f"chunk={chunk.chunk_id})"
            )
        else:
            logger.warning(f"未找到复杂 Skill: {skill_type}，降级到基础 Skill")
            skill = get_skill_for_rule(rule_card)
    else:
        # 使用基础 Skill（按规则自动路由）
        skill = get_skill_for_rule(rule_card)

    # 构建 span 字典
    spans_dict = [
        {"span_id": s.span_id, "span_text": s.span_text}
        for s in chunk.spans
    ]

    # 可选：先执行规则引擎获取前置证据
    deterministic_report = evaluate_rule_on_text(chunk.chunk_text, rule_card)
    prompt_deterministic_report = _select_prompt_deterministic_report(deterministic_report)
    context_bundle = _build_longdoc_context_bundle(document, chunk)

    # 构建 Prompt（包含 Few-shot）
    prompt = skill.build_prompt(
        chunk=chunk,
        rule_card=rule_card,
        spans_dict=spans_dict,
        chunk_fact=chunk_fact,
        deterministic_report=prompt_deterministic_report,
        context_bundle=context_bundle,
    )

    # 创建 Agent
    agent = create_agent(
        output_schema=JudgmentResult,
        instructions=skill.system_instructions,
        name=f"skill_{skill.name}",
        temperature=skill.temperature,
        profile=config.JUDGE_MODEL_PROFILE,
    )

    # 并发控制
    if semaphore:
        async with semaphore:
            result = await safe_arun(
                agent,
                prompt,
                max_retries=config.JUDGE_MODEL_PROFILE.max_retries,
                timeout_seconds=config.JUDGE_MODEL_PROFILE.timeout_seconds,
            )
    else:
        result = await safe_arun(
            agent,
            prompt,
            max_retries=config.JUDGE_MODEL_PROFILE.max_retries,
            timeout_seconds=config.JUDGE_MODEL_PROFILE.timeout_seconds,
        )

    # 后验证：过滤幻觉 span_id
    valid_span_ids = {s.span_id for s in chunk.spans}
    result.evidence_span_ids = [
        sid for sid in result.evidence_span_ids if sid in valid_span_ids
    ]

    # 后验证：reason_codes 白名单
    if rule_card.reason_codes:
        result.reason_codes = [
            rc for rc in result.reason_codes if rc in rule_card.reason_codes
        ]

    result = _refine_violation_evidence(result, chunk, rule_card)
    result = _apply_rule_card_defaults(result, rule_card)

    # 记录审计轨迹
    trace_event(
        "stage2.skill_strategy",
        {
            "chunk_id": chunk.chunk_id,
            "rule_id": rule_card.rule_id,
            "skill_name": skill.name,
            "skill_type": skill_type or "basic",
            "verdict": result.verdict,
            "evidence_span_ids": result.evidence_span_ids,
            "reasoning_length": len(result.reasoning_cot),
        },
    )

    return result


# ============================================================
# unsure 高风险二次审查
# ============================================================


async def retry_unsure_judgment(
    judgment: JudgmentResult,
    chunk: Chunk,
    rule_card: RuleCard,
    document: DocumentState,
    chunk_fact: ChunkFactProfile | None = None,
    skill_type: str | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> JudgmentResult:
    """
    对 unsure 且高风险的判定进行二次审查。

    策略：
      - 使用更详细的 prompt
      - 提高 temperature 增加探索性
      - 强调必须给出明确判定
      - 保持使用相同的 skill_type（如果有）
    """
    logger.info(
        f"二次审查 unsure 判定: chunk={chunk.chunk_id}, rule={rule_card.rule_id}"
    )

    # 选择 Skill：优先使用原 skill_type
    if skill_type:
        skill = get_complex_skill(skill_type)
        if skill:
            logger.debug(f"二次审查使用复杂 Skill: {skill.name}")
        else:
            logger.warning(f"未找到复杂 Skill: {skill_type}，降级到基础 Skill")
            skill = get_skill_for_rule(rule_card)
    else:
        skill = get_skill_for_rule(rule_card)
    spans_dict = [
        {"span_id": s.span_id, "span_text": s.span_text}
        for s in chunk.spans
    ]

    # 增强 prompt
    base_prompt = skill.build_prompt(
        chunk=chunk,
        rule_card=rule_card,
        spans_dict=spans_dict,
        chunk_fact=chunk_fact,
        context_bundle=_build_longdoc_context_bundle(document, chunk),
    )

    retry_prompt = f"""{base_prompt}

========== 二次审查要求 ==========
这是一次二次审查。之前的判定结果为 unsure（不确定）。
请更加仔细地分析文本，结合规则定义和例外条款，给出明确的判定。
【强制约束】verdict 字段必须输出 violation 或 compliant，禁止再次输出 unsure。
若证据倾向违规但不充分，输出 violation 并在 reasoning_cot 中说明置信度。
若无充分证据支持违规，输出 compliant（无罪推定原则）。"""

    # 提高 temperature
    agent = create_agent(
        output_schema=JudgmentResult,
        instructions=skill.system_instructions,
        name=f"retry_{skill.name}",
        temperature=0.3,  # 提高探索性
        profile=config.JUDGE_MODEL_PROFILE,
    )

    if semaphore:
        async with semaphore:
            result = await safe_arun(
                agent,
                retry_prompt,
                max_retries=config.JUDGE_MODEL_PROFILE.max_retries,
                timeout_seconds=config.JUDGE_MODEL_PROFILE.timeout_seconds,
            )
    else:
        result = await safe_arun(
            agent,
            retry_prompt,
            max_retries=config.JUDGE_MODEL_PROFILE.max_retries,
            timeout_seconds=config.JUDGE_MODEL_PROFILE.timeout_seconds,
        )

    # 后验证
    valid_span_ids = {s.span_id for s in chunk.spans}
    result.evidence_span_ids = [
        sid for sid in result.evidence_span_ids if sid in valid_span_ids
    ]

    if rule_card.reason_codes:
        result.reason_codes = [
            rc for rc in result.reason_codes if rc in rule_card.reason_codes
        ]

    result = _refine_violation_evidence(result, chunk, rule_card)
    result = _apply_rule_card_defaults(result, rule_card)

    trace_event(
        "stage2.retry_unsure",
        {
            "chunk_id": chunk.chunk_id,
            "rule_id": rule_card.rule_id,
            "original_verdict": "unsure",
            "retry_verdict": result.verdict,
        },
    )

    return result


# ============================================================
# Stage 2 主入口：双策略并发调度
# ============================================================


async def run_stage2(
    document: DocumentState,
    rule_cards: Dict[str, RuleCard],
    candidates: List[ChunkCandidates],
    routed_pairs: List[RoutedPair],
    chunk_facts: Dict[str, ChunkFactProfile] | None = None,
    gate_results: Dict[str, Any] | None = None,
    max_concurrent: int = 6,
    shared_semaphore: asyncio.Semaphore | None = None,
) -> List[JudgmentResult]:
    """
    Stage 2 主入口：双策略混合架构。

    工作流程：
      1. 根据 gate_results 过滤掉 should_skip=True 的组合
      2. 根据 routed_pairs 的 strategy 分发到不同策略
      3. base 轨：同步执行规则引擎
      4. skill 轨：异步并发调用 LLM Agent
      5. unsure 高风险二次审查
      6. 返回所有判定结果

    参数：
      document: 文档状态（包含 chunks 和 span_pool）
      rule_cards: 规则卡片字典
      candidates: Stage 1 候选结果（用于兼容性，实际使用 routed_pairs）
      routed_pairs: Stage 1.8 路由结果
      chunk_facts: Stage 1.5 事实画像
      gate_results: Stage 1.9 Gate 结果字典
      max_concurrent: 最大并发 LLM 调用数
      shared_semaphore: 可选的共享并发信号量，用于与全文审核共用预算
    """
    # 过滤掉 should_skip=True 的组合
    filtered_pairs = []
    if gate_results:
        for pair in routed_pairs:
            key = f"{pair.chunk_id}_{pair.rule_id}"
            gate_result = gate_results.get(key)
            if gate_result and gate_result.should_skip:
                logger.info(f"  跳过 Gate 标记的组合: {key}")
                continue
            filtered_pairs.append(pair)
    else:
        filtered_pairs = routed_pairs

    logger.info(f"Stage 2 开始: {len(filtered_pairs)} 个路由对（已过滤 {len(routed_pairs) - len(filtered_pairs)} 个）")

    # 构建 chunk_id -> Chunk 的索引
    chunk_map = {c.chunk_id: c for c in document.chunks}

    # 并发控制信号量
    semaphore = shared_semaphore or asyncio.Semaphore(max_concurrent)

    # 分离 base 轨和 skill 轨
    base_tasks = []
    skill_tasks = []
    skill_route_map = {}  # 记录 skill 任务索引 -> route 的映射

    for route in filtered_pairs:
        chunk = chunk_map.get(route.chunk_id)
        rule_card = rule_cards.get(route.rule_id)

        if chunk is None or rule_card is None:
            logger.warning(
                f"跳过无效路由: chunk={route.chunk_id}, rule={route.rule_id}"
            )
            continue

        chunk_fact = chunk_facts.get(route.chunk_id) if chunk_facts else None

        if route.strategy == "base":
            # 策略A：同步执行规则引擎
            base_tasks.append((chunk, rule_card))
        else:
            # 策略B：异步调用 LLM Agent
            skill_idx = len(skill_tasks)
            skill_route_map[skill_idx] = route  # 记录映射
            skill_tasks.append(
                judge_with_skill_strategy(
                    chunk=chunk,
                    rule_card=rule_card,
                    document=document,
                    chunk_fact=chunk_fact,
                    skill_type=route.skill_type,  # 传递复杂场景类型
                    semaphore=semaphore,
                )
            )

    # 执行 base 轨（同步）
    base_results = []
    verify_tasks = []      # (index_in_base_results, chunk, rule_card, base_result)
    for chunk, rule_card in base_tasks:
        result = judge_with_base_strategy(chunk, rule_card, document)
        result = _refine_violation_evidence(result, chunk, rule_card)
        result = _apply_rule_card_defaults(result, rule_card)
        # 所有 base 轨 violation 都进入 base_verify_llm 做最终语义裁决
        # （Codex P0-1：规则引擎只提证，LLM 做最终分类，不再直接输出 violation）
        if result.verdict == "violation":
            verify_tasks.append((len(base_results), chunk, rule_card, result))
        base_results.append(result)

    # base_verify_llm：所有 base 轨 violation 都进入轻量 LLM 最终语义裁决
    if verify_tasks:
        logger.info(
            f"base_verify_llm: {len(verify_tasks)} 个 violation 进入 LLM 验证"
        )
        verify_coros = [
            judge_with_base_verify_llm(chunk, rule_card, document, base_result, semaphore)
            for _, chunk, rule_card, base_result in verify_tasks
        ]
        verify_results = await asyncio.gather(*verify_coros, return_exceptions=True)
        for (idx, chunk, rule_card, _), verify_result in zip(verify_tasks, verify_results):
            if isinstance(verify_result, Exception):
                logger.error(
                    f"base_verify_llm 任务失败 [{chunk.chunk_id} x {rule_card.rule_id}]: "
                    f"{verify_result}，保留规则引擎原判"
                )
            else:
                base_results[idx] = verify_result

    logger.info(f"base 轨完成: {len(base_results)} 个判定")

    # 执行 skill 轨（并发）
    skill_results = []
    if skill_tasks:
        skill_results = await asyncio.gather(*skill_tasks, return_exceptions=True)

        # 处理异常
        valid_skill_results = []
        for i, result in enumerate(skill_results):
            if isinstance(result, Exception):
                logger.error(f"skill 轨任务 {i} 失败: {result}")
                # 降级为 unsure
                route = skill_route_map[i]  # 使用映射获取正确的 route
                chunk = chunk_map[route.chunk_id]
                rule_card = rule_cards[route.rule_id]
                valid_skill_results.append(
                    JudgmentResult(
                        rule_id=rule_card.rule_id,
                        chunk_id=chunk.chunk_id,
                        verdict="unsure",
                        reasoning_cot=f"LLM 调用失败: {str(result)[:100]}",
                        evidence_span_ids=[],
                        evidence_texts=[],
                        reason_codes=[],
                        decision_basis="insufficient_evidence",
                    )
                )
            else:
                valid_skill_results.append(result)

        skill_results = valid_skill_results

    logger.info(f"skill 轨完成: {len(skill_results)} 个判定")

    # 合并结果
    all_results = base_results + skill_results

    # unsure 高风险二次审查
    retry_tasks = []
    retry_indices = []

    for i, result in enumerate(all_results):
        if result.verdict == "unsure":
            rule_card = rule_cards.get(result.rule_id)
            if rule_card and rule_card.risk_level == "high":
                chunk = chunk_map.get(result.chunk_id)
                chunk_fact = chunk_facts.get(result.chunk_id) if chunk_facts else None

                if chunk:
                    # 查找原始路由的 skill_type
                    original_skill_type = None
                    for route in routed_pairs:
                        if route.chunk_id == result.chunk_id and route.rule_id == result.rule_id:
                            original_skill_type = route.skill_type
                            break

                    retry_tasks.append(
                        retry_unsure_judgment(
                            judgment=result,
                            chunk=chunk,
                            rule_card=rule_card,
                            document=document,
                            chunk_fact=chunk_fact,
                            skill_type=original_skill_type,
                            semaphore=semaphore,
                        )
                    )
                    retry_indices.append(i)

    if retry_tasks:
        logger.info(f"开始二次审查: {len(retry_tasks)} 个 unsure 高风险判定")
        retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)

        # 替换原结果
        for idx, retry_result in zip(retry_indices, retry_results):
            if not isinstance(retry_result, Exception):
                all_results[idx] = retry_result
            else:
                logger.error(f"二次审查失败: {retry_result}")

    # 统计
    verdict_counts = {"violation": 0, "compliant": 0, "unsure": 0}
    for result in all_results:
        verdict_counts[result.verdict] = verdict_counts.get(result.verdict, 0) + 1

    logger.info(
        f"Stage 2 完成: 总计 {len(all_results)} 个判定, "
        f"violation={verdict_counts['violation']}, "
        f"compliant={verdict_counts['compliant']}, "
        f"unsure={verdict_counts['unsure']}"
    )

    return all_results
