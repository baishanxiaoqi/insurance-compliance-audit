"""
标准审查类别映射配置
====================
Phase 4 P1++ 新增：建立标准类别映射闭环

目标：
- 解决 category_hit_rate 偏低的问题
- 将细粒度类别映射到 benchmark 标准类别
- 保留细粒度类别用于内部分析，但对外输出标准类别

标准类别定义：
1. financial_product_confusion - 金融产品混淆
2. guaranteed_return - 收益承诺
3. gifts_or_extra_benefits - 礼品/额外利益
4. responsibility_exaggeration - 责任夸大
5. absolute_expression - 绝对化表述
6. regulatory_misinterpretation - 监管误读
7. surrender_guidance - 退保引导
8. agent_title_violation - 代理人职称违规
9. comparison_violation - 不当比较
10. other - 其他违规
"""

from typing import Dict, Optional

# 标准类别映射表
STANDARD_CATEGORY_MAPPING: Dict[str, str] = {
    # 金融产品混淆类
    "financial_product_confusion": "financial_product_confusion",
    "investment_implication": "financial_product_confusion",
    "stable_return_implication": "financial_product_confusion",
    "savings_account_confusion": "financial_product_confusion",
    "wealth_management_confusion": "financial_product_confusion",
    "forced_savings_implication": "financial_product_confusion",
    "deposit_payment_confusion": "financial_product_confusion",
    "principal_interest_confusion": "financial_product_confusion",
    "bank_fund_analogy": "financial_product_confusion",

    # 收益承诺类
    "guaranteed_return": "guaranteed_return",
    "income_promise": "guaranteed_return",
    "dividend_certainty": "guaranteed_return",
    "return_exaggeration": "guaranteed_return",
    "stable_income_promise": "guaranteed_return",
    "locked_return_claim": "guaranteed_return",
    "deterministic_return_claim": "guaranteed_return",
    "fixed_return_claim": "guaranteed_return",
    "case_based_return_analogy": "guaranteed_return",
    "rhetorical_guarantee": "guaranteed_return",
    "template_return_structure": "guaranteed_return",
    "relative_bank_return_claim": "guaranteed_return",

    # 礼品/额外利益类
    "gifts_or_extra_benefits": "gifts_or_extra_benefits",
    "contractual_outside_interests": "gifts_or_extra_benefits",
    "warm_service_promotion": "gifts_or_extra_benefits",
    "unauthorized_gifts": "gifts_or_extra_benefits",
    "rebate_promotion": "gifts_or_extra_benefits",
    "extra_benefits_promise": "gifts_or_extra_benefits",
    "rebate_or_premium_return": "gifts_or_extra_benefits",
    "gift_discount_lottery_inducement": "gifts_or_extra_benefits",
    "service_beyond_health_management": "gifts_or_extra_benefits",

    # 责任夸大类
    "responsibility_exaggeration": "responsibility_exaggeration",
    "coverage_exaggeration": "responsibility_exaggeration",
    "legal_consequence_exaggeration": "responsibility_exaggeration",
    "asset_protection_exaggeration": "responsibility_exaggeration",
    "income_protection_exaggeration": "responsibility_exaggeration",
    "coverage_absolute_claim": "responsibility_exaggeration",
    "debt_planning_claim": "responsibility_exaggeration",
    "tax_planning_claim": "responsibility_exaggeration",
    "universal_coverage_claim": "responsibility_exaggeration",
    "inheritance_dispute_resolution": "responsibility_exaggeration",
    "marriage_dispute_resolution": "responsibility_exaggeration",
    "claim_condition_simplification": "responsibility_exaggeration",
    "claim_scope_exaggeration": "responsibility_exaggeration",

    # 绝对化表述类
    "absolute_expression": "absolute_expression",
    "ranking_claim": "absolute_expression",
    "superlative_claim": "absolute_expression",
    "uniqueness_claim": "absolute_expression",
    "assertive_promise": "absolute_expression",
    "conditional_absolute_claim": "absolute_expression",
    "fear_pressure_claim": "absolute_expression",
    "urgency_claim": "absolute_expression",
    "improper_term_claim": "absolute_expression",

    # 监管误读类
    "regulatory_misinterpretation": "regulatory_misinterpretation",
    "tax_law_misinterpretation": "regulatory_misinterpretation",
    "legal_provision_misinterpretation": "regulatory_misinterpretation",
    "national_endorsement_claim": "regulatory_misinterpretation",
    "regulatory_approval_endorsement": "regulatory_misinterpretation",
    "leader_endorsement_claim": "regulatory_misinterpretation",
    "policy_backing_claim": "regulatory_misinterpretation",

    # 退保引导类
    "surrender_guidance": "surrender_guidance",
    "surrender_inducement": "surrender_guidance",
    "policy_replacement_guidance": "surrender_guidance",

    # 代理人职称违规类
    "agent_title_violation": "agent_title_violation",
    "recruitment_violation": "agent_title_violation",
    "position_title_violation": "agent_title_violation",
    "misleading_position_title": "agent_title_violation",
    "income_exaggeration_recruitment": "agent_title_violation",
    "scope_of_practice_confusion": "agent_title_violation",
    "recruitment_nature_confusion": "agent_title_violation",

    # 不当比较类
    "comparison_violation": "comparison_violation",
    "unfair_comparison": "comparison_violation",
    "misleading_comparison": "comparison_violation",
    "peer_product_derogation": "comparison_violation",
    "one_sided_financial_comparison": "comparison_violation",

    # 风险相关（映射到其他）
    "risk_downplay": "other",
    "risk_transfer": "other",
    "risk_management": "other",
}

# 标准类别中文名称
STANDARD_CATEGORY_NAMES: Dict[str, str] = {
    "financial_product_confusion": "金融产品混淆",
    "guaranteed_return": "收益承诺",
    "gifts_or_extra_benefits": "礼品/额外利益",
    "responsibility_exaggeration": "责任夸大",
    "absolute_expression": "绝对化表述",
    "regulatory_misinterpretation": "监管误读",
    "surrender_guidance": "退保引导",
    "agent_title_violation": "代理人职称违规",
    "comparison_violation": "不当比较",
    "other": "其他违规",
}


def map_to_standard_category(primary_category: Optional[str]) -> str:
    """
    将细粒度类别映射到标准类别

    参数：
      - primary_category: 细粒度主审查点类别

    返回：
      - 标准类别（用于 benchmark 评估）
    """
    if not primary_category:
        return "other"

    # 直接映射
    if primary_category in STANDARD_CATEGORY_MAPPING:
        return STANDARD_CATEGORY_MAPPING[primary_category]

    # 如果已经是标准类别，直接返回
    if primary_category in STANDARD_CATEGORY_NAMES:
        return primary_category

    # 未知类别映射到 other
    return "other"


def get_standard_category_name(standard_category: str) -> str:
    """
    获取标准类别的中文名称

    参数：
      - standard_category: 标准类别

    返回：
      - 中文名称
    """
    return STANDARD_CATEGORY_NAMES.get(standard_category, "其他违规")
