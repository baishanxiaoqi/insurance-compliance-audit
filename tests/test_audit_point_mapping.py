import unittest

from src.moderation.audit_points import (
    build_audit_point_coverage,
    enrich_rule_card,
    load_audit_point_catalog,
)
from src.moderation.complex_classifier import classify_complex_scenario
from src.moderation.schemas import RuleCard
from src.moderation.workflow import load_rule_cards


class TestAuditPointCatalog(unittest.TestCase):
    def test_catalog_loads_all_audit_points(self):
        catalog = load_audit_point_catalog()

        self.assertEqual(len(catalog), 54)
        self.assertIn("1.1.1", catalog)
        self.assertIn("14.1.1", catalog)

    def test_enrich_financial_confusion_rule(self):
        rule = RuleCard(
            rule_id="KB_TEST_FIN",
            rule_name="知识库规则-理财 / 理财产品",
            risk_level="high",
            violation_definition="使用易与银行等金融产品相混淆的表述",
            keywords=["理财", "投资"],
            violation_terms=["理财"],
            category_group="financial_confusion",
        )

        enriched = enrich_rule_card(rule)

        self.assertEqual(enriched.primary_category, "financial_product_confusion")
        self.assertTrue(enriched.audit_point_id.startswith("1."))
        self.assertEqual(enriched.route_hint, "prefer_skill")
        self.assertEqual(classify_complex_scenario(enriched), "financial_confusion")

    def test_enrich_absolute_expression_rule(self):
        rule = RuleCard(
            rule_id="KB_TEST_ABS",
            rule_name="知识库规则-国家级 / 最高级",
            risk_level="high",
            violation_definition="使用第一、最好、最高级等绝对化表述",
            keywords=["第一", "最好"],
            violation_terms=["第一"],
            category_group="absolute_expression",
        )

        enriched = enrich_rule_card(rule)

        self.assertEqual(enriched.primary_category, "absolute_expression")
        self.assertTrue(enriched.audit_point_id.startswith("7."))
        self.assertEqual(classify_complex_scenario(enriched), "comparison_or_absolute")

    def test_build_coverage_matrix_contains_known_mapping(self):
        rule = RuleCard(
            rule_id="KB_TEST_GIFT",
            rule_name="知识库规则-礼品 / 送礼",
            risk_level="high",
            violation_definition="以礼品方式诱导销售",
            keywords=["礼品", "抽奖"],
            violation_terms=["礼品"],
            category_group="gifts_benefits",
        )

        coverage = build_audit_point_coverage({"KB_TEST_GIFT": enrich_rule_card(rule)})

        self.assertIn("6.5.2", coverage)
        self.assertIn("KB_TEST_GIFT", coverage["6.5.2"])

    def test_first_batch_p0_audit_points_are_covered(self):
        cards = load_rule_cards(force_reload=True)
        coverage = build_audit_point_coverage(cards)

        expected_points = {
            "2.2.3",
            "3.5.1",
            "3.6.1",
            "3.8.1",
            "7.1.3",
            "7.1.4",
            "7.2.1",
            "7.3.1",
            "7.5.1",
            "12.1.1",
            "12.2.1",
            "12.4.1",
            "13.4.1",
        }

        missing_points = sorted(point_id for point_id in expected_points if not coverage.get(point_id))
        self.assertEqual(missing_points, [])

    def test_new_bank_comparison_rule_keeps_target_metadata(self):
        cards = load_rule_cards(force_reload=True)
        card = cards["KB0635"]

        self.assertEqual(card.audit_point_id, "3.8.1")
        self.assertEqual(card.primary_category, "guaranteed_return")
        self.assertEqual(card.secondary_category, "relative_bank_return_claim")
        self.assertEqual(card.route_hint, "prefer_skill")


if __name__ == "__main__":
    unittest.main()
