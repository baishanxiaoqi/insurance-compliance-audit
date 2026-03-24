# 规则提证 + 轻量 LLM 最终分类改造方案

## 1. 目标

本次改造的目标不是继续增强“关键词直判”，而是把当前流水线调整为：

- 规则引擎负责 **提证据**
- Gate 负责 **打前置信号**
- 轻量 LLM 负责 **最终违规分类**

核心原则：

- 不再让策略A（base）直接输出最终 `violation`
- 所有“命中证据”的候选，都必须再经过一层轻量 LLM 做最终分类
- Gate 不再作为强裁决器，而是尽量退化为“前置提示器”

---

## 2. 当前问题判断

### 2.1 Gate 是什么

当前 `Stage 1.9 Gate` 是一个纯代码前置闸门，输入是 `(chunk, rule)`，输出是：

- `gate_signals`
- `should_skip`

其主要职责是：

- 判断是否缺少必要锚点
- 判断是否处于明显例外或中性语境
- 在高置信度情况下直接让 `Stage 2` 跳过该候选

关键代码位置：

- `src/moderation/stages/stage1_9_gate.py`
- `src/moderation/stages/stage2_deep_judge.py:619`

### 2.2 Gate 是否是当前低召回的主因

结论：**是影响因素之一，但不是唯一主因。**

原因：

- 当前 `Stage 1` 在 filter 失败时，已经改为保留混合召回候选全集，不会因为 filter 异常直接裁掉候选
- 这次跑批中存在大量样本进入 `Stage 2` 深判，说明不是单纯“候选没召回到”
- 但 Gate 会对以下几类场景直接做 skip：
  - `financial_confusion_missing_anchor`
  - `financial_confusion_negative_subject`
  - `guaranteed_return_missing_anchor`
  - `responsibility_exaggeration_missing_anchor`
  - `neutral_knowledge`

所以当前低召回更像是三部分叠加：

1. 少量样本在 `Stage 1` 召回不全
2. 一部分样本被 `Gate` 过早跳过
3. 更多样本是进入 `Stage 2` 后被保守判成 `compliant/unsure`

### 2.3 策略A 当前的根本问题

当前 base 轨在 `judge_with_base_strategy()` 中，规则引擎会直接输出最终 `JudgmentResult`：

- `hard_block -> compliant`
- 通过结构化约束校验 -> `violation`

这意味着 base 轨本质上仍是：

- 违规词命中
- 条件词/排除词校验
- 前后缀过滤
- 直接生成最终违规结论

这会带来两个风险：

1. 对复杂语义边界不稳，容易退化成“关键词硬判”
2. base 轨输出的 `violation` 没有经过 LLM 的最终语义确认

对于以下类别，这个问题尤其明显：

- `financial_confusion`
- `comparison_or_absolute`
- `responsibility_exaggeration`
- `agent_title_violation`

---

## 3. 改造方向

### 3.1 总体思路

把当前的“规则引擎最终裁决”改成“规则引擎先提证，LLM 再分类”。

改造后的职责：

- `Stage 1`：召回候选
- `Stage 1.8`：路由
- `Stage 1.9`：只打 Gate 信号，不轻易跳过
- `Stage 2A`：规则提证 / 结构化证据构建
- `Stage 2B`：轻量 LLM 最终分类
- `Stage 2.5`：override / refute
- `Stage 2.7`：建议生成
- `Stage 3`：定位组装

### 3.2 新原则

- 规则引擎不再直接输出最终 `violation`
- 所有命中证据的候选，都必须进入轻量 LLM 做最终分类
- 没有任何证据命中的候选，可以在纯代码层淘汰
- Gate 对“已有证据命中”的候选，不应直接 skip

---

## 4. 具体设计

### 4.1 新增 Stage 2A：证据提取层

新增一个中间层，输出统一的 `EvidenceBundle`

建议结构：

- `rule_id`
- `chunk_id`
- `has_positive_evidence`
- `has_hard_block`
- `violation_terms_hit`
- `condition_terms_hit`
- `exclusion_terms_hit`
- `blocked_by_prefix_suffix`
- `evidence_span_ids`
- `evidence_texts`
- `gate_signals`
- `chunk_fact_signals`
- `route_strategy`
- `skill_type`
- `evidence_strength`

其中：

- base 轨：由规则引擎生成 `EvidenceBundle`
- skill 轨：由锚点/事实信号/规则卡片生成弱证据包

这样后面的 LLM 不再面对“裸文本 + 裸规则”，而是面对“规则 + 文本 + 已结构化证据”

### 4.2 新增 Stage 2B：轻量 LLM 分类层

该层负责做最终裁决：

- 输入：
  - 单条规则
  - chunk 原文
  - `EvidenceBundle`
  - Gate 信号
  - 规则卡片的主次类别和审查点信息
- 输出：
  - `verdict`
  - `decision_basis`
  - `primary_category`
  - `secondary_category`
  - `audit_point_id`
  - `evidence_span_ids`
  - `reasoning_cot`

