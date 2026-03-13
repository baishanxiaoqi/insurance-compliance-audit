"""
Stage 1.5: 事实抽取（Fact Extraction）
=====================================
当前版本采用纯代码的确定性抽取，用于搭建事实层框架：
  - 从 chunk 的 spans 中抽取否定/确定性/比较/时间/动作等事实信号
  - 输出 ChunkFactProfile，供 Stage 2 提示增强与后续可执行规则引擎使用

Phase 2 升级：新增 5 类锚点抽取
  - actor: 主体识别（agent/customer/company/third_party）
  - claim: 主张类型（income_promise/risk_downplay/ranking_claim 等）
  - time_scope: 时间范围（past/present/future/limited_time）
  - evidence_need: 证据需求（是否涉及需证明的陈述）
  - tone_strength: 语气强度（guarantee/possible/expected/suggest）

说明：
  - 本阶段不改变对外 API 输出
  - 后续可平滑替换为 LLM 结构化抽取（Schema 保持不变）
"""

from __future__ import annotations

import re
from typing import Dict, List, Set

from ..log import get_logger
from ..schemas import ChunkFactProfile, ChunkCandidates, DocumentState, FactSignal

logger = get_logger(__name__)


# ============================================================
# 原有信号词库
# ============================================================

NEGATION_TERMS = ["不", "无", "非", "未", "不要", "不得", "不能"]
CERTAINTY_TERMS = ["保证", "一定", "稳赚", "必然", "无条件", "全额", "肯定"]
COMPARISON_TERMS = ["比", "高于", "低于", "远超", "优于", "不如", "超过"]
TIME_TERMS = ["之前", "后来", "目前", "曾", "过去", "未来", "即将", "最后", "限时"]
ACTION_TERMS = ["建议", "推荐", "退保", "购买", "停售", "抢购", "转购", "投保"]

PERCENT_PATTERN = re.compile(r"\d+(?:\.\d+)?%")
MONEY_PATTERN = re.compile(r"(?:\d+(?:\.\d+)?)(?:万|亿|元|块|w)")

# ============================================================
# Phase 2 新增：5 类锚点词库
# ============================================================

# 1. 主体识别（actor）
ACTOR_AGENT_TERMS = ["代理人", "营销员", "业务员", "经理", "顾问", "我们", "我司", "加入我们", "团队"]
ACTOR_CUSTOMER_TERMS = ["您", "客户", "投保人", "被保险人", "受益人", "消费者"]
ACTOR_COMPANY_TERMS = ["本公司", "我司", "公司", "保险公司", "XX保险"]
ACTOR_THIRD_PARTY_TERMS = ["银行", "外企", "其他公司", "之前", "曾在"]

# 2. 主张类型（claim）
CLAIM_INCOME_PROMISE = ["收益", "回报", "分红", "利息", "年化", "收益率", "稳赚", "保本"]
CLAIM_RISK_DOWNPLAY = ["安全", "无风险", "零风险", "保障", "稳定", "不会亏"]
CLAIM_RANKING = ["第一", "最好", "最优", "领先", "冠军", "排名", "榜首", "NO.1"]
CLAIM_SURRENDER = ["退保", "退出", "解约", "终止", "取消"]
CLAIM_COMPARISON = ["比", "高于", "优于", "超过", "远超", "不如"]
CLAIM_HISTORICAL = ["历史", "过往", "曾经", "业绩", "往年"]
CLAIM_MISLEADING = ["误导", "欺骗", "虚假", "夸大", "隐瞒"]

# 3. 时间范围（time_scope）
TIME_PAST = ["之前", "曾经", "过去", "当时", "那时", "以前", "原来", "历史上"]
TIME_PRESENT = ["现在", "目前", "如今", "当前", "正在", "眼下"]
TIME_FUTURE = ["未来", "将来", "即将", "马上", "很快", "接下来"]
TIME_LIMITED = ["限时", "截止", "最后", "仅剩", "倒计时", "今天", "本月"]

# 4. 证据需求（evidence_need）
EVIDENCE_NEED_TERMS = [
    "收益", "回报", "分红", "年化", "收益率",  # 收益类
    "排名", "第一", "最好", "领先", "冠军",    # 排名类
    "历史", "业绩", "往年", "过往",           # 历史业绩类
    "数据", "统计", "调查", "报告",           # 数据来源类
    "获奖", "荣誉", "认证", "批准"            # 资质类
]

# 5. 语气强度（tone_strength）
TONE_GUARANTEE = ["保证", "承诺", "一定", "必然", "肯定", "确保", "绝对"]
TONE_POSSIBLE = ["可能", "或许", "也许", "大概", "估计", "可以"]
TONE_EXPECTED = ["预期", "预计", "预测", "预估", "预料", "期望"]
TONE_SUGGEST = ["建议", "推荐", "提议", "劝", "希望", "最好"]


