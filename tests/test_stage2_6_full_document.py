"""
Stage 2.6 单元测试：全文数据引用信号提取（纯代码部分）
"""
import unittest

from src.moderation.stages.stage0_preprocess import preprocess
from src.moderation.stages.stage2_6_full_document import (
    extract_document_audit_signals,
    get_fulldoc_rule_cards,
    FULLDOC_RULE_ID_THIRD_PARTY_SOURCE,
)


class TestStage26SignalExtraction(unittest.TestCase):

    def _make_doc(self, text: str):
        return preprocess(original_text=text, working_text=text, doc_id="test")

    def test_no_data_citation(self):
        """无任何数据引用时，has_data_citation 为 False"""
        doc = self._make_doc("我们的产品保障全面，适合家庭投保。")
        signals = extract_document_audit_signals(doc)
        self.assertFalse(signals["has_data_citation"])
        self.assertEqual(signals["missing_source_span_ids"], [])

    def test_data_citation_with_source(self):
        """有数据引用且紧邻有来源说明时，missing_source_span_ids 为空"""
        text = "本产品连续三年排名行业第一（数据来源：XX研究院2025年报告）。"
        doc = self._make_doc(text)
        signals = extract_document_audit_signals(doc)
        # 有数据引用
        self.assertTrue(signals["has_data_citation"])
        # 有来源说明
        self.assertTrue(signals["has_source_indicators"])
        # 所有数据引用均有来源，missing 为空
        self.assertEqual(signals["missing_source_span_ids"], [])

    def test_data_citation_without_source(self):
        """有数据引用但无来源说明时，missing_source_span_ids 非空"""
        text = "本产品保费收入同比增长35%，在行业中排名第二。"
        doc = self._make_doc(text)
        signals = extract_document_audit_signals(doc)
        self.assertTrue(signals["has_data_citation"])
        self.assertGreater(len(signals["missing_source_span_ids"]), 0)
        # 缺失的 span_id 都在 span_pool 中
        for sid in signals["missing_source_span_ids"]:
            self.assertIn(sid, doc.span_pool)

    def test_percent_pattern_detected(self):
        """百分比数字应触发数据引用检测"""
        text = "客户满意度达到98.5%，远超行业均值。"
        doc = self._make_doc(text)
        signals = extract_document_audit_signals(doc)
        self.assertTrue(signals["has_data_citation"])

    def test_fulldoc_rule_card_registered(self):
        """get_fulldoc_rule_cards 返回有效的规则卡片"""
        cards = get_fulldoc_rule_cards()
        self.assertIn(FULLDOC_RULE_ID_THIRD_PARTY_SOURCE, cards)
        rc = cards[FULLDOC_RULE_ID_THIRD_PARTY_SOURCE]
        self.assertEqual(rc.rule_id, FULLDOC_RULE_ID_THIRD_PARTY_SOURCE)
        self.assertEqual(rc.risk_level, "medium")
        self.assertNotEqual(rc.suggestion_template, "")


if __name__ == "__main__":
    unittest.main()
