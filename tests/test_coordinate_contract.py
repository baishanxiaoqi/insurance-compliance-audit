"""
测试原文坐标契约
================
验证当文本经过 OCR 预处理后，最终返回的坐标仍然对应用户输入的原始文本。
"""

import unittest
from src.moderation.stages.stage0_preprocess import preprocess
from src.moderation.schemas import JudgmentResult
from src.moderation.stages.stage3_assemble import locate_violation_spans


class TestCoordinateContract(unittest.TestCase):
    """测试原文坐标契约"""

    def test_coordinate_mapping_with_identical_texts(self):
        """测试：当 original_text 和 working_text 相同时，坐标映射正确"""
        original_text = "这是一段测试文本，包含违规内容。"
        working_text = original_text  # 完全相同

        doc = preprocess(
            original_text=original_text,
            working_text=working_text,
            doc_id="TEST_IDENTICAL"
        )

        # 验证 original_text 保存正确
        self.assertEqual(doc.original_text, original_text)
        self.assertEqual(doc.working_text, working_text)

        # 找到包含"违规"的 span
        target_span = None
        for span in doc.span_pool.values():
            if "违规" in span.span_text:
                target_span = span
                break

        self.assertIsNotNone(target_span, "应该找到包含'违规'的 span")

        # 模拟 Stage 2 判定结果
        judgment = JudgmentResult(
            rule_id="TEST_RULE",
            chunk_id=target_span.chunk_id,
            verdict="violation",
            reasoning_cot="测试判定",
            evidence_span_ids=[target_span.span_id],
            evidence_texts=["违规"],
            reason_codes=["TEST"],
        )

        # Stage 3 定位
        locations = locate_violation_spans(judgment, doc)

        self.assertGreater(len(locations), 0, "应该有定位结果")
        location = locations[0]

        # 验证坐标对应原文
        extracted = doc.original_text[location.raw_start:location.raw_end]
        self.assertIn("违规", extracted, f"提取的文本应包含'违规'，实际为: {extracted}")

    def test_coordinate_mapping_with_ocr_modified_text(self):
        """测试：当 working_text 是 OCR 修复后的版本时，坐标仍映射回原文"""
        # 模拟 OCR 场景：原文是单行，OCR 修复后添加了换行
        original_text = "第一段。第二段。第三段。"
        working_text = "第一段。\n第二段。\n第三段。\n"  # OCR 修复后

        doc = preprocess(
            original_text=original_text,
            working_text=working_text,
            doc_id="TEST_OCR"
        )

        # 验证两个文本都正确保存
        self.assertEqual(doc.original_text, original_text)
        self.assertEqual(doc.working_text, working_text)

        # 找到包含"第二段"的 span
        target_span = None
        for span in doc.span_pool.values():
            if "第二段" in span.span_text:
                target_span = span
                break

        self.assertIsNotNone(target_span, "应该找到包含'第二段'的 span")

        # 模拟 Stage 2 判定结果
        judgment = JudgmentResult(
            rule_id="TEST_RULE",
            chunk_id=target_span.chunk_id,
            verdict="violation",
            reasoning_cot="测试判定",
            evidence_span_ids=[target_span.span_id],
            evidence_texts=["第二段"],
            reason_codes=["TEST"],
        )

        # Stage 3 定位
        locations = locate_violation_spans(judgment, doc)

        self.assertGreater(len(locations), 0, "应该有定位结果")
        location = locations[0]

        # 关键验证：坐标应该对应原文，而不是 working_text
        extracted = doc.original_text[location.raw_start:location.raw_end]
        self.assertIn("第二段", extracted, f"提取的文本应包含'第二段'，实际为: {extracted}")

        # 验证提取的文本确实来自原文（不包含 OCR 添加的换行）
        self.assertNotIn("\n", extracted, "从原文提取的片段不应包含 OCR 添加的换行符")

    def test_coordinate_mapping_preserves_original_text(self):
        """测试：original_text 字段始终保存用户真正的输入"""
        user_input = "用户输入的原始文本"
        ocr_modified = "用户输入的原始文本\n"  # OCR 可能添加换行

        doc = preprocess(
            original_text=user_input,
            working_text=ocr_modified,
            doc_id="TEST_PRESERVE"
        )

        # 核心验证：original_text 必须等于用户输入
        self.assertEqual(doc.original_text, user_input)
        self.assertNotEqual(doc.original_text, ocr_modified)

        # working_text 应该是 OCR 修复后的版本
        self.assertEqual(doc.working_text, ocr_modified)

    def test_multiple_newlines_insertion_mapping(self):
        """测试：多个连续换行插入的坐标映射"""
        original_text = "第一段。第二段。"
        working_text = "第一段。\n\n第二段。"  # 插入了两个换行

        doc = preprocess(
            original_text=original_text,
            working_text=working_text,
            doc_id="TEST_MULTI_NEWLINES"
        )

        # 找到包含"第二段"的 span
        target_span = None
        for span in doc.span_pool.values():
            if "第二段" in span.span_text:
                target_span = span
                break

        self.assertIsNotNone(target_span, "应该找到包含'第二段'的 span")

        # 模拟 Stage 2 判定结果
        judgment = JudgmentResult(
            rule_id="TEST_RULE",
            chunk_id=target_span.chunk_id,
            verdict="violation",
            reasoning_cot="测试判定",
            evidence_span_ids=[target_span.span_id],
            evidence_texts=["第二段"],
            reason_codes=["TEST"],
        )

        # Stage 3 定位
        locations = locate_violation_spans(judgment, doc)

        self.assertGreater(len(locations), 0, "应该有定位结果")
        location = locations[0]

        # 验证坐标对应原文
        extracted = doc.original_text[location.raw_start:location.raw_end]
        self.assertIn("第二段", extracted, f"多个换行插入后，提取的文本应包含'第二段'，实际为: {extracted}")

    def test_mixed_insertion_deletion_mapping(self):
        """测试：混合插入和删除的坐标映射"""
        original_text = "第一段。  第二段。"  # 有两个空格
        working_text = "第一段。\n第二段。"   # 空格被换行替换

        doc = preprocess(
            original_text=original_text,
            working_text=working_text,
            doc_id="TEST_MIXED"
        )

        # 找到包含"第二段"的 span
        target_span = None
        for span in doc.span_pool.values():
            if "第二段" in span.span_text:
                target_span = span
                break

        self.assertIsNotNone(target_span, "应该找到包含'第二段'的 span")

        # 模拟 Stage 2 判定结果
        judgment = JudgmentResult(
            rule_id="TEST_RULE",
            chunk_id=target_span.chunk_id,
            verdict="violation",
            reasoning_cot="测试判定",
            evidence_span_ids=[target_span.span_id],
            evidence_texts=["第二段"],
            reason_codes=["TEST"],
        )

        # Stage 3 定位
        locations = locate_violation_spans(judgment, doc)

        self.assertGreater(len(locations), 0, "应该有定位结果")
        location = locations[0]

        # 验证坐标对应原文
        extracted = doc.original_text[location.raw_start:location.raw_end]
        self.assertIn("第二段", extracted, f"混合修改后，提取的文本应包含'第二段'，实际为: {extracted}")


if __name__ == "__main__":
    unittest.main()
