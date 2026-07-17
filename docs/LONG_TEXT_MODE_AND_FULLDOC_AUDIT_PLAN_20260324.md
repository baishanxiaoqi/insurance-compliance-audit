# 长文本模式 + 全文审核审查点并行子流程升级方案

日期：2026-03-24

## 1. 方案目标

这份方案解决两个问题：

1. **长文本模式升级方案**
   - 目标不是压缩成本，而是**优先保证 5000 字级文本的审核效果**
   - 重点解决当前 `chunk` 过小导致的语义割裂问题

2. **在 Workflow 中接入一类“全文审核”的审查点**
   - 这类审查点不适合按单个 `chunk × rule` 审核
   - 例如：**引用第三方数据但未给数据来源**
   - 采用“skills 模式”的独立子流程，与主流程并行
   - 最后接入 `Stage 2.7 suggestion` 与 `Stage 3 assemble`

本方案遵循两个原则：

- **不为了提速牺牲效果**
- **不重构主流程，只做增量接入**

---

## 2. 当前问题定位

## 2.1 长文本问题的根因

当前流水线是标准的 `chunk-first` 架构：

- Stage 1 逐 chunk 召回/filter：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/workflow.py:153`
- Stage 1.8 逐 `(chunk, rule)` 路由：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage1_8_route_dispatch.py:93`
- Stage 2 逐 `(chunk, rule)` 精判：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_deep_judge.py:715`

当前默认切块参数：

- `CHUNK_SIZE=300`：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/config.py:213`
- `CHUNK_MIN_SIZE=80`：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/config.py:214`

对短文案这套策略是合理的，但对 `5000` 字长文有两个明显问题：

1. 一个完整审查点的前置条件、主张、限定语、免责语可能被切散
2. 后续 `skill` prompt 主要看当前 chunk，不是按全文证据组来裁决

## 2.2 当前没有真正的“全文级审查点审核”

项目里已经有：

- `audit_point_id / audit_point_name` 元数据：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/schemas.py:80`
- `cross_paragraph` 复杂 skill：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/complex_skills.py:226`

但当前真正执行时仍然主要是：

- 单个 `chunk`
- 单条 `rule`
- 当前 `chunk` 的 `spans` 和 `facts`

因此现状更像：

- **规则审核后映射回审查点**

而不是：

- **站在某个审查点角度，对全文做一次完整审核**

---

## 3. 第一部分：长文本模式升级方案

## 3.1 设计目标

长文本模式的目标不是“减少模型调用”，而是：

1. **保住完整语义单元**
2. **减少跨 chunk 语义割裂**
3. **仍然保留精细定位能力**

所以应该采用：

- **大块判定**
- **小粒度定位**

而不是单纯把所有逻辑都继续绑在 `300` 字 chunk 上。

## 3.2 方案核心：双尺度文本资产

建议把长文本模式改为“双尺度资产”：

### A. 审核块（Large Audit Chunk）

用于召回、语义预检、Stage 2 精判。  
建议参数：

- `LONGDOC_CHUNK_SIZE = 800 ~ 1200`
- `LONGDOC_CHUNK_OVERLAP = 150 ~ 250`

特点：

- 一个审查点的前提 + 结论更容易在同一审核块内保留
- 对跨句、跨段逻辑更友好

### B. 证据 Span（Fine Evidence Span）

继续保持当前的细粒度 `span_pool` 体系，用于：

- `evidence_span_ids`
- 最终定位
- 展示给业务侧的证据片段

即：

- **大块用于理解**
- **小 span 用于落点**

## 3.3 进入长文本模式的触发条件

建议做自动切换，不影响短文本主链路：

- `len(normalized_text) >= 1800`
  或
- `paragraph_count >= 8`
  或
- 预切块后 `chunk_count >= 8`

满足任一条件，切换到 `LONGDOC_MODE=true`。

## 3.4 长文本模式下 Stage 0 的改法

当前 `adaptive_split_chunks()`：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage0_preprocess.py:215`

建议升级为：

1. 先保留现有 `span_pool`
2. 新增一层 `audit_chunks`
3. 在 `DocumentState` 中同时保存：
   - `chunks`：长文本模式下改为大审核块
   - `span_pool`：仍然细粒度
   - 可选新增 `section_map / paragraph_map`

### 注意

不要让“大 chunk”取代 `span`。  
长文本模式只是改变“判定载体”，不是改变“定位载体”。

## 3.5 长文本模式下 Stage 1 的改法

### 保留 AC / 关键词召回

AC 仍然有价值，但它应当作用于：

- 大审核块内的词面证据发现
- 文档级审查点候选提示

### 调整 Stage 1 目标

长文本模式下，Stage 1 不应该过度追求“每个 chunk 都精确筛到 3 条”，而应当优先保证：

- 真正相关的审查点不要被早期切碎或漏掉

