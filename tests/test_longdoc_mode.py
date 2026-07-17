import unittest

import src.moderation.config as cfg_mod
from src.moderation.schemas import RuleCard
from src.moderation.skills import SKILL_LANGUAGE
from src.moderation.stages.stage0_preprocess import adaptive_split_chunks, preprocess
from src.moderation.stages.stage2_deep_judge import _build_longdoc_context_bundle


class TestLongDocChunking(unittest.TestCase):
    def test_adaptive_split_chunks_respects_explicit_overlap_chars(self):
        text = "AAAAAA111111。BBBBBB222222。CCCCCC333333。"
        chunks = adaptive_split_chunks(
            text,
            max_size=13,
            min_size=4,
            overlap_chars=50,
        )
        self.assertGreaterEqual(len(chunks), 3)
        # 第二块应该携带完整的第一句作为 overlap，而不是仅携带 min_size=4 的尾部
        self.assertTrue(chunks[1][0].startswith("AAAAAA111111。"))
        self.assertIn("\nBBBBBB222222。", chunks[1][0])


class TestLongDocContextBundle(unittest.TestCase):
    def test_context_bundle_contains_prev_and_next_chunks_for_long_docs(self):
        original_threshold = cfg_mod.LONGDOC_THRESHOLD
        original_context_chars = cfg_mod.LONGDOC_CONTEXT_CHARS
        try:
            cfg_mod.LONGDOC_THRESHOLD = 1
            cfg_mod.LONGDOC_CONTEXT_CHARS = 80
            text = (
                "第一段用于介绍背景和主体，这里提供前文信息。"
                "第二段包含当前审核的核心表述，需要结合前后文判断。"
                "第三段补充限制条件和后续解释，用于帮助模型理解边界。"
            )
            doc = preprocess(
                original_text=text,
                working_text=text,
                doc_id="LONGDOC_TEST",
                chunk_size=22,
                chunk_min_size=6,
                chunk_overlap_chars=12,
            )
            self.assertGreaterEqual(len(doc.chunks), 3)
            bundle = _build_longdoc_context_bundle(doc, doc.chunks[1])
            self.assertIsNotNone(bundle)
            self.assertIn("前文审核块摘要", bundle)
            self.assertIn("后文审核块摘要", bundle)
        finally:
            cfg_mod.LONGDOC_THRESHOLD = original_threshold
            cfg_mod.LONGDOC_CONTEXT_CHARS = original_context_chars

    def test_skill_prompt_can_embed_context_bundle(self):
        doc = preprocess(
            original_text="第一段背景。第二段当前判断。第三段补充说明。",
            working_text="第一段背景。第二段当前判断。第三段补充说明。",
            doc_id="PROMPT_LONGDOC",
            chunk_size=8,
            chunk_min_size=4,
            chunk_overlap_chars=8,
        )
        prompt = SKILL_LANGUAGE.build_prompt(
            chunk=doc.chunks[1],
            rule_card=RuleCard(
                rule_id="TEST_LONGDOC_PROMPT",
                rule_name="长文本上下文规则",
                risk_level="high",
                violation_definition="测试长文本上下文块是否进入 prompt",
                keywords=["判断"],
                violation_terms=["判断"],
            ),
            spans_dict=[{"span_id": s.span_id, "span_text": s.span_text} for s in doc.chunks[1].spans],
            context_bundle="前文审核块摘要：第一段背景。\n\n后文审核块摘要：第三段补充说明。",
        )
        self.assertIn("邻近上下文", prompt)
        self.assertIn("前文审核块摘要", prompt)
        self.assertIn("后文审核块摘要", prompt)


if __name__ == "__main__":
    unittest.main()
