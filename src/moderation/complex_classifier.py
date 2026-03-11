"""
复杂场景分类器
==============
统一管理复杂场景识别逻辑，避免重复实现。
"""

from .schemas import RuleCard


def classify_complex_scenario(rule_card: RuleCard) -> str | None:
    """
    根据规则特征自动分类到复杂场景。

    返回：
      - "temporal_context": 需要时态判断（区分"过往经历"vs"当前状态"）
      - "subject_switch": 需要主体识别（区分"代理人"vs"客户"vs"公司"）
      - "commitment_strength": 需要承诺强度判断（区分"保证"vs"预期"）
      - "cross_paragraph": 需要跨段落逻辑（需要全文上下文）
      - None: 不属于复杂场景

    分类策略：
      基于规则名称、违规定义、关键词中的特征词进行模式匹配。
    """
    rule_text = " ".join([
        rule_card.rule_name,
        rule_card.violation_definition,
        " ".join(rule_card.keywords),
    ]).lower()

    # 时态判断场景（优先级最高）
    # 典型场景：薪资诱导（需要区分"之前的收入"vs"当前承诺的收入"）
    if any(kw in rule_text for kw in ["薪资", "收入", "月薪", "年薪", "之前", "曾经", "过往"]):
        return "temporal_context"

    # 主体切换场景
    # 典型场景：需要区分"代理人的行为"vs"客户的行为"
    if any(kw in rule_text for kw in ["代理人", "客户", "投保人", "营销员", "主体"]):
        return "subject_switch"

    # 承诺强度场景
    # 典型场景：收益承诺（需要区分"保证收益"vs"预期收益"）
    if any(kw in rule_text for kw in ["保证", "承诺", "确保", "分红", "收益", "回报"]):
        return "commitment_strength"

    # 跨段落逻辑场景
    # 典型场景：需要全文上下文才能判断的复杂逻辑
    if any(kw in rule_text for kw in ["上下文", "全文", "前后", "关联"]):
        return "cross_paragraph"

    return None
