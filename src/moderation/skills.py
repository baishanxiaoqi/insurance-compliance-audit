"""
Skills 技能注册表 ── Skill-based Agent Dispatch
=================================================

核心理念:
  原来 Stage 2 使用一个通用 Critic Agent 处理所有 12 条规则，
  现在按「违规类型」拆分为 5 个专业 Skill，每个 Skill 携带:
    1. 聚焦的 system_instructions（领域知识）
    2. 正反例 Few-shot（指导 LLM 推理方向）
    3. 自定义 prompt 构建逻辑
    4. 针对性的后验证规则

优势:
  - Few-shot 正反例显著提升边界 case 的判定准确率
  - 专业系统提示让 reasoning_cot 更深入
  - 每个 Skill 可独立调参（temperature、重试次数等）
  - 新增规则 → 新增 Skill 或追加到现有分组，不影响其他 Skill
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .rule_engine import RuleEvalReport
from .schemas import Chunk, RuleCard, JudgmentResult, ChunkFactProfile
from .log import get_logger

logger = get_logger(__name__)


# ============================================================
# Skill 基类
# ============================================================

@dataclass
class ComplianceSkill:
    """合规审核技能单元"""
    name: str                                     # 技能名称
    description: str                              # 简要说明
    rule_ids: set[str]                            # 该 Skill 处理的 rule_id 集合
    system_instructions: list[str]                # 专用系统提示
    few_shots: list[FewShotExample] = field(default_factory=list)  # 正反例
    temperature: float = 0.1                      # 可独立调参

    def build_prompt(
        self,
        chunk: Chunk,
        rule_card: RuleCard,
        spans_dict: List[Dict[str, str]],
        chunk_fact: ChunkFactProfile | None = None,
        deterministic_report: RuleEvalReport | None = None,
    ) -> str:
        """
        构建包含 Few-shot 正反例的精判 Prompt。
        子类可重写此方法做更深度的定制。
        """
        # ---- 基础上下文 ----
        spans_text = "\n".join(
            f"  {s['span_id']}: \"{s['span_text']}\"" for s in spans_dict
        )
        exceptions_text = "\n".join(
            f"  - {e}" for e in rule_card.exceptions
        ) if rule_card.exceptions else "  无"
        reason_codes_text = ", ".join(rule_card.reason_codes) if rule_card.reason_codes else "无"
        structured_terms = [
            f"违规词: {'|'.join(rule_card.violation_terms) if rule_card.violation_terms else '无'}",
            f"条件词: {'|'.join(rule_card.condition_terms) if rule_card.condition_terms else '无'}",
            f"条件词限定距离: {rule_card.condition_distance if rule_card.condition_distance is not None else '无'}",
            f"排除词: {'|'.join(rule_card.exclusion_terms) if rule_card.exclusion_terms else '无'}",
            f"排除词限定距离: {rule_card.exclusion_distance if rule_card.exclusion_distance is not None else '无'}",
            f"前缀不匹配: {'|'.join(rule_card.prefix_no_match) if rule_card.prefix_no_match else '无'}",
            f"后缀不匹配: {'|'.join(rule_card.suffix_no_match) if rule_card.suffix_no_match else '无'}",
        ]
        kb_evidence = [
            f"合规依据: {rule_card.compliant_basis or '无'}",
            f"合规case: {rule_card.compliant_case or '无'}",
            f"违规依据: {rule_card.violation_basis or '无'}",
            f"违规case: {rule_card.violation_case or '无'}",
        ]

        # ---- Few-shot 正反例 ----
        few_shot_block = ""
        if self.few_shots:
            examples = []
            for i, fs in enumerate(self.few_shots, 1):
                examples.append(
                    f"--- 示例 {i} ({fs.label}) ---\n"
                    f"文本: {fs.text_snippet}\n"
                    f"verdict: {fs.verdict}\n"
                    f"推理: {fs.reasoning}"
                )
            few_shot_block = (
                "\n\n========== 参考示例（仅供推理参考，不要照抄）==========\n"
                + "\n\n".join(examples)
            )

        facts_block = "无"
        if chunk_fact and chunk_fact.signals:
            fact_lines = [f"  - {s.label}: {s.value} (spans={','.join(s.evidence_span_ids[:3])})" for s in chunk_fact.signals[:20]]
            summary_line = f"摘要: {chunk_fact.summary}" if chunk_fact.summary else ""
            facts_block = "\n".join(([summary_line] if summary_line else []) + fact_lines)

        deterministic_block = "无"
        if deterministic_report is not None:
            deterministic_block = (
                f"summary: {deterministic_report.summary}\n"
                f"has_violation_hit: {deterministic_report.has_violation_hit}\n"
                f"condition_pass: {deterministic_report.condition_pass}\n"
                f"exclusion_blocked: {deterministic_report.exclusion_blocked}\n"
                f"hard_block: {deterministic_report.hard_block}"
            )

        return f"""请对以下文本片段进行合规审核，判断是否违反了指定的合规规则。

