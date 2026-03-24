#!/usr/bin/env python3
"""
自动标注规则的 category_group 字段

根据规则的 violation_definition、keywords、rule_name 自动推断类别分组
"""

import json
from typing import Dict, List


# 类别识别规则
CATEGORY_PATTERNS = {
    "financial_confusion": {
        "keywords": ["金融", "理财", "投资", "存款", "储蓄", "本金", "定投", "基金", "退休金", "养老金"],
        "violation_terms": ["混淆", "误导", "误解", "暗示"],
        "description": "金融产品混淆"
    },
    "guaranteed_return": {
        "keywords": ["收益", "回报", "分红", "利息", "利率", "保证", "承诺", "确定", "稳定"],
        "violation_terms": ["承诺", "保证", "确定", "锁定"],
        "description": "收益承诺"
    },
    "gifts_benefits": {
        "keywords": ["礼品", "赠送", "返佣", "返利", "优惠", "利益", "好处", "温馨服务", "惊喜"],
        "violation_terms": ["赠送", "礼品", "利益", "好处"],
        "description": "礼品/额外利益"
    },
    "responsibility_exaggeration": {
        "keywords": ["责任", "保障", "覆盖", "赔付", "理赔", "保额"],
        "violation_terms": ["夸大", "扩大", "超出"],
        "description": "责任夸大"
    },
    "absolute_expression": {
        "keywords": ["最", "第一", "唯一", "绝对", "必须", "一定", "肯定"],
        "violation_terms": ["绝对化", "最高级", "唯一"],
        "description": "绝对化表述"
    },
    "regulatory_misinterpretation": {
        "keywords": ["监管", "法律", "政策", "国家", "政府", "税收", "税法"],
        "violation_terms": ["误读", "误解", "曲解"],
        "description": "监管误读"
    },
    "surrender_guidance": {
        "keywords": ["退保", "退保金", "解约", "终止"],
        "violation_terms": ["引导", "诱导", "劝说"],
        "description": "退保引导"
    },
    "agent_title_violation": {
        "keywords": ["招聘", "应聘", "职位", "职称", "经理", "总监"],
        "violation_terms": ["招聘", "职称", "职位"],
        "description": "代理人职称违规"
    },
    "comparison_violation": {
        "keywords": ["对比", "比较", "优于", "超过", "高于"],
        "violation_terms": ["对比", "比较", "不当"],
        "description": "不当比较"
    },
}


def infer_category_group(rule: Dict) -> str:
    """
    根据规则内容推断 category_group

    优先级：
    1. violation_definition 中的违规术语匹配
    2. keywords 中的关键词匹配
    3. rule_name 中的关键词匹配
    """
    rule_name = rule.get("rule_name", "").lower()
    violation_def = rule.get("violation_definition", "").lower()
    keywords = [k.lower() for k in rule.get("keywords", [])]

    # 计算每个类别的匹配分数
    scores: Dict[str, int] = {}

    for category, patterns in CATEGORY_PATTERNS.items():
        score = 0

        # violation_definition 中的违规术语匹配（权重最高）
        for term in patterns["violation_terms"]:
            if term in violation_def:
                score += 10

        # keywords 中的关键词匹配（权重中等）
        for kw in patterns["keywords"]:
            if any(kw in k for k in keywords):
                score += 5

        # rule_name 中的关键词匹配（权重较低）
        for kw in patterns["keywords"]:
            if kw in rule_name:
                score += 3

        # violation_definition 中的关键词匹配（权重较低）
        for kw in patterns["keywords"]:
            if kw in violation_def:
                score += 2

        if score > 0:
            scores[category] = score

    # 返回得分最高的类别
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]

    return "other"


def main():
    # 读取现有规则
    with open("data/rule_cards.json", "r", encoding="utf-8") as f:
        rules = json.load(f)

    print(f"总规则数: {len(rules)}")

    # 统计类别分布
    category_stats: Dict[str, int] = {}

    # 标注 category_group
    for rule in rules:
        category = infer_category_group(rule)
        rule["category_group"] = category
        category_stats[category] = category_stats.get(category, 0) + 1

    # 输出统计
    print("\n类别分布:")
    for category, count in sorted(category_stats.items(), key=lambda x: -x[1]):
        desc = CATEGORY_PATTERNS.get(category, {}).get("description", "其他")
        print(f"  {category:30s} ({desc:15s}): {count:3d} 条")

    # 保存标注后的规则
    with open("data/rule_cards.json", "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已保存标注后的规则到 data/rule_cards.json")

    # 输出部分示例
    print("\n示例规则:")
    for category in ["financial_confusion", "guaranteed_return", "gifts_benefits"]:
        examples = [r for r in rules if r.get("category_group") == category][:2]
        if examples:
            print(f"\n{category}:")
            for rule in examples:
                print(f"  - {rule['rule_id']}: {rule['rule_name']}")


if __name__ == "__main__":
    main()
