"""
Stage 2.7: 建议生成层
====================
默认使用确定性模板生成建议；
如果启用 `SUGGESTION_USE_LLM_RENDERER`，则使用独立建议模型
对模板建议做业务可读性渲染，但保留 deterministic fallback。
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Literal

from pydantic import BaseModel, Field

from .. import config
from ..llm_agent import create_agent, safe_arun
from ..schemas import JudgmentResult, SuggestionResult, RuleCard
from ..log import get_logger

logger = get_logger(__name__)


class SuggestionRenderPayload(BaseModel):
    suggestion: str = Field(..., description="面向业务侧的简洁修改建议")
    suggestion_type: Literal["delete", "weaken", "add_disclosure", "rephrase"] = "rephrase"


def _clean_fragment(text: str) -> str:
    return (text or "").strip(" \t\r\n，。；！？、：:,.!?'\"“”‘’（）()[]【】《》")


def _build_suggestion_render_prompt(
    judgment: JudgmentResult,
    rule_card: RuleCard,
    base_suggestion: str,
    base_suggestion_type: str,
) -> str:
    evidence_summary = "、".join(
        fragment
        for fragment in (_clean_fragment(text) for text in judgment.evidence_texts[:3])
        if fragment
    ) or "无明确片段"

    return f"""你是一名保险合规审核结果润色助手，需要把已有的确定性修改建议改写成更适合业务查看的简洁批注。

【要求】
1. 不得改变原建议的合规方向，只能润色表达。
2. 优先保持具体、直接、可执行。
3. 不要新增原文中不存在的事实，不要扩写监管结论。
4. `suggestion_type` 只能在以下四个值中选择：delete / weaken / add_disclosure / rephrase。

【规则信息】
- rule_id: {rule_card.rule_id}
- 规则名称: {rule_card.rule_name}
- 违规定义: {rule_card.violation_definition}

【违规证据】
- 证据片段: {evidence_summary}

【基础建议】
- suggestion_type: {base_suggestion_type}
- suggestion: {base_suggestion}

