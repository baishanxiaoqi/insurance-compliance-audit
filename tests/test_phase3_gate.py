"""
测试 Phase 3 轻量 Gate 功能
"""

import unittest
from src.moderation.stages.stage0_preprocess import preprocess
from src.moderation.stages.stage1_5_fact_extract import run_stage1_5
from src.moderation.stages.stage1_9_gate import run_gate, _check_actor_mismatch, _check_time_context, _check_evidence_missing, _check_exception_likely
from src.moderation.schemas import ChunkCandidates, RuleCard, RoutedPair, ChunkFactProfile


class TestPhase3Gate(unittest.TestCase):
    """测试 Phase 3 轻量 Gate"""

    def test_actor_mismatch_detection(self):
        """测试主体不匹配检测"""
        # 创建规则：要求主体是 agent
        rule = RuleCard(
            rule_id="TEST_ACTOR",
            rule_name="测试规则",
            risk_level="high",
            violation_definition="测试",
            exceptions=[],
            keywords=[],
            actor_scope="agent",  # 要求代理人主体
        )

        # 创建文本：只有客户主体
        text = "客户满意度很高，投保人收益稳定。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST")
        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["TEST_ACTOR"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        # 检查主体不匹配
        signal = _check_actor_mismatch(rule, profiles[doc.chunks[0].chunk_id])

        self.assertIsNotNone(signal, "应该检测到主体不匹配")
        self.assertEqual(signal.signal_type, "actor_mismatch")
        self.assertGreater(signal.confidence, 0.5)

    def test_time_context_detection(self):
        """测试时态语境检测"""
        rule = RuleCard(
            rule_id="TEST_TIME",
            rule_name="测试规则",
            risk_level="high",
            violation_definition="测试",
            exceptions=[],
            keywords=[],
        )

        # 创建文本：过去时态 + 第三方主体
        text = "李经理之前在银行工作，月薪3万元。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST")
        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["TEST_TIME"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        # 检查时态语境
        signal = _check_time_context(rule, profiles[doc.chunks[0].chunk_id])

        self.assertIsNotNone(signal, "应该检测到时态语境")
        self.assertEqual(signal.signal_type, "time_context")
        self.assertGreater(signal.confidence, 0.5)

    def test_evidence_missing_detection(self):
        """测试证据缺失检测"""
        # 创建规则：要求证据
        rule = RuleCard(
            rule_id="TEST_EVIDENCE",
            rule_name="测试规则",
            risk_level="high",
            violation_definition="测试",
            exceptions=[],
            keywords=[],
            evidence_required=True,  # 要求证据
        )

        # 创建文本：有需要证据的陈述
        text = "产品收益率高达8%，排名行业第一。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST")
        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["TEST_EVIDENCE"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        # 检查证据缺失
        signal = _check_evidence_missing(rule, profiles[doc.chunks[0].chunk_id])

        self.assertIsNotNone(signal, "应该检测到证据缺失")
        self.assertEqual(signal.signal_type, "evidence_missing")

    def test_exception_likely_detection(self):
        """测试例外可能性检测"""
        rule = RuleCard(
            rule_id="TEST_EXCEPTION",
            rule_name="测试规则",
            risk_level="high",
            violation_definition="测试",
            exceptions=[],
            keywords=[],
        )

        # 创建文本：有否定信号
        text = "不要退保，建议保留原保单。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST")
        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["TEST_EXCEPTION"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        # 检查例外可能性
        signal = _check_exception_likely(rule, profiles[doc.chunks[0].chunk_id])

        self.assertIsNotNone(signal, "应该检测到例外可能性")
        self.assertEqual(signal.signal_type, "exception_likely")

    def test_gate_skip_decision(self):
        """测试 Gate 跳过决策"""
        # 创建规则：要求主体是 agent
        rule = RuleCard(
            rule_id="TEST_SKIP",
            rule_name="测试规则",
            risk_level="high",
            violation_definition="测试",
            exceptions=[],
            keywords=[],
            actor_scope="agent",
        )

        # 创建文本：只有客户主体（高置信度不匹配）
        text = "客户满意度很高。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST")
        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["TEST_SKIP"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        # 运行 Gate
        routed_pairs = [RoutedPair(
            chunk_id=doc.chunks[0].chunk_id,
            rule_id="TEST_SKIP",
            strategy="skill",
            reason="test",
            skill_type=None
        )]

        results = run_gate(
            routed_pairs=routed_pairs,
            rule_cards={"TEST_SKIP": rule},
            chunk_facts=profiles
        )

        self.assertEqual(len(results), 1)
        result = results[0]

        # 验证检测到主体不匹配
        self.assertGreater(len(result.gate_signals), 0)
        self.assertTrue(
            any(sig.signal_type == "actor_mismatch" for sig in result.gate_signals),
            "应该检测到主体不匹配信号"
        )

        # 验证应该跳过（高置信度不匹配）
        self.assertTrue(result.should_skip, "应该标记为跳过")

    def test_gate_priority_assignment(self):
        """测试 Gate 优先级分配"""
        rule = RuleCard(
            rule_id="TEST_PRIORITY",
            rule_name="测试规则",
            risk_level="high",
            violation_definition="测试",
            exceptions=[],
            keywords=[],
        )

        # 场景 1：无信号 -> high priority
        text1 = "这是普通文本。"
        doc1 = preprocess(original_text=text1, working_text=text1, doc_id="TEST1")
        candidates1 = [ChunkCandidates(chunk_id=doc1.chunks[0].chunk_id, candidate_rule_ids=["TEST_PRIORITY"])]
        profiles1 = run_stage1_5(document=doc1, candidates=candidates1)

        routed_pairs1 = [RoutedPair(
            chunk_id=doc1.chunks[0].chunk_id,
            rule_id="TEST_PRIORITY",
            strategy="skill",
            reason="test",
            skill_type=None
        )]

        results1 = run_gate(
            routed_pairs=routed_pairs1,
            rule_cards={"TEST_PRIORITY": rule},
            chunk_facts=profiles1
        )

        self.assertEqual(results1[0].priority, "high", "无信号应该是 high priority")

        # 场景 2：有否定信号 + 中性知识信号 -> low priority（Phase 4 升级后有 2 个信号）
        text2 = "不要退保。"
        doc2 = preprocess(original_text=text2, working_text=text2, doc_id="TEST2")
        candidates2 = [ChunkCandidates(chunk_id=doc2.chunks[0].chunk_id, candidate_rule_ids=["TEST_PRIORITY"])]
        profiles2 = run_stage1_5(document=doc2, candidates=candidates2)

        routed_pairs2 = [RoutedPair(
            chunk_id=doc2.chunks[0].chunk_id,
            rule_id="TEST_PRIORITY",
            strategy="skill",
            reason="test",
            skill_type=None
        )]

        results2 = run_gate(
            routed_pairs=routed_pairs2,
            rule_cards={"TEST_PRIORITY": rule},
            chunk_facts=profiles2
        )

        self.assertEqual(results2[0].priority, "low", "多个信号应该是 low priority")

    def test_rule_plan_generation(self):
        """测试规则计划生成"""
        rule = RuleCard(
            rule_id="TEST_PLAN",
            rule_name="测试规则",
            risk_level="high",
            violation_definition="这是一个很长的违规定义，用于测试规则计划生成功能，确保生成的计划简洁明了。",
            exceptions=[],
            keywords=[],
            actor_scope="agent",
            claim_type="income_promise",
            evidence_required=True,
        )

        text = "代理人收益高。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST")
        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["TEST_PLAN"])]
        profiles = run_stage1_5(document=doc, candidates=candidates)

        routed_pairs = [RoutedPair(
            chunk_id=doc.chunks[0].chunk_id,
            rule_id="TEST_PLAN",
            strategy="skill",
            reason="test",
            skill_type=None
        )]

        results = run_gate(
            routed_pairs=routed_pairs,
            rule_cards={"TEST_PLAN": rule},
            chunk_facts=profiles
        )

        rule_plan = results[0].rule_plan

        # 验证规则计划包含关键信息
        self.assertIn("TEST_PLAN", rule_plan)
        self.assertIn("测试规则", rule_plan)
        self.assertIn("high", rule_plan)
        self.assertIn("agent", rule_plan)
        self.assertIn("income_promise", rule_plan)
        self.assertIn("证据要求", rule_plan)


if __name__ == "__main__":
    unittest.main()
