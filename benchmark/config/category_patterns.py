"""类别映射与清洗规则。"""

from __future__ import annotations

import re


CATEGORY_PATTERNS: dict[str, list[str]] = {
    "financial_product_confusion": [
        r"银行",
        r"存款",
        r"理财",
        r"投资",
        r"国债",
        r"信托",
        r"杠杆",
        r"现金流",
        r"挪储",
        r"固收",
        r"与其它?金融产品混淆",
        r"与其他金融产品混淆",
        r"银保",
        r"存钱",
        r"储蓄",
        r"账户",
        r"换个地方放钱",
        r"金融房产",
    ],
    "guaranteed_return": [
        r"承诺保险收益",
        r"违规承诺保险收益",
        r"刚性兑付",
        r"稳定且有保障的收益",
        r"长期收益",
        r"稳赚",
        r"稳赢",
        r"复利",
        r"收益改利益",
        r"较高的现金价值",
    ],
    "responsibility_exaggeration": [
        r"夸大保险责任",
        r"返还保费",
        r"返还现金",
        r"收入替代",
        r"可以应对法律诉讼",
        r"保证永远过得好",
        r"带走三大风险",
        r"报销形容商业保险",
    ],
    "tax_or_law_misinterpretation": [
        r"税收",
        r"法条",
        r"法律",
        r"片面解读",
        r"专属方案",
        r"税务风险",
        r"数据要有具体来源出处",
        r"来源出处",
        r"错误解",
        r"风险提示语",
    ],
    "false_urgency": [
        r"炒停",
        r"停售",
        r"限时",
        r"最后机会",
    ],
    "transfer_or_inheritance": [
        r"传承",
        r"财富传承",
        r"转移.*风险",
        r"规避.*风险",
        r"遗产",
        r"避债",
        r"债务隔离",
        r"资产保全",
    ],
    "gifts_or_extra_benefits": [
        r"赠送",
        r"奖品",
        r"礼物",
        r"合同外利益",
        r"健康管理服务",
        r"对客户送实物",
        r"保费回扣",
    ],
    "brand_or_ip_risk": [
        r"品牌名",
        r"侵权",
        r"平安要规范表述为平安人寿",
        r"提及具体平台名",
    ],
    "agent_title_or_recruitment": [
        r"代理人称呼",
        r"高质团队",
        r"招聘",
        r"薪资诱导",
        r"保险代理人",
        r"财富健康管理师",
        r"私人财富规划师",
        r"岗位",
        r"增员",
        r"平安大学",
    ],
    "comparison_or_absolute": [
        r"唯一",
        r"第一",
        r"最好",
        r"最优",
        r"绝对",
        r"贬低",
        r"最高级",
        r"最XX",
        r"不当类比",
        r"比喻成房产",
        r"比作房产",
        r"宗教",
    ],
    "false_positive_regression": [
        r"AI误判",
        r"无需提示",
        r"badcase",
    ],
    "evidence_or_source_required": [
        r"数据要有",
        r"来源出处",
        r"具体来源",
        r"具体数据来源",
        r"理赔数据要有具体来源出处",
    ],
    "pension_term_misuse": [
        r"养老金",
        r"个人养老账户",
        r"非养老型保险产品",
        r"违规使用“养老”",
        r"使用“养老”表述介绍非养老",
    ],
    "policy_loan_or_cash_value": [
        r"保单贷款",
        r"现金价值",
        r"贷款遗漏风险提示语",
        r"费用补偿性医疗保险遗漏赔付比例提示语",
    ],
    "service_disclosure_missing": [
        r"服务提供主体",
        r"居家养老服务",
        r"其它服务要说明服务提供主体",
    ],
    "national_or_regulatory_endorsement": [
        r"国家名义",
        r"监管做背书",
        r"用监管做背书",
        r"国家政策",
        r"监管单位",
    ],
    "inappropriate_metaphor": [
        r"房产",
        r"宗教",
        r"医生的名义",
        r"交警",
        r"婚姻",
        r"秘密",
        r"不当类比",
    ],
}


RISK_TERMS = [
    "保证",
    "稳赚",
    "稳赢",
    "第一",
    "唯一",
    "最好",
    "最优",
    "投资",
    "理财",
    "存款",
    "银行",
    "退保",
    "税收",
    "传承",
    "刚性兑付",
    "账户",
    "复利",
    "财富",
]


DISCLAIMER_TERMS = [
    "不代表未来表现",
    "分红利益演示",
    "分红是不确定的",
    "分红有可能为零",
    "以实际为准",
    "具体以",
    "购买需谨慎",
    "非银行存款",
    "风险提示",
]


COMPLIANT_REVIEW_PATTERNS = [
    r"财富传承",
    r"家族信托",
    r"税收问题",
    r"收益率",
    r"更高的收益",
    r"收益潜力",
    r"资产配置价值",
    r"账户增长",
    r"零利率",
    r"财富类产品",
    r"财富管理方案",
    r"银行.*类似的产品",
]


def infer_categories(*parts: str) -> list[str]:
    text = " ".join(part for part in parts if part).strip()
    if not text:
        return []
    matched: list[str] = []
    for category, patterns in CATEGORY_PATTERNS.items():
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            matched.append(category)
    return matched


def count_risk_hits(text: str) -> int:
    return sum(term in text for term in RISK_TERMS)


def count_disclaimer_hits(text: str) -> int:
    return sum(term in text for term in DISCLAIMER_TERMS)


def has_compliant_review_pattern(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in COMPLIANT_REVIEW_PATTERNS)
