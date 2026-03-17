# Debug 审查报告：路由与 Stage 2 Prompt

## 审查范围

- `src/moderation/stages/stage1_8_route_dispatch.py`
- `src/moderation/stages/stage2_deep_judge.py`
- `src/moderation/skills.py`
- `src/moderation/schemas.py`
- `data/rule_cards.json`
- 参考最近评测结果：`benchmark/reports/smoke_run_20260317_kb_refresh/summary.json`

## 结论摘要

### 结论 1：`decide_route()` 里看到 `rule_card.risk_level` 基本全是 `high`，这个观察是对的

- 当前不是“代码里没有 base 轨”，而是**知识库元数据让 risk-based 路由几乎失去区分能力**
- 也就是说：**base 轨还在，但 `risk_level` 这个维度已经退化成常量**

### 结论 2：`judge_with_skill_strategy()` 的 Prompt 设计确实存在问题

- 不是单点语法问题，而是**Prompt 结构整体偏向保守裁决**
- 这会把模型推向 `compliant / unsure`，对当前项目最重要的“违规识别召回”不利

### 结论 3：这两个问题和当前效果是能对上的

- 最新 `smoke` 结果：`Recall=0.4375`、`FN=9`
- 当前更像是“误报压下来了，但召回被压住了”

---

## 一、关于 `decide_route()`：是不是没有 base 级别

## 代码事实

`decide_route()` 的优先级是：

1. `route_strategy == base/skill`
2. `complexity_level == complex`
3. `risk_level == high` 且有结构化约束 → `skill`
4. 有复杂信号且有结构化约束 → `skill`
5. 否则 → `base`

对应位置：

- `src/moderation/stages/stage1_8_route_dispatch.py:42`
- `src/moderation/stages/stage1_8_route_dispatch.py:50`
- `src/moderation/stages/stage1_8_route_dispatch.py:58`
- `src/moderation/stages/stage1_8_route_dispatch.py:63`
- `src/moderation/stages/stage1_8_route_dispatch.py:67`

## 当前知识库的静态分布

基于当前 `data/rule_cards.json` 的静态统计：

- 规则总数：`534`
- `risk_level=high`：`534`
- `route_strategy=auto`：`534`
- `route_strategy=base`：`0`
- `route_strategy=skill`：`0`
- `complexity_level=complex`：`0`
- 含 `exceptions/condition_terms/exclusion_terms` 的规则：`446`
- 不含上述结构化约束的规则：`88`

进一步按 `decide_route(rule_card, None)` 静态模拟：

- `skill`：`446`
- `base`：`88`

也就是：

- **base 轨并没有消失**
- 但当前 base 轨只剩 `default_base` 这个兜底入口
- `risk_level`、`route_strategy`、`complexity_level` 这三类“设计上应该用于分层路由”的元数据，当前几乎没有真实区分力

## 影响判断

这会导致两个结果：

### 1. 路由语义退化

从代码设计看，系统原本想要的是“多维路由”：

- 显式路由
- 复杂度路由
- 风险路由
- 事实信号路由

但当前知识库下，路由实际上退化成了：

- **有结构化约束 → skill**
- **无结构化约束 → base**

这和“根据规则复杂度/风险度自动分发”的设计目标已经不完全一致。

### 2. base 轨比例会明显低于设计预期

文档预期是 base 轨约 `65%`、skill 轨约 `35%`。

但当前知识库静态上已经是：

- base：`88 / 534 ≈ 16.5%`
- skill：`446 / 534 ≈ 83.5%`

而真实运行时，如果召回出的规则又更多集中在“带条件/排除/例外”的规则上，实际 base 比例还会更低。

## 审查结论

- 你的判断**方向是对的**
- 更准确地说，不是“没有 base 级别”，而是：
  - **base 轨还在**
  - **但当前知识库让路由分层明显失真**
  - `risk_level` 现在基本不再是有效路由信号

## 补充观察

