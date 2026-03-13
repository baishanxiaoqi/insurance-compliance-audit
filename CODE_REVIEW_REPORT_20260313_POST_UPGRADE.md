# 综合代码与方案审查报告（升级后复审）

日期：2026-03-13

## 一、审查范围

本次审查基于当前工作区代码，覆盖：

- 项目背景与方案文档：`README.md`
- 主工作流：`src/moderation/workflow.py`
- 核心数据结构：`src/moderation/schemas.py`
- 召回、事实抽取、路由、精判、反证、定位：`src/moderation/stages/`
- 技能与复杂技能：`src/moderation/skills.py`、`src/moderation/complex_skills.py`
- 规则库与配置：`data/rule_cards.json`、`data/rule_cards_new.json`、`src/moderation/config.py`
- 新增升级项：`src/moderation/stages/stage1_9_gate.py`
- 测试：`tests/`

本次未修改任何业务代码，仅输出审查结论。

---

## 二、项目背景、需求与难点理解

### 1. 项目本质

这是一个保险营销文本合规审核系统，目标不是简单分类，而是同时满足：

1. 从 612 条规则中识别违规；
2. 输出字符级原文定位；
3. 生成可执行修改建议；
4. 控制误报；
5. 满足单次审核 ≤ 3 分钟的 SLA。

### 2. 真正难点

当前项目的核心难点仍然是四类：

- **语义歧义**：时态、主体、承诺强度、例外条款；
- **坐标契约**：OCR 修复、规范化、分块后仍要稳定还原到原文；
- **规则规模**：612 条规则不可能直接塞进一个 prompt；
- **成本与准确率平衡**：不能全靠 LLM，也不能只靠关键词。

### 3. 这轮升级的真实目标

从本次代码变化看，这轮升级试图做的是一条**轻量结构化升级路线**：

- 给规则增加结构化字段：`src/moderation/schemas.py:89`
- 给 Stage 1.5 增加锚点抽取：`src/moderation/stages/stage1_5_fact_extract.py:44`
- 新增 Stage 1.9 Gate：`src/moderation/stages/stage1_9_gate.py:1`
- 把 skill prompt 从“宽泛判断”改为“约束式裁决”：`src/moderation/skills.py:57`
- 新增 `decision_basis` 以提升解释性：`src/moderation/schemas.py:178`

方向是正确的，而且和项目既有架构并不冲突。

---

## 三、总体结论

### 结论 1：当前总体方案仍然是正确方向

在当前业务约束下，项目继续采用：

- 确定性预处理与定位；
- 混合召回；
- 双轨判定（base / skill）；
- 反证纠偏；
- span-only 定位；

这仍然是**比纯规则、纯 LLM、纯 RAG 更合理的工程方案**。

### 结论 2：这轮升级提升了“结构化表达能力”，但尚未形成完整闭环

从代码上看，这轮升级的核心问题不是“方向错了”，而是：

> **新增能力大多完成了“模块实现”和“单元测试”，但没有完整进入主运行链路和数据链路。**

所以我的判断是：

- **方案仍然接近最优的工程路线；**
- **但当前版本还不能算升级完全落地；**
- **最关键的剩余工作不是再上更重的技术，而是把现有轻量升级真正接入端到端链路。**

---

## 四、关键审查结论

## [高优先级] Stage 1.9 Gate 已实现，但没有接入主工作流

### 现状

- Gate 模块已实现：`src/moderation/stages/stage1_9_gate.py:241`
- 但工作流实际步骤仍只有：
  - `preprocess`
  - `recall_filter`
  - `fact_extract`
  - `route_dispatch`
  - `deep_judge`
  - `refute_validate`
  - `assemble`
  
  位置：`src/moderation/workflow.py:313`

- `workflow.py` 中没有导入 `stage1_9_gate`，也没有调用 `run_gate()`：`src/moderation/workflow.py:29`
- `run_stage2()` 也没有接收 Gate 输出或 `rule_plan`：`src/moderation/stages/stage2_deep_judge.py:325`

### 影响

这意味着本轮最重要的升级之一，当前仍是**旁路模块**：

- 不会过滤任何组合；
- 不会减少任何 LLM 调用；
- 不会把 `rule_plan` 喂给模型；
- 不会影响主链路判定结果。

