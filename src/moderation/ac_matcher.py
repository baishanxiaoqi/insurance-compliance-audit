"""
AC自动机封装
============
基于 pyahocorasick 实现的多模式字符串匹配器，用于替换正则表达式匹配。

性能优势：
- 一次扫描匹配所有模式（vs N次正则匹配）
- 时间复杂度 O(n + m)，n=文本长度，m=匹配数量
- 对于1000+个模式，比正则快10-50倍

接口兼容性：
- 提供与 _find_positions() 完全兼容的接口
- 支持大小写不敏感匹配
- 返回所有匹配位置的起始索引
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set

try:
    import ahocorasick
    HAS_AHOCORASICK = True
except ImportError:
    HAS_AHOCORASICK = False
    import re


class AhocorasickMatcher:
    """
    AC自动机封装，提供高效的多模式字符串匹配。

    特性：
    - 大小写不敏感
    - 一次扫描匹配所有模式
    - 返回所有匹配位置
    - 自动回退到正则（如果 pyahocorasick 未安装）
    """

    def __init__(self, terms: List[str], term_to_rules: Dict[str, List[str]] = None):
        """
        构建AC自动机。

        Args:
            terms: 要匹配的词汇列表
            term_to_rules: 词汇到规则ID的映射（可选，用于调试）
        """
        self.terms = [t for t in terms if t]  # 过滤空字符串
        self.term_to_rules = term_to_rules or {}
        self.use_ac = HAS_AHOCORASICK and len(self.terms) > 0

        if self.use_ac:
            self._build_automaton()
        else:
            # 回退到正则匹配
            self._regex_patterns = {term: re.compile(re.escape(term), re.IGNORECASE) for term in self.terms}

    def _build_automaton(self):
        """构建AC自动机（大小写不敏感）"""
        self.automaton = ahocorasick.Automaton()

        # 添加所有模式（转小写）
        for term in self.terms:
            term_lower = term.lower()
            # 存储原始term作为payload，用于后续查找
            self.automaton.add_word(term_lower, term)

        # 构建失败指针
        self.automaton.make_automaton()

    def find_all(self, text: str) -> Dict[str, List[int]]:
        """
        在文本中查找所有匹配的词汇及其位置。

        Args:
            text: 待匹配文本

        Returns:
            {term: [positions]} 字典，positions 是匹配位置的起始索引列表
        """
        if not text:
            return {}

        if self.use_ac:
            return self._find_all_ac(text)
        else:
            return self._find_all_regex(text)

    def _find_all_ac(self, text: str) -> Dict[str, List[int]]:
        """使用AC自动机查找所有匹配"""
        result: Dict[str, List[int]] = defaultdict(list)
        text_lower = text.lower()

        # AC自动机返回 (end_index, original_term)
        for end_index, original_term in self.automaton.iter(text_lower):
            # 计算起始位置
            start_index = end_index - len(original_term) + 1
            result[original_term].append(start_index)

        return dict(result)

    def _find_all_regex(self, text: str) -> Dict[str, List[int]]:
        """使用正则表达式查找所有匹配（回退方案）"""
        result: Dict[str, List[int]] = {}

        for term, pattern in self._regex_patterns.items():
            positions = [m.start() for m in pattern.finditer(text)]
            if positions:
                result[term] = positions

        return result

    def find_positions(self, text: str, term: str) -> List[int]:
        """
        查找单个词汇的所有匹配位置（兼容接口）。

        Args:
            text: 待匹配文本
            term: 要查找的词汇

        Returns:
            匹配位置的起始索引列表
        """
        if not term or not text:
            return []

        all_matches = self.find_all(text)
        return all_matches.get(term, [])

    def has_match(self, text: str) -> bool:
        """检查文本中是否有任何匹配"""
        if not text:
            return False

        if self.use_ac:
            text_lower = text.lower()
            try:
                next(self.automaton.iter(text_lower))
                return True
            except StopIteration:
                return False
        else:
            for pattern in self._regex_patterns.values():
                if pattern.search(text):
                    return True
            return False

    def get_matched_terms(self, text: str) -> Set[str]:
        """获取文本中所有匹配的词汇（不含位置）"""
        return set(self.find_all(text).keys())

    @property
    def term_count(self) -> int:
        """返回自动机中的词汇数量"""
        return len(self.terms)

    @property
    def is_using_ac(self) -> bool:
        """是否使用AC自动机（vs 正则回退）"""
        return self.use_ac
