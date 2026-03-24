#!/usr/bin/env python3
"""
补充 responsibility_exaggeration 类别规则

根据 smoke 报告 FN-1 分析，补充以下知识簇：
1. 法律纠纷规避类
2. 财产隔离/分割类
3. 收入保障外延类
"""

import json
from typing import List, Dict

# 新增规则定义
NEW_RULES: List[Dict] = [
    # === 1. 法律纠纷规避类 ===
    {
        "rule_id": "KB0614",
        "rule_name": "知识库规则-避免法律纠纷",
        "risk_level": "high",
        "violation_definition": "宣传保险产品可以避免、规避法律纠纷，夸大保险的法律保护功能，误导客户认为购买保险可以免除法律责任或避免法律纠纷",
        "exceptions": [
            "客观说明保险合同的法律效力",
            "引用法律条文说明保险的合法性",
            "说明保险理赔的法律程序"
        ],
        "keywords": ["避免法律纠纷", "规避法律纠纷", "免除法律责任", "避免纠纷"],
        "reason_codes": ["夸大保险法律保护功能", "误导法律责任规避"],
        "suggestion_template": "请删除关于避免法律纠纷的表述，保险产品不能规避法律责任。",
        "violation_terms": ["避免法律纠纷", "规避法律纠纷", "免除法律责任", "避免纠纷"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["法律程序", "法律效力", "合法性"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品不能规避法律责任，不应宣传可以避免法律纠纷",
        "compliant_case": "保险理赔需要按照法律程序进行",
        "violation_basis": "《保险法》第131条",
        "violation_case": "购买保险可以避免法律纠纷",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "responsibility_exaggeration",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": ["legal_context"],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    # === 2. 财产隔离/分割类 ===
    {
        "rule_id": "KB0615",
        "rule_name": "知识库规则-避免财产分割",
        "risk_level": "high",
        "violation_definition": "宣传保险产品可以避免财产分割、隔离婚变风险、避免成为分割焦点，夸大保险的财产保护功能，误导客户认为购买保险可以规避财产分割",
        "exceptions": [
            "客观说明保险金的法定受益人规则",
            "引用法律条文说明保险金的归属",
            "说明保险合同的财产属性"
        ],
        "keywords": ["避免财产分割", "隔离婚变风险", "避免成为分割焦点", "财产隔离", "规避财产分割"],
        "reason_codes": ["夸大保险财产保护功能", "误导财产分割规避"],
        "suggestion_template": "请删除关于避免财产分割的表述，保险产品不能规避法定财产分割规则。",
        "violation_terms": ["避免财产分割", "隔离婚变风险", "避免成为分割焦点", "财产隔离", "规避财产分割"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["法定受益人", "法律规定", "保险金归属"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品不能规避法定财产分割规则",
        "compliant_case": "保险金按照法定受益人规则归属",
        "violation_basis": "《婚姻法》《保险法》",
        "violation_case": "购买保险可以避免财产分割",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "responsibility_exaggeration",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": ["legal_context"],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    {
        "rule_id": "KB0616",
        "rule_name": "知识库规则-规避债务",
        "risk_level": "high",
        "violation_definition": "宣传保险产品可以规避债务、避债、债务规划，夸大保险的债务保护功能，误导客户认为购买保险可以逃避债务责任",
        "exceptions": [
            "客观说明保险金的法定受益人规则",
            "引用法律条文说明保险金的债务隔离功能",
            "说明保险合同的法律属性"
        ],
        "keywords": ["规避债务", "避债", "债务规划", "逃避债务", "债务隔离"],
        "reason_codes": ["夸大保险债务保护功能", "误导债务规避"],
        "suggestion_template": "请删除关于规避债务的表述，保险产品不能用于逃避债务责任。",
        "violation_terms": ["规避债务", "避债", "逃避债务"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["法定受益人", "法律规定", "债务隔离功能"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品不能用于逃避债务责任",
        "compliant_case": "保险金按照法律规定处理债务关系",
        "violation_basis": "《保险法》《合同法》",
        "violation_case": "购买保险可以规避债务",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "responsibility_exaggeration",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": ["legal_context"],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    # === 3. 收入保障外延类 ===
    {
        "rule_id": "KB0617",
        "rule_name": "知识库规则-保障未来收入",
        "risk_level": "high",
        "violation_definition": "宣传保险产品可以保障未来收入、确保未来收入、锁定未来收入，夸大保险的收入保障功能，超出保险合同约定的保障范围",
        "exceptions": [
            "客观说明年金险的领取规则",
            "说明保险金的给付条件",
            "引用保险合同条款说明保障内容"
        ],
        "keywords": ["保障未来收入", "确保未来收入", "锁定未来收入", "未来收入保障"],
        "reason_codes": ["夸大保险收入保障功能", "超出合同约定范围"],
        "suggestion_template": "请修改为客观说明保险合同约定的保障内容，不要夸大为保障未来收入。",
        "violation_terms": ["保障未来收入", "确保未来收入", "锁定未来收入"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["年金领取", "保险金给付", "合同约定"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品应客观说明合同约定的保障内容",
        "compliant_case": "年金险按照合同约定领取年金",
        "violation_basis": "《保险法》第131条",
        "violation_case": "购买保险可以保障未来收入",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "responsibility_exaggeration",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    {
        "rule_id": "KB0618",
        "rule_name": "知识库规则-收入保障外延",
        "risk_level": "medium",
        "violation_definition": "宣传保险产品可以保障工作收入、保障薪资收入、保障经营收入等超出保险合同约定的收入保障范围，夸大保险的收入保障功能",
        "exceptions": [
            "客观说明失能收入损失险的保障范围",
            "说明保险金的给付条件",
            "引用保险合同条款说明保障内容"
        ],
        "keywords": ["保障工作收入", "保障薪资收入", "保障经营收入", "收入损失保障"],
        "reason_codes": ["夸大保险收入保障功能", "超出合同约定范围"],
        "suggestion_template": "请修改为客观说明保险合同约定的保障内容，不要夸大为保障工作收入。",
        "violation_terms": ["保障工作收入", "保障薪资收入", "保障经营收入"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["失能收入损失险", "保险金给付", "合同约定"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品应客观说明合同约定的保障内容",
        "compliant_case": "失能收入损失险按照合同约定给付保险金",
        "violation_basis": "《保险法》第131条",
        "violation_case": "购买保险可以保障工作收入",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "responsibility_exaggeration",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    # === 4. 综合保障夸大类 ===
    {
        "rule_id": "KB0619",
        "rule_name": "知识库规则-全方位保障",
        "risk_level": "medium",
        "violation_definition": "使用全方位保障、全面保障、360度保障等绝对化表述，夸大保险的保障范围，误导客户认为保险可以覆盖所有风险",
        "exceptions": [
            "客观说明保险产品的多重保障功能",
            "列举具体的保障项目",
            "引用保险合同条款说明保障范围"
        ],
        "keywords": ["全方位保障", "全面保障", "360度保障", "全覆盖"],
        "reason_codes": ["使用绝对化表述", "夸大保障范围"],
        "suggestion_template": "请修改为客观说明保险产品的具体保障项目，避免使用全方位、全面等绝对化表述。",
        "violation_terms": ["全方位保障", "全面保障", "360度保障", "全覆盖"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["多重保障", "具体保障项目", "合同约定"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "保险产品应客观说明具体保障项目，避免绝对化表述",
        "compliant_case": "本产品提供重疾、医疗、意外等多重保障",
        "violation_basis": "《保险法》第131条",
        "violation_case": "本产品提供全方位保障",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "responsibility_exaggeration",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
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

    # 统计 responsibility_exaggeration 类别规则数
    resp_rules = [r for r in rules if r.get("category_group") == "responsibility_exaggeration"]
    print(f"\nresponsibility_exaggeration 类别规则数: {len(resp_rules)} 条")


if __name__ == "__main__":
    main()
