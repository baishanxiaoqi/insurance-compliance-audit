"""
测试 OCR 检测策略
==================
验证 OCR 检测不会误判正常文本
"""

import unittest
from src.moderation.ocr_preprocessor import detect_text_source, fix_ocr_spacing


class TestOCRDetection(unittest.TestCase):
    """测试 OCR 检测策略"""

    def test_normal_single_line_not_detected_as_ocr(self):
        """测试：正常的单行文本不应被误判为 OCR"""
        text = "这是普通的一行营销文案，没有换行，但并不是OCR文本。"
        result = detect_text_source(text)
        self.assertEqual(result, "normal", "正常单行文本不应被误判为 OCR")

    def test_normal_short_paragraph_not_detected_as_ocr(self):
        """测试：正常的短段落不应被误判为 OCR"""
        text = "第一段。第二段。第三段。"
        result = detect_text_source(text)
        self.assertEqual(result, "normal", "正常短段落不应被误判为 OCR")

    def test_normal_multiline_text_detected_as_normal(self):
        """测试：正常的多行文本应被识别为 normal"""
        text = """这是第一段文本。
这是第二段文本。
这是第三段文本。"""
        result = detect_text_source(text)
        self.assertEqual(result, "normal", "正常多行文本应被识别为 normal")

    def test_ocr_text_with_no_newlines_and_long(self):
        """测试：无换行且超长且标点少的文本应被识别为 OCR"""
        # 构造一个超过 500 字符、无换行、标点少的文本（模拟真实 OCR 场景）
        text = "保险产品介绍包括保障范围理赔流程投保须知等内容" * 20  # 约 600 字符，无标点
        result = detect_text_source(text)
        self.assertEqual(result, "ocr", "无换行且超长且标点少的文本应被识别为 OCR")

    def test_ocr_text_with_abnormal_spaces(self):
        """测试：中文间有大量异常空格的文本应被识别为 OCR"""
        # 构造一个有大量中文间空格的长文本
        text = "保 险 产 品 收 益 稳 健 " * 30  # 约 360 字符，空格比例 > 20%
        result = detect_text_source(text)
        self.assertEqual(result, "ocr", "中文间有大量异常空格的文本应被识别为 OCR")

    def test_ocr_text_with_table_markers(self):
        """测试：有表格痕迹的文本应被识别为 OCR"""
        text = "产品名称    保费    保额    期限\n产品A    1000元    10万    20年" * 10
        result = detect_text_source(text)
        self.assertEqual(result, "ocr", "有表格痕迹的文本应被识别为 OCR")

    def test_short_text_always_normal(self):
        """测试：短文本（<50 字符）默认为 normal"""
        text = "短文本"
        result = detect_text_source(text)
        self.assertEqual(result, "normal", "短文本应默认为 normal")

    def test_fix_ocr_spacing_converges(self):
        """测试：中文间空格修复能够收敛"""
        text = "保 险 产 品 收 益 稳 健，预期年化3%。"
        fixed = fix_ocr_spacing(text)
        # 应该完全移除中文间的空格
        self.assertEqual(fixed, "保险产品收益稳健，预期年化3%。")

    def test_fix_ocr_spacing_handles_multiple_spaces(self):
        """测试：处理多个连续空格"""
        text = "保险  产品   收益"
        fixed = fix_ocr_spacing(text)
        # 多个空格应该被移除
        self.assertEqual(fixed, "保险产品收益")


if __name__ == "__main__":
    unittest.main()
