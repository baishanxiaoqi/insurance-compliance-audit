"""
方案3双策略混合架构测试
========================
测试双轨路由、复杂场景识别、Skills 分发等核心功能。
"""

import unittest
from pathlib import Path

from src.moderation.schemas import RuleCard, ChunkFactProfile, FactSignal
from src.moderation.stages.stage1_8_route_dispatch import decide_route, run_stage1_8
from src.moderation.complex_classifier import classify_complex_scenario
from src.moderation.complex_skills import (
    get_complex_skill,
    SKILL_TEMPORAL_CONTEXT,
)
from src.moderation.stages.stage0_preprocess import preprocess


class TestDualStrategyArchitecture(unittest.TestCase):
    """测试双策略混合架构"""

    def test_base_strategy_routing(self):
        """测试简单规则路由到 base 轨"""
        rule = RuleCard(
            rule_id="R_SIMPLE",
            rule_name="简单关键词规则",
            risk_level="low",
            violation_definition="命中关键词即违规",
            keywords=["违规词"],
            violation_terms=["违规词"],
        )

        strategy, reason, skill_type = decide_route(rule)
        self.assertEqual(strategy, "base")
        self.assertIsNone(skill_type)

    def test_skill_strategy_routing(self):
        """测试复杂规则路由到 skill 轨"""
        rule = RuleCard(
            rule_id="R_COMPLEX",
            rule_name="复杂上下文规则",
            risk_level="high",
            violation_definition="需要判断时态和主体",
            keywords=["薪资"],
            violation_terms=["薪资"],
            exceptions=["描述过往经历不算违规"],
            complexity_level="complex",
        )

        strategy, reason, skill_type = decide_route(rule)
        self.assertEqual(strategy, "skill")
        self.assertIsNotNone(skill_type)

    def test_temporal_context_classification(self):
        """测试时态上下文场景识别"""
        rule = RuleCard(
            rule_id="KB_SALARY",
            rule_name="代理人薪资诱导规则",
            risk_level="high",
            violation_definition="用具体收入数字诱导应聘",
            keywords=["薪资", "月薪", "年薪"],
            violation_terms=["薪资"],
        )

        skill_type = classify_complex_scenario(rule)
        self.assertEqual(skill_type, "temporal_context")

    def test_subject_switch_classification(self):
        """测试主体切换场景识别"""
        rule = RuleCard(
            rule_id="KB_SUBJECT",
            rule_name="主体混淆规则",
            risk_level="high",
            violation_definition="混淆代理人和客户的收益",
            keywords=["代理人", "客户"],
            violation_terms=["收益"],
        )

        skill_type = classify_complex_scenario(rule)
        self.assertEqual(skill_type, "subject_switch")

    def test_commitment_strength_classification(self):
        """测试承诺强度场景识别"""
        rule = RuleCard(
            rule_id="KB_COMMIT",
            rule_name="收益承诺规则",
            risk_level="high",
            violation_definition="对收益做确定性承诺",
            keywords=["保证", "承诺", "分红"],
            violation_terms=["保证"],
        )

        skill_type = classify_complex_scenario(rule)
        self.assertEqual(skill_type, "commitment_strength")

    def test_complex_skill_retrieval(self):
        """测试复杂 Skill 获取"""
        skill = get_complex_skill("temporal_context")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "时态上下文判断")
        self.assertGreater(len(skill.few_shots), 0)

    def test_temporal_context_skill_few_shots(self):
        """测试时态上下文 Skill 的 Few-shot 示例"""
        skill = SKILL_TEMPORAL_CONTEXT

        # 验证有正反例
        labels = {fs.label for fs in skill.few_shots}
        self.assertIn("compliant", labels)
        self.assertIn("violation", labels)

        # 验证示例包含关键场景
        snippets = [fs.text_snippet for fs in skill.few_shots]
        has_past_tense = any("之前" in s or "曾经" in s for s in snippets)
        has_current_tense = any("目前" in s or "现在" in s for s in snippets)

        self.assertTrue(has_past_tense, "应包含过往时态示例")
        self.assertTrue(has_current_tense, "应包含当前时态示例")

    def test_route_with_complex_signals(self):
        """测试复杂信号触发 skill 轨"""
        rule = RuleCard(
            rule_id="R_WITH_CONDITION",
            rule_name="条件约束规则",
            risk_level="high",
            violation_definition="需要条件词配合",
            keywords=["退保"],
            violation_terms=["退保"],
            condition_terms=["建议"],
            condition_distance=10,
        )

        # 有复杂信号的 chunk_fact
        chunk_fact = ChunkFactProfile(
            chunk_id="chunk_001",
            signals=[
                FactSignal(label="negation", value="不要", evidence_span_ids=["S_001"]),
                FactSignal(label="time", value="之前", evidence_span_ids=["S_002"]),
            ],
        )

        strategy, reason, skill_type = decide_route(rule, chunk_fact)
        self.assertEqual(strategy, "skill")

    def test_integration_temporal_scenario(self):
        """集成测试：时态场景端到端"""
        # 准备测试文本
        text = "张经理之前在某外企工作，月薪8000元。后来他选择了保险行业。"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST_TEMPORAL")

        # 准备规则
        rule = RuleCard(
            rule_id="KB_SALARY_001",
            rule_name="代理人薪资诱导",
            risk_level="high",
            violation_definition="用具体收入数字诱导应聘",
            keywords=["薪资", "月薪"],
            violation_terms=["月薪"],
            exceptions=["描述加入保险行业之前的其他岗位收入不算违规"],
        )

        # 路由决策
        strategy, reason, skill_type = decide_route(rule)

        # 验证路由到 skill 轨且识别为时态场景
        self.assertEqual(strategy, "skill")
        self.assertEqual(skill_type, "temporal_context")

        # 验证能获取到对应的复杂 Skill
        skill = get_complex_skill(skill_type)
        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "时态上下文判断")


class TestPerformanceOptimization(unittest.TestCase):
    """测试性能优化"""

    def test_base_strategy_no_llm_call(self):
        """验证 base 轨不调用 LLM"""
        from src.moderation.stages.stage2_deep_judge import judge_with_base_strategy
        from src.moderation.stages.stage0_preprocess import preprocess

        text = "这是一个包含免税店的文本"
        doc = preprocess(original_text=text, working_text=text, doc_id="TEST_BASE")

        rule = RuleCard(
            rule_id="R_TAX_FREE",
            rule_name="免税词规则",
            risk_level="high",
            violation_definition="命中免税违规词",
            keywords=["免税"],
            violation_terms=["免税"],
            suffix_no_match=["店"],  # "免税店"不算违规
        )

        # 执行 base 策略（应该很快，无 LLM 调用）
        result = judge_with_base_strategy(
            chunk=doc.chunks[0],
            rule_card=rule,
            document=doc,
        )

        # 验证结果
        self.assertEqual(result.verdict, "compliant")
        self.assertIn("规则引擎判定", result.reasoning_cot)


if __name__ == "__main__":
    unittest.main()
