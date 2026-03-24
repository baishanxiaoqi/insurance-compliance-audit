import unittest
from unittest.mock import AsyncMock, patch

from benchmark.scorers.score_results import score_record
from src.moderation import config
from src.moderation.schemas import JudgmentResult, RuleCard, SuggestionResult
from src.moderation.stages.stage0_preprocess import preprocess
from src.moderation.stages.stage2_deep_judge import _refine_violation_evidence
from src.moderation.stages.stage3_assemble import assemble_violations
from src.moderation.stages.stage2_7_suggestion import run_stage2_7_suggestion


class TestEvidenceRefinement(unittest.TestCase):
    def test_refine_violation_evidence_keeps_stronger_anchor_span(self):
        text = "保险作为一种金融产品，其价值在于它能提供财务保障和风险管理功能。"
        doc = preprocess(original_text=text, working_text=text, doc_id="EVIDENCE_TEST")
        chunk = doc.chunks[0]
        rule = RuleCard(
            rule_id="KB0017",
            rule_name="知识库规则-本金 / 计息",
            risk_level="high",
            violation_definition="直接宣传保险产品具备投资理财功能，或与其他金融产品混淆。",
            keywords=["本金"],
            violation_terms=["本金", "存款", "投资", "理财"],
        )
        judgment = JudgmentResult(
            rule_id="KB0017",
            chunk_id=chunk.chunk_id,
            verdict="violation",
            reasoning_cot="测试判定",
            evidence_span_ids=[chunk.spans[0].span_id, chunk.spans[1].span_id],
            evidence_texts=["保险作为一种金融产品，其价值在于它能提供财务保障和风险管理功能。"],
            reason_codes=["RC_KB0017"],
        )

        refined = _refine_violation_evidence(judgment, chunk, rule)

        self.assertEqual(refined.evidence_span_ids, [chunk.spans[0].span_id])
        self.assertEqual(refined.evidence_texts, ["保险作为一种金融产品"])


class TestStructuredOutputAndBenchmark(unittest.TestCase):
    def test_stage3_propagates_structured_fields(self):
        text = "这是最好的保险产品。"
        doc = preprocess(original_text=text, working_text=text, doc_id="OUTPUT_TEST")
        span = doc.chunks[0].spans[0]
        rule = RuleCard(
            rule_id="KB_TEST",
            rule_name="绝对化用语规则",
            risk_level="high",
            violation_definition="禁止使用最好等绝对化用语",
            keywords=["最好"],
            violation_terms=["最好"],
            reason_codes=["RC_TEST"],
            audit_point_id="7.1.1",
            audit_point_name="极限词汇滥用",
            primary_category="absolute_expression",
            secondary_category="superlative_claim",
        )
        judgment = JudgmentResult(
            rule_id="KB_TEST",
            chunk_id=span.chunk_id,
            verdict="violation",
            reasoning_cot="测试判定",
            evidence_span_ids=[span.span_id],
            evidence_texts=["最好的保险产品"],
            reason_codes=["RC_TEST"],
            decision_basis="explicit_violation",
            primary_category="comparison_or_absolute",
            secondary_category="absolute_product_claim",
        )
        suggestions = {
            f"{span.chunk_id}_KB_TEST": SuggestionResult(
                rule_id="KB_TEST",
                chunk_id=span.chunk_id,
                suggestion="请删除绝对化表述。",
                suggestion_type="delete",
            )
        }

        violations = assemble_violations([judgment], doc, {"KB_TEST": rule}, suggestions)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].decision_basis, "explicit_violation")
        self.assertEqual(violations[0].primary_category, "comparison_or_absolute")
        self.assertEqual(violations[0].secondary_category, "absolute_product_claim")
        self.assertEqual(violations[0].suggestion_type, "delete")
        self.assertEqual(violations[0].audit_point_id, "7.1.1")
        self.assertEqual(violations[0].audit_point_name, "极限词汇滥用")

    def test_benchmark_prefers_structured_categories(self):
        scored = score_record(
            {
                "sample_id": "sample_001",
                "label": "violation",
                "predicted_verdict": "violation",
                "predicted_rule_ids": ["KB_TEST"],
                "predicted_audit_point_ids": ["7.1.1"],
                "predicted_location_slices": ["最好的保险产品"],
                "expected_categories": ["comparison_or_absolute"],
                "expected_audit_point_id": "7.1.1",
                "expected_text_slices": ["最好的保险产品"],
                "response": {
                    "violations": [
                        {
                            "primary_category": "comparison_or_absolute",
                            "secondary_category": "absolute_product_claim",
                        }
                    ]
                },
            }
        )

        self.assertEqual(scored["predicted_categories"], ["comparison_or_absolute", "absolute_product_claim"])
        self.assertTrue(scored["category_hit"])
        self.assertTrue(scored["audit_point_hit"])


class TestSuggestionRenderer(unittest.IsolatedAsyncioTestCase):
    async def test_stage27_can_use_independent_suggestion_model(self):
        judgment = JudgmentResult(
            rule_id="KB_TEST",
            chunk_id="chunk_001",
            verdict="violation",
            reasoning_cot="测试判定",
            evidence_span_ids=["S_chunk_001_01"],
            evidence_texts=["最好的保险产品"],
            reason_codes=["RC_TEST"],
        )
        rule = RuleCard(
            rule_id="KB_TEST",
            rule_name="绝对化用语规则",
            risk_level="high",
            violation_definition="禁止使用最好等绝对化用语",
            keywords=["最好"],
            violation_terms=["最好"],
            suggestion_template="请删除绝对化表述。",
        )
        rendered = AsyncMock(return_value=type(
            "Rendered",
            (),
            {"suggestion": "建议将“最好”改为客观描述。", "suggestion_type": "weaken"},
        )())

        with patch.object(config, "SUGGESTION_USE_LLM_RENDERER", True), \
             patch("src.moderation.stages.stage2_7_suggestion.safe_arun", rendered), \
             patch("src.moderation.stages.stage2_7_suggestion.create_agent"), \
             patch("src.moderation.stages.stage2_7_suggestion.config.is_model_profile_configured", return_value=True):
            suggestions = await run_stage2_7_suggestion([judgment], {"KB_TEST": rule})

        result = suggestions["chunk_001_KB_TEST"]
        self.assertEqual(result.suggestion, "建议将“最好”改为客观描述。")
        self.assertEqual(result.suggestion_type, "weaken")


if __name__ == "__main__":
    unittest.main()