换句话说，**Phase 3 在代码层面是“实现了模块”，但在运行层面还没有真正生效。**

### 判断

这是当前版本最重要的架构落地缺口。

---

## [高优先级] 新增的规则结构化字段没有进入规则数据层，路由经济性没有实质改变

### 现状

`RuleCard` 新增了：

- `actor_scope`
- `claim_type`
- `exception_group`
- `evidence_required`
- `route_hint`
- `mutual_exclusion_group`

位置：`src/moderation/schemas.py:93`

但当前生效规则文件仍是：`src/moderation/config.py:41`  
默认路径指向：`data/rule_cards.json`

对 `data/rule_cards.json` 和 `data/rule_cards_new.json` 的静态统计结果：

- 612 / 612 条规则中，上述新字段全部为空；
- `complexity_level` 原始值仍全部缺失；
- `route_strategy` 原始值仍全部缺失；
- `risk_level` 仍全部是 `high`。

基于当前路由逻辑的静态结果仍为：

- `skill = 497`
- `base = 115`

### 影响

这说明这轮“规则结构化升级”主要停留在 **Schema 层**，没有真正进入：

1. 规则生产链路；
2. 规则数据本身；
3. 路由决策经济性。

因此，README 里长期想达到的：

- base 轨 65%
- skill 轨 35%

在当前数据上仍没有落地。

### 判断

当前双轨方案依然对，但**数据层没有跟上结构化设计**，所以这轮升级还没释放出本来该有的成本和稳定性收益。

---

## [中优先级] `decision_basis` 已有 Schema 和 Prompt，但还没有形成端到端解释链路

### 现状

- `JudgmentResult` 已新增 `decision_basis`：`src/moderation/schemas.py:182`
- skill prompt 已要求模型输出 `decision_basis`：`src/moderation/skills.py:173`

但当前仍存在三个缺口：

1. **base 轨没有填 `decision_basis`**  
   `judge_with_base_strategy()` 返回 `JudgmentResult` 时未设置该字段：`src/moderation/stages/stage2_deep_judge.py:82`

2. **Stage 2.5 改判结果没有填 `decision_basis`**  
   反证改判为 compliant 时也未设置该字段：`src/moderation/stages/stage2_5_refute.py:110`

3. **Stage 3 / API 输出没有消费 `decision_basis`**  
   最终输出结构没有保留该信息：`src/moderation/stages/stage3_assemble.py:179`

另外，当前测试中也没有看到对 `decision_basis` 的端到端验证。

### 影响

这意味着“判断依据分类”目前主要仍是：

- prompt 约束；
- schema 承诺；

还不是一条稳定、可追踪、可消费的运行时链路。

### 判断

这是一次正确的解释性升级，但目前完成度还停留在 **半落地状态**。

---

## [中优先级] 新增锚点抽取已经进入主链路，但当前词法设计噪声较大

### 现状

Stage 1.5 的新锚点已经真实进入主链路，并会进入 skill prompt：  
`src/moderation/stages/stage1_5_fact_extract.py:48`  
`src/moderation/skills.py:112`

但当前锚点词表存在明显的“语义混叠”：

- `actor_agent` 包含“我们”：`src/moderation/stages/stage1_5_fact_extract.py:49`
- `actor_company` 也包含“我司 / 公司”：`src/moderation/stages/stage1_5_fact_extract.py:51`
- `actor_third_party` 中混入了“之前 / 曾在”这类更像时间线索的词：`src/moderation/stages/stage1_5_fact_extract.py:52`

### 影响

这类锚点作为“软提示”还可以接受，但如果未来直接用于硬 Gate / 跳过决策，会有两个风险：

1. 主体识别噪声偏高；
2. 时态信号与主体信号混淆。

### 判断

当前锚点更适合做 **prompt 辅助信息**，还不适合直接承担强决策责任。  
如果后续要真正依赖 Gate，建议先把锚点词法做一轮去噪和分层。

---

## [中优先级] 新增的部分结构化字段目前仍未被运行时使用

当前搜索结果表明，以下字段基本仍停留在 Schema 中：

- `route_hint`
- `mutual_exclusion_group`

另外：

