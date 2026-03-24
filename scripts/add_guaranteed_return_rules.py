#!/usr/bin/env python3
"""
补充 guaranteed_return 类别规则

根据 smoke 报告 FN-2 分析，补充以下知识簇：
1. 锁定收益类（软性承诺）
2. 稳健收益类（委婉承诺）
3. 未来收益类（包装式承诺）
4. 退休品质生活收入类（外延承诺）
"""

import json
from typing import List, Dict

# 新增规则定义
NEW_RULES: List[Dict] = [
    # === 1. 锁定收益类 ===
    {
        "rule_id": "KB0620",
        "rule_name": "知识库规则-锁定收益",
        "risk_level": "high",
        "violation_definition": "宣传保险产品可以锁定收益、锁定未来收益、锁定利率，暗示保险收益是确定的、不变的，误导客户认为保险产品可以保证收益",
        "exceptions": [
            "客观说明保险产品的预定利率",
            "说明保险合同约定的固定给付金额",
            "引用保险合同条款说明现金价值计算方式"
        ],
        "keywords": ["锁定收益", "锁定未来收益", "锁定利率", "锁定回报"],
        "reason_codes": ["暗示收益确定性", "误导保证收益"],
        "suggestion_template": "请删除关于锁定收益的表述，保险产品的收益受多种因素影响，不应暗示收益确定。",
        "violation_terms": ["锁定收益", "锁定未来收益", "锁定利率", "锁定回报"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["预定利率", "固定给付", "合同约定", "现金价值"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品不应暗示收益确定性",
        "compliant_case": "本产品的预定利率为3.5%，现金价值按照合同约定计算",
        "violation_basis": "《保险法》第131条",
        "violation_case": "购买保险可以锁定未来收益",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "guaranteed_return",
        "actor_scope": "agent",
        "claim_type": "income_promise",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": "income_promise_group"
    },

    # === 2. 稳健收益类 ===
    {
        "rule_id": "KB0621",
        "rule_name": "知识库规则-稳健收益",
        "risk_level": "high",
        "violation_definition": "宣传保险产品可以提供稳健收益、稳定收益、稳定回报，暗示保险收益是稳定的、可靠的，误导客户认为保险产品没有风险",
        "exceptions": [
            "客观说明保险产品的长期性特点",
            "说明保险合同约定的给付方式",
            "引用保险合同条款说明分红方式"
        ],
        "keywords": ["稳健收益", "稳定收益", "稳定回报", "稳健回报"],
        "reason_codes": ["暗示收益稳定性", "淡化投资风险"],
        "suggestion_template": "请删除关于稳健收益的表述，保险产品的收益存在不确定性，不应暗示收益稳定。",
        "violation_terms": ["稳健收益", "稳定收益", "稳定回报", "稳健回报"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["长期性", "合同约定", "分红方式", "不确定性"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品不应暗示收益稳定性",
        "compliant_case": "本产品为长期保险产品，分红按照合同约定方式分配",
        "violation_basis": "《保险法》第131条",
        "violation_case": "购买保险可以获得稳健收益",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "guaranteed_return",
        "actor_scope": "agent",
        "claim_type": "income_promise",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": "income_promise_group"
    },

    # === 3. 长期稳定回报类 ===
    {
        "rule_id": "KB0622",
        "rule_name": "知识库规则-长期稳定回报",
        "risk_level": "high",
        "violation_definition": "宣传保险产品可以提供长期稳定回报、持续稳定收益，暗示保险收益在长期内是稳定的、可预期的，误导客户认为保险产品可以保证长期收益",
        "exceptions": [
            "客观说明保险产品的长期性特点",
            "说明保险合同约定的给付期限",
            "引用保险合同条款说明年金领取方式"
        ],
        "keywords": ["长期稳定回报", "持续稳定收益", "长期收益", "持续回报"],
        "reason_codes": ["暗示长期收益确定性", "误导保证收益"],
        "suggestion_template": "请删除关于长期稳定回报的表述，保险产品的长期收益存在不确定性。",
        "violation_terms": ["长期稳定回报", "持续稳定收益"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["长期性", "合同约定", "年金领取", "不确定性"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品不应暗示长期收益确定性",
        "compliant_case": "本产品为长期年金保险，年金按照合同约定方式领取",
        "violation_basis": "《保险法》第131条",
        "violation_case": "购买保险可以获得长期稳定回报",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "guaranteed_return",
        "actor_scope": "agent",
        "claim_type": "income_promise",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": "income_promise_group"
    },

    # === 4. 退休品质生活收入类 ===
    {
        "rule_id": "KB0623",
        "rule_name": "知识库规则-退休品质生活收入",
        "risk_level": "medium",
        "violation_definition": "宣传保险产品可以保证退休品质生活收入、确保退休后的生活品质，暗示保险产品可以保证退休后的收入水平和生活质量，超出保险合同约定的保障范围",
        "exceptions": [
            "客观说明年金险的领取规则",
            "说明保险合同约定的年金给付金额",
            "引用保险合同条款说明领取条件"
        ],
        "keywords": ["退休品质生活收入", "确保退休后的生活品质", "保证退休收入", "退休生活保障"],
        "reason_codes": ["夸大保险保障功能", "超出合同约定范围"],
        "suggestion_template": "请修改为客观说明年金险的领取规则，不要夸大为保证退休品质生活收入。",
        "violation_terms": ["退休品质生活收入", "确保退休后的生活品质", "保证退休收入"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["年金领取", "合同约定", "领取条件", "年金给付"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品应客观说明合同约定的保障内容",
        "compliant_case": "本产品为年金保险，年金按照合同约定金额和方式领取",
        "violation_basis": "《保险法》第131条",
        "violation_case": "购买年金险可以确保退休后的生活品质",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "guaranteed_return",
        "actor_scope": "agent",
        "claim_type": "income_promise",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": "income_promise_group"
    },

    # === 5. 未来经济收益类 ===
    {
        "rule_id": "KB0624",
        "rule_name": "知识库规则-未来经济收益",
        "risk_level": "medium",
        "violation_definition": "宣传保险产品可以提供未来的经济收益、未来收益保障，暗示保险产品可以保证未来的经济回报，误导客户认为保险产品是投资工具",
        "exceptions": [
            "客观说明保险产品的给付条件",
            "说明保险合同约定的保险金给付",
            "引用保险合同条款说明现金价值"
        ],
        "keywords": ["未来的经济收益", "未来收益保障", "未来回报", "未来经济回报"],
        "reason_codes": ["暗示收益确定性", "混淆保险与投资"],
        "suggestion_template": "请删除关于未来经济收益的表述，保险产品不应被宣传为投资工具。",
        "violation_terms": ["未来的经济收益", "未来收益保障", "未来经济回报"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["给付条件", "合同约定", "保险金给付", "现金价值"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品不应被宣传为投资工具",
        "compliant_case": "本产品的保险金按照合同约定条件给付",
        "violation_basis": "《保险法》第131条",
        "violation_case": "购买保险可以获得未来的经济收益",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "guaranteed_return",
        "actor_scope": "agent",
        "claim_type": "income_promise",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": "income_promise_group"
    },
]


def main():
    # 读取现有规则
    with open("data/rule_cards.json", "r", encoding="utf-8") as f:
        rules = json.load(f)

    print(f"现有规则数: {len(rules)}")

    # 检查 rule_id 冲突
    existing_ids = {r["rule_id"] for r in rules}
    new_ids = {r["rule_id"] for r in NEW_RULES}
    conflicts = existing_ids & new_ids

    if conflicts:
        print(f"⚠️  发现 rule_id 冲突: {conflicts}")
        return

    # 添加新规则
    rules.extend(NEW_RULES)

    print(f"新增规则数: {len(NEW_RULES)}")
    print(f"更新后规则数: {len(rules)}")
    print()

    # 输出新增规则摘要
    print("新增规则摘要:")
    for rule in NEW_RULES:
        print(f"  {rule['rule_id']}: {rule['rule_name']}")
        print(f"    Keywords: {rule['keywords'][:3]}")
        print(f"    Risk Level: {rule['risk_level']}")
        print()

    # 保存更新后的规则
    with open("data/rule_cards.json", "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

    print(f"✅ 已保存更新后的规则到 data/rule_cards.json")

    # 统计 guaranteed_return 类别规则数
    return_rules = [r for r in rules if r.get("category_group") == "guaranteed_return"]
    print(f"\nguaranteed_return 类别规则数: {len(return_rules)} 条")


if __name__ == "__main__":
    main()