def _extract_span_signals(span_text: str) -> List[tuple[str, str]]:
    """从单个 span 文本抽取信号（label, value）。

    Phase 2 升级：新增 5 类锚点抽取
    """
    signals: List[tuple[str, str]] = []

    # ---- 原有信号 ----
    for term in NEGATION_TERMS:
        if term in span_text:
            signals.append(("negation", term))

    for term in CERTAINTY_TERMS:
        if term in span_text:
            signals.append(("certainty", term))

    for term in COMPARISON_TERMS:
        if term in span_text:
            signals.append(("comparison", term))

    for term in TIME_TERMS:
        if term in span_text:
            signals.append(("time", term))

    for term in ACTION_TERMS:
        if term in span_text:
            signals.append(("action", term))

    for m in PERCENT_PATTERN.findall(span_text):
        signals.append(("number_percent", m))

    for m in MONEY_PATTERN.findall(span_text):
        signals.append(("number_money", m))

    # ============================================================
    # Phase 2 新增：5 类锚点抽取
    # ============================================================

    # 1. 主体识别（actor）
    for term in ACTOR_AGENT_TERMS:
        if term in span_text:
            signals.append(("actor_agent", term))

    for term in ACTOR_CUSTOMER_TERMS:
        if term in span_text:
            signals.append(("actor_customer", term))

    for term in ACTOR_COMPANY_TERMS:
        if term in span_text:
            signals.append(("actor_company", term))

    for term in ACTOR_THIRD_PARTY_TERMS:
        if term in span_text:
            signals.append(("actor_third_party", term))

    # 2. 主张类型（claim）
    for term in CLAIM_INCOME_PROMISE:
        if term in span_text:
            signals.append(("claim_income_promise", term))

    for term in CLAIM_RISK_DOWNPLAY:
        if term in span_text:
            signals.append(("claim_risk_downplay", term))

    for term in CLAIM_RANKING:
        if term in span_text:
            signals.append(("claim_ranking", term))

    for term in CLAIM_SURRENDER:
        if term in span_text:
            signals.append(("claim_surrender", term))

    for term in CLAIM_COMPARISON:
        if term in span_text:
            signals.append(("claim_comparison", term))

    for term in CLAIM_HISTORICAL:
        if term in span_text:
            signals.append(("claim_historical", term))

    for term in CLAIM_MISLEADING:
        if term in span_text:
            signals.append(("claim_misleading", term))

    # 3. 时间范围（time_scope）
    for term in TIME_PAST:
        if term in span_text:
            signals.append(("time_past", term))

    for term in TIME_PRESENT:
        if term in span_text:
            signals.append(("time_present", term))

    for term in TIME_FUTURE:
        if term in span_text:
            signals.append(("time_future", term))

    for term in TIME_LIMITED:
        if term in span_text:
            signals.append(("time_limited", term))

    # 4. 证据需求（evidence_need）
    for term in EVIDENCE_NEED_TERMS:
        if term in span_text:
            signals.append(("evidence_need", term))

    # 5. 语气强度（tone_strength）
    for term in TONE_GUARANTEE:
        if term in span_text:
            signals.append(("tone_guarantee", term))

    for term in TONE_POSSIBLE:
        if term in span_text:
            signals.append(("tone_possible", term))

    for term in TONE_EXPECTED:
        if term in span_text:
            signals.append(("tone_expected", term))

    for term in TONE_SUGGEST:
        if term in span_text:
            signals.append(("tone_suggest", term))

    return signals


def _build_summary(signals: List[FactSignal]) -> str:
    """构建事实信号摘要。

    Phase 2 升级：包含新增的 5 类锚点
    """
    if not signals:
        return ""
    labels: Dict[str, Set[str]] = {}
    for s in signals:
        labels.setdefault(s.label, set()).add(s.value)

    parts = []
    # 原有信号
    for label in ["negation", "certainty", "comparison", "time", "action", "number_percent", "number_money"]:
        values = sorted(labels.get(label, set()))
        if values:
            parts.append(f"{label}: {'/'.join(values[:5])}")

    # Phase 2 新增：5 类锚点
    for label in [
        "actor_agent", "actor_customer", "actor_company", "actor_third_party",
        "claim_income_promise", "claim_risk_downplay", "claim_ranking", "claim_surrender",
        "claim_comparison", "claim_historical", "claim_misleading",
        "time_past", "time_present", "time_future", "time_limited",
        "evidence_need",
        "tone_guarantee", "tone_possible", "tone_expected", "tone_suggest"
    ]:
        values = sorted(labels.get(label, set()))
        if values:
            parts.append(f"{label}: {'/'.join(values[:3])}")  # 限制每类最多3个值

    return "; ".join(parts)


def run_stage1_5(
    document: DocumentState,
    candidates: List[ChunkCandidates],
) -> Dict[str, ChunkFactProfile]:
    """
    仅对 Stage 1 有候选规则的 chunk 进行事实抽取，减少无效计算。
    返回：chunk_id -> ChunkFactProfile
    """
    chunk_ids = {c.chunk_id for c in candidates}
    chunk_map = {c.chunk_id: c for c in document.chunks}

    profiles: Dict[str, ChunkFactProfile] = {}

    for chunk_id in chunk_ids:
        chunk = chunk_map.get(chunk_id)
        if chunk is None:
            continue

        merged: Dict[tuple[str, str], Set[str]] = {}
        for span in chunk.spans:
            raw_signals = _extract_span_signals(span.span_text)
            for label, value in raw_signals:
                key = (label, value)
                merged.setdefault(key, set()).add(span.span_id)

        signals: List[FactSignal] = []
        for (label, value), span_ids in merged.items():
            signals.append(
                FactSignal(
                    label=label,
                    value=value,
                    evidence_span_ids=sorted(span_ids),
                )
            )

        signals.sort(key=lambda s: (s.label, s.value))
        profiles[chunk_id] = ChunkFactProfile(
            chunk_id=chunk_id,
            signals=signals,
            summary=_build_summary(signals),
        )

    logger.info(f"Stage 1.5 完成: 生成 {len(profiles)} 个 chunk 事实画像")
    return profiles
