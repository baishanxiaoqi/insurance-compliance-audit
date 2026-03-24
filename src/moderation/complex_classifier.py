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
      - "gifts_or_extra_benefits": 合同外利益识别
      - "agent_title_or_recruitment": 招募代理人误导头衔识别
      - "national_or_regulatory_endorsement": 监管背书/国家背书识别
      - "tax_or_law_misinterpretation": 税法/法律误导识别
      - "transfer_or_inheritance": 传承/资产转移类误导识别
      - "guaranteed_return": 收益承诺/稳定收益暗示识别
      - "comparison_or_absolute": 简单对比/绝对化识别
      - None: 不属于复杂场景

    分类策略：
      基于规则名称、违规定义、关键词中的特征词进行模式匹配。
    """
    rule_text = " ".join([
        rule_card.rule_name,
        rule_card.violation_definition,
        " ".join(rule_card.keywords),
    ]).lower()

    if (
        rule_card.primary_category == "financial_product_confusion"
        or rule_card.category_group == "financial_confusion"
    ):
        return "financial_confusion"

    if (
        rule_card.primary_category == "absolute_expression"
        or rule_card.category_group in {"absolute_expression", "comparison_violation"}
    ):
        return "comparison_or_absolute"

    if (
        rule_card.primary_category == "gifts_or_extra_benefits"
        or rule_card.category_group == "gifts_benefits"
    ):
        return "gifts_or_extra_benefits"

    if rule_card.primary_category == "agent_title_violation" or rule_card.category_group == "agent_title_violation":
        return "agent_title_or_recruitment"

    if rule_card.primary_category == "regulatory_misinterpretation" or rule_card.category_group == "regulatory_misinterpretation":
        return "national_or_regulatory_endorsement"

    # 合同外利益场景（优先级最高，避免被其他场景误判）
    if any(kw in rule_text for kw in ["合同外利益", "赠送", "礼品", "奖品", "抽奖", "红酒会", "卡券", "保费回扣"]):
        return "gifts_or_extra_benefits"

    # 招募代理人误导头衔场景
    if any(kw in rule_text for kw in ["招募", "增员", "金融理财顾问", "税务规划师", "合伙人", "误导头衔", "用工性质"]):
        return "agent_title_or_recruitment"

    # 监管背书/国家背书场景
    if any(kw in rule_text for kw in ["监管背书", "国家背书", "国家级", "国家政策", "政府", "监管要求", "监管审批"]):
        return "national_or_regulatory_endorsement"

    # 税法/法律误导场景
    if any(kw in rule_text for kw in ["避税", "免税", "避债", "债务隔离", "遗产税", "税收", "税法", "法律误导"]):
        return "tax_or_law_misinterpretation"

    # 传承/资产转移类误导场景
    if any(kw in rule_text for kw in ["财富传承", "资产转移", "有序转移", "财富隔离", "资产保全", "规避争议"]):
        return "transfer_or_inheritance"

    # 收益承诺/稳定收益暗示场景（需要与 commitment_strength 区分）
    # guaranteed_return 更关注"稳定性暗示"，commitment_strength 更关注"承诺强度"
    if any(kw in rule_text for kw in ["稳定收益", "锁定收益", "固定回报", "保证收益", "承诺分红"]):
        return "guaranteed_return"

    if any(kw in rule_text for kw in ["理财", "投资", "存款", "存入", "储蓄", "本金", "利息", "复利", "账户", "万能账户", "保本", "杠杆"]):
        return "financial_confusion"

    # 简单对比/绝对化场景
    if any(kw in rule_text for kw in ["绝对化", "最", "第一", "唯一", "最好", "最优", "简单对比", "贬低"]):
        return "comparison_or_absolute"

    # 时态判断场景
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