========== 待审核文本 ==========
{chunk.chunk_text}

========== 合规规则 ==========
规则ID: {rule_card.rule_id}
规则名称: {rule_card.rule_name}
风险等级: {rule_card.risk_level}
违规定义: {rule_card.violation_definition}
例外条款（以下情况不算违规）:
{exceptions_text}
建议模板: {rule_card.suggestion_template}

========== 结构化关键词规则 ==========
{"\n".join(structured_terms)}

========== 知识库判例与依据（用于推理与参考示例） ==========
{"\n".join(kb_evidence)}

========== Span 字典（用于定位）==========
{spans_text}

========== 结构化事实信号（辅助推理，不可替代规则条款）==========
{facts_block}

========== 可执行规则前置结果（代码引擎）==========
{deterministic_block}

========== 可用的 reason_codes ==========
{reason_codes_text}{few_shot_block}

========== 输出要求 ==========
请严格按照以下规则输出：
1. rule_id: 填入 "{rule_card.rule_id}"
2. chunk_id: 填入 "{chunk.chunk_id}"
3. verdict: "violation"(违规) / "compliant"(合规) / "unsure"(不确定)
4. reasoning_cot: 详细的推理过程（必须超过50字），需要结合例外条款逐条排查后再做判定
5. evidence_span_ids: 如果违规，从上方 Span 字典中选择包含违规内容的 span_id（可多选）。如果合规则留空。
6. evidence_texts: 如果违规，从原文中逐字摘录最短的违规片段（只保留核心违规语义，不要整个句子）。每个独立违规点一个片段。例如"收益比存银行高出好几倍"而非"这款产品就像在银行存钱一样安全，但收益比存银行高出好几倍。"。必须是原文的连续子串，一字不差。
7. reason_codes: 如果违规，从可用的 reason_codes 中选择。
8. draft_suggestion: 如果违规，结合建议模板生成具体的修改建议。"""


@dataclass
class FewShotExample:
    """Few-shot 正反例"""
    label: str          # "violation" / "compliant"
    text_snippet: str   # 示例文本片段
    verdict: str        # violation / compliant
    reasoning: str      # 推理示范


# ============================================================
# 5 个专业 Skill 定义
# ============================================================

# ---- 1. 收益类违规检测 Skill (R001 夸大收益, R003 分红承诺) ----
SKILL_REVENUE = ComplianceSkill(
    name="收益类违规检测",
    description="检测夸大保险收益、虚假回报承诺、分红确定性承诺等违规",
    rule_ids={"R001", "R003"},
    system_instructions=[
        "你是保险金融领域的合规审核专家，专精于收益表述合规性判定。",
        "你的核心能力是区分以下两类表述：",
        "  A) 合规表述：基于合同约定的保底利率、使用'预期/演示'等措辞的浮动收益说明、标注了利益演示表的分红说明",
        "  B) 违规表述：绝对化收益承诺（如'稳赚不赔'）、确定性分红承诺（如'保证每年分红X%'）、夸大回报（如'翻倍增长'）",
        "审核要求：",
        "1. 仔细阅读例外条款，引用了精算数据或合同约定固定收益的表述不算违规",
        "2. 注意区分「保底利率」（合规）和「确定性高收益承诺」（违规）",
        "3. 分红型产品使用'红利分配不确定'等措辞是合规的",
        "4. 如果判定违规，必须从 span 字典中选择证据 span，严禁捏造",
        "",
        "evidence_span_ids 选择原则【关键】：",
        "- 只选择包含核心违规词的 span_id（如'稳赚'、'保证分红'、'翻倍'等）",
        "- 不要选择仅包含上下文、修饰词、连接词的 span",
        "- 如果违规表述跨越多个连续的 span，选择所有相关的 span",
        "- 确保选中的 span 构成最小完整语义单元",
    ],
    few_shots=[
        FewShotExample(
            label="violation",
            text_snippet="投保后您的资金将获得稳定的高额回报，预计年化收益可达8%以上，远超银行存款利率。",
            verdict="violation",
            reasoning="该表述使用'稳定的高额回报'和'年化收益可达8%以上'暗示确定性高收益，"
                      "且未标注'预期/演示'字样，未引用精算数据或合同保底利率，"
                      "不属于例外条款中'使用预期措辞描述浮动收益'的情形。构成夸大收益违规。",
        ),
        FewShotExample(
            label="compliant",
            text_snippet="根据合同约定，该产品保底年利率为2.5%，实际结算利率以公司每月公告为准。过往结算利率不代表未来表现。",
            verdict="compliant",
            reasoning="该表述引用了合同约定的保底利率(2.5%)，属于例外条款中"
                      "'引用保险合同中明确约定的保底利率'的情形。"
                      "同时使用了'过往业绩不代表未来表现'的风险提示，合规。",
        ),
        FewShotExample(
            label="violation",
            text_snippet="每年保证分红不低于保费的3%，让您年年享受红利。",
            verdict="violation",
            reasoning="'保证分红不低于保费的3%'属于对分红水平做确定性承诺。"
                      "分红保险的红利分配是不确定的，此表述违反了禁止承诺分红的规定。"
                      "不属于任何例外条款情形。",
        ),
    ],
)

# ---- 2. 用语合规检测 Skill (R002 绝对化用语, R009 不当对比) ----
SKILL_LANGUAGE = ComplianceSkill(
    name="用语合规检测",
    description="检测绝对化用语、排他性表述、夸张竞争性比较等",
    rule_ids={"R002", "R009"},
    system_instructions=[
        "你是广告合规审查专家，专精于保险营销用语合规性审核。",
        "你的核心能力是识别以下违规用语模式：",
        "  A) 绝对化用语：'最好/唯一/第一/绝对/NO.1/最优' 等排他性表述",
        "  B) 不当竞争对比：'碾压/秒杀/完胜/吊打/远超' 等贬损性比较",
        "审核要求：",
        "1. 检查是否有'之一'等限定词修饰（如'领先之一'是合规的）",
        "2. 检查是否引用了权威第三方评级并注明来源",
        "3. 基于公开数据的客观功能比较不算违规",
        "4. 严禁捏造不存在的 span_id",
        "",
        "evidence_span_ids 选择原则【关键】：",
        "- 只选择包含核心违规词的 span_id（如'最好'、'唯一'、'NO.1'等）",
        "- 不要选择仅包含上下文、修饰词、连接词的 span",
        "- 如果违规表述跨越多个连续的 span，选择所有相关的 span",
        "- 确保选中的 span 构成最小完整语义单元",
    ],
    few_shots=[
        FewShotExample(
            label="violation",
            text_snippet="我们已经成为业界NO.1的综合保险服务商，这是市场上最优的终身寿险产品。",
            verdict="violation",
            reasoning="'NO.1'和'最优'均为绝对化用语，具有排他性。"
                      "未引用任何第三方评级来源，未使用'之一'等限定词修饰。"
                      "不属于例外条款中的任何情形。构成绝对化用语违规。",
        ),
        FewShotExample(
            label="compliant",
            text_snippet="根据XX评级机构2024年报告，本公司综合偿付能力居行业前列之一。",
            verdict="compliant",
            reasoning="虽然提到了行业排名，但使用了'之一'限定词，且引用了第三方评级机构来源。"
                      "属于例外条款中'引用权威第三方机构的评级结果并注明来源'和'使用之一等非排他性限定词'的情形。",
        ),
    ],
)

# ---- 3. 信息真实性检测 Skill (R006 虚假限时, R007 冒用监管名义) ----
SKILL_INTEGRITY = ComplianceSkill(
    name="信息真实性检测",
    description="检测虚假停售/限时活动、不当使用监管机构名义、政策曲解等",
    rule_ids={"R006", "R007"},
    system_instructions=[
        "你是保险监管合规专家，专精于识别虚假营销信息和监管名义滥用。",
        "你的核心能力是区分：",
        "  A) 合规引用：准确引用监管文件编号、经审批的限时活动",
        "  B) 违规滥用：虚构停售信息制造紧迫感、曲解政策为产品背书",
        "审核要求：",
        "1. '即将停售/限时抢购/最后机会' — 必须有银保监会正式停售通知或公司审批文号，否则违规",
        "2. '国家规定必须买/国家推荐' — 必须准确引用政策原文和文件编号，否则违规",
        "3. 注意区分「客观介绍监管背景」与「暗示监管推荐特定产品」",
        "4. 严禁捏造不存在的 span_id",
        "",
        "evidence_span_ids 选择原则【关键】：",
        "- 只选择包含核心违规词的 span_id（如'即将停售'、'限时抢购'、'国家推荐'等）",
        "- 不要选择仅包含上下文、修饰词、连接词的 span",
        "- 如果违规表述跨越多个连续的 span，选择所有相关的 span",
        "- 确保选中的 span 构成最小完整语义单元",
    ],
    few_shots=[
        FewShotExample(
            label="violation",
            text_snippet="该产品即将停售！请务必抓住最后机会，限时抢购！错过这次机会就要再等一年了。",
            verdict="violation",
            reasoning="使用'即将停售'、'最后机会'、'限时抢购'等表述制造紧迫感。"
                      "未引用任何银保监会正式停售通知或公司审批文号。"
                      "不属于例外条款中的任何情形。构成虚假宣传限时活动违规。",
        ),
        FewShotExample(
            label="violation",
            text_snippet="国家政策规定每个家庭必须配置保障型保险，这是国家推荐的保障方式。",
            verdict="violation",
            reasoning="'国家规定必须配置'和'国家推荐'将个人保险选择包装为政策强制要求。"
                      "未引用任何具体政策文件编号。"
                      "属于将监管政策曲解为对特定产品的推荐背书。违规。",
        ),
        FewShotExample(
            label="compliant",
            text_snippet="根据银保监办发〔2023〕15号文，保险公司应加强消费者适当性管理，建议客户根据自身需求选择保障方案。",
            verdict="compliant",
            reasoning="准确引用了监管文件编号'银保监办发〔2023〕15号文'，"
                      "且表述为'建议根据自身需求选择'，未将政策曲解为强制购买或产品背书。"
                      "属于例外条款中'准确引用监管政策原文并注明文件编号'的情形。",
        ),
    ],
)

# ---- 4. 消费者保护检测 Skill (R008 隐瞒免责, R010 诱导退保, R011 混淆存款) ----
SKILL_CONSUMER = ComplianceSkill(
    name="消费者保护检测",
    description="检测隐瞒免责条款、诱导退保、银保混淆等侵害消费者权益的行为",
    rule_ids={"R008", "R010", "R011"},
    system_instructions=[
        "你是消费者权益保护合规专家，专精于识别侵害保险消费者合法权益的营销行为。",
        "你的核心能力是识别三类违规：",
        "  A) 隐瞒免责：'什么都赔/全额赔付/无条件理赔' — 隐瞒了免责条款、等待期等限制",
        "  B) 诱导退保：贬低客户现有保单、夸大新产品、隐瞒退保损失",
        "  C) 混淆存款：'像存钱一样/和银行存款一样安全' — 模糊保险与银行存款的区别",
        "审核要求：",
        "1. 如果同一材料中已列明免责条款，则'在合同约定范围内赔付'是合规的",
        "2. 客户主动要求保单检视且告知了退保损失的，不算诱导退保",
        "3. 明确说明'本产品为保险'后再做银行对比的，需看有无误导意图",
        "4. 严禁捏造不存在的 span_id",
        "",
        "evidence_span_ids 选择原则【关键】：",
        "- 只选择包含核心违规词的 span_id（如'什么都赔'、'退保'、'像存钱一样'等）",
        "- 不要选择仅包含上下文、修饰词、连接词的 span",
        "- 如果违规表述跨越多个连续的 span，选择所有相关的 span",
        "- 确保选中的 span 构成最小完整语义单元",
    ],
    few_shots=[
        FewShotExample(
            label="violation",
            text_snippet="我们承诺：出险后什么都赔，全额赔付，无条件理赔，让您没有任何后顾之忧。",
            verdict="violation",
            reasoning="'什么都赔'、'全额赔付'、'无条件理赔'隐瞒了保险产品必然存在的免责条款和赔付条件。"
                      "文中未列明任何免责条款。"
                      "不属于例外条款中'在合同约定范围内赔付'或'已列明免责条款'的情形。违规。",
        ),
        FewShotExample(
            label="violation",
            text_snippet="建议您退保后转购我们的产品。旧保单保障范围窄、性价比低。退保流程简单，我们全程协助。",
            verdict="violation",
            reasoning="该表述同时包含：(1)贬低客户现有保单'保障窄/性价比低'；"
                      "(2)主动建议退保并承诺'全程协助'；(3)未提及退保损失。"
                      "不属于'客户主动要求且告知退保损失'的例外情形。构成诱导退保。",
        ),
        FewShotExample(
            label="compliant",
            text_snippet="本产品为保险合同，非银行存款。在流动性、收益性方面与银行存款存在差异，请知悉。",
            verdict="compliant",
            reasoning="该表述明确说明产品性质为保险合同（非存款），"
                      "并提示了与银行存款的差异。"
                      "属于例外条款中'明确说明产品性质为保险合同'和'客观对比差异'的情形。",
        ),
    ],
)

# ---- 5. 营销合规检测 Skill (R004 薪资诱导, R005 诋毁同业, R012 不当案例) ----
SKILL_MARKETING = ComplianceSkill(
    name="营销合规检测",
    description="检测代理人招聘中的薪资诱导、诋毁同业公司、不当使用客户案例等",
    rule_ids={"R004", "R005", "R012"},
    system_instructions=[
        "你是保险营销合规审查专家，专精于识别代理人招募宣传和营销素材中的违规行为。",
        "你的核心能力是识别三类违规：",
        "  A) 薪资诱导：用具体收入数字诱导应聘 — '月入过万/年薪百万'",
        "  B) 诋毁同业：贬损其他保险公司 — '不靠谱/赔付难'",
        "  C) 不当案例：未授权使用客户信息或编造案例",
        "审核要求【特别重要】：",
        "1. R004 有特殊例外：描述代理人加入保险行业**之前**在其他岗位的收入（如'之前在外企月薪8000元'）不算违规",
        "2. 仅当薪资数字用于描述加入保险行业**之后**的收入/承诺/预期时才算薪资诱导",
        "3. 诋毁同业需区分「客观功能对比」和「主观贬损评价」",
        "4. 客户案例如标注'模拟案例'或经脱敏处理则合规",
        "5. 严禁捏造不存在的 span_id",
        "",
        "evidence_span_ids 选择原则【关键】：",
        "- 只选择包含核心违规词的 span_id（如'月入过万'、'年薪百万'、'不靠谱'等）",
        "- 不要选择仅包含上下文、修饰词、连接词的 span",
        "- 如果违规表述跨越多个连续的 span，选择所有相关的 span",
        "- 确保选中的 span 构成最小完整语义单元",
    ],
    few_shots=[
        FewShotExample(
            label="violation",
            text_snippet="加入即享高薪待遇，月入过万不是梦，优秀代理人年薪可达百万！",
            verdict="violation",
            reasoning="'月入过万'、'年薪可达百万'是对加入保险代理后的收入做具体数字承诺，"
                      "属于薪资诱导。不属于'描述之前其他岗位收入'的例外情形。违规。",
        ),
        FewShotExample(
            label="compliant",
            text_snippet="张经理之前在某外企工作，月薪8000元。后来他选择了保险行业。",
            verdict="compliant",
            reasoning="'月薪8000元'描述的是张经理加入保险行业之前在外企的收入，"
                      "属于例外条款中'描述代理人加入保险行业之前的其他岗位的历史收入'。合规。",
        ),
        FewShotExample(
            label="violation",
            text_snippet="市面上很多保险公司的产品都不靠谱，赔付困难。相比之下，我们完胜同行。",
            verdict="violation",
            reasoning="'不靠谱'和'赔付困难'是对其他保险公司的贬损性评价，"
                      "'完胜同行'是不当竞争表述。不属于'基于公开数据的客观对比'。"
                      "构成诋毁同业违规。",
        ),
    ],
)


# ============================================================
# Skill 注册表 & 路由器
# ============================================================

# 所有 Skill 的注册表
ALL_SKILLS: List[ComplianceSkill] = [
    SKILL_REVENUE,
    SKILL_LANGUAGE,
    SKILL_INTEGRITY,
    SKILL_CONSUMER,
    SKILL_MARKETING,
]

# rule_id → Skill 的快速索引
_RULE_TO_SKILL: Dict[str, ComplianceSkill] = {}
for _skill in ALL_SKILLS:
    for _rid in _skill.rule_ids:
        _RULE_TO_SKILL[_rid] = _skill

# 基于规则语义的自动路由关键词（用于 KBxxxx 全量规则）
_SKILL_KEYWORDS: Dict[str, List[str]] = {
    SKILL_REVENUE.name: [
        "收益", "回报", "年化", "分红", "结算利率", "保值增值", "稳赚", "理财", "投资", "本金", "计息",
    ],
    SKILL_LANGUAGE.name: [
        "绝对", "最好", "第一", "唯一", "顶级", "不当对比", "完胜", "碾压", "远超", "上不封顶", "无上限",
    ],
    SKILL_INTEGRITY.name: [
        "停售", "限时", "抢购", "先到先得", "国家", "监管", "政策", "号召", "银保监", "背书",
    ],
    SKILL_CONSUMER.name: [
        "免责", "理赔", "全额赔付", "无条件", "退保", "减保", "保单", "存款", "存钱", "银行", "现金价值",
    ],
    SKILL_MARKETING.name: [
        "薪", "月入", "年薪", "招募", "代理人", "同业", "诋毁", "案例", "客户信息", "宣传",
    ],
}

_SKILL_BY_NAME: Dict[str, ComplianceSkill] = {s.name: s for s in ALL_SKILLS}

# 兜底 Skill（处理未映射的规则）
DEFAULT_SKILL = ComplianceSkill(
    name="通用合规检测",
    description="通用合规审核（无专项 Few-shot 示例）",
    rule_ids=set(),
    system_instructions=[
        "你是一个专业的保险文本合规审核专家。",
        "你的任务是根据给定的合规规则，对文本片段进行深度审核判定。",
        "你必须严格遵循以下要求：",
        "1. 仔细阅读文本内容和规则定义，特别关注规则中的例外条款",
        "2. 进行充分的逻辑推演（reasoning_cot 必须大于50字），说明判定理由",
        "3. 如果判定为违规，必须从 span 字典中选择证据 span_id，严禁捏造",
        "4. reason_codes 必须从规则卡片提供的候选列表中选择",
        "5. 结合规则的 suggestion_template 生成具体的修改建议",
        "6. 如果无法确定是否违规，verdict 设为 'unsure'",
    ],
)


def _build_rule_text(rule_card: RuleCard) -> str:
    parts = [
        rule_card.rule_name,
        rule_card.violation_definition,
        " ".join(rule_card.keywords),
        " ".join(rule_card.violation_terms),
        " ".join(rule_card.condition_terms),
        " ".join(rule_card.exclusion_terms),
        rule_card.compliant_basis,
        rule_card.violation_basis,
    ]
    return " ".join(p for p in parts if p)


def _infer_skill_from_rule_card(rule_card: RuleCard) -> ComplianceSkill:
    """对未显式映射的规则，按规则语义关键词做自动技能路由。"""
    text = _build_rule_text(rule_card)
    if not text:
        return DEFAULT_SKILL

    scores: Dict[str, int] = {skill.name: 0 for skill in ALL_SKILLS}
    for skill_name, keywords in _SKILL_KEYWORDS.items():
        for keyword in keywords:
            if keyword and keyword in text:
                scores[skill_name] += 1

    best_skill_name = max(scores, key=scores.get)
    if scores[best_skill_name] <= 0:
        return DEFAULT_SKILL
    return _SKILL_BY_NAME.get(best_skill_name, DEFAULT_SKILL)


def get_skill_for_rule(rule: str | RuleCard) -> ComplianceSkill:
    """
    规则路由：
    1) 显式映射（R00x 等固定规则）优先
    2) 未映射规则（如 KBxxxx）走规则语义自动路由
    """
    if isinstance(rule, str):
        skill = _RULE_TO_SKILL.get(rule, DEFAULT_SKILL)
        logger.debug(f"规则 {rule} → 技能: {skill.name}")
        return skill

    explicit = _RULE_TO_SKILL.get(rule.rule_id)
    if explicit is not None:
        logger.debug(f"规则 {rule.rule_id}（显式）→ 技能: {explicit.name}")
        return explicit

    inferred = _infer_skill_from_rule_card(rule)
    logger.debug(f"规则 {rule.rule_id}（自动）→ 技能: {inferred.name}")
    return inferred


def get_skill_stats(rule_cards: Optional[Dict[str, RuleCard]] = None) -> Dict[str, list[str] | int]:
    """
    返回技能路由统计：
      - 未传 rule_cards：返回静态显式映射
      - 传入 rule_cards：返回全量规则的路由计数
    """
    if not rule_cards:
        return {s.name: sorted(s.rule_ids) for s in ALL_SKILLS}

    counter: Dict[str, int] = {s.name: 0 for s in ALL_SKILLS}
    counter[DEFAULT_SKILL.name] = 0

    for card in rule_cards.values():
        skill = get_skill_for_rule(card)
        counter[skill.name] = counter.get(skill.name, 0) + 1

    return counter
