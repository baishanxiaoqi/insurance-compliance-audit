"""
测试 Phase 4 升级功能
====================
测试新增的 7 个 Skill 和 3 个 Gate 检查
"""

import unittest
from src.moderation.complex_skills import (
    SKILL_GIFTS_OR_EXTRA_BENEFITS,
    SKILL_AGENT_TITLE_OR_RECRUITMENT,
    SKILL_NATIONAL_OR_REGULATORY_ENDORSEMENT,
    SKILL_TAX_OR_LAW_MISINTERPRETATION,
    SKILL_TRANSFER_OR_INHERITANCE,
    SKILL_GUARANTEED_RETURN,
    SKILL_COMPARISON_OR_ABSOLUTE,
    get_complex_skill,
)
from src.moderation.complex_classifier import classify_complex_scenario
from src.moderation.schemas import RuleCard, ChunkFactProfile, FactSignal, RoutedPair
from src.moderation.stages.stage1_9_gate import (
    _check_non_marketing_absolute,
    _check_sufficient_disclaimer,
    _check_neutral_vs_sales,
    run_gate,
)


class TestPhase4Skills(unittest.TestCase):
    """测试新增的 7 个 Skill"""

    def test_gifts_or_extra_benefits_skill_exists(self):
        """测试合同外利益 Skill 存在"""
        self.assertIsNotNone(SKILL_GIFTS_OR_EXTRA_BENEFITS)
        self.assertEqual(SKILL_GIFTS_OR_EXTRA_BENEFITS.name, "合同外利益识别")

    def test_agent_title_or_recruitment_skill_exists(self):
        """测试招募代理人误导头衔 Skill 存在"""
        self.assertIsNotNone(SKILL_AGENT_TITLE_OR_RECRUITMENT)
        self.assertEqual(SKILL_AGENT_TITLE_OR_RECRUITMENT.name, "招募代理人误导头衔识别")

    def test_national_or_regulatory_endorsement_skill_exists(self):
        """测试监管背书/国家背书 Skill 存在"""
        self.assertIsNotNone(SKILL_NATIONAL_OR_REGULATORY_ENDORSEMENT)
        self.assertEqual(SKILL_NATIONAL_OR_REGULATORY_ENDORSEMENT.name, "监管背书/国家背书识别")

    def test_tax_or_law_misinterpretation_skill_exists(self):
        """测试税法/法律误导 Skill 存在"""
        self.assertIsNotNone(SKILL_TAX_OR_LAW_MISINTERPRETATION)
        self.assertEqual(SKILL_TAX_OR_LAW_MISINTERPRETATION.name, "税法/法律误导识别")

    def test_transfer_or_inheritance_skill_exists(self):
        """测试传承/资产转移类误导 Skill 存在"""
        self.assertIsNotNone(SKILL_TRANSFER_OR_INHERITANCE)
        self.assertEqual(SKILL_TRANSFER_OR_INHERITANCE.name, "传承/资产转移类误导识别")

    def test_guaranteed_return_skill_exists(self):
        """测试收益承诺/稳定收益暗示 Skill 存在"""
        self.assertIsNotNone(SKILL_GUARANTEED_RETURN)
        self.assertEqual(SKILL_GUARANTEED_RETURN.name, "收益承诺/稳定收益暗示识别")

    def test_comparison_or_absolute_skill_exists(self):
        """测试简单对比/绝对化 Skill 存在"""
        self.assertIsNotNone(SKILL_COMPARISON_OR_ABSOLUTE)
        self.assertEqual(SKILL_COMPARISON_OR_ABSOLUTE.name, "简单对比/绝对化识别")

    def test_get_complex_skill_mapping(self):
        """测试 get_complex_skill 函数映射"""
        self.assertEqual(
            get_complex_skill("gifts_or_extra_benefits"),
            SKILL_GIFTS_OR_EXTRA_BENEFITS
        )
        self.assertEqual(
            get_complex_skill("agent_title_or_recruitment"),
            SKILL_AGENT_TITLE_OR_RECRUITMENT
        )
        self.assertEqual(
            get_complex_skill("national_or_regulatory_endorsement"),
            SKILL_NATIONAL_OR_REGULATORY_ENDORSEMENT
        )
        self.assertEqual(
            get_complex_skill("tax_or_law_misinterpretation"),
            SKILL_TAX_OR_LAW_MISINTERPRETATION
        )
        self.assertEqual(
            get_complex_skill("transfer_or_inheritance"),
            SKILL_TRANSFER_OR_INHERITANCE
        )
        self.assertEqual(
            get_complex_skill("guaranteed_return"),
            SKILL_GUARANTEED_RETURN
        )
        self.assertEqual(
            get_complex_skill("comparison_or_absolute"),
            SKILL_COMPARISON_OR_ABSOLUTE
        )


