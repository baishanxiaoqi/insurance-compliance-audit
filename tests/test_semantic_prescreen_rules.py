"""
测试语义预检的轻量规则检测逻辑：
- financial_confusion: 银行/存款类词 + 保险主体词同时出现
- absolute_expression: 绝对化词 + 高风险修饰对象
"""

import pytest

from src.moderation.rule_indexes import build_category_group_index
from src.moderation.schemas import RuleCard
from src.moderation.stages.stage1_1_semantic_prescreen import (
    _detect_financial_confusion_signal,
    _detect_absolute_expression_signal,
    _detect_signals,
    _extend_rules_from_directions,
)


# ============================================================
# financial_confusion 轻量规则检测
# ============================================================

class TestFinancialConfusionSignal:

    def test_hit_bank_insurance(self):
        """银行 + 保险主体词 -> 命中"""
        text = "这款产品像银行存款一样安全，但收益更高"
        assert _detect_financial_confusion_signal(text) is True

    def test_hit_savings_product(self):
        """储蓄 + 产品 -> 命中"""
        text = "这款产品的安全性相当于储蓄，让您放心"
        assert _detect_financial_confusion_signal(text) is True

    def test_hit_investment_policy(self):
        """投资 + 保单 -> 命中"""
        text = "这份保单的投资收益非常稳健"
        assert _detect_financial_confusion_signal(text) is True

    def test_miss_negative_regulatory(self):
        """监管规定出现时，降低或取消补召回 -> 不命中"""
        text = "根据监管规定，不得把保险说成理财或银行存款"
        assert _detect_financial_confusion_signal(text) is False

    def test_miss_negative_prohibition(self):
        """禁止 + 不得 语境 -> 不命中"""
        text = "禁止将保险产品说成银行存款，不得混淆"
        assert _detect_financial_confusion_signal(text) is False

    def test_miss_no_insurance_context(self):
        """只有银行词，没有保险主体词 -> 不命中"""
        text = "银行存款利率上升，理财收益也提高了"
        assert _detect_financial_confusion_signal(text) is False

    def test_miss_no_bank_context(self):
        """只有保险词，没有银行/存款类词 -> 不命中"""
        text = "这款保险产品保障全面，适合家庭投保"
        # 包含'保险'和'产品'，但没有银行/存款/储蓄类词
        # 注意：'理财'不在这段文本中
        assert _detect_financial_confusion_signal(text) is False


# ============================================================
# absolute_expression 轻量规则检测
# ============================================================

class TestAbsoluteExpressionSignal:

    def test_hit_best_product(self):
        """最 + 产品 -> 命中"""
        text = "这是市场上最好的保险产品"
        assert _detect_absolute_expression_signal(text) is True

    def test_hit_only_coverage(self):
        """唯一 + 保障 -> 命中"""
        text = "唯一能提供此类保障的产品"
        assert _detect_absolute_expression_signal(text) is True

    def test_hit_absolute_claim(self):
        """百分百 + 收益 -> 命中"""
        text = "百分百保证您的收益不受损失"
        assert _detect_absolute_expression_signal(text) is True

    def test_hit_first_advisor(self):
        """第一 + 顾问 -> 命中"""
        text = "我们拥有行业第一的顾问团队"
        assert _detect_absolute_expression_signal(text) is True

    def test_miss_service_aspiration(self):
        """服务理念中的最好 -> 不命中（高风险修饰对象不匹配）"""
        # '最好' 后跟 '服务体验'，不在高风险对象集合中
        text = "我们始终追求最好的服务体验"
        assert _detect_absolute_expression_signal(text) is False

    def test_miss_service_concept_negative(self):
        """负向保护词出现时，不应触发 absolute_expression 预检"""
        text = "公司服务理念是做客户心中最好的伙伴"
        assert _detect_absolute_expression_signal(text) is False

    def test_miss_no_absolute_word(self):
        """无绝对化词 -> 不命中"""
        text = "这款产品收益稳定，保障全面"
        assert _detect_absolute_expression_signal(text) is False

    def test_miss_no_high_risk_object(self):
        """有绝对化词但无高风险修饰对象 -> 不命中"""
        text = "这是最美丽的风景"
        assert _detect_absolute_expression_signal(text) is False

    def test_hit_certain_claim(self):
        """一定 + 理赔 -> 命中"""
        text = "发生事故后一定可以理赔"
        assert _detect_absolute_expression_signal(text) is True