分类器要回答的核心不是“有没有词命中”，而是：

- 这些证据是否构成 **直接保险违规表达**
- 是否只是中性说明、禁止性表述、培训材料、负面案例说明
- 规则引擎给出的命中是否真的是本规则下的有效证据

### 4.3 策略A 的新定义

策略A 不再是“规则引擎直判”，而改成：

- `base_extract`: 规则引擎提证
- `base_verify_llm`: 轻量 LLM 分类

也就是说，base 轨仍然保留：

- 快速
- 低成本
- 结构化

但不再直接承担最终违规裁决。

### 4.4 Gate 的调整建议

当前 Gate 过强，建议改成“两级制”：

#### 一级：提示型信号

只输出：

- `negative_hint`
- `exception_hint`
- `neutral_hint`
- `missing_anchor_hint`

不直接跳过。

#### 二级：极少数强跳过

只有以下条件同时满足时才允许 skip：

- `has_positive_evidence = False`
- Gate 置信度高
- 且属于明显非保险/非营销/明确例外语境

建议：对以下类别，默认不允许 Gate 在“有证据命中”时 skip：

- `financial_confusion`
- `comparison_or_absolute`
- `responsibility_exaggeration`

---

## 5. Prompt 设计建议

### 5.1 轻量 LLM 分类器 Prompt 目标

Prompt 不要问：

- “文本是否可能违规”

而要问：

- “基于给定证据，这段话是否已经形成了该规则所定义的直接违规宣传”

### 5.2 推荐判定框架

轻量分类器按固定顺序判断：

1. 规则引擎证据是否成立
2. 证据主体是否直接指向保险产品/保险代理人
3. 是否属于负面说明、禁令、培训、解读、客观介绍
4. 是否达到“直接违规宣传”门槛
5. 若违规，证据最小片段是什么

### 5.3 输出要求

必须保持严格结构化输出：

- `verdict`
- `decision_basis`
- `primary_category`
- `secondary_category`
- `evidence_span_ids`
- `reasoning_cot`

不要再让 LLM 直接生成业务展示建议，建议继续留在 `Stage 2.7`

---

## 6. 数据结构改造建议

### 6.1 保留

- `ChunkCandidates`
- `RoutedPair`
- `JudgmentResult`

### 6.2 新增

建议新增：

- `EvidenceBundle`
- `EvidenceStatus`
- `GateContext`

### 6.3 JudgmentResult 的来源变化

改造后 `JudgmentResult` 不再由 base 轨直接生成，而统一由“最终分类层”生成。

这样可以保证：

- base / skill 两条轨道的最终结论口径统一
- benchmark 不再出现“base 是硬规则口径、skill 是 LLM 口径”的混杂问题

---

## 7. 验证方案

为了确认 Gate 是否真的是低召回主因，建议新增一套诊断字段：

- `stage1_recalled`
- `stage1_filter_kept`
- `gate_skipped`
- `gate_signal_types`
- `evidence_positive`
- `evidence_strength`
- `classifier_called`
- `classifier_verdict`
- `final_verdict`
- `drop_reason`

然后把每条漏报拆成以下类型：

1. `retrieval_miss`
2. `filter_drop`
3. `gate_skip`
4. `no_evidence`
5. `classifier_false_negative`
6. `override_reverted`
7. `runtime_error`

这一步非常关键，否则后续优化会继续混在一起看。

---

## 8. 为什么这版方案更适合当前项目

### 8.1 相比现状

优点：

- 避免 base 轨退化成关键词硬判
- 提升复杂边界类目的最终判定质量
- 保留规则引擎的高可解释性和高召回价值
- 最终裁决口径统一

代价：

- 比当前 base 轨更慢
- 需要新增一层轻量 LLM 调用

### 8.2 相比“所有候选都直接走大模型”

优点：

- 成本更低
- 速度更可控
- 仍能利用规则引擎把证据和边界先结构化

所以更合理的做法不是“所有候选都走重模型”，而是：

- **先提证**
- **再对有证据的候选走轻量分类**

---

## 9. 实施顺序

### P0

1. 新增 `EvidenceBundle`
2. base 轨从“直判”改为“提证”
3. 新增 `base_verify_llm`
4. Gate 从强 skip 改成 hint-first
5. benchmark 增加 drop reason 统计

### P1

1. skill 轨也统一接入证据包
2. 统一 base / skill 的最终分类器输出
3. 强化 `financial_confusion` / `comparison_or_absolute` 两类的分类 prompt

### P2

1. 对 `responsibility_exaggeration` 建立专门 evidence schema
2. 建立漏报归因看板
3. 建立“Gate 开/关、hint/skip”对照评测

---

## 10. 最终建议

结论明确：

- `Gate` 需要降权，不能继续承担过强的“提前裁决”职责
- `策略A` 必须升级，不能再让规则引擎直接输出最终违规
- 更合理的主链路应是：

`规则引擎提证 -> 轻量 LLM 最终分类 -> override -> 输出`

这是当前项目在“审核效果优先”目标下，最值得优先落地的一次架构修正。