class TestPhase4Classifier(unittest.TestCase):
    """测试复杂场景分类器对新 Skill 的识别"""

    def test_classify_gifts_or_extra_benefits(self):
        """测试识别合同外利益场景"""
        rule = RuleCard(
            rule_id="TEST_GIFTS",
            rule_name="合同外利益测试",
            risk_level="high",
            violation_definition="禁止赠送礼品",
            exceptions=[],
            keywords=["赠送", "礼品"],
        )
        self.assertEqual(classify_complex_scenario(rule), "gifts_or_extra_benefits")

    def test_classify_agent_title_or_recruitment(self):
        """测试识别招募代理人误导头衔场景"""
        rule = RuleCard(
            rule_id="TEST_RECRUITMENT",
            rule_name="招募代理人测试",
            risk_level="high",
            violation_definition="禁止使用金融理财顾问头衔",
            exceptions=[],
            keywords=["招募", "金融理财顾问"],
        )
        self.assertEqual(classify_complex_scenario(rule), "agent_title_or_recruitment")

    def test_classify_national_or_regulatory_endorsement(self):
        """测试识别监管背书场景"""
        rule = RuleCard(
            rule_id="TEST_ENDORSEMENT",
            rule_name="监管背书测试",
            risk_level="high",
            violation_definition="禁止使用国家政策背书",
            exceptions=[],
            keywords=["监管背书", "国家政策"],
        )
        self.assertEqual(classify_complex_scenario(rule), "national_or_regulatory_endorsement")

    def test_classify_tax_or_law_misinterpretation(self):
        """测试识别税法/法律误导场景"""
        rule = RuleCard(
            rule_id="TEST_TAX",
            rule_name="税法误导测试",
            risk_level="high",
            violation_definition="禁止片面宣传避税",
            exceptions=[],
            keywords=["避税", "税法"],
        )
        self.assertEqual(classify_complex_scenario(rule), "tax_or_law_misinterpretation")

    def test_classify_transfer_or_inheritance(self):
        """测试识别传承/资产转移场景"""
        rule = RuleCard(
            rule_id="TEST_TRANSFER",
            rule_name="财富传承测试",
            risk_level="high",
            violation_definition="禁止夸大财富传承功能",
            exceptions=[],
            keywords=["财富传承", "资产转移"],
        )
        self.assertEqual(classify_complex_scenario(rule), "transfer_or_inheritance")

    def test_classify_guaranteed_return(self):
        """测试识别收益承诺场景"""
        rule = RuleCard(
            rule_id="TEST_RETURN",
            rule_name="收益承诺测试",
            risk_level="high",
            violation_definition="禁止承诺稳定收益",
            exceptions=[],
            keywords=["稳定收益", "保证收益"],
        )
        self.assertEqual(classify_complex_scenario(rule), "guaranteed_return")

    def test_classify_comparison_or_absolute(self):
        """测试识别简单对比/绝对化场景"""
        rule = RuleCard(
            rule_id="TEST_ABSOLUTE",
            rule_name="绝对化用语测试",
            risk_level="high",
            violation_definition="禁止使用最好等绝对化用语",
            exceptions=[],
            keywords=["最好", "绝对化"],
        )
        self.assertEqual(classify_complex_scenario(rule), "comparison_or_absolute")


