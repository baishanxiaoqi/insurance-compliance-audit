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
from typing import Dict, List

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
            draft_suggestion="",
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
        draft_suggestion=rule_card.suggestion_template or "请修改违规表述。",
    )


# ============================================================
# 策略B：skill 轨（LLM Agent + Skills）
# ============================================================


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

    # 构建 Prompt（包含 Few-shot）
    prompt = skill.build_prompt(
        chunk=chunk,
        rule_card=rule_card,
        spans_dict=spans_dict,
        chunk_fact=chunk_fact,
        deterministic_report=deterministic_report,
    )

    # 创建 Agent
    agent = create_agent(
        output_schema=JudgmentResult,
        instructions=skill.system_instructions,
        name=f"skill_{skill.name}",
        temperature=skill.temperature,
    )

    # 并发控制
    if semaphore:
        async with semaphore:
            result = await safe_arun(agent, prompt)
    else:
        result = await safe_arun(agent, prompt)

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
    )

    retry_prompt = f"""{base_prompt}

========== 二次审查要求 ==========
这是一次二次审查。之前的判定结果为 unsure（不确定）。
请更加仔细地分析文本，结合规则定义和例外条款，给出明确的判定（violation 或 compliant）。
如果确实无法判定，请在 reasoning_cot 中详细说明原因。"""

    # 提高 temperature
    agent = create_agent(
        output_schema=JudgmentResult,
        instructions=skill.system_instructions,
        name=f"retry_{skill.name}",
        temperature=0.3,  # 提高探索性
    )

    result = await safe_arun(agent, retry_prompt)

    # 后验证
    valid_span_ids = {s.span_id for s in chunk.spans}
    result.evidence_span_ids = [
        sid for sid in result.evidence_span_ids if sid in valid_span_ids
    ]

    if rule_card.reason_codes:
        result.reason_codes = [
            rc for rc in result.reason_codes if rc in rule_card.reason_codes
        ]

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
    max_concurrent: int = 3,
) -> List[JudgmentResult]:
    """
    Stage 2 主入口：双策略混合架构。

    工作流程：
      1. 根据 routed_pairs 的 strategy 分发到不同策略
      2. base 轨：同步执行规则引擎
      3. skill 轨：异步并发调用 LLM Agent
      4. unsure 高风险二次审查
      5. 返回所有判定结果

    参数：
      document: 文档状态（包含 chunks 和 span_pool）
      rule_cards: 规则卡片字典
      candidates: Stage 1 候选结果（用于兼容性，实际使用 routed_pairs）
      routed_pairs: Stage 1.8 路由结果
      chunk_facts: Stage 1.5 事实画像
      max_concurrent: 最大并发 LLM 调用数
    """
    logger.info(f"Stage 2 开始: {len(routed_pairs)} 个路由对")

    # 构建 chunk_id -> Chunk 的索引
    chunk_map = {c.chunk_id: c for c in document.chunks}

    # 并发控制信号量
    semaphore = asyncio.Semaphore(max_concurrent)

    # 分离 base 轨和 skill 轨
    base_tasks = []
    skill_tasks = []
    skill_route_map = {}  # 记录 skill 任务索引 -> route 的映射

    for route in routed_pairs:
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
    for chunk, rule_card in base_tasks:
        result = judge_with_base_strategy(chunk, rule_card, document)
        base_results.append(result)

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
                        draft_suggestion="",
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
                            skill_type=original_skill_type,  # 传递原始 skill_type
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

