# 语义预检并行召回方案审查（2026-03-24）

> 说明：本次实际审查的文件为 `docs/semantic_prescreen_parallel_plan.md`。你消息里提到的 `docs/semantic_prescreen_upgrade_plan.md` 当前仓库中未找到，推测是同一方案的旧文件名或口误。

## 一、总体结论

这份方案的**升级方向是正确的**，尤其这三点判断是对的：

1. **仅靠关键词/AC/TF-IDF 做第一步召回，确实会漏掉语义型违规表达**。
2. **语义预检不应该直接做最终违规判定**，而应该只做“风险方向识别 + 候选扩展”。
3. **语义预检应尽量做轻量化**，否则会把整个主链路拉重，破坏当前项目的可用性。

但是，按当前文档里的写法，方案**还没有完全对齐现有代码结构**，存在几个关键问题。最重要的不是“方向错了”，而是**接入位置、过滤顺序、数据结构和性能预估还不够严谨**。

我的判断是：

- **方案方向正确，可以继续推进**
- **但不建议按文档当前版本直接落代码**
- **需要先修正为“合并后统一过滤”的架构版本**，否则容易把 Stage 2 成本和误报一起拉高

---

## 二、当前方案里最关键的正确点

### 1. “并行”比“串行”更合理
你把“语义预检”从“Stage 1 后串行追加”修正为“与关键词召回并行执行”，这是对的。

原因很明确：
- 串行会把召回链路整体拉长
- 并行至少在架构上保留了“总耗时取 max(两条支路)”的可能性
- 这比“关键词召回结束后再补做一轮语义召回”更适合当前项目

### 2. 只聚焦少数高风险方向是正确的
方案把语义预检收敛到 4 类：
- `financial_confusion`
- `agent_title_confusion`
- `absolute_expression`
- `gifts_or_benefits`

这个收敛思路是对的。因为当前项目真正最容易被“纯关键词召回”漏掉的，也确实主要是这类**依赖语义关系、主体指向或修饰对象**的违规表达。

### 3. “LLM 只识别风险方向，不做最终判定”是对的
这和当前主链路的职责划分匹配：
- 预检层负责“把可能相关的规则召回来”
- 最终判定仍留给后续 Stage 2 / Stage 2.5 / Stage 3

这条边界必须保留，否则 Stage 1 会变成第二套审核系统。

---

## 三、当前方案里最需要修正的问题

### 问题 1：当前方案的“并行边界”没有对齐现有 Stage 1 实现
这是最大的结构性问题。

当前项目里的 `run_stage1()` 并不是“纯关键词召回”，而是：
- 先做混合召回 Top-K
- 再做 Filter Agent 过滤到 Top-3

也就是说，当前 `Stage 1` 本身已经包含了“召回 + LLM 过滤”两个步骤。

但你现在方案里的并行结构是：
- 左边：`Stage 1`（关键词召回通道）
- 右边：`Stage 1.1`（语义预检通道）
- 然后直接 `Stage 1.2 merge`

这会导致一个实际问题：

**关键词通道输出的是“已经被 Filter 压缩过的候选”，而语义通道输出的是“未经过同等过滤的扩展候选”。**

这样一合并，就会变成：
- 关键词通道候选已经被二次筛过
- 语义通道候选却直接带着扩展规则进入后续 Stage 2

这会破坏候选质量的一致性。

#### 建议修正
不要把“当前的完整 Stage 1”直接拿来并行。

正确做法应该是把 Stage 1 拆开为：

- **Stage 1A：关键词原始召回（raw recall）**
- **Stage 1B：语义预检风险方向识别**
- **Stage 1C：基于风险方向做规则扩展**
- **Stage 1D：合并 raw candidates**
- **Stage 1E：统一 Filter Agent 过滤**

这样才是“同一候选池统一过滤”。

否则当前方案会出现：
- 语义扩展候选绕过统一过滤
- Stage 2 对新增候选承担额外成本
- 误报风险也会同步抬升

---

### 问题 2：`keyword_candidate_count` 这个触发条件设计不够合理
文档里语义预检触发条件用了：
- `keyword_candidate_count < MIN_RULES_KEYWORD_CHANNEL`
- 或检测到 `risk_signals`

这个思路本身能理解，但当前设计有两个问题：