建议：

1. `Stage 1A raw recall` 继续跑，但基于大审核块
2. `Stage 1B semantic prescreen` 也基于大审核块
3. `Stage 1D filter` 不要单纯按“最多 3 条”硬截
4. 对同一规则在多个相邻块中的命中做聚合

可以引入一个轻量规则：

- 同一 `rule_id` 在连续两个大审核块命中，则提升优先级

## 3.6 长文本模式下 Stage 2 的改法

当前 `skill` prompt 并没有真正利用全文，而是主要看当前 chunk：

- `judge_with_skill_strategy()`：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_deep_judge.py:493`
- `build_prompt()`：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/skills.py:46`

建议长文本模式下改成：

### 不直接喂全文

不要把 5000 字全文直接塞进每次 skill prompt。  
这会：

- 太慢
- 太贵
- 不稳定

### 改成“相关上下文组”

每个 `(audit_chunk, rule)` 在进入 skill 前，先拼一个 `context bundle`：

- 当前审核块
- 前一个审核块摘要/关键句
- 后一个审核块摘要/关键句
- 同规则在全文其他位置的命中提示

这样 skill 看的是：

- **局部核心文本 + 相邻支持上下文**

而不是：

- 只有单个 chunk
或
- 无脑整篇全文

## 3.7 长文本模式下最值得先做的 3 个点

### P0-1：把判定 chunk 从 300 提到长文本模式的 800~1200

这是最直接的效果提升点。

### P0-2：保留现有 span-only 定位

不要动 `Stage 3` 的核心定位契约。

### P0-3：skill 改用 context bundle

比“继续单 chunk”更稳，也比“全文直灌”更轻。

---

## 4. 第二部分：全文审核审查点并行子流程方案

## 4.1 为什么要单独做“全文审核审查点”

有一类审查点，天然不是单句或单 chunk 的问题，而是需要从全文角度判断：

例如：

- **引用第三方数据没有给到数据来源**
- 使用市场排名、理赔率、行业数据但全文未注明来源
- 使用研究结论、权威说法、监管解读但没有出处
- 图表/数据/结论在文中多处出现，需要全文汇总后才能判断

这类问题如果硬塞进当前 `chunk × rule` 主流程，会有两个问题：

1. 每个 chunk 单看都不一定构成违规
2. 真正的违规是“全文缺了某个全局信息”，不是单句表述本身

因此它们应该是：

- **并行于主流程的一条全文审查支路**

## 4.2 目标形态

建议新增一条“全文审核技能支路”，风格上采用类似 `skills` 的模块化模式，但职责不同：

- 主流程：处理 `chunk × rule`
- 全文支路：处理 `document × audit_point`

即：

- 主流程负责局部违规
- 全文支路负责全局缺失类、全局一致性类、全局来源类审查点

## 4.3 适合放进全文支路的第一批审查点

建议第一批只接入 1~3 类，不要一上来铺太多。

### 第一优先级

1. **第三方数据/事实引用缺少来源**
   - 例如：`行业报告显示`、`数据显示`、`根据调研`、`权威机构指出`
   - 但全文没有来源主体、报告名称、统计口径、时间


这些都非常适合做全文审核。

## 4.4 在 Workflow 中的接入位置

当前 Workflow：

- `preprocess`
- `recall_filter`
- `fact_extract`
- `route_dispatch`
- `gate`
- `deep_judge`
- `override`
- `suggestion`
- `assemble`

定义位置：

- `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/workflow.py:455`

建议新增：

### 新 Stage：`Stage 2.6 full_document_audit`

放置顺序建议为：

- `Stage 2.5 override`
- `Stage 2.6 full_document_audit`
- `Stage 2.7 suggestion`
- `Stage 3 assemble`

原因：

- Stage 2.6 不依赖 Stage 2.7
- 它和主流程判定是并行支路结果，不应该被 suggestion 之后才接入
- 但它可以复用前面 Stage 0 / 1.5 的资产

## 4.5 并行方式

建议不是“替换主流程”，而是：

### 主流程继续保留

- `chunk × rule` 的现有流水线不动

### 新增全文审查子流程

输入：

- `document.original_text`
- `document.normalized_text`
- `chunks`
- `span_pool`
- `stage15_facts`
- 可选的 AC/关键词全文扫描结果

输出：

- `full_document_judgments`

两条支路在逻辑上并行，最后在 `Stage 2.7` 和 `Stage 3` 汇总。

---

## 5. “Claude Code skills 模式”在这里应该怎么落

这里不建议理解成真的去调用外部 Claude Code。  
更合适的工程含义是：

- 采用类似当前 `skills.py / complex_skills.py` 的技能模块模式
- 但把对象从 `chunk-rule` 改成 `document-audit_point`

建议新增一类技能：

- `DocumentComplianceSkill`

