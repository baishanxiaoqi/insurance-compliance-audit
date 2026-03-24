#!/usr/bin/env python3
"""
补充 gifts_benefits 类别规则

根据 smoke 报告 FN-3 分析，补充以下知识簇：
1. 惊喜/心意类（情感化委婉表达）
2. 温馨服务类（服务包装式利益）
3. 小物品类（实物委婉表达）
4. 定制晚宴/高端体检类（高端服务利益）
5. 感谢/答谢类（回馈式利益）
"""

import json
from typing import List, Dict

# 新增规则定义
NEW_RULES: List[Dict] = [
    # === 1. 惊喜/心意类 ===
    {
        "rule_id": "KB0625",
        "rule_name": "知识库规则-惊喜/心意",
        "risk_level": "high",
        "violation_definition": "宣传代理人会给客户准备惊喜、送心意、表达心意，暗示会给予客户保险合同外的利益，以此吸引客户购买保险",
        "exceptions": [
            "客观说明保险公司的客户服务",
            "说明保险合同约定的服务内容",
            "节日祝福等纯情感表达（不涉及实物或服务）"
        ],
        "keywords": ["惊喜", "心意", "小心意", "准备惊喜", "送心意"],
        "reason_codes": ["暗示合同外利益", "不当销售诱导"],
        "suggestion_template": "请删除关于惊喜、心意的表述，不应暗示给予客户保险合同外的利益。",
        "violation_terms": ["惊喜", "心意", "小心意", "准备惊喜", "送心意"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["节日祝福", "情感表达", "客户服务", "合同约定"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "不应暗示给予客户保险合同外的利益",
        "compliant_case": "祝您节日快乐（纯情感表达）",
        "violation_basis": "《保险法》第116条",
        "violation_case": "我会给您准备一份小惊喜",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "gifts_benefits",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    # === 2. 温馨服务类 ===
    {
        "rule_id": "KB0626",
        "rule_name": "知识库规则-温馨服务",
        "risk_level": "high",
        "violation_definition": "宣传代理人会提供温馨服务、贴心服务、专属服务等超出保险合同约定的额外服务，暗示会给予客户保险合同外的利益",
        "exceptions": [
            "客观说明保险公司的标准客户服务",
            "说明保险合同约定的服务内容",
            "说明保险理赔服务流程"
        ],
        "keywords": ["温馨服务", "贴心服务", "专属服务", "暖心服务"],
        "reason_codes": ["暗示合同外利益", "夸大服务承诺"],
        "suggestion_template": "请删除关于温馨服务的表述，或修改为客观说明保险公司的标准客户服务。",
        "violation_terms": ["温馨服务", "贴心服务", "专属服务", "暖心服务"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["标准客户服务", "合同约定", "理赔服务", "保险公司"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "不应暗示给予客户保险合同外的服务",
        "compliant_case": "保险公司提供标准的客户服务",
        "violation_basis": "《保险法》第116条",
        "violation_case": "我会为您提供温馨服务",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "gifts_benefits",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    # === 3. 小物品类 ===
    {
        "rule_id": "KB0627",
        "rule_name": "知识库规则-小物品/小礼物",
        "risk_level": "high",
        "violation_definition": "宣传代理人会送客户小物品、小礼物、小东西，暗示会给予客户保险合同外的实物利益，以此吸引客户购买保险",
        "exceptions": [
            "客观说明保险公司的营销活动",
            "说明保险合同约定的权益"
        ],
        "keywords": ["小物品", "小礼物", "小东西", "小礼品"],
        "reason_codes": ["暗示合同外利益", "不当销售诱导"],
        "suggestion_template": "请删除关于小物品、小礼物的表述，不应暗示给予客户保险合同外的利益。",
        "violation_terms": ["小物品", "小礼物", "小东西", "小礼品"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["营销活动", "合同约定", "保险公司"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "不应暗示给予客户保险合同外的利益",
        "compliant_case": "保险公司开展的营销活动",
        "violation_basis": "《保险法》第116条",
        "violation_case": "我会送您一些小物品",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "gifts_benefits",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    # === 4. 定制晚宴类 ===
    {
        "rule_id": "KB0628",
        "rule_name": "知识库规则-定制晚宴/高端宴请",
        "risk_level": "high",
        "violation_definition": "宣传代理人会为客户安排定制晚宴、高端宴请、私人晚宴等高端餐饮服务，暗示会给予客户保险合同外的高价值利益",
        "exceptions": [
            "客观说明保险公司的客户活动",
            "说明保险公司组织的合规客户联谊活动"
        ],
        "keywords": ["定制晚宴", "高端宴请", "私人晚宴", "专属晚宴"],
        "reason_codes": ["暗示合同外利益", "不当销售诱导"],
        "suggestion_template": "请删除关于定制晚宴的表述，不应暗示给予客户保险合同外的利益。",
        "violation_terms": ["定制晚宴", "高端宴请", "私人晚宴", "专属晚宴"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["客户活动", "客户联谊", "保险公司组织"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "不应暗示给予客户保险合同外的利益",
        "compliant_case": "保险公司组织的客户联谊活动",
        "violation_basis": "《保险法》第116条",
        "violation_case": "我会为您安排定制晚宴",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "gifts_benefits",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    # === 5. 高端体检类 ===
    {
        "rule_id": "KB0629",
        "rule_name": "知识库规则-高端体检/专属体检",
        "risk_level": "high",
        "violation_definition": "宣传代理人会为客户安排高端体检、专属体检、VIP体检等医疗服务，暗示会给予客户保险合同外的高价值利益",
        "exceptions": [
            "客观说明保险公司的客户权益",
            "说明保险合同约定的体检服务",
            "说明保险公司提供的合规增值服务"
        ],
        "keywords": ["高端体检", "专属体检", "VIP体检", "定制体检"],
        "reason_codes": ["暗示合同外利益", "不当销售诱导"],
        "suggestion_template": "请删除关于高端体检的表述，或修改为客观说明保险合同约定的体检服务。",
        "violation_terms": ["高端体检", "专属体检", "VIP体检", "定制体检"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["客户权益", "合同约定", "增值服务", "保险公司提供"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "不应暗示给予客户保险合同外的利益",
        "compliant_case": "保险合同约定的体检服务",
        "violation_basis": "《保险法》第116条",
        "violation_case": "我会为您安排高端体检",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "gifts_benefits",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    # === 6. 感谢/答谢类 ===
    {
        "rule_id": "KB0630",
        "rule_name": "知识库规则-感谢礼/答谢礼",
        "risk_level": "medium",
        "violation_definition": "宣传代理人会送客户感谢礼、答谢礼、回馈礼，暗示会给予客户保险合同外的利益，以此吸引客户购买保险或获得转介绍",
        "exceptions": [
            "纯情感表达的感谢（不涉及实物或服务）",
            "客观说明保险公司的营销活动"
        ],
        "keywords": ["感谢礼", "答谢礼", "回馈礼", "感谢回馈"],
        "reason_codes": ["暗示合同外利益", "不当销售诱导"],
        "suggestion_template": "请删除关于感谢礼、答谢礼的表述，不应暗示给予客户保险合同外的利益。",
        "violation_terms": ["感谢礼", "答谢礼", "回馈礼"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["感谢您的信任", "营销活动", "保险公司"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "不应暗示给予客户保险合同外的利益",
        "compliant_case": "感谢您的信任（纯情感表达）",
        "violation_basis": "《保险法》第116条",
        "violation_case": "我会送您一份感谢礼",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "gifts_benefits",
        "actor_scope": "agent",
        "claim_type": "other",
        "exception_group": [],
        "evidence_required": False,
        "route_hint": "prefer_base",
        "mutual_exclusion_group": None
    },

    # === 7. 礼遇/回馈类 ===
    {
        "rule_id": "KB0631",
        "rule_name": "知识库规则-客户礼遇/专属礼遇",
        "risk_level": "medium",
        "violation_definition": "宣传代理人会提供客户礼遇、专属礼遇、VIP礼遇等超出保险合同约定的额外权益，暗示会给予客户保险合同外的利益",
        "exceptions": [
            "客观说明保险公司的客户权益体系",
            "说明保险合同约定的权益内容"
        ],
        "keywords": ["客户礼遇", "专属礼遇", "VIP礼遇", "尊享礼遇"],
        "reason_codes": ["暗示合同外利益", "夸大权益承诺"],
        "suggestion_template": "请删除关于客户礼遇的表述，或修改为客观说明保险合同约定的权益内容。",
        "violation_terms": ["客户礼遇", "专属礼遇", "VIP礼遇", "尊享礼遇"],
        "condition_terms": [],
        "condition_distance": None,
        "exclusion_terms": ["客户权益体系", "合同约定", "保险公司"],
        "exclusion_distance": 20,
        "prefix_no_match": [],
        "suffix_no_match": [],
        "compliant_basis": "不应暗示给予客户保险合同外的利益",
        "compliant_case": "保险合同约定的客户权益",
        "violation_basis": "《保险法》第116条",
        "violation_case": "我会为您提供专属礼遇",
        "complexity_level": "simple",
        "route_strategy": "auto",
        "category_group": "gifts_benefits",
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

    # 统计 gifts_benefits 类别规则数
    gifts_rules = [r for r in rules if r.get("category_group") == "gifts_benefits"]
    print(f"\ngifts_benefits 类别规则数: {len(gifts_rules)} 条")


if __name__ == "__main__":
    main()
