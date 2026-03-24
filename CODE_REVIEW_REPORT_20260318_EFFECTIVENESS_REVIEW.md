# 项目代码审查结论（2026-03-18）

## 1. 审查范围

- 审查对象：当前主流程代码、Stage 2/Stage 3 判定与组装链路、最新 `smoke` 评估结果
- 审查目标：判断当前版本是否已经接近“审核效果最优”，重点看**违规识别效果**，不看效率
- 本次重点核对你的 3 个判断：
  1. 是否应该把“违规提取”和“批注建议生成”拆开
  2. Agent 是否已经加入 CoT/推理过程
  3. 为什么 `smoke` 样本 `违规_0004` 会抽出“保险可以提供补偿或保障”这种明显合规的文本

---

## 2. 总结论

当前版本已经是**方向正确、效果明显提升的轻量升级版**，但从“精准识别保险违规内容”的角度看，**还不能算最优**。

这次复核后，我认为当前最主要的问题已经不再是“召回框架”或“路由框架”本身，而是以下 3 个更贴近效果的问题：

1. **违规提取结果和业务展示建议仍然耦合在一起**
2. **当前已经有显式推理字段，但还没有真正形成“先推理计划、再裁决”的独立 deliberation 机制**
3. **用户可见的违规片段质量，当前仍然被 Stage 2 的证据 span 选择质量直接决定**

也就是说：现在项目最大的优化点，不是再去大改主流程，而是把**判定结果层**和**展示表达层**拆开，并进一步收紧 **evidence span** 的产出质量。

---

## 3. 对你提出的 3 个问题的判断

### 3.1 问题一：是否应该把“违规提取”和“输出批注建议”拆成两步

**结论：这个判断是对的，而且是当前最值得做的结构优化点之一。**

### 当前代码现状

当前 `Stage 2` 的 `JudgmentResult` 同时承担了两类职责：

- **审核职责**：`verdict`、`reasoning_cot`、`evidence_span_ids`、`reason_codes`
- **展示职责**：`draft_suggestion`

对应代码位置：

- `JudgmentResult` 定义：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/schemas.py:149`
- `draft_suggestion` 字段：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/schemas.py:174`
- Stage 2 直接生成建议：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_deep_judge.py:118`
- Stage 3 直接透传建议：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage3_assemble.py:179`
- `suggestion=judgment.draft_suggestion`：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage3_assemble.py:187`

### 为什么这会影响效果

从产品角度看，“识别出哪里违规”与“怎么给业务人员写修改建议”其实是两套目标：

- 前者追求**稳定、可验证、可评估**
- 后者追求**可读性、业务表达、展示风格**

这两件事现在绑在一起，会带来 3 个问题：

1. **评估口径混杂**  
   当前我们很难把“判定错了”与“建议写得不好”彻底分开评估。

2. **展示格式迭代成本高**  
   只要业务想改建议话术、语气、模板，就会连带触碰精判输出结构。

3. **模型注意力被分散**  
   Stage 2 本应聚焦“当前 rule 是否成立 + 最小证据是什么”，现在还要同时写业务建议，容易挤占判定注意力。

### 审查判断

这不是“可做可不做的小优化”，而是一个**能直接提升审核效果稳定性**的结构分层点。

**建议方向**：

- 先固定一个“审核真值层”：`verdict + reason_codes + decision_basis + evidence_span_ids + categories`
- 再单独生成“业务展示层”：`批注文案 / 修改建议 / 对外解释`

我认为这是当前最值得排进后续优化的结构点之一。

---

### 3.2 问题二：Agent 是否没有加入 CoT，是否应该加入

**结论：你的判断只有一半对。**

更准确地说：

- **项目里并不是“没有 CoT”**
- 但**目前还没有一个独立的、计划式的 deliberation 过程**

### 当前代码现状

当前 Stage 2 的 Skill Prompt 明确要求模型输出 `reasoning_cot`：

- `reasoning_cot` 字段定义：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/schemas.py:158`
- Prompt 输出要求中明确要求 `reasoning_cot`：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/skills.py:180`
- Prompt 里还有明确的“裁决优先级”：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/skills.py:140`
- `judge_with_skill_strategy()` 实际就是按这个 Prompt 去生成结构化判定：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_deep_judge.py:142`

### 所以问题到底在哪

当前项目的推理方式更接近：

> 单次 Prompt 内要求模型“边思考、边输出结构化结果”

而不是：

> 先做一轮内部审查计划 / 证据核对 / 例外排查，再进入最终裁决

所以如果你说“完全没有 CoT”，这个说法**不准确**；  
但如果你说“还没有独立的 plan-first / deliberate-first 策略”，这个判断**是成立的**。

### 审查判断

我认为**适度增强 deliberation 策略，确实有机会继续提升效果**，但要注意边界：

#### 适合增强的方向

- 先列“是否存在直接违规主张”
- 再列“是否存在明确例外/否定/主体不匹配”
- 最后再给 verdict 与 evidence

也就是把现在 Prompt 里的“裁决优先级”，从文字说明进一步升级成更强约束的**判定计划**。

#### 不建议的方向

- 不建议为了追求 CoT 而让模型输出更长、更自由的思维过程
- 不建议把对业务无价值的长推理直接暴露到最终结果里

### 最终判断

这个点的本质不是“补一个 CoT 字段”，因为字段已经有了；  
真正的优化点是：**把当前单次裁决式推理，升级成更强的 plan-first 裁决流程**。

所以：

- **“没有 CoT”** → 不准确
- **“应该加强推理过程设计，这会提升效果”** → 正确

---

### 3.3 问题三：为什么 `违规_0004` 会抽出“保险可以提供补偿或保障”

**结论：这个现象确实是当前效果上的问题，但根因不在 Stage 3，而在 Stage 2 的“规则对齐 + 证据 span 选择”。**

### 现象确认

在最新 `smoke` 结果里，`sample_id = "违规_0004"` 的输出确实包含了这段文本：

- 结果文件：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/benchmark/reports/smoke_run_20260317_p0/raw_results.jsonl:1`
- 其中一个被抽出的片段是：`保险可以提供补偿或保障`