`schemas.py` 中已经有 `route_hint` 字段，但当前代码没有消费它：

- `src/moderation/schemas.py:122`

这意味着你即使后续在知识库里补了“更偏 base / 更偏 skill”的提示，当前路由逻辑也不会使用它。

---

## 二、关于 `judge_with_skill_strategy()`：Prompt 是否有问题

## 代码事实

Prompt 的组装链路是：

- `judge_with_skill_strategy()` 先做一次 `evaluate_rule_on_text()`
- 然后把 `deterministic_report`、`chunk_fact`、规则依据、few-shot、span 字典等一起塞进 `skill.build_prompt()`
- 最后再交给 Agent

对应位置：

- `src/moderation/stages/stage2_deep_judge.py:174`
- `src/moderation/stages/stage2_deep_judge.py:178`
- `src/moderation/skills.py:46`
- `src/moderation/skills.py:128`

## 我确认到的主要问题

### 问题 1：Prompt 明显偏向保守裁决，容易压低召回

核心约束里有多条都在强化“不要报违规”：

- 主体/时态/否定/例外 → 优先 `compliant` 或 `unsure`
- 证据不足 → `unsure`
- 无法稳定结论 → `unsure`
- 证据不足时优先保守，不要强行 `violation`

对应位置：

- `src/moderation/skills.py:132`
- `src/moderation/skills.py:133`
- `src/moderation/skills.py:134`
- `src/moderation/skills.py:136`
- `src/moderation/skills.py:138`

这类规则本身并不是错的，但当前组合起来的效果是：

- 对误报控制有利
- 对召回不利

结合当前效果看，这种 Prompt 倾向已经反映到结果里了：

- `Precision=0.7778`
- `Recall=0.4375`

这说明当前模型更像“宁可放过，也不轻易报违规”。

### 问题 2：Skill Prompt 被 `deterministic_report` 过早锚定

在 skill 轨中，代码仍然会先执行一次规则引擎，并把结果塞进 Prompt：

- `src/moderation/stages/stage2_deep_judge.py:175`
- `src/moderation/skills.py:118`
- `src/moderation/skills.py:167`

这会带来一个实际问题：

- skill 轨本来就是为了解决“规则引擎不够”的复杂场景
- 但模型在看到 `has_violation_hit=False`、`hard_block=False`、`summary=...` 之后，很容易被前置结果锚定
- 尤其在当前 Prompt 本身已经偏保守的情况下，这种锚定更容易把结果推向 `compliant / unsure`

也就是说：

- `deterministic_report` 在这里不是纯粹的辅助信息
- 它已经实质上成为了一个**前置倾向信号**

对复杂违规、软表达违规、知识弱覆盖违规来说，这会直接伤召回。

### 问题 3：Prompt 把太多异质信息堆在一起，主判定焦点被稀释

当前 Prompt 同时包含：

- chunk 原文
- 规则定义
- 例外条款
- 结构化关键词
- 合规依据 / 违规依据
- 合规 case / 违规 case
- 结构化 facts
- 规则引擎前置结果
- few-shot 示例
- 详细输出格式

对应位置基本集中在：

- `src/moderation/skills.py:67`
- `src/moderation/skills.py:76`
- `src/moderation/skills.py:112`
- `src/moderation/skills.py:118`
- `src/moderation/skills.py:128`

这会带来两个副作用：

- 模型更容易“参考资料过载”
- 真正决定这次判定的关键信号，反而不够突出

特别是当 `compliant_basis` 和 `violation_basis` 很长、case 很多时，Prompt 会变得更像“知识包展示”，而不是“当前这条规则的约束式裁决单”。

### 问题 4：Prompt 术语和真实输入不完全对齐

Prompt 明确写了：

- “你只能使用输入中给出的事实、锚点、规则计划和 span_id”

对应位置：

- `src/moderation/skills.py:132`

但当前实际输入里：