class TestPhase4Gates(unittest.TestCase):
    """测试新增的 3 个 Gate 检查"""

    def test_non_marketing_absolute_detection(self):
        """测试非营销绝对化检测"""
        rule = RuleCard(
            rule_id="TEST_ABSOLUTE",
            rule_name="绝对化测试",
            risk_level="high",
            violation_definition="测试",
            exceptions=[],
            keywords=[],
            claim_type="ranking_claim",
        )

        # 场景 1：历史语境（过去时态 + 第三方主体）
        chunk_fact = ChunkFactProfile(
            chunk_id="test_chunk",
            signals=[
                FactSignal(label="time_past", value="之前", span_id="s1"),
                FactSignal(label="actor_third_party", value="银行", span_id="s2"),
            ],
            summary="time_past: 之前; actor_third_party: 银行"
        )

        signal = _check_non_marketing_absolute(rule, chunk_fact)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "non_marketing_absolute")
        self.assertGreaterEqual(signal.confidence, 0.7)

    def test_sufficient_disclaimer_detection(self):
        """测试充分提示语检测"""
        rule = RuleCard(
            rule_id="TEST_SURRENDER",
            rule_name="减保测试",
            risk_level="high",
            violation_definition="减保风险提示",
            exceptions=[],
            keywords=[],
            claim_type="surrender_guidance",  # 修正：使用正确的枚举值
        )

        # 场景：包含充分的减保提示语
        chunk_fact = ChunkFactProfile(
            chunk_id="test_chunk",
            signals=[
                FactSignal(label="action", value="降低保障额度", span_id="s1"),
                FactSignal(label="action", value="影响现金价值", span_id="s2"),
                FactSignal(label="action", value="谨慎选择", span_id="s3"),
            ],
            summary="action: 降低保障额度/影响现金价值/谨慎选择"
        )

        signal = _check_sufficient_disclaimer(rule, chunk_fact)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "sufficient_disclaimer")
        self.assertGreaterEqual(signal.confidence, 0.7)

    def test_neutral_vs_sales_detection(self):
        """测试中性知识 vs 销售话术检测"""
        # 场景 1：中性知识说明
        chunk_fact_neutral = ChunkFactProfile(
            chunk_id="test_chunk",
            signals=[
                FactSignal(label="action", value="介绍功能", span_id="s1"),
                FactSignal(label="action", value="说明规则", span_id="s2"),
            ],
            summary="action: 介绍功能/说明规则"
        )

        signal = _check_neutral_vs_sales(None, chunk_fact_neutral)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "neutral_knowledge")

        # 场景 2：销售话术
        chunk_fact_sales = ChunkFactProfile(
            chunk_id="test_chunk",
            signals=[
                FactSignal(label="action", value="诱导购买", span_id="s1"),
                FactSignal(label="action", value="优势夸大", span_id="s2"),
            ],
            summary="action: 诱导购买/优势夸大"
        )

        signal = _check_neutral_vs_sales(None, chunk_fact_sales)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "sales_pitch")

    def test_gate_integration(self):
        """测试 Gate 集成（包含新增的 3 个检查）"""
        rule = RuleCard(
            rule_id="TEST_GATE",
            rule_name="测试规则",
            risk_level="high",
            violation_definition="测试",
            exceptions=[],
            keywords=[],
            claim_type="ranking_claim",
        )

        chunk_fact = ChunkFactProfile(
            chunk_id="test_chunk",
            signals=[
                FactSignal(label="time_past", value="之前", span_id="s1"),
                FactSignal(label="actor_third_party", value="银行", span_id="s2"),
            ],
            summary="time_past: 之前; actor_third_party: 银行"
        )

        routed_pairs = [RoutedPair(
            chunk_id="test_chunk",
            rule_id="TEST_GATE",
            strategy="skill",
            reason="test",
            skill_type=None
        )]

        results = run_gate(
            routed_pairs=routed_pairs,
            rule_cards={"TEST_GATE": rule},
            chunk_facts={"test_chunk": chunk_fact}
        )

        self.assertEqual(len(results), 1)
        result = results[0]

        # 验证检测到非营销绝对化信号
        self.assertGreater(len(result.gate_signals), 0)
        has_non_marketing_signal = any(
            sig.signal_type == "non_marketing_absolute"
            for sig in result.gate_signals
        )
        self.assertTrue(has_non_marketing_signal, "应该检测到非营销绝对化信号")


if __name__ == "__main__":
    unittest.main()
