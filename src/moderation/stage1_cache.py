"""
Stage 1 缓存管理
================
缓存 HybridRetriever 和 Filter Agent，避免每次请求重建。
"""

import hashlib
import json
from typing import Dict, Optional

from .schemas import RuleCard
from .stages.stage1_recall_filter import HybridRetriever, build_filter_agent


# 全局缓存
_retriever_cache: Dict[str, HybridRetriever] = {}
_filter_agent_cache: Optional[object] = None


def _compute_rules_hash(rule_cards: Dict[str, RuleCard]) -> str:
    """计算规则卡片的 hash 值，用于缓存键"""
    # 使用规则 ID 列表的排序结果作为 hash 输入
    rule_ids = sorted(rule_cards.keys())
    hash_input = json.dumps(rule_ids, ensure_ascii=False)
    return hashlib.md5(hash_input.encode()).hexdigest()


def get_cached_retriever(rule_cards: Dict[str, RuleCard]) -> HybridRetriever:
    """
    获取缓存的 HybridRetriever，如果不存在则创建并缓存。

    缓存策略：
      - 基于规则卡片的 hash 值作为缓存键
      - 当规则库未变化时，复用已构建的索引
    """
    cache_key = _compute_rules_hash(rule_cards)

    if cache_key not in _retriever_cache:
        # 缓存未命中，创建新的 retriever
        _retriever_cache[cache_key] = HybridRetriever(rule_cards)

    return _retriever_cache[cache_key]


def get_cached_filter_agent():
    """
    获取缓存的 Filter Agent，如果不存在则创建并缓存。

    Filter Agent 是无状态的，可以全局复用。
    """
    global _filter_agent_cache

    if _filter_agent_cache is None:
        _filter_agent_cache = build_filter_agent()

    return _filter_agent_cache


def clear_cache():
    """清空所有缓存（用于测试或规则更新后）"""
    global _retriever_cache, _filter_agent_cache
    _retriever_cache.clear()
    _filter_agent_cache = None