#### 2.1 它没有区分“文档级”还是“chunk 级”
现在写法看起来更像是文档级总量，但实际审核是按 `chunk` 处理。

真正需要的不是：
- “整篇文档召回少于 3 条”

而是：
- “这个 chunk 在关键词通道里对当前高风险类目召回不足”

否则很容易出现：
- 文档整体候选很多
- 但某个 chunk 对关键风险类目其实没召回到
- 结果语义预检被错误跳过

#### 2.2 它破坏了“真正并行”
你文档里自己也意识到了这一点：
- 如果先等关键词结果，再决定语义预检要不要跑
- 那就不是真正并行了

而如果像文档里的优化版那样，直接把 `keyword_candidate_count=0` 传进去，又会变成：
- 语义预检几乎总是执行
- 失去轻量化控制

#### 建议修正
语义预检的触发，建议改成：

**只依赖本通道可独立获得的轻量信号，不依赖另一通道的实时结果。**

更稳的触发条件可以是：
- 命中 4 类风险的轻量规则信号
- 或 chunk 很短、但包含高歧义营销表达
- 或 Stage 1A raw recall 中对目标高风险家族命中为 0（这个只能在“伪并行 / 半并行”版本里做）

如果你坚持完全并行，那么就不要把 `keyword_candidate_count` 作为前置依赖。

---

### 问题 3：`SemanticPrescreenResult` 的 schema 设计前后不一致
文档里这个 schema 定义为：
- `risk_directions`
- `confidence`
- `extended_rules`
- `reasoning`
- `duration_ms`

但下面给 LLM 的 prompt 实际只要求输出：
- `risk_directions`
- `confidence`
- `reasoning`

也就是说：
- `extended_rules` 实际不是 LLM 输出
- `duration_ms` 也不是 LLM 输出

这会导致 schema 设计和 prompt 契约不一致。

#### 建议修正
把 LLM 输出 schema 缩成最小版本：
- `risk_directions`
- `confidence`
- `reasoning`

而：
- `extended_rules` 应由代码根据 `risk_directions` 决定
- `duration_ms` 应由运行时埋点记录，不应进 LLM 输出 schema

---

### 问题 4：当前合并设计需要额外数据结构支持，现有 `ChunkCandidates` 不够用
文档里合并阶段想记录：
- `source="semantic_recall"`
- `rule_sources={rule_id: source}`

但当前代码里的 `ChunkCandidates` 只有：
- `chunk_id`
- `candidate_rule_ids`

没有 `source`，也没有 `rule_sources`。

#### 建议修正
这里有两种方式：

##### 方案 A：扩 schema
给 `ChunkCandidates` 增加：
- `rule_sources: Dict[str, str]`
- `semantic_risk_directions: List[str]`

##### 方案 B：不改现有 schema，单独挂在 `WorkflowState`
例如新增：
- `stage11_semantic_metadata: Dict[str, SemanticChunkMetadata]`
- `stage12_rule_sources: Dict[str, Dict[str, str]]`

如果你想少动现有接口，**方案 B 更稳**。

---

### 问题 5：`dynamic_recall_by_risk_directions()` 不能每次全量扫描规则库
文档里现在是：
- 每次根据 `risk_directions`
- 遍历整个 `rule_cards`
- 找 `category_group` 匹配的规则

这在规则库 500+ 条时虽然还能跑，但不是好结构。

#### 建议修正
在规则加载后就预建索引：
- `category_group -> rule_ids`
- `audit_point_id -> rule_ids`
- `route_hint -> rule_ids`

这样语义预检只要 O(1) 取对应规则桶，不需要每个 chunk 再扫全库。

---

### 问题 6：性能预估过于乐观
文档里写：
- 并行后总延迟大约 `+50ms`
- 语义预检轻量模型 `~500ms`

这在当前项目里很可能过于乐观。

因为当前项目实际环境里：
- 主模型是兼容模式大模型
- `think` 可能开启
- `safe_arun()` 还带结构化恢复、重试、超时保护
- 一旦网络抖动或结构化输出不稳定，单次调用会远超理想值

#### 建议修正
这部分不要写成“预计收益已经成立”，而应该写成：
- **目标延迟预算**
- **理想状态估算**
- **待验证假设**

建议改成：
- 目标：语义预检额外 wall time 不超过 `300~800ms`
- 若超过 `1.5s`，自动降级为纯轻量规则，不调 LLM

