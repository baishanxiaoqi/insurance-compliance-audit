# Claude Code 执行版：语义预检并行召回升级方案（2026-03-24）

## 1. 文档目的

这不是思路稿，而是一份**可直接交给 Claude Code 执行**的实施方案。

目标只有一个：

**在不破坏当前主链路稳定性的前提下，补上关键词召回对语义型违规表达的漏召回问题。**

---

## 2. Claude Code 执行边界

Claude Code 执行时必须遵守下面这些边界：

1. **不要直接按原方案把“当前完整 Stage 1”和语义预检并行后就合并。**
2. **必须改成“raw recall 并行 + 合并 + 统一 filter”的结构。**
3. **第一版只做两类重点风险：**
   - `financial_confusion`
   - `absolute_expression`
4. **不要一次性扩到 `agent_title_violation` 和 `gifts_benefits`。**
5. **不要改 Stage 2/2.5 的核心判定逻辑。**
6. **不要引入新三方依赖。**
7. **必须加 feature flag，默认可先关闭或保持兼容行为。**
8. **所有语义扩展候选都必须经过统一 Filter Agent，不能绕过过滤直接进 Stage 2。**

---

## 3. 最终目标架构

Claude Code 实现时，目标流程应调整为：

```text
Stage 0: preprocess
    ↓
Stage 1A: raw keyword recall
    ├── 并行 ── Stage 1B: semantic prescreen
    ↓
Stage 1C: merge raw candidates
    ↓
Stage 1D: unified filter agent
    ↓
Stage 1.5: fact extract
    ↓
Stage 1.8: route dispatch
    ↓
Stage 1.9: gate
    ↓
Stage 2 ...
```

注意：

- `Stage 1A` 和 `Stage 1B` 是并行
- `Stage 1D` 是统一过滤
- 不能让 semantic 通道扩出的规则直接跳进后续 Stage 2

---

## 4. 第一版范围（P0）

第一版只落地下面这些能力：

### 4.1 支持的语义风险方向

- `financial_confusion`
- `absolute_expression`

### 4.2 第一版必须做到的事情

1. 从现有 `stage1_recall_filter.py` 中拆出：
   - raw recall
   - filter only
2. 新增语义预检 stage
3. 新增 merge stage
4. 增加规则来源 provenance
5. 增加 `category_group -> rule_ids` 索引
6. 在 workflow 中接入并行编排
7. 加 feature flag
8. 加单元测试与回归测试

### 4.3 第一版不要做的事情

- 不要上 embedding 检索
- 不要引入向量库
- 不要把语义预检扩成最终违规判定器
- 不要把四类全部一次性上线
- 不要大改 `ChunkCandidates` 现有主契约，除非确实必要

---

## 5. 推荐实现方式

## 5.1 对现有 Stage 1 做“拆而不重写”

Claude Code 不要推翻现有 `stage1_recall_filter.py`，而是**在现有文件内抽 helper**。

推荐拆成下面三层：

### A. raw recall helper

在 `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage1_recall_filter.py`
中新增：

- `run_stage1_raw_recall(...)`
- 只负责：
  - AC 召回
  - TF-IDF 召回
  - 生成每个 chunk 的 raw Top-K rule_id

输出建议仍复用 `ChunkCandidates`

### B. unified filter helper

同文件新增：

- `run_stage1_filter_only(...)`

输入：
- raw merged candidates

输出：
- 过滤后的 `ChunkCandidates`

要求：
- 复用现有 `Filter Agent`
- 复用现有 prompt 结构
- 不要复制一套新 filter 逻辑

### C. 保留兼容入口

保留现有：
- `run_stage1(...)`

让它内部走：
- raw recall
- unified filter

这样旧调用方不至于全断。

---

## 5.2 新增 Stage 1.1：语义预检

新增文件：

- `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage1_1_semantic_prescreen.py`

第一版只做以下内容：

### 输入

- `document`
- `rule_cards`
- `category_group_index`
- `semaphore`

### 输出

建议输出两块：

1. `List[ChunkCandidates]`
2. `Dict[str, SemanticChunkMetadata]`

其中 `SemanticChunkMetadata` 建议包含：

