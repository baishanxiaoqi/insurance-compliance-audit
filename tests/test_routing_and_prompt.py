import unittest

from src.moderation.rule_engine import RuleEvalReport
from src.moderation.schemas import RuleCard
from src.moderation.skills import SKILL_LANGUAGE, get_skill_for_rule
from src.moderation.stages.stage0_preprocess import preprocess
from src.moderation.stages.stage1_8_route_dispatch import decide_route
from src.moderation.stages.stage2_deep_judge import _select_prompt_deterministic_report


class TestRoutingOptimization(unittest.TestCase):
    def test_inferred_complex_rule_routes_to_skill(self):
        rule = RuleCard(
            rule_id="TEST_ABSOLUTE",
            rule_name="绝对化用语规则",
            risk_level="high",
            violation_definition="禁止使用第一、最好等绝对化用语",
            keywords=["最好", "第一"],
            violation_terms=["最好"],
        )

        strategy, reason, skill_type = decide_route(rule)

        self.assertEqual(strategy, "skill")
        self.assertEqual(reason, "inferred_complex_skill")
        self.assertEqual(skill_type, "comparison_or_absolute")

    def test_structured_simple_rule_routes_to_base(self):
        rule = RuleCard(
            rule_id="TEST_STRUCTURED",
            rule_name="条件约束规则",
            risk_level="high",
            violation_definition="命中退保且带建议时违规",
            keywords=["退保"],
            violation_terms=["退保"],
            condition_terms=["建议"],
            condition_distance=10,
        )

        strategy, reason, skill_type = decide_route(rule)

        self.assertEqual(strategy, "base")
        self.assertEqual(reason, "rule_complexity=simple")
        self.assertIsNone(skill_type)

    def test_financial_confusion_rule_routes_to_dedicated_skill(self):
        rule = RuleCard(
            rule_id="TEST_FINANCIAL",
            rule_name="理财 / 存款 混淆规则",
            risk_level="high",
            violation_definition="将保险直接描述为理财或存款",
            keywords=["理财", "存款"],
            violation_terms=["理财"],
            category_group="financial_confusion",
        )

        strategy, reason, skill_type = decide_route(rule)

        self.assertEqual(strategy, "skill")
        self.assertEqual(reason, "inferred_complex_skill")
        self.assertEqual(skill_type, "financial_confusion")

    def test_route_hint_prefer_base_is_honored(self):
        rule = RuleCard(
            rule_id="TEST_HINT",
            rule_name="带 base hint 的规则",
            risk_level="high",
            violation_definition="测试规则",
            keywords=["收益"],
            violation_terms=["收益"],
            route_hint="prefer_base",
        )

        strategy, reason, skill_type = decide_route(rule)

        self.assertEqual(strategy, "base")
        self.assertEqual(reason, "rule_route_hint=prefer_base")
        self.assertIsNone(skill_type)

    def test_reimbursement_rule_prefers_consumer_skill_over_default(self):
        rule = RuleCard(
            rule_id="TEST_REIMBURSE",
            rule_name="知识库规则-报销 / 实报实销",
            risk_level="high",
            violation_definition="介绍商业保险产品过程中使用报销表述",
            keywords=["报销"],
            violation_terms=["报销", "实报实销"],
            exclusion_terms=["社保", "医保"],
        )

        skill = get_skill_for_rule(rule)

        self.assertEqual(skill.name, "消费者保护检测")


class TestPromptOptimization(unittest.TestCase):
    def test_prompt_emphasizes_direct_violation_priority(self):
        doc = preprocess(
            original_text="这是最好的保险产品。",
            working_text="这是最好的保险产品。",
            doc_id="PROMPT_TEST",
        )
        rule = RuleCard(
            rule_id="TEST_PROMPT",
            rule_name="绝对化用语规则",
            risk_level="high",
            violation_definition="禁止使用最好等绝对化用语直接夸大保险产品",
            keywords=["最好"],
            violation_terms=["最好"],
        )
        report = RuleEvalReport(
            rule_id=rule.rule_id,
            has_violation_hit=True,
            violation_positions={"最好": [2]},
            summary="命中违规词",
        )

        prompt = SKILL_LANGUAGE.build_prompt(
            chunk=doc.chunks[0],
            rule_card=rule,
            spans_dict=[{"span_id": s.span_id, "span_text": s.span_text} for s in doc.chunks[0].spans],
            deterministic_report=report,
        )

        self.assertIn("裁决优先级", prompt)
        self.assertIn("不要因为前置规则引擎未命中就默认 compliant", prompt)
        self.assertIn("仅辅助参考，不得替代最终判断", prompt)

    def test_non_hit_deterministic_report_is_not_used_for_prompt(self):
        report = RuleEvalReport(
            rule_id="TEST_RULE",
            has_violation_hit=False,
            hard_block=True,
            summary="无有效违规词命中（或被前后缀不匹配规则过滤）",
        )

        selected = _select_prompt_deterministic_report(report)

        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