---

## 四、我建议的优化版架构

我更推荐你把方案调整成下面这版：

### 推荐流程

```text
Stage 1A 关键词原始召回（AC + TF-IDF Top-K raw）
        │
        ├── 并行 ── Stage 1B 语义预检（轻量规则 -> 可选轻量 LLM）
        │
Stage 1C 按风险方向扩展少量规则
        │
Stage 1D 合并 raw candidates（记录来源）
        │
Stage 1E 统一 Filter Agent 过滤到 Top-N
        │
Stage 1.5 事实抽取
        │
Stage 1.8 路由
        │
Stage 1.9 Gate
        │
Stage 2 ...
```

### 这版的优点

1. **关键词通道和语义通道地位对称**
2. **所有候选都经过统一 Filter**，不会让语义扩展候选绕过筛选
3. **更符合当前项目结构演进**，不会把 Stage 2 直接打爆
4. **保留 source/provenance**，后续好做评估

---

## 五、两类重点审查点的专门优化建议

你项目里最重要的其实还是这两类：
- `financial_confusion`
- `absolute_expression`

这两类在语义预检里必须单独加强，不然效果不稳定。

### 5.1 `financial_confusion` 建议

不能只看“理财/银行/存款/投资”等词，还要看：
- **主语是否直接指向保险产品**
- 是否是**正向营销话术**
- 是否是**监管解读 / 负面示例 / 说明书 / 公司投资行为**

建议在轻量规则里增加：
- 正向锚点：`保险 / 产品 / 保单 / 这款产品 / 长期投资 / 收益 / 理财功能`
- 负向锚点：`监管规定 / 不得 / 禁止 / 处罚 / 说明书 / 投资策略 / 公司投资 / 账户配置`

语义预检只在“保险主体 + 金融化表达”同时出现时才触发高优先级扩展。

### 5.2 `absolute_expression` 建议

不能只看：
- `最`
- `第一`
- `唯一`

必须看这些词修饰的对象是不是：
- 保险产品能力
- 保险代理人资质
- 保障/收益/理赔效果

应排除：
- 主观感受
- 企业愿景
- 服务理念
- 文学化夸张
- 非产品责任类服务表达

换句话说，**绝对化词本身不是风险，修饰对象才是风险。**

---

## 六、建议补充的验证指标

当前文档验证部分还不够，建议至少补 5 个指标：

### 1. Stage 1 候选覆盖率提升
- 语义预检前后，高风险类别是否进入候选池

### 2. semantic-only 召回量
- 有多少规则是关键词没召回、语义通道单独补回来的

### 3. Stage 2 对数膨胀率
- 平均每个 chunk 的 `(chunk, rule)` 组合数增加了多少

### 4. 最终审核效果变化
- 在 smoke / benchmark 上看：
  - Recall
  - Precision
  - F1
  - 两类重点审查点召回率

### 5. 延迟分位数
- `p50 / p90 / p95` 的单文档耗时

否则只能看到“想法好不好”，看不到“工程上值不值”。

---

## 七、建议的落地顺序

### P0
1. 把当前 Stage 1 拆成“raw recall”和“统一 filter”两个部分
2. 建 `category_group -> rule_ids` 索引
3. 明确 semantic prescreen 的最小 schema
4. 明确 provenance 存储方式

### P1
1. 先只做两类：
   - `financial_confusion`
   - `absolute_expression`
2. 只允许每类最多补 2 条规则
3. 合并后统一 Filter 到 Top-3/Top-5

### P2
1. 再扩到 `agent_title_violation`
2. 再扩到 `gifts_benefits`
3. 最后补完整 benchmark 评估与 A/B 对照

---

## 八、最终结论

这份方案的**方向是对的**，而且值得继续推进。

但当前文档版本还存在 4 个关键缺口：

1. **并行边界没有对齐当前 Stage 1 的真实实现**
2. **语义扩展候选会绕过统一 Filter**
3. **schema / provenance / 索引设计还没补齐**
4. **性能预估偏理想化**

因此我建议你的下一版方案目标不是“继续补更多细节”，而是先把核心结构改成：

**“raw recall 并行 + 合并 + 统一 filter”**

如果按这个版本推进，我认为这会是一个正确且值得实现的升级方向。