- `chunk_id`
- `risk_directions`
- `confidence`
- `reasoning`
- `extended_rule_ids`

### 设计要求

- 先跑轻量规则检测
- 只有命中轻量风险信号时，才允许调用 LLM 预检
- LLM 只识别风险方向，不做违规判定
- 每个 chunk 最多返回 2 个风险方向
- 每个 chunk 最多补 2~4 条扩展规则

---

## 5.3 语义预检的 schema 要最小化

不要让 LLM 输出下面这些字段：

- `extended_rules`
- `duration_ms`

第一版 LLM 输出 schema 只保留：

- `risk_directions`
- `confidence`
- `reasoning`

扩展规则必须由代码完成。

---

## 5.4 新增 Stage 1.2：合并 candidates

新增文件：

- `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage1_2_merge_candidates.py`

核心职责：

1. 合并 keyword raw candidates 和 semantic candidates
2. 去重
3. 保留顺序（关键词优先，语义补充在后）
4. 限制总量
5. 产出 provenance

### provenance 设计

第一版不建议直接改 `ChunkCandidates` 主 schema。

建议做法：

在 `WorkflowState` 新增：

- `stage11_semantic_metadata`
- `stage12_rule_sources`

其中：

- `stage12_rule_sources[chunk_id][rule_id] = "keyword" | "semantic" | "both"`

这样改动更稳，不会把太多现有函数签名拉坏。

---

## 5.5 预建 category 索引

不要在语义预检中每次全量扫规则库。

建议新增轻量索引模块，或者在 `workflow.load_rule_cards()` 后顺手构建：

- `category_group -> rule_ids`

第一版只需要这个索引就够了。

可选新增文件：

- `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/rule_indexes.py`

至少提供：

- `build_category_group_index(rule_cards)`

---

## 6. 两类重点风险的执行细则

## 6.1 `financial_confusion`

第一版语义预检只在以下条件下补召回：

### 轻量正向信号

- 出现：`银行` / `存款` / `储蓄` / `理财` / `投资` / `收益`
- 且出现保险主体相关词：
  - `保险`
  - `产品`
  - `保单`
  - `这款产品`

### 轻量负向排除

出现以下语境时，降低或取消语义补召回：

- `监管规定`
- `禁止`
- `不得`
- `处罚`
- `说明书`
- `投资策略`
- `公司投资`
- `账户配置`

### 召回目标

只补 `category_group=financial_confusion` 的规则。

第一版不要擅自扩到其它近邻组。

---

## 6.2 `absolute_expression`

第一版只在“绝对化词 + 高风险修饰对象”同时出现时补召回。

### 绝对化词

- `最`
- `第一`
- `唯一`
- `绝对`
- `一定`
- `百分百`

### 高风险修饰对象

- `产品`
- `收益`
- `保障`
- `理赔`
- `代理人`
- `专家`
- `顾问`

### 需要排除的语境

- 主观感受
- 企业愿景
- 服务理念
- 文学化表述
- 非产品责任类服务介绍

### 召回目标

只补 `category_group=absolute_expression` 的规则。

---

## 7. workflow 接入方式

修改文件：

- `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/workflow.py`

不要粗暴重写整个 workflow。

建议做法：

### 7.1 保持对外阶段编号稳定

对外日志仍可以保持：

- Stage 1
- Stage 1.5
- Stage 1.8
- Stage 1.9

但在 Stage 1 executor 内部组织成：

1. raw recall
2. semantic prescreen
3. merge
4. unified filter

### 7.2 推荐封装一个新 orchestration helper

例如：

- `run_stage1_with_semantic_prescreen(...)`

由它统一返回：

- 最终过滤后的 `ChunkCandidates`
- semantic metadata
- rule sources
- stage1 metrics

然后 `_stage1_executor()` 仍只负责调用这个 helper。

---

## 8. 配置项建议

在 `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/config.py`
中增加以下配置：

