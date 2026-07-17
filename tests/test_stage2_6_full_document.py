"""
Stage 2.6 单元测试：全文数据引用信号提取（纯代码部分）
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import src.moderation.config as cfg_mod
from src.moderation.schemas import JudgmentResult
from src.moderation.stages.stage0_preprocess import preprocess
from src.moderation.stages.stage2_6_full_document import (
    _build_fulldoc_prompt,
    _call_fulldoc_llm,
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

    def test_fulldoc_prompt_uses_full_text_when_under_limit(self):
        text = "本产品保费收入同比增长35%，在行业中排名第二，数据来源见文末。"
        doc = self._make_doc(text)
        prompt = _build_fulldoc_prompt(doc, ["S_chunk_000_00"])
        self.assertIn("【全文文本】", prompt)
        self.assertIn(text, prompt)

    def test_fulldoc_prompt_keeps_tail_source_excerpt_when_text_is_long(self):
        original_limit = cfg_mod.FULLDOC_INLINE_TEXT_LIMIT
        original_window = cfg_mod.FULLDOC_CONTEXT_WINDOW
        try:
            cfg_mod.FULLDOC_INLINE_TEXT_LIMIT = 120
            cfg_mod.FULLDOC_CONTEXT_WINDOW = 40
            text = (
                "本产品保费收入同比增长35%，在行业中排名第二。"
                + "这是一段背景说明。" * 40
                + "数据来源：XX研究院2025年度保险行业报告。"
            )
            doc = self._make_doc(text)
            prompt = _build_fulldoc_prompt(doc, ["S_chunk_000_00"])
            self.assertIn("【全文相关片段包】", prompt)
            self.assertIn("数据来源：XX研究院2025年度保险行业报告", prompt)
        finally:
            cfg_mod.FULLDOC_INLINE_TEXT_LIMIT = original_limit
            cfg_mod.FULLDOC_CONTEXT_WINDOW = original_window

    def test_call_fulldoc_llm_accepts_structured_result_and_fills_defaults(self):
        doc = self._make_doc("本产品保费收入同比增长35%，在行业中排名第二。")
        fake_agent = MagicMock()
        fake_result = JudgmentResult(
            rule_id="TEMP",
            chunk_id="TEMP",
            verdict="violation",
            reasoning_cot="文本引用了行业排名和增长数据，但未说明数据来源，属于缺少来源的第三方数据引用。",
            evidence_span_ids=[],
            evidence_texts=[],
            reason_codes=[],
        )
        with patch(
            "src.moderation.stages.stage2_6_full_document.create_agent",
            return_value=fake_agent,
        ) as mocked_create_agent, patch(
            "src.moderation.stages.stage2_6_full_document.safe_arun",
            new=AsyncMock(return_value=fake_result),
        ):
            async def _run():
                return await _call_fulldoc_llm(doc, ["S_chunk_000_00"])
            result = asyncio.run(_run())

        mocked_create_agent.assert_called_once()
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_id, FULLDOC_RULE_ID_THIRD_PARTY_SOURCE)
        self.assertEqual(result.chunk_id, "__fulldoc__")
        self.assertEqual(result.decision_basis, "insufficient_evidence")
        self.assertGreater(len(result.evidence_span_ids), 0)
        self.assertGreater(len(result.evidence_texts), 0)
        self.assertEqual(result.primary_category, "data_citation")
        self.assertEqual(result.secondary_category, "missing_third_party_source")

    def test_call_fulldoc_llm_overrides_model_categories_to_canonical_values(self):
        doc = self._make_doc("某机构研究显示，超过82%的家庭更重视养老安全感。")
        fake_agent = MagicMock()
        fake_result = JudgmentResult(
            rule_id="TEMP",
            chunk_id="TEMP",
            verdict="violation",
            reasoning_cot="引用了外部统计数据但未标明来源。",
            evidence_span_ids=["S_chunk_000_00"],
            evidence_texts=["超过82%的家庭更重视养老安全感"],
            reason_codes=["MISSING_SOURCE"],
            primary_category="data_compliance",
            secondary_category="unverified_statistics",
        )
        with patch(
            "src.moderation.stages.stage2_6_full_document.create_agent",
            return_value=fake_agent,
        ), patch(
            "src.moderation.stages.stage2_6_full_document.safe_arun",
            new=AsyncMock(return_value=fake_result),
        ):
            async def _run():
                return await _call_fulldoc_llm(doc, ["S_chunk_000_00"])
            result = asyncio.run(_run())

        self.assertIsNotNone(result)
        self.assertEqual(result.primary_category, "data_citation")
        self.assertEqual(result.secondary_category, "missing_third_party_source")

    def test_call_fulldoc_llm_uses_fulldoc_profile_instead_of_judge_profile(self):
        doc = self._make_doc("某机构研究显示，超过82%的家庭更重视养老安全感。")
        fake_agent = MagicMock()
        fake_result = JudgmentResult(
            rule_id="TEMP",
            chunk_id="TEMP",
            verdict="compliant",
            reasoning_cot="数据已有来源或不构成外部可验证引用。",
            evidence_span_ids=[],
            evidence_texts=[],
            reason_codes=[],
        )
        with patch(
            "src.moderation.stages.stage2_6_full_document.create_agent",
            return_value=fake_agent,
        ) as mocked_create_agent, patch(
            "src.moderation.stages.stage2_6_full_document.safe_arun",
            new=AsyncMock(return_value=fake_result),
        ) as mocked_safe_arun:
            async def _run():
                return await _call_fulldoc_llm(doc, ["S_chunk_000_00"])
            asyncio.run(_run())

        self.assertEqual(
            mocked_create_agent.call_args.kwargs["profile"],
            cfg_mod.FULLDOC_MODEL_PROFILE,
        )
        self.assertEqual(
            mocked_safe_arun.call_args.kwargs["max_retries"],
            cfg_mod.FULLDOC_MODEL_PROFILE.max_retries,
        )
        self.assertEqual(
            mocked_safe_arun.call_args.kwargs["timeout_seconds"],
            cfg_mod.FULLDOC_MODEL_PROFILE.timeout_seconds,
        )


if __name__ == "__main__":
    unittest.main()
