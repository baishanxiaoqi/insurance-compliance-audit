"""
轻量规则索引模块
=================
为语义预检等阶段提供预建的规则索引，避免每次全量扫描规则库。
"""

import re
from typing import Dict, List, Tuple
from .schemas import RuleCard


_RULE_NAME_SPLIT_RE = re.compile(r"[\s/、,，；;：:（）()\[\]【】\-]+")
_IGNORED_RULE_NAME_TERMS = frozenset({"知识库规则"})


def _dedupe_terms(terms: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for term in terms:
        cleaned = (term or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _extract_rule_name_terms(rule_name: str) -> List[str]:
    raw_name = (rule_name or "").replace("知识库规则-", "").replace("知识库规则", "").strip()
    if not raw_name:
        return []
    parts = [
        part.strip()
        for part in _RULE_NAME_SPLIT_RE.split(raw_name)
        if part.strip() and part.strip() not in _IGNORED_RULE_NAME_TERMS
    ]
    return _dedupe_terms([raw_name, *parts])


def score_rule_for_text(text: str, card: RuleCard) -> Tuple[int, int, int]:
    matched_terms: List[str] = []
    weighted_term_groups = [
        (6, card.violation_terms),
        (5, card.keywords),
        (3, card.condition_terms),
        (2, _extract_rule_name_terms(card.rule_name)),
    ]

    score = 0
    for weight, terms in weighted_term_groups:
        for term in _dedupe_terms(list(terms)):
            if len(term) < 2:
                continue
            if term in text:
                matched_terms.append(term)
                score += weight

    max_term_len = max((len(term) for term in matched_terms), default=0)
    return score, max_term_len, len(matched_terms)


def select_group_rule_ids_for_text(
    text: str,
    category_group: str,
    category_group_index: Dict[str, List[str]],
    rule_cards: Dict[str, RuleCard],
    max_rules: int,
) -> List[str]:
    rule_ids = category_group_index.get(category_group, [])
    if max_rules <= 0 or not rule_ids:
        return []

    ranked: List[Tuple[int, int, int, int, str]] = []
    for order, rule_id in enumerate(rule_ids):
        card = rule_cards.get(rule_id)
        if card is None:
            continue
        score, max_term_len, matched_count = score_rule_for_text(text, card)
        ranked.append((score, max_term_len, matched_count, order, rule_id))

    positive_hits = [item for item in ranked if item[0] > 0]
    if positive_hits:
        positive_hits.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
        return [rule_id for *_rest, rule_id in positive_hits[:max_rules]]

    return rule_ids[:max_rules]


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
