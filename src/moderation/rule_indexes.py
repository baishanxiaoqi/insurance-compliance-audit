"""
轻量规则索引模块
=================
为语义预检等阶段提供预建的规则索引，避免每次全量扫描规则库。

第一版只需要 category_group -> rule_ids 索引。
"""

from typing import Dict, List
from .schemas import RuleCard


def build_category_group_index(rule_cards: Dict[str, RuleCard]) -> Dict[str, List[str]]:
    """
    构建 category_group -> rule_ids 索引。

    Args:
        rule_cards: 规则卡片字典 {rule_id: RuleCard}

    Returns:
        {category_group: [rule_id, ...]} 字典。
        没有 category_group 的规则不会出现在索引中。
    """
    index: Dict[str, List[str]] = {}
    for rule_id, card in rule_cards.items():
        if card.category_group:
            index.setdefault(card.category_group, []).append(rule_id)
    return index
