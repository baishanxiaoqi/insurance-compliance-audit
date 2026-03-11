import unittest
import json
from pathlib import Path

from src.moderation.schemas import RuleCard
from src.moderation.skills import get_skill_for_rule
from src.moderation.stages.stage0_preprocess import preprocess
from src.moderation.stages.stage1_5_fact_extract import run_stage1_5
from src.moderation.stages.stage1_recall_filter import HybridRetriever
from src.moderation.stages.stage3_assemble import locate_violation_spans
from src.moderation.schemas import JudgmentResult
from src.moderation.schemas import ChunkCandidates
from src.moderation.rule_engine import evaluate_rule_on_text
from src.moderation.stages.stage2_5_refute import run_stage2_5_refute


class TestCoreBehaviors(unittest.TestCase):
    def test_preprocess_keeps_given_doc_id(self):
        text = "测试文本"
        state = preprocess(original_text=text, working_text=text, doc_id="DOC_TEST_001")
        self.assertEqual(state.doc_id, "DOC_TEST_001")

    def test_suffix_no_match_blocks_false_hit(self):
        cards = {
            "R1": RuleCard(
                rule_id="R1",
                rule_name="免税词规则",
                risk_level="high",
                violation_definition="命中免税违规词",
                keywords=["免税"],
                violation_terms=["免税"],
                suffix_no_match=["店"],
            )
        }
        retriever = HybridRetriever(cards)
        result = retriever.recall("这是一家免税店", top_k=5)
        self.assertNotIn("R1", result)

    def test_condition_and_exclusion_terms(self):
        cards = {
            "R2": RuleCard(
                rule_id="R2",
                rule_name="利率条件规则",
                risk_level="high",
                violation_definition="利率+数值条件",
                keywords=["利率", "3.5"],
                violation_terms=["利率"],
                condition_terms=["3.5"],
                condition_distance=6,
            ),
            "R3": RuleCard(
                rule_id="R3",
                rule_name="退保排除规则",
                risk_level="high",
                violation_definition="退保词，含排除词则不违规",
                keywords=["退保", "不要"],
                violation_terms=["退保"],
                exclusion_terms=["不要"],
            ),
        }
        retriever = HybridRetriever(cards)

        # 条件词满足 -> 命中
        result_hit = retriever.recall("该产品利率3.5可参考", top_k=5)
        self.assertIn("R2", result_hit)

        # 条件词不满足 -> 不命中
        result_miss = retriever.recall("该产品利率较高", top_k=5)
        self.assertNotIn("R2", result_miss)

        # 排除词与违规词同时出现 -> 排除
        result_excluded = retriever.recall("请不要退保", top_k=5)
        self.assertNotIn("R3", result_excluded)

    def test_rule_cards_keywords_primary_only(self):
        rule_cards_path = Path("data/rule_cards.json")
        self.assertTrue(rule_cards_path.exists())

        data = json.loads(rule_cards_path.read_text(encoding="utf-8"))
        self.assertGreater(len(data), 0)

        for rule in data:
            keywords = rule.get("keywords", [])
            condition_terms = set(rule.get("condition_terms", []))
            exclusion_terms = set(rule.get("exclusion_terms", []))

            self.assertEqual(len(keywords), 1, f"规则 {rule.get('rule_id')} 的 keywords 不是单关键词")
            self.assertNotIn(keywords[0], condition_terms, f"规则 {rule.get('rule_id')} 的关键词错误来自条件词")
            self.assertNotIn(keywords[0], exclusion_terms, f"规则 {rule.get('rule_id')} 的关键词错误来自排除词")

    def test_skill_auto_route_for_kb_rules(self):
        rule = RuleCard(
            rule_id="KB9999",
            rule_name="知识库规则-退保 / 减保",
            risk_level="high",
            violation_definition="宣传退保减保并引导客户转保",
            keywords=["退保"],
            violation_terms=["退保"],
            exclusion_terms=["谨慎考虑"],
        )
        skill = get_skill_for_rule(rule)
        self.assertEqual(skill.name, "消费者保护检测")

    def test_stage3_localization_span_only(self):
        text = "我们建议您退保后转购新的方案"
        doc = preprocess(original_text=text, working_text=text, doc_id="DOC_LOC_001")
        target_span = None
        for span in doc.span_pool.values():
            if "退保" in span.span_text:
                target_span = span
                break

        self.assertIsNotNone(target_span)

        judgment = JudgmentResult(
            rule_id="KB0061",
            chunk_id=target_span.chunk_id,
            verdict="violation",
            reasoning_cot="该表述直接建议客户退保并转购，属于诱导退保，违反规则。",
            evidence_span_ids=[target_span.span_id],
            evidence_texts=["一个不存在的片段"],
            reason_codes=["RC_KB0061"],
            draft_suggestion="建议删除诱导退保表述。",
        )

        locations = locate_violation_spans(judgment, doc)
        self.assertGreater(len(locations), 0)
        self.assertIn("退保", locations[0].original_text_slice)

    def test_stage15_fact_extract_signals(self):
        text = "我们建议您不要退保，收益保证8%以上"
        doc = preprocess(original_text=text, working_text=text, doc_id="DOC_FACT_001")
        candidates = [ChunkCandidates(chunk_id=doc.chunks[0].chunk_id, candidate_rule_ids=["KB0061"])]
        profiles = run_stage1_5(doc, candidates)

        self.assertIn(doc.chunks[0].chunk_id, profiles)
        signals = profiles[doc.chunks[0].chunk_id].signals
        labels = {s.label for s in signals}

        self.assertIn("action", labels)
        self.assertIn("negation", labels)
        self.assertIn("certainty", labels)
        self.assertIn("number_percent", labels)

    def test_rule_engine_hard_block_no_violation_hit(self):
        rule = RuleCard(
            rule_id="R_NO_HIT",
            rule_name="无命中规则",
            risk_level="high",
            violation_definition="命中退保",
            keywords=["退保"],
            violation_terms=["退保"],
        )
        report = evaluate_rule_on_text("这里没有相关词", rule)
        self.assertTrue(report.hard_block)
        self.assertFalse(report.has_violation_hit)

    def test_rule_engine_condition_and_exclusion(self):
        rule = RuleCard(
            rule_id="R_COMPLEX",
            rule_name="条件排除规则",
            risk_level="high",
            violation_definition="退保+建议，排除不要",
            keywords=["退保"],
            violation_terms=["退保"],
            condition_terms=["建议"],
            condition_distance=6,
            exclusion_terms=["不要"],
            exclusion_distance=6,
        )

        # 条件不满足 -> 阻断
        report_miss = evaluate_rule_on_text("请您退保", rule)
        self.assertTrue(report_miss.hard_block)
        self.assertFalse(report_miss.condition_pass)

        # 命中排除词 -> 阻断
        report_excl = evaluate_rule_on_text("建议不要退保", rule)
        self.assertTrue(report_excl.hard_block)
        self.assertTrue(report_excl.exclusion_blocked)

        # 条件满足且无排除词 -> 通过
        report_ok = evaluate_rule_on_text("建议您退保后转购", rule)
        self.assertFalse(report_ok.hard_block)
        self.assertTrue(report_ok.condition_pass)

    def test_stage25_refute_negated_violation(self):
        text = "请不要退保，建议保留原保单"
        doc = preprocess(original_text=text, working_text=text, doc_id="DOC_REFUTE_001")
        rule = RuleCard(
            rule_id="KB0061",
            rule_name="知识库规则-退保 / 减保",
            risk_level="high",
            violation_definition="出现退保词且引导退保视为违规",
            keywords=["退保"],
            violation_terms=["退保"],
            reason_codes=["RC_KB0061"],
        )
        judgments = [
            JudgmentResult(
                rule_id="KB0061",
                chunk_id=doc.chunks[0].chunk_id,
                verdict="violation",
                reasoning_cot="初判为违规。",
                evidence_span_ids=[doc.chunks[0].spans[0].span_id],
                evidence_texts=["退保"],
                reason_codes=["RC_KB0061"],
                draft_suggestion="建议修改",
            )
        ]

        revised = run_stage2_5_refute(
            judgments=judgments,
            document=doc,
            rule_cards={"KB0061": rule},
            chunk_facts=None,
        )

        self.assertEqual(len(revised), 1)
        self.assertEqual(revised[0].verdict, "compliant")


if __name__ == "__main__":
    unittest.main()
