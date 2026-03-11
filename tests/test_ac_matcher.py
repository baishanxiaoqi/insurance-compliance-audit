"""
测试 AC 自动机匹配器
"""

import pytest
from src.moderation.ac_matcher import AhocorasickMatcher


class TestAhocorasickMatcher:
    """测试 AC 自动机的基本功能"""

    def test_basic_matching(self):
        """测试基本的多模式匹配"""
        matcher = AhocorasickMatcher(["保证", "承诺", "收益"])
        text = "我们保证高收益，承诺不会亏损"

        result = matcher.find_all(text)

        assert "保证" in result
        assert "收益" in result
        assert "承诺" in result
        assert len(result["保证"]) == 1
        assert len(result["收益"]) == 1
        assert len(result["承诺"]) == 1

    def test_case_insensitive(self):
        """测试大小写不敏感匹配"""
        matcher = AhocorasickMatcher(["ABC", "xyz"])
        text = "This is abc and XYZ test"

        result = matcher.find_all(text)

        assert "ABC" in result
        assert "xyz" in result

    def test_overlapping_matches(self):
        """测试重叠匹配"""
        matcher = AhocorasickMatcher(["保证", "保证金"])
        text = "需要缴纳保证金"

        result = matcher.find_all(text)

        # 应该同时匹配到 "保证" 和 "保证金"
        assert "保证" in result
        assert "保证金" in result

    def test_multiple_occurrences(self):
        """测试同一词汇的多次出现"""
        matcher = AhocorasickMatcher(["保证"])
        text = "我们保证质量，保证服务，保证满意"

        result = matcher.find_all(text)

        assert "保证" in result
        assert len(result["保证"]) == 3

    def test_find_positions(self):
        """测试单个词汇的位置查找"""
        matcher = AhocorasickMatcher(["保证", "收益"])
        text = "保证高收益"

        positions = matcher.find_positions(text, "保证")

        assert positions == [0]

    def test_has_match(self):
        """测试快速匹配检测"""
        matcher = AhocorasickMatcher(["保证", "承诺"])

        assert matcher.has_match("我们保证质量")
        assert matcher.has_match("我们承诺服务")
        assert not matcher.has_match("这是普通文本")

    def test_get_matched_terms(self):
        """测试获取匹配的词汇集合"""
        matcher = AhocorasickMatcher(["保证", "承诺", "收益"])
        text = "我们保证高收益"

        matched = matcher.get_matched_terms(text)

        assert matched == {"保证", "收益"}
        assert "承诺" not in matched

    def test_empty_terms(self):
        """测试空词汇列表"""
        matcher = AhocorasickMatcher([])
        text = "任意文本"

        result = matcher.find_all(text)

        assert result == {}
        assert not matcher.has_match(text)

    def test_empty_text(self):
        """测试空文本"""
        matcher = AhocorasickMatcher(["保证"])

        result = matcher.find_all("")

        assert result == {}

    def test_chinese_characters(self):
        """测试中文字符匹配"""
        matcher = AhocorasickMatcher(["免税", "退保", "误导"])
        text = "不要退保，避免误导，免税店除外"

        result = matcher.find_all(text)

        assert "退保" in result
        assert "误导" in result
        assert "免税" in result

    def test_term_count(self):
        """测试词汇数量统计"""
        matcher = AhocorasickMatcher(["保证", "承诺", "收益"])

        assert matcher.term_count == 3

    def test_filter_empty_strings(self):
        """测试过滤空字符串"""
        matcher = AhocorasickMatcher(["保证", "", "承诺", None, "收益"])

        # 空字符串和 None 应该被过滤掉
        assert matcher.term_count == 3