请输出更适合业务侧直接查看的一条建议。"""


async def _render_with_suggestion_model(
    judgment: JudgmentResult,
    rule_card: RuleCard,
    base_suggestion: str,
    base_suggestion_type: str,
) -> tuple[str, str]:
    prompt = _build_suggestion_render_prompt(
        judgment=judgment,
        rule_card=rule_card,
        base_suggestion=base_suggestion,
        base_suggestion_type=base_suggestion_type,
    )
    agent = create_agent(
        output_schema=SuggestionRenderPayload,
        instructions=[
            "你负责把合规整改建议润色成业务可读、简短、可执行的批注。",
            "不要改变原始建议的整改方向，不要新增事实。",
        ],
        name="suggestion_renderer",
        profile=config.SUGGESTION_MODEL_PROFILE,
    )
    rendered = await safe_arun(
        agent,
        prompt,
        max_retries=config.SUGGESTION_MODEL_PROFILE.max_retries,
        timeout_seconds=config.SUGGESTION_MODEL_PROFILE.timeout_seconds,
    )
    return rendered.suggestion, rendered.suggestion_type


async def run_stage2_7_suggestion(
    judgments: List[JudgmentResult],
    rule_cards: Dict[str, RuleCard],
) -> Dict[str, SuggestionResult]:
    """
    Stage 2.7: 为所有违规判定生成修改建议

    输入：
      - judgments: Stage 2 的判定结果列表
      - rule_cards: 规则卡片字典

    输出：
      - Dict[str, SuggestionResult]: key 为 f"{chunk_id}_{rule_id}"

    策略：
      1. 只为 violation 判定生成建议
      2. 优先使用 RuleCard 的 suggestion_template
      3. 如果模板为空，根据违规类型生成默认建议
      4. 结合 evidence_texts 提供具体的修改指导
    """
    suggestions: Dict[str, SuggestionResult] = {}

    # 只处理 violation 判定
    violation_judgments = [j for j in judgments if j.verdict == "violation"]
    logger.info(f"Stage 2.7: 为 {len(violation_judgments)} 个违规判定生成建议")
    renderer_enabled = (
        config.SUGGESTION_USE_LLM_RENDERER
        and config.is_model_profile_configured(config.SUGGESTION_MODEL_PROFILE)
    )
    if config.SUGGESTION_USE_LLM_RENDERER and not renderer_enabled:
        logger.warning(
            "Stage 2.7 建议模型未启用：SUGGESTION_MODEL_PROFILE 缺少完整 provider 凭证，"
            "将继续使用确定性模板建议。"
        )

    render_tasks: list[asyncio.Task[tuple[str, str] | Exception]] = []
    render_meta: list[tuple[JudgmentResult, RuleCard, str, str]] = []

    for judgment in violation_judgments:
        rule_card = rule_cards.get(judgment.rule_id)
        if not rule_card:
            logger.warning(f"  RuleCard {judgment.rule_id} 未找到，跳过建议生成")
            continue

        # 生成建议
        suggestion_text, suggestion_type = _generate_suggestion(
            judgment=judgment,
            rule_card=rule_card,
        )

        if renderer_enabled:
            render_meta.append((judgment, rule_card, suggestion_text, suggestion_type))
            render_tasks.append(
                asyncio.create_task(
                    _render_with_suggestion_model(
                        judgment=judgment,
                        rule_card=rule_card,
                        base_suggestion=suggestion_text,
                        base_suggestion_type=suggestion_type,
                    )
                )
            )
            continue

        suggestion_result = SuggestionResult(
            rule_id=judgment.rule_id,
            chunk_id=judgment.chunk_id,
            suggestion=suggestion_text,
            suggestion_type=suggestion_type,
        )

        key = f"{judgment.chunk_id}_{judgment.rule_id}"
        suggestions[key] = suggestion_result

    if render_tasks:
        rendered_results = await asyncio.gather(*render_tasks, return_exceptions=True)
        for (judgment, rule_card, base_text, base_type), rendered in zip(render_meta, rendered_results):
            if isinstance(rendered, Exception):
                logger.warning(
                    "  建议模型渲染失败，回退到模板建议: rule=%s, error=%s",
                    judgment.rule_id,
                    rendered,
                )
                final_text, final_type = base_text, base_type
            else:
                final_text, final_type = rendered

            suggestion_result = SuggestionResult(
                rule_id=judgment.rule_id,
                chunk_id=judgment.chunk_id,
                suggestion=final_text,
                suggestion_type=final_type,
            )
            suggestions[f"{judgment.chunk_id}_{judgment.rule_id}"] = suggestion_result

    logger.info(f"Stage 2.7 完成: 生成 {len(suggestions)} 条建议")
    return suggestions


def _generate_suggestion(
    judgment: JudgmentResult,
    rule_card: RuleCard,
) -> tuple[str, str]:
    """
    为单个违规判定生成修改建议

    返回：
      - (suggestion_text, suggestion_type)
    """
    # 优先使用 RuleCard 的 suggestion_template
    if rule_card.suggestion_template:
        suggestion_text = rule_card.suggestion_template
        suggestion_type = _infer_suggestion_type(rule_card.suggestion_template)
    else:
        # 根据违规类型生成默认建议
        suggestion_text, suggestion_type = _generate_default_suggestion(
            rule_card=rule_card,
            evidence_texts=judgment.evidence_texts,
        )

    # 如果有具体的违规证据，补充到建议中
    if judgment.evidence_texts:
        evidence_summary = "、".join([
            fragment
            for fragment in (_clean_fragment(text) for text in judgment.evidence_texts[:3])
            if fragment
        ])
        if evidence_summary:
            suggestion_text = f"{suggestion_text} 具体违规表述：「{evidence_summary}」"

    return suggestion_text, suggestion_type


def _infer_suggestion_type(template: str) -> str:
    """
    从建议模板推断建议类型

    策略：
      - 包含"删除"/"移除" → delete
      - 包含"弱化"/"改为" → weaken
      - 包含"补充"/"增加"/"披露" → add_disclosure
      - 其他 → rephrase
    """
    template_lower = template.lower()

    if "删除" in template or "移除" in template:
        return "delete"
    elif "弱化" in template or "改为" in template:
        return "weaken"
    elif "补充" in template or "增加" in template or "披露" in template:
        return "add_disclosure"
    else:
        return "rephrase"


def _generate_default_suggestion(
    rule_card: RuleCard,
    evidence_texts: List[str],
) -> tuple[str, str]:
    """
    根据违规类型生成默认建议

    策略：
      - 收益承诺类 → 删除或弱化
      - 绝对化表述 → 删除或改为相对表述
      - 金融混淆类 → 删除或补充区分说明
      - 其他 → 删除违规表述
    """
    rule_name = rule_card.rule_name.lower()

    # 收益承诺类
    if "收益" in rule_name or "回报" in rule_name or "分红" in rule_name:
        return "请删除或弱化收益承诺表述，避免误导客户对收益的预期。", "weaken"

    # 绝对化表述
    elif "绝对化" in rule_name or "最" in rule_name or "第一" in rule_name:
        return "请删除绝对化表述，改为相对表述或客观描述。", "delete"

    # 金融混淆类
    elif "理财" in rule_name or "投资" in rule_name or "储蓄" in rule_name:
        return "请删除将保险与理财/投资/储蓄混淆的表述，或补充说明保险与理财产品的区别。", "delete"

    # 送礼/赠送优惠
    elif "礼品" in rule_name or "赠送" in rule_name or "优惠" in rule_name:
        return "请删除赠送礼品或优惠的表述，避免违反监管规定。", "delete"

    # 退保引导
    elif "退保" in rule_name or "减保" in rule_name:
        return "请删除引导客户退保的表述，并补充退保风险提示。", "add_disclosure"

    # 默认建议
    else:
        return "请修改或删除违规表述，确保符合监管要求。", "rephrase"