### 为什么会这样

这条样本当前被命中了两个规则：

1. `KB0017`：金融用语混淆 / 本金计息类
2. `KB0530`：转嫁风险

真正异常的是 `KB0017` 这条判定。  
从输出看，模型把下面这类中性或偏合规的功能性表述，也一起当成了 `KB0017` 的证据：

- `保险作为一种金融产品，其价值在于它能提供财务保障和风险管理功能`
- `保险可以提供补偿或保障`
- `这在一定程度上是对个人资金安全的一种间接保障`

### 根因判断

这里至少有两层问题：

#### 问题 A：规则语义对齐偏宽

`KB0017` 的规则重点，本质是：

> 直接把保险宣传成具有投资理财/存款/本金/计息属性

但这条样本里，模型把“金融产品”“财务保障”“间接保障”也纳入了同一违规解释里，说明它在做的是一种**语义泛化式归因**，而不是严格抓“保险被宣传成理财/存款”的最小违规主张。

对应规则卡可见：

- `KB0017` 定义来自：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/data/rule_cards.json:1`

也就是说，这不是 Stage 3 在乱定位，而是 Stage 2 先把不该归进来的 span 选进来了。

#### 问题 B：evidence span 选择仍然偏宽

Stage 3 当前是一个**确定性组装器**，它只会使用 `evidence_span_ids` 做还原：

- Stage 3 span-only 定位：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage3_assemble.py:81`
- 只按 `evidence_span_ids` 组装：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage3_assemble.py:169`

所以：

- **Stage 3 没有凭空造出“保险可以提供补偿或保障”**
- 它只是忠实地把 Stage 2 选中的 span 还原出来

当前真正需要优化的是：

> Stage 2 对“最小违规证据”的选择还不够稳，仍会把相邻的中性功能描述也带进去

### 审查判断

这个 badcase 很有代表性，它说明当前项目的一个核心瓶颈已经很清楚了：

> **不是系统不会判违规，而是系统在“为什么违规、具体哪一句违规”这件事上还不够收敛。**

这会直接影响业务侧体验，因为业务会看到“明明是合规描述，为什么也被圈出来”。

---

## 4. 当前版本是否已经最优

**结论：还不是最优，但已经进入“后半程优化阶段”。**

我认为当前版本已经完成了前半程最难的部分：

- 路由框架已经基本站稳
- Skill Prompt 已比旧版明显更有约束
- `smoke` 的 Precision / Recall 已比之前显著提升

但从“业务真正信任审核结果”的角度看，项目还差最后一层关键打磨：

1. **判定真值层与展示层彻底解耦**
2. **把 evidence span 选择继续收紧到“最小违规主张”**
3. **把当前已有的 reasoning，升级成更强的 plan-first 裁决结构**

在这三点没有完成之前，我不建议把当前版本定义为“最优版”。

---

## 5. 我认为当前最值得做的优化优先级

### P0：拆分“违规提取”和“业务批注建议”

这是当前最应该做的结构优化。  
理由不是为了代码好看，而是为了：

- 提升审核层可评估性
- 降低展示层迭代成本
- 让 Stage 2 更聚焦“判定 + 证据”

### P0：继续压缩 evidence span 的边界

当前业务侧最容易产生不信任感的问题，就是：

> 判对了规则，但圈出来的文本不够准

这会直接削弱项目效果感知。

### P1：把当前“reasoning_cot”升级为更强的计划式裁决

不是增加更长的解释，而是增加更强的裁决顺序：

- 先看直接违规主张
- 再看例外/否定/主体
- 最后再给 verdict 与 span

### P1：把建议文案的评估从审核评估中拆开

建议把后续 benchmark 指标拆成两层：

- 审核效果：是否判对、类别是否判对、位置是否圈对
- 展示效果：建议是否可读、是否可执行、是否符合业务口径

---

## 6. 最终一句话结论

你这次提出的 3 个问题里：

- **第 1 个判断是对的，而且很关键**
- **第 2 个判断方向对，但表述要修正：不是没有 CoT，而是没有独立 deliberation**
- **第 3 个现象判断是对的，根因主要在 Stage 2 的规则对齐和证据 span 选择，不在 Stage 3**

所以我的最终结论是：

> 当前项目已经不是“框架级问题”，而是进入“判定真值层 / 证据层 / 展示层分离”的精修阶段；从审核效果看，当前版本还不是最优，但优化方向已经非常明确。
