"""
复杂场景专用 Skills（Phase 2）
================================
针对需要深度上下文理解和复杂逻辑推理的审查点，提供专门的 Skill。

核心复杂场景：
  1. 时态上下文判断（temporal_context）：区分"过往"vs"当前"
  2. 主体切换识别（subject_switch）：区分"代理人"vs"客户"
  3. 承诺强度判断（commitment_strength）：区分"保证"vs"可能"
  4. 跨段落逻辑（cross_paragraph）：需要全文上下文的判定

每个复杂 Skill 包含：
  - 专业的系统提示（领域知识）
  - 丰富的 Few-shot 正反例（边界 case）
  - 多轮推理逻辑（可选）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .schemas import Chunk, RuleCard, ChunkFactProfile
from .rule_engine import RuleEvalReport
from .skills import ComplianceSkill, FewShotExample

# ============================================================
# 1. 时态上下文判断 Skill
# ============================================================

SKILL_TEMPORAL_CONTEXT = ComplianceSkill(
    name="时态上下文判断",
    description="区分描述对象的时态：过往经历 vs 当前状态",
    rule_ids=set(),  # 动态路由
    system_instructions=[
        "你是时态语境分析专家，专精于识别文本中的时间线索和时态标记。",
        "你的核心能力是区分以下两类表述：",
        "  A) 过往经历：'曾经/之前/过去/当时/那时' + 动词过去式",
        "  B) 当前状态：'现在/目前/如今/正在' + 动词现在式",
        "审核要求【特别重要】：",
        "1. 仔细识别时态标记词：'曾经/之前/过去' → 过往；'现在/目前' → 当前",
        "2. 分析动词时态：'担任过/做过' → 过往；'担任/正在做' → 当前",
        "3. 上下文语境：如果前文已说明'加入保险行业之前'，后续描述默认为过往",
        "4. 薪资场景特殊规则：",
        "   - 描述代理人加入保险行业**之前**的其他岗位收入 → 合规",
        "   - 描述代理人加入保险行业**之后**的收入/承诺 → 违规",
        "5. 如果时态不明确，优先判定为 unsure，在 reasoning 中说明原因",
        "",
        "evidence_span_ids 选择原则【关键】：",
        "- 只选择包含核心违规词的 span_id（如'月薪'、'月收入'、'年薪'等）",
        "- 不要选择仅包含上下文、修饰词、连接词的 span",
        "- 如果违规表述跨越多个连续的 span，选择所有相关的 span",
        "- 例如：'业绩，月收入稳定在3-5万元' 中，'月收入'是违规词，只选择包含'月收入稳定在3-5万元'的 span，不要选择'业绩，'所在的 span",
    ],
    few_shots=[
        FewShotExample(
            label="compliant",
            text_snippet="张经理之前在某外企担任销售总监，月薪2万元。后来他选择了保险行业。",
            verdict="compliant",
            reasoning="'之前'是明确的时态标记，表示过往经历。'担任'是过去式动词。"
                      "'月薪2万元'描述的是张经理加入保险行业之前在外企的收入。"
                      "属于例外条款中'描述代理人加入保险行业之前的其他岗位的历史收入'。合规。",
        ),
        FewShotExample(
            label="violation",
            text_snippet="李经理目前在我司担任高级代理人，月收入可达3万元以上。",
            verdict="violation",
            reasoning="'目前'是明确的当前时态标记。'担任'是现在式动词。"
                      "'月收入可达3万元以上'描述的是李经理当前在保险行业的收入。"
                      "属于用具体收入数字诱导应聘的薪资诱导违规。",
        ),
        FewShotExample(
            label="compliant",
            text_snippet="王总监加入我司之前，曾在银行工作，年薪50万。",
            verdict="compliant",
            reasoning="'加入我司之前'和'曾在'都是过往时态标记。"
                      "'年薪50万'描述的是王总监在银行工作时的收入，属于加入保险行业之前的历史收入。合规。",
        ),
        FewShotExample(
            label="unsure",
            text_snippet="赵经理在金融行业工作多年，收入稳定可观。",
            verdict="unsure",
            reasoning="时态不明确。'工作多年'可能指过往也可能包含当前。"
                      "'收入稳定可观'未明确是过往还是当前。"
                      "缺少'之前/曾经'或'现在/目前'等明确时态标记。无法判定。",
        ),
    ],
    temperature=0.2,
)


# ============================================================
# 2. 主体切换识别 Skill
# ============================================================

SKILL_SUBJECT_SWITCH = ComplianceSkill(
    name="主体切换识别",
    description="区分描述对象：代理人 vs 客户 vs 公司",
    rule_ids=set(),
    system_instructions=[
        "你是主体识别专家，专精于识别文本中的描述对象和主体切换。",
        "你的核心能力是区分以下主体：",
        "  A) 代理人：'我们的代理人/营销员/业务员/经理/顾问'",
        "  B) 客户：'您/客户/投保人/被保险人'",
        "  C) 公司：'本公司/我司/XX保险'",
        "审核要求：",
        "1. 识别主语：明确判断句子的主语是谁",
        "2. 代词指代：'他/她/其' 需要回溯前文确定指代对象",
        "3. 隐含主语：中文常省略主语，需根据上下文推断",
        "4. 主体切换：注意段落间的主体变化",
        "5. 特殊场景：",
        "   - 招聘宣传中的薪资 → 主体是代理人",
        "   - 产品宣传中的收益 → 主体是客户",
        "",
        "evidence_span_ids 选择原则【关键】：",
        "- 只选择包含核心违规词的 span_id",
        "- 不要选择仅包含上下文、修饰词、连接词的 span",
        "- 如果违规表述跨越多个连续的 span，选择所有相关的 span",
        "- 确保选中的 span 构成最小完整语义单元",
    ],
    few_shots=[
        FewShotExample(
            label="violation",
            text_snippet="加入我们，月入过万不是梦！优秀代理人年薪可达百万。",
            verdict="violation",
            reasoning="主体是'代理人'（从'加入我们'和'优秀代理人'可判断）。"
                      "'月入过万'和'年薪可达百万'是对代理人收入的承诺。"
                      "属于薪资诱导违规。",
        ),
        FewShotExample(
            label="compliant",
            text_snippet="该产品预期年化收益率3%-5%，具体以实际结算为准。",
            verdict="compliant",
            reasoning="主体是'客户'（产品收益的受益人）。"
                      "描述的是保险产品的收益，非代理人薪资。"
                      "且使用了'预期'和'以实际结算为准'的风险提示。合规。",
        ),
        FewShotExample(
            label="compliant",
            text_snippet="张经理之前在外企工作，月薪8000元。现在他帮助客户规划保障方案。",
            verdict="compliant",
            reasoning="第一句主体是'张经理'，描述其过往收入（合规）。"
                      "第二句主体仍是'张经理'，但描述的是工作内容（帮助客户），非当前薪资。"
                      "未涉及当前收入承诺。合规。",
        ),
    ],
    temperature=0.2,
)


# ============================================================
# 3. 承诺强度判断 Skill
# ============================================================

SKILL_COMMITMENT_STRENGTH = ComplianceSkill(
    name="承诺强度判断",
    description="区分表述的确定性程度：保证/承诺 vs 预期/可能",
    rule_ids=set(),
    system_instructions=[
        "你是语义强度分析专家，专精于识别表述的确定性程度。",
        "你的核心能力是区分以下强度等级：",
        "  A) 绝对承诺：'保证/确保/必定/一定/承诺/稳赚'",
        "  B) 高度确定：'肯定/绝对/100%/无疑'",
        "  C) 中度预期：'预期/预计/可能/有望'",
        "  D) 低度可能：'或许/也许/可能会'",
        "审核要求：",
        "1. 识别确定性词汇：'保证/承诺' → 违规；'预期/可能' → 合规",
        "2. 数字表述：'年化8%' → 违规；'预期年化3%-5%' → 合规",
        "3. 风险提示：有'以实际为准/不代表未来'等提示 → 降低违规风险",
        "4. 分红场景：'保证分红X%' → 违规；'红利分配不确定' → 合规",
        "5. 收益场景：'稳赚不赔' → 违规；'基于合同约定的保底利率' → 合规",
        "",
        "evidence_span_ids 选择原则【关键】：",
        "- 只选择包含核心违规词的 span_id（如'保证'、'承诺'、'保底'等）",
        "- 不要选择仅包含上下文、修饰词、连接词的 span",
        "- 如果违规表述跨越多个连续的 span，选择所有相关的 span",
        "- 例如：'产品特色：\n1. 保底年利率2.5%' 中，只选择包含'保底年利率2.5%'的 span，不要选择'产品特色：'所在的 span",
    ],
    few_shots=[
        FewShotExample(
            label="violation",
            text_snippet="我们保证每年分红不低于3%，让您年年享受红利。",
            verdict="violation",
            reasoning="'保证'是绝对承诺词汇。'每年分红不低于3%'是对分红水平的确定性承诺。"
                      "分红保险的红利分配是不确定的，此表述违反了禁止承诺分红的规定。违规。",
        ),
        FewShotExample(
            label="compliant",
            text_snippet="该产品预期年化收益率3%-5%，具体以实际结算为准，过往业绩不代表未来表现。",
            verdict="compliant",
            reasoning="'预期'是中度预期词汇，非绝对承诺。"
                      "'以实际结算为准'和'过往业绩不代表未来表现'是明确的风险提示。"
                      "未做确定性收益承诺。合规。",
        ),
        FewShotExample(
            label="violation",
            text_snippet="投保后您的资金将获得稳定的高额回报，年化收益可达8%以上。",
            verdict="violation",
            reasoning="'稳定的高额回报'暗示确定性。'年化收益可达8%以上'是具体数字承诺。"
                      "未使用'预期/演示'等措辞，未标注风险提示。"
                      "属于夸大收益违规。",
        ),
    ],
    temperature=0.2,
)


# ============================================================
# 4. 跨段落逻辑 Skill
# ============================================================

SKILL_CROSS_PARAGRAPH = ComplianceSkill(
    name="跨段落逻辑判断",
    description="需要全文上下文才能判定的复杂逻辑",
    rule_ids=set(),
    system_instructions=[
        "你是全文逻辑分析专家，专精于识别需要跨段落上下文才能判定的违规。",
        "你的核心能力是：",
        "  A) 前后文关联：前文定义 + 后文约束",
        "  B) 代词回溯：识别代词指代的前文对象",
        "  C) 隐含逻辑：推断省略的主语或条件",
        "  D) 矛盾识别：前后文表述不一致",
        "审核要求：",
        "1. 仔细阅读当前 chunk 的上下文（通过 chunk overlap 提供）",
        "2. 识别代词指代：'他/她/其/该' 需要回溯前文",
        "3. 时间线索：前文的时态标记影响后文判定",
        "4. 主体延续：前文确定的主体在后文中延续",
        "5. 如果上下文不足以判定，verdict 设为 unsure",
        "",
        "evidence_span_ids 选择原则【关键】：",
        "- 只选择包含核心违规词的 span_id",
        "- 不要选择仅包含上下文、修饰词、连接词的 span",
        "- 如果违规表述跨越多个连续的 span，选择所有相关的 span",
        "- 确保选中的 span 构成最小完整语义单元",
    ],
    few_shots=[
        FewShotExample(
            label="compliant",
            text_snippet="张经理之前在某银行工作。他的月薪当时是1万元。后来他选择了保险行业。",
            verdict="compliant",
            reasoning="第一句确定主体'张经理'和时态'之前'。"
                      "第二句'他的月薪'指代张经理，'当时'延续过往时态。"
                      "第三句'后来'表示时间转折，但未提及当前薪资。"
                      "整体描述的是加入保险行业之前的收入。合规。",
        ),
        FewShotExample(
            label="violation",
            text_snippet="李总监是我们的明星代理人。他目前的收入非常可观，月入3万以上。",
            verdict="violation",
            reasoning="第一句确定主体'李总监'是代理人。"
                      "第二句'他'指代李总监，'目前'是当前时态标记。"
                      "'月入3万以上'是对当前收入的具体数字描述。"
                      "属于薪资诱导违规。",
        ),
    ],
    temperature=0.3,  # 提高探索性
)


# ============================================================
# 复杂 Skills 注册表
# ============================================================

COMPLEX_SKILLS: List[ComplianceSkill] = [
    SKILL_TEMPORAL_CONTEXT,
    SKILL_SUBJECT_SWITCH,
    SKILL_COMMITMENT_STRENGTH,
    SKILL_CROSS_PARAGRAPH,
]

COMPLEX_SKILL_BY_NAME: Dict[str, ComplianceSkill] = {
    s.name: s for s in COMPLEX_SKILLS
}


def get_complex_skill(skill_type: str) -> ComplianceSkill | None:
    """
    根据 skill_type 获取复杂 Skill。

    skill_type 映射：
      - "temporal_context" → 时态上下文判断
      - "subject_switch" → 主体切换识别
      - "commitment_strength" → 承诺强度判断
      - "cross_paragraph" → 跨段落逻辑判断
    """
    mapping = {
        "temporal_context": SKILL_TEMPORAL_CONTEXT,
        "subject_switch": SKILL_SUBJECT_SWITCH,
        "commitment_strength": SKILL_COMMITMENT_STRENGTH,
        "cross_paragraph": SKILL_CROSS_PARAGRAPH,
    }
    return mapping.get(skill_type)