- `ENABLE_SEMANTIC_PRESCREEN`
- `SEMANTIC_PRESCREEN_MAX_DIRECTIONS`
- `SEMANTIC_PRESCREEN_MAX_EXTENDED_RULES`
- `SEMANTIC_PRESCREEN_ENABLE_LLM`
- `SEMANTIC_PRESCREEN_TIMEOUT_SECONDS`
- `SEMANTIC_PRESCREEN_MAX_RETRIES`
- `SEMANTIC_PRESCREEN_ENABLED_GROUPS`

### 默认值建议

- `ENABLE_SEMANTIC_PRESCREEN=false`
- `SEMANTIC_PRESCREEN_ENABLE_LLM=true`
- `SEMANTIC_PRESCREEN_MAX_DIRECTIONS=2`
- `SEMANTIC_PRESCREEN_MAX_EXTENDED_RULES=4`
- `SEMANTIC_PRESCREEN_ENABLED_GROUPS=financial_confusion,absolute_expression`

原因：

- 第一版先通过 feature flag 控制风险
- 默认关掉，方便做 A/B 对照

---

## 9. 测试要求

Claude Code 必须补以下测试。

## 9.1 Stage 1 raw recall / merge / filter 单元测试

新增测试文件建议：

- `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/tests/test_semantic_prescreen_pipeline.py`

至少覆盖：

1. semantic 候选不会绕过 unified filter
2. merge 顺序是 keyword 优先、semantic 补充
3. provenance 正确记录 `keyword/semantic/both`
4. feature flag 关闭时行为与旧版一致

## 9.2 语义预检规则测试

新增测试文件建议：

- `/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/tests/test_semantic_prescreen_rules.py`

至少覆盖：

### financial_confusion

- “像银行存款一样安全，但收益更高” -> 命中
- “根据监管规定，不得把保险说成理财” -> 不命中高优先级补召回

### absolute_expression

- “这是市场上最好的保险产品” -> 命中
- “我们始终追求最好的服务体验” -> 不命中

## 9.3 benchmark 验证

第一版至少要求在 benchmark 中补两个指标：

- `semantic_only_recall_count`
- `stage1_pair_expansion_delta`

如果时间够，再补：

- `financial_confusion_recall_delta`
- `absolute_expression_recall_delta`

---

## 10. Claude Code 执行顺序

必须按下面顺序做，不要乱序：

### Step 1

先抽 `raw recall` 与 `filter only`，保证旧 `run_stage1()` 还能工作。

### Step 2

加 `category_group` 索引。

### Step 3

加 `stage1_1_semantic_prescreen.py`，只做两类：

- `financial_confusion`
- `absolute_expression`

### Step 4

加 `stage1_2_merge_candidates.py`。

### Step 5

在 `workflow.py` 中接入新的 Stage 1 orchestration。

### Step 6

补测试，先跑：

- unit tests
- stage1 相关测试
- benchmark 小样本

### Step 7

再打开 feature flag 做 smoke 对比。

---

## 11. 验收标准

Claude Code 完成后，至少要满足下面这些验收条件：

### 功能验收

1. 开关关闭时，现有主链路结果不变
2. 开关打开时，semantic 风险方向能补候选
3. semantic 补回的候选也会进入统一 Filter
4. `financial_confusion` 与 `absolute_expression` 两类样本有可观测召回提升

### 工程验收

1. 不引入新依赖
2. 不破坏现有 `Stage 2/2.5/3`
3. 不显著增加现有接口复杂度

### 性能验收

1. 单条样本 wall time 不应无上限增长
2. 若 semantic LLM 超时，应自动降级为纯轻量规则模式
3. Stage 2 pair 数膨胀应可被监控

---

## 12. 明确禁止的实现方式

Claude Code 不要做下面这些事情：

1. 不要让 semantic 通道直接输出最终违规
2. 不要让 semantic 扩展规则绕过 unified filter
3. 不要一次性扩到 4 类全部上线
4. 不要每个 chunk 都无脑跑 semantic LLM
5. 不要在 semantic prescreen 中每次全库扫描规则
6. 不要把 benchmark 指标提升写死成“必然成立”

---

## 13. 最终一句话要求

Claude Code 实现时，应把这次升级收敛成一句话：

**“在不破坏现有稳定性的前提下，为 `financial_confusion` 和 `absolute_expression` 增加一条轻量、可回退、统一过滤的语义补召回通道。”**
