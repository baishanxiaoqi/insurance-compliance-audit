"""
测试 Stage 1 缓存机制
====================
验证缓存键的正确性和失效机制
"""

import unittest
from src.moderation.stage1_cache import (
    _compute_rules_hash,
    get_cached_retriever,
    clear_cache
)
from src.moderation.schemas import RuleCard


class TestStage1Cache(unittest.TestCase):
    """测试 Stage 1 缓存机制"""

    def setUp(self):
        """每个测试前清空缓存"""
        clear_cache()

    def test_cache_key_changes_when_rule_content_changes(self):
        """测试：规则内容变化时，缓存键应该变化"""
        # 创建两个内容不同但 rule_id 相同的规则
        rule1 = RuleCard(
            rule_id="R001",
            rule_name="退保规则",
            risk_level="high",
            violation_definition="禁止承诺退保",
            keywords=["退保"],
            violation_terms=["退保"],
            condition_terms=[],
            exclusion_terms=[]
        )

        rule2 = RuleCard(
            rule_id="R001",
            rule_name="收益规则",
            risk_level="high",
            violation_definition="禁止承诺收益",
            keywords=["收益"],
            violation_terms=["收益"],
            condition_terms=[],
            exclusion_terms=[]
        )

        rules_v1 = {"R001": rule1}
        rules_v2 = {"R001": rule2}

        hash1 = _compute_rules_hash(rules_v1)
        hash2 = _compute_rules_hash(rules_v2)

        # 核心断言：规则内容变了，hash 应该不同
        self.assertNotEqual(hash1, hash2, "规则内容变化时，缓存键应该变化")

    def test_cache_key_same_when_rule_content_same(self):
        """测试：规则内容相同时，缓存键应该相同"""
        rule1 = RuleCard(
            rule_id="R001",
            rule_name="退保规则",
            risk_level="high",
            violation_definition="禁止承诺退保",
            keywords=["退保"],
            violation_terms=["退保"],
            condition_terms=[],
            exclusion_terms=[]
        )

        rule2 = RuleCard(
            rule_id="R001",
            rule_name="退保规则",
            risk_level="high",
            violation_definition="禁止承诺退保",
            keywords=["退保"],
            violation_terms=["退保"],
            condition_terms=[],
            exclusion_terms=[]
        )

        rules_v1 = {"R001": rule1}
        rules_v2 = {"R001": rule2}

        hash1 = _compute_rules_hash(rules_v1)
        hash2 = _compute_rules_hash(rules_v2)

        # 规则内容相同，hash 应该相同
        self.assertEqual(hash1, hash2, "规则内容相同时，缓存键应该相同")

    def test_retriever_cache_invalidates_on_content_change(self):
        """测试：规则内容变化时，retriever 缓存应该失效"""
        rule1 = RuleCard(
            rule_id="R001",
            rule_name="退保规则",
            risk_level="high",
            violation_definition="禁止承诺退保",
            keywords=["退保"],
            violation_terms=["退保"],
            condition_terms=[],
            exclusion_terms=[]
        )

        rule2 = RuleCard(
            rule_id="R001",
            rule_name="收益规则",
            risk_level="high",
            violation_definition="禁止承诺收益",
            keywords=["收益"],
            violation_terms=["收益"],
            condition_terms=[],
            exclusion_terms=[]
        )

        rules_v1 = {"R001": rule1}
        rules_v2 = {"R001": rule2}

        # 获取第一个 retriever
        retriever1 = get_cached_retriever(rules_v1)

        # 获取第二个 retriever（规则内容变了）
        retriever2 = get_cached_retriever(rules_v2)

        # 应该是不同的对象（缓存失效，重新创建）
        self.assertIsNot(retriever1, retriever2, "规则内容变化时，应该创建新的 retriever")

    def test_retriever_cache_reuses_on_same_content(self):
        """测试：规则内容相同时，retriever 缓存应该复用"""
        rule1 = RuleCard(
            rule_id="R001",
            rule_name="退保规则",
            risk_level="high",
            violation_definition="禁止承诺退保",
            keywords=["退保"],
            violation_terms=["退保"],
            condition_terms=[],
            exclusion_terms=[]
        )

        rules_v1 = {"R001": rule1}
        rules_v2 = {"R001": rule1}  # 同一个对象

        # 获取两次 retriever
        retriever1 = get_cached_retriever(rules_v1)
        retriever2 = get_cached_retriever(rules_v2)

        # 应该是同一个对象（缓存命中）
        self.assertIs(retriever1, retriever2, "规则内容相同时，应该复用缓存的 retriever")


if __name__ == "__main__":
    unittest.main()
