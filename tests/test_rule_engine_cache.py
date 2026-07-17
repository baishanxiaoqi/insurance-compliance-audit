from unittest.mock import patch

from src.moderation.rule_engine import (
    clear_eval_cache,
    evaluate_rule_on_text,
    get_eval_cache_size,
)
from src.moderation.schemas import RuleCard


def _build_rule_card() -> RuleCard:
    return RuleCard(
        rule_id="KB_TEST",
        rule_name="测试规则",
        risk_level="high",
        violation_definition="测试规则定义",
        keywords=["收益"],
        violation_terms=["收益"],
    )


def test_rule_engine_cache_is_bounded_by_config():
    clear_eval_cache()
    card = _build_rule_card()

    with patch("src.moderation.rule_engine.config.RULE_ENGINE_CACHE_MAX_SIZE", 2):
        evaluate_rule_on_text("收益稳定", card)
        evaluate_rule_on_text("收益确定", card)
        evaluate_rule_on_text("收益有保障", card)

    assert get_eval_cache_size() == 2
    clear_eval_cache()