# ============================================================
# _detect_signals 集成测试
# ============================================================

class TestDetectSignals:

    def test_both_signals(self):
        """同时命中两类风险"""
        text = "这款产品和银行存款一样安全，而且是市场上最好的产品"
        signals = _detect_signals(text, ["financial_confusion", "absolute_expression"])
        assert "financial_confusion" in signals
        assert "absolute_expression" in signals

    def test_only_enabled_groups(self):
        """只检测 enabled_groups 中的类别"""
        text = "这款产品和银行存款一样安全，而且是市场上最好的产品"
        signals = _detect_signals(text, ["financial_confusion"])
        assert "financial_confusion" in signals
        assert "absolute_expression" not in signals

    def test_empty_enabled_groups(self):
        """enabled_groups 为空时，无任何信号"""
        text = "这款产品和银行存款一样安全，而且是最好的"
        signals = _detect_signals(text, [])
        assert signals == []

    def test_no_signal(self):
        """无风险文本 -> 空列表"""
        text = "本产品依法合规销售，请仔细阅读条款"
        signals = _detect_signals(text, ["financial_confusion", "absolute_expression"])
        assert signals == []


class TestExtendRulesFromDirections:

    def _build_rule_cards(self):
        return {
            "R_FAMILY": RuleCard(
                rule_id="R_FAMILY",
                rule_name="知识库规则-家庭纠纷",
                risk_level="high",
                violation_definition="宣传保险可以解决家庭纠纷。",
                keywords=["家庭纠纷"],
                violation_terms=["家庭纠纷"],
                category_group="financial_confusion",
            ),
            "R_INVEST": RuleCard(
                rule_id="R_INVEST",
                rule_name="知识库规则-理财 / 理财产品",
                risk_level="high",
                violation_definition="直接宣传保险产品具备投资理财功能。",
                keywords=["理财", "投资", "收益"],
                violation_terms=["理财", "理财产品", "投资", "收益", "像储蓄一样"],
                condition_terms=["保险", "产品", "保单"],
                category_group="financial_confusion",
            ),
            "R_ABS_PRODUCT": RuleCard(
                rule_id="R_ABS_PRODUCT",
                rule_name="知识库规则-国家级 / 最高级",
                risk_level="high",
                violation_definition="绝对化夸大产品能力。",
                keywords=["最佳"],
                violation_terms=["最佳", "最好的", "第一", "唯一"],
                category_group="absolute_expression",
            ),
            "R_ABS_EXPLAIN": RuleCard(
                rule_id="R_ABS_EXPLAIN",
                rule_name="知识库规则-解释权",
                risk_level="high",
                violation_definition="最终解释权归公司。",
                keywords=["解释权"],
                violation_terms=["解释权"],
                category_group="absolute_expression",
            ),
        }

    def test_prefers_text_matched_rule_within_group(self):
        rule_cards = self._build_rule_cards()
        index = build_category_group_index(rule_cards)
        result = _extend_rules_from_directions(
            chunk_text="这款保险产品像银行存款一样安全，收益更高",
            directions=["financial_confusion"],
            category_group_index=index,
            rule_cards=rule_cards,
            max_rules=2,
        )
        assert result[0] == "R_INVEST"
        assert "R_FAMILY" not in result

    def test_different_texts_expand_to_different_rules(self):
        rule_cards = self._build_rule_cards()
        index = build_category_group_index(rule_cards)
        family_result = _extend_rules_from_directions(
            chunk_text="这份保险可以帮助解决家庭纠纷",
            directions=["financial_confusion"],
            category_group_index=index,
            rule_cards=rule_cards,
            max_rules=2,
        )
        invest_result = _extend_rules_from_directions(
            chunk_text="这款保险产品收益稳定，像理财一样灵活",
            directions=["financial_confusion"],
            category_group_index=index,
            rule_cards=rule_cards,
            max_rules=2,
        )
        assert family_result[0] == "R_FAMILY"
        assert invest_result[0] == "R_INVEST"