- 有 `chunk_fact`
- 有 `deterministic_report`
- 有 span 字典

却没有一个真正显式的：

- `rule plan`
- `gate result`
- `anchor plan`

这会产生一个问题：

- Prompt 说模型可以依赖“规则计划/锚点”
- 但实际没有把这类结构化对象稳定送进去

从 Prompt 契约角度看，这是**描述与输入不一致**。

### 问题 5：输出要求里有一部分字段属于“开放分类”，容易漂

Prompt 要求输出：

- `primary_category`
- `secondary_category`

对应位置：

- `src/moderation/skills.py:201`

Schema 虽然允许这两个字段存在：

- `src/moderation/schemas.py:201`
- `src/moderation/schemas.py:206`

但 Prompt 并没有提供一个明确可选列表或映射表，而是只给了示例名称。

结果就是：

- 模型容易自由命名
- 离线评测时类别更容易漂移
- 同一个规则在不同样本上可能输出不同风格的 category

这个问题不会直接让 verdict 错掉，但会让“类别稳定性”和后续评测解释性变差。

### 问题 6：Prompt 对 `evidence_texts` 的要求过重，容易分散注意力

Prompt 要求模型：

- 选最小 `evidence_span_ids`
- 同时逐字摘录“最短连续子串”的 `evidence_texts`

对应位置：

- `src/moderation/skills.py:179`
- `src/moderation/skills.py:189`

但从项目总体设计看，真正可靠的定位主契约是 `span_id`，Stage 3 也主要依赖 `span_id`。

因此这里的问题是：

- 模型为了满足“最短连续子串”这类精细摘录要求，会额外消耗注意力
- 对 verdict 判定本身没有明显帮助
- 还会放大“证据提取难于判定本身”的问题

---

## 三、综合判断

## 1. 关于路由

- 代码层面：base 轨没有消失
- 知识库层面：当前路由元数据几乎已经退化
- 工程层面：当前系统并不真的在做“多维双轨分发”，而更像“约束规则上 skill、其余 default_base”

## 2. 关于 Prompt

- 你的直觉是对的，Prompt 不是“有点啰嗦”这么简单
- 它当前的主要问题是：
  - **保守偏置过强**
  - **被规则引擎前置信号锚定**
  - **输入块过多，主裁决焦点不够突出**
  - **术语与真实输入不完全对齐**
  - **开放分类输出缺少词表约束**

## 3. 和项目效果的关系

这两个问题放在一起看，会自然导向当前这种结果：

- 误报下降
- 召回不足
- 复杂违规 / 委婉违规 / 软表达违规容易被放过

---

## 四、最终结论

### 对问题 1 的回答

- **不是没有 base 级别**
- **而是当前知识库让 base / skill 的分流逻辑明显塌缩**
- 你在 Debug 时看到 `risk_level` 基本全是 `high`，这个现象本身就说明路由元数据已经失去区分力

### 对问题 2 的回答

- **是的，`judge_with_skill_strategy()` 的 Prompt 设计存在实质性问题**
- 主要不是“写法不优雅”，而是它会把模型推向保守输出，并受到规则引擎前置结果的锚定
- 这和当前项目“精准识别违规内容”的核心目标并不完全一致

---

## 五、建议优先级（只给结论，不改代码）

### P0

- 先复核知识库里的 `risk_level / route_strategy / complexity_level` 填充策略是否仍符合当前双轨设计目标

### P0

- 重新审视 skill Prompt 的裁决方向：当前更像“误报抑制 Prompt”，不完全像“违规识别 Prompt”

### P1

- 检查 `deterministic_report` 是否应该以当前强度进入 skill Prompt；它现在更像“前置判官”，而不是“辅助证据”

### P1

- 检查 `primary_category / secondary_category` 是否需要明确词表，否则类别输出会持续漂移

### P1

- 检查 `route_hint` 这类新元数据是否应该真正接入路由，否则知识库升级无法转化为路由效果