每个技能只负责一个全文审查点簇，例如：

1. `full_doc_third_party_source_check`
2. `full_doc_ranking_source_check`
3. `full_doc_regulatory_basis_check`

### 这类 skill 的输入不再是单 chunk

而是：

- 全文文本
- 全文切段摘要
- 相关证据片段列表
- 命中的数据/排名/机构/报告关键词
- 已检测到的来源信息片段

### 这类 skill 的输出建议结构

- `audit_point_id`
- `audit_point_name`
- `verdict`
- `reasoning_cot`
- `evidence_span_ids`
- `evidence_texts`
- `missing_elements`
- `decision_basis`
- `primary_category`
- `secondary_category`

这样它在后续合并时能和现有 `JudgmentResult` 尽量兼容。

---

## 6. 全文审核子流程的建议结构

## 6.1 子流程拆分

建议拆成三步：

### Step A：全文信号提取（纯代码优先）

先做一个 `document-level prescan`：

- 找出数据词：`数据显示 / 调研 / 统计 / 报告 / 白皮书 / 第三方 / 权威机构`
- 找出来源词：`来源 / 数据来源 / 统计口径 / 报告名称 / 发布机构 / 日期`
- 找出排名词：`第一 / 排名 / 领先 / top / 市占率`
- 找出监管依据词：`根据监管要求 / 国家规定 / 银保监会指出`

输出：

- `DocumentAuditSignals`

### Step B：全文审查点路由

根据 `DocumentAuditSignals` 决定是否触发某个全文 skill。

例如：

- 命中数据词很多，但来源词几乎没有
- 就触发 `full_doc_third_party_source_check`

### Step C：全文 skill 审核

每个触发的审查点调用一次全文 skill，输出一个 `DocumentJudgmentResult`。

注意：

- 这里不是按命中次数调很多次
- 而是按“全文审查点”调一次

这样成本才可控。

## 6.2 为什么这样适合“引用第三方数据没来源”

因为这类审查点的判断逻辑本来就是：

- 全文是否出现了第三方数据引用
- 全文是否补充了来源
- 两者是否配套

这个判断天然就是 `document-level`，不适合单 chunk 做。

---

## 7. 与主流程的合并方式

## 7.1 在 State 中新增独立结果槽

建议在 `WorkflowState` 里新增：

- `stage26_full_document_judgments`

不要把全文审查结果硬塞进 `stage2_judgments` 原列表里，先保持隔离更稳。

## 7.2 在 Stage 2.7 suggestion 中合并

当前 `Stage 2.7` 只消费 `stage2_judgments`：

- `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/workflow.py:378`
- `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_7_suggestion.py:98`

建议改成：

- `run_stage2_7_suggestion(judgments=stage2_judgments + stage26_full_document_judgments, ...)`

这样主流程违规和全文审核违规都会生成建议。

## 7.3 在 Stage 3 assemble 中统一输出

最终仍要在 `Stage 3` 统一输出给 API。  
因此建议：

1. `Stage 3` 消费合并后的 judgments
2. 全文审查结果也尽量带 `evidence_span_ids`
3. 如果是“全文缺来源”这种场景，可允许多段 `location`

### 一个关键原则

全文审核结果不要只输出“结论”，必须尽量落到具体证据片段：

- 哪些地方用了数据
- 哪些地方缺少来源

否则业务侧很难修改。

---

## 8. 这两个方案如何协同

这两个升级方向其实是互相增强的：

### 长文本模式

解决：

- 主流程在 5000 字下语义割裂的问题

### 全文审核支路

解决：

- 天生需要全文角度判断的审查点

二者一起上，项目就会从：

- “chunk 级规则审核系统”

升级为：

- “chunk 级主流程 + document 级专项审查支路”的双层审核系统

这比直接把所有事情都丢给单条主流程更合理。

---

## 9. 建议实施顺序

## P0：先做长文本模式底座

1. 新增长文本模式开关
2. 支持大审核块 + 小 span 双尺度资产
3. skill 输入改成 `context bundle`

## P1：接入第一类全文审查点

先只做：

- `引用第三方数据没有给到数据来源`

这是最典型、最容易验证价值的一类。

## P2：扩展第二批全文审查点

再扩：

- 排名/行业地位无来源
- 监管/国家/政策依据无出处

## P3：再做统一评测

建议 benchmark 里单独增加两套评测：

1. 长文本模式评测集
2. 全文审查点评测集

---

## 10. 最终建议

如果只做一件事，我建议先做：

- **长文本模式的大审核块 + 小 span 定位**

因为它会同时改善：

- 主流程效果
- 后续全文审查支路的输入质量

如果做第二件事，再接：

- **全文审核审查点并行子流程**

并且第一批只做：

- **第三方数据引用缺少来源**

这是最轻、最明确、最容易体现“全文审核价值”的起点。