- `actor_scope`
- `claim_type`
- `evidence_required`

目前主要只被 `stage1_9_gate.py` 和 prompt 使用，尚未进入：

- Stage 1.8 路由策略；
- Stage 2 结果合并；
- Stage 3 最终去重 / 冲突裁决。

### 影响

这意味着项目已经迈出“结构化规则”的第一步，但还没进入“结构化规则真正驱动运行行为”的阶段。

---

## [低优先级] 文档与实现存在明显漂移

当前文档口径与实现不完全一致：

1. `README.md` 仍写“6 阶段流水线”：`README.md:56`
2. `workflow.py` 文件头也仍写“6 阶段”：`src/moderation/workflow.py:4`
3. `create_workflow()` 描述甚至写成“5 阶段”：`src/moderation/workflow.py:311`
4. 升级总结文档里将 Stage 1.9 视为已进入流水线，但代码实际未接入：`LIGHTWEIGHT_UPGRADE_SUMMARY_20260313.md:207`

### 判断

这不影响运行正确性，但会影响：

- 方案评审；
- 新成员理解；
- 后续升级优先级判断。

---

## 五、方案是否最优

### 我的判断

**当前方案仍然是这个项目在现实约束下最合理的主方案，但当前版本还不是“全局最优状态”。**

### 为什么仍然是最合理的主方案

因为它继续保留了三个最重要的正确设计：

1. **确定性资产先行**  
   span-only 定位和坐标映射仍是整个系统最重要的正确性底座；

2. **双轨处理而不是单模型裁决**  
   base 轨保留了成本与稳定性优势，skill 轨处理复杂语义；

3. **反证纠偏**  
   Stage 2.5 继续把误报控制放在核心位置，而不是只追求召回。

### 为什么现在还不能算“最优状态”

因为这轮升级的最高价值部分还没有真正落到运行面：

- Gate 没接进工作流；
- 结构化规则没有进入数据层；
- 解释性字段没有进入最终输出链路；
- 路由占比和成本结构几乎没变。

换句话说：

> **方案本身接近最优，但这轮升级的落地完整度还没到最优状态。**

---

## 六、仍值得继续做的升级点

这里我只列“轻量、务实”的升级点，不建议走重平台路线。

### 1. 第一优先级：把 Gate 真正接入主链路

优先级最高，不建议继续后置。

最小落地要求：

- 工作流接入 Stage 1.9；
- `run_stage2()` 接收 Gate 输出；
- `rule_plan` 真正进入 skill prompt；
- `should_skip` / `priority` 真正影响调度。

### 2. 第二优先级：把规则结构化字段补进规则数据

当前新字段都在 Schema 里，但规则数据里为 0。  
下一步最值得做的是在规则生成链路中补齐：

- `actor_scope`
- `claim_type`
- `evidence_required`
- `route_hint`

只要这一步没做，结构化升级就只能发挥一半价值。

### 3. 第三优先级：让 `decision_basis` 成为真正的运行时字段

建议至少做到：

- base 轨填值；
- refute 改判填值；
- API 输出可选保留；
- 增加端到端测试。

### 4. 第四优先级：对锚点词法做一轮去噪

不用做重型 NER，只要先把明显混叠项拆开，例如：

- 时间词不要混入主体词；
- “我们 / 我司 / 公司”做更谨慎的角色区分；
- 把 actor / time / tone 的词表边界收紧。

---

## 七、验证结果

已执行：

```bash
python -m pytest -q
```

结果：

- `80 passed`
- `3 warnings`

warnings 仍主要来自 `jieba/pkg_resources` 的 Python 3.13 兼容性提示，不属于本次主链路正确性问题。

---

## 八、最终结论

本轮升级后的项目，整体判断如下：

1. **方案方向依然正确**，不建议推翻重做；
2. **当前主架构仍是现实约束下的优选方案**；
3. **这轮升级已经把结构化升级的框架搭起来了**；
4. **但最关键的升级收益还没有完全进入生产链路**；
5. **下一步最值得做的不是更重的技术，而是把已新增的轻量结构化能力真正接入运行路径。**

如果只用一句话概括：

**项目方案本身依旧优秀，但当前版本的升级更多完成了“能力铺设”，还没有完全完成“端到端生效”。**
