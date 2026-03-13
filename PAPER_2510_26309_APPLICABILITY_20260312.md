# 论文《GraphCompliance》对当前项目的可应用建议（2026-03-12）

参考文件：`/Users/junqi/Downloads/2510.26309v1.pdf`  
论文标题：**GraphCompliance: Aligning Policy and Context Graphs for LLM-Based Regulatory Compliance**

## 一、先给结论

这篇论文 **有参考价值，而且比上一份业务方案文档更有参考价值**。  
原因不是它更“完整”，而是它更聚焦于一个真正关键的问题：

**如何在合规场景里，把“结构化规则逻辑”与“非结构化文本语义”对齐，而不是只做普通 RAG。**

但同样要明确：

- **不建议整套照搬**
- **建议局部吸收**
- **最适合借鉴的是“轻量图化 + 确定性 gate + 例外闭包”**
- **不适合直接照搬的是“完整 policy graph / context graph 平台化建设”**

对你当前项目，我给出的结论是：

> 最优做法不是把现有系统重构成论文原型，  
> 而是把论文的核心思想嵌入你现有的 0/1/1.5/1.8/2/2.5/3 流水线。

---

## 二、这篇论文真正解决了什么问题

论文指出，合规场景里普通 LLM / 普通 RAG 的失败点不只是“召回不准”，而是三类更深层问题：

1. **交叉引用丢失**  
   规则 A 依赖规则 B，规则 B 又受规则 C 的例外约束；普通检索只按相似度召回，容易漏链路。

2. **决策路径被打断**  
   某些合规判断本质是顺序判断或分支判断，不是把相关段落都找出来就够了。

3. **互斥清单被混合**  
   两套条件只应命中一套，但 LLM 容易把它们合并，导致漏项或重复项。

论文的核心做法不是“图检索更高级”，而是：

- 先把规则表示成 **Policy Graph**
- 再把上下文表示成 **Context Graph**
- 然后通过 **Compliance Gate** 做确定性结构分析
- 最后才把“被压缩后的判断问题”交给 LLM

这点对你的项目有实际启发。

---

## 三、为什么它对你当前项目有价值

因为你当前项目已经有了几个和论文高度相容的部件，只是还没有“图化”到那一步。

### 1. 你已经有轻量的“规则结构”

当前 `RuleCard` 已经承载了部分结构约束：

- `violation_terms`
- `condition_terms`
- `exclusion_terms`
- `prefix_no_match`
- `suffix_no_match`

位置：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/schemas.py:56`

这说明你并不是从零开始。  
你现在缺的不是“规则结构化意识”，而是 **更高一层的规则关系结构**。

### 2. 你已经有轻量的“上下文结构”

当前 Stage 1.5 已经在做事实抽取：

- 否定
- 确定性
- 比较
- 时间
- 动作
- 百分比 / 金额

位置：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage1_5_fact_extract.py:1`

这本质上已经是 Context Graph 的前身，只是现在还停留在“信号表”层，而不是“关系图”层。

### 3. 你已经有 gate 的雏形

当前系统其实已经存在几个“半成品 gate”：

- Stage 1 的候选召回：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage1_recall_filter.py:106`
- Stage 1.8 的 base / skill 路由：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage1_8_route_dispatch.py:33`
- Stage 2.5 的反证纠偏：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_5_refute.py:1`

所以，论文里最有价值的东西，并不是替换你的流水线，而是：

**把这些零散的 gate 合并成更明确的结构化“合规闸门”。**

---

## 四、哪些思想值得直接应用

## 1. 引入“轻量 Policy Graph”，不要直接上完整知识图谱

论文里的 Policy Graph 值得借鉴，但不建议你直接做成复杂 KG 系统。

对当前项目，更现实的做法是把规则卡片扩成“轻量图化规则单元”。

建议新增或补齐的关系型元数据：

- `applies_to_actor`
- `applies_to_subject`
- `claim_type`
- `exception_of`
- `depends_on`
- `mutually_exclusive_group`
- `decision_stage`
- `requires_evidence`
- `scope_tags`

这些字段的作用不是为了“知识图谱好看”，而是为了：

1. 让规则不再只是扁平列表；
2. 让某些规则的例外关系可遍历；
3. 让 Stage 1 / 1.8 不再只靠关键词和启发式路由。

### 为什么这点重要

你当前规则更多还是“独立卡片”思维。  
而论文的真正价值，是把规则从“卡片集合”提升为“关系网络”。

这对保险合规尤其有价值，因为很多规则都存在：

- 主规则
- 适用条件
- 例外条款
- 主体限制
- 渠道限制
- 话术强度差异

这天然适合用轻量图关系表达。

---

## 2. 把 Stage 1.5 从“信号提取”升级成“锚点抽取”

论文的 Context Graph 里有一个非常实用的思想：  
不要只提取零散 token，而是提取 **可用于对齐规则的锚点**。

对你当前项目，我建议把 Stage 1.5 未来升级方向定义为：

### 当前状态

`ChunkFactProfile` 主要是：

- `label`
- `value`
- `evidence_span_ids`

这适合做纠偏，但还不够支撑“结构化对齐”。

### 建议升级后的锚点类型

优先增加这些锚点：

- **actor**：谁在说、谁是主体  
  例如：代理人 / 客户 / 公司 / 第三方

- **action**：在做什么  
  例如：推荐 / 承诺 / 比较 / 退保建议 / 销售引导

- **claim**：陈述类型  
  例如：收益承诺 / 风险淡化 / 排名声称 / 历史业绩引用

- **time_scope**：时态  
  例如：过去 / 当前 / 未来 / 限时

- **evidence_need**：是否涉及需证明的事实  
  例如：收益率、排名、获奖、销量、客户案例

也就是说，不是马上做重型 ER 图，而是先把 Stage 1.5 做成“**结构化锚点层**”。

---

## 3. 在 Stage 1.5 与 Stage 2 之间加入真正的 Compliance Gate

这是我认为最值得吸收的论文思想。

论文的 gate 本质是：

**让确定性结构判断先做掉，只把语义上真的需要模型裁决的那部分送进 LLM。**

你的项目里，这个东西目前分散在：

- 规则引擎
- 路由分发
- 反证校验

建议未来演进成一个更明确的 gate，职责包括：

1. **作用域过滤**  
   例如当前文本主体是客户经历，而不是代理人承诺，则先过滤部分规则；

2. **例外链路预展开**  
   如果某条规则存在明确例外/排除/互斥关系，先在结构层展开；

3. **判断计划编译**  
   把原始规则卡片编译成对当前 chunk 的“检查计划”；

4. **LLM 输入收缩**  
   不把完整 RuleCard 文本直接给模型，而是给：
   - 当前锚点
   - 当前规则计划
   - 当前例外条件
   - 当前必须核验的事实

### 这对现有项目的直接价值

如果做对了，会带来三点收益：

1. 降低 skill 轨 prompt 噪声；
2. 降低 LLM 把互斥条件混在一起的概率；
3. 让 Stage 2.5 的“事后纠偏”前移成“事前约束”。

---

## 4. 把 Stage 2.5 从“局部反证”升级成“规则闭包覆盖”

论文里有个非常值得借鉴的点：

**reference closure / exception closure**

意思是：

- 某条规则初判违规后，
- 不能只看这一条规则本身，
- 还要看它所有可达的引用和例外节点，
- 再决定是否被 override。

你当前 Stage 2.5 已经有这个思想的最小版本：

- 可执行规则硬阻断
- 否定语境纠偏

位置：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_5_refute.py:96`

但它现在还是 **局部文本反证**，不是 **规则关系反证**。

### 建议升级方向

未来可以让每条规则支持：

- `exception_of`
- `overrides`
- `requires_all`
- `requires_any`

然后在 violation 初判后，做一个轻量闭包遍历：

1. 找到当前规则的例外和依赖；
2. 用当前 chunk 的锚点和信号判断这些例外是否成立；
3. 再决定是否覆盖 violation。

这会比单纯加更多 negation 规则更稳。

---

## 5. 用“anchor-based retrieval”替代纯文本相似度思维

论文的另一个实用点是：

它不是直接“query -> top-k chunks”，而是先找 **anchor**，再围绕 anchor 做规则对齐。

这对你当前项目的启发是：

Stage 1 不一定要长期停留在：

- AC 关键词
- TF-IDF
- LLM Filter

这个组合当然还有效，但下一阶段更值得做的是：

### 从“文本召回规则”
转向
### “锚点召回规则”

例如：

- 如果抽取到 `actor=代理人` + `claim=收益承诺` + `certainty=保证`
- 就优先召回“收益承诺类 + 主体敏感类 + 绝对化表达类”

这比只靠 chunk 全文相似度更像“合规推理入口”。

### 注意

这不意味着 AC / TF-IDF 要废弃。  
更合理的做法是：

- AC 继续做高效词命中；
- 锚点召回做结构补充；
- 两者融合后再做 filter。

---

## 6. 评测思路值得借鉴，而且很适合你当前阶段

论文最务实的一点，不是图，而是 **评测方法很清楚**。

值得借鉴的有三点：

### 6.1 用高保真案例，不依赖纯合成数据

论文强调：

- 不直接用纯 synthetic narrative；
- 先基于真实案例和一手材料；
- 再做匿名化、抽象化、重写。

这对你的项目非常重要。  
保险合规如果只拿模型自己造的例子做测试，很容易看起来效果很好，实际上上线就漂。

### 6.2 指标上优先关注 F2

论文用 F2 作为关键指标，因为 compliance 场景里漏报成本通常更高。

这对你项目是适用的。  
当前你更需要一个“合规业务友好”的评测指标体系，而不是只看通用 accuracy。

### 6.3 除了标签准确率，还评估理由质量

论文还用 LLM rater 做定性评估，检查理由是否和依据一致。

这对你项目也有现实意义，因为你最终输出不只是 verdict，还有：

- reasoning
- reason_codes
- suggestion

如果这些内容和规则依据不一致，系统在业务上还是不可靠。

---

## 五、哪些地方不建议直接应用

## 1. 不建议现在就做完整 Policy Graph / Context Graph 系统

论文里的方法在学术上成立，但如果直接照搬到当前项目，会有明显问题：

- 规则资产还没有足够丰富的关系字段；
- 当前上下文抽取还不是实体关系级别；
- 全量 graph construction 会提高实现复杂度；
- 你当前最核心的收益还没到必须用重图结构才能拿到的程度。

所以更适合的是：

**轻量图化，不做重型知识图谱工程。**

---

## 2. 不建议现在就引入 cross-encoder reranker / 多跳图检索全家桶

论文里有：

- preselect
- rerank
- compile plan
- closure traversal

这些在论文 benchmark 上有效，但你当前项目有自己的现实约束：

- 审核文本较短；
- 规则库规模 612 条；
- 当前主瓶颈不一定是检索排序，而更可能是规则治理与路由经济性；
- SLA 和工程复杂度都不适合盲目加重。

所以建议优先顺序是：

1. 规则关系字段
2. 锚点层
3. gate
4. 规则闭包

而不是先上更重的 reranker。

---

## 3. 不建议假设论文中的精度提升会直接迁移

论文报告了相对 LLM-only / RAG baseline 的显著提升。  
但这些结果不能直接外推到你的项目，因为：

- 任务域不同：GDPR vs 保险营销合规
- 数据形态不同：案例场景 vs 文案审核
- 标签体系不同：article-level multi-label vs rule-level violation localization
- 规则结构密度不同：GDPR 交叉引用非常重，保险规则未必同等密集

所以，**论文提供的是方法启发，不是效果承诺**。

---

## 六、结合当前项目，我建议的落地方案

## Phase 1：先做“轻量规则关系层”

目标：让规则从扁平卡片，变成可遍历的轻量图。

建议新增的不是复杂图数据库，而是先补规则元数据：

- `depends_on`
- `exception_of`
- `mutually_exclusive_group`
- `actor_scope`
- `channel_scope`
- `claim_type`
- `evidence_required`

这一层完成后，Stage 1.8 路由和 Stage 2.5 纠偏都会更稳。

---

## Phase 2：把 Stage 1.5 升级为“Anchor Extractor”

目标：从纯信号表升级为结构化锚点层。

优先抽取：

- 主体
- 行为
- 主张类型
- 时态
- 数值 / 比较
- 是否需外部证据

不需要一步到位做完整 ER graph，只要让这些锚点能支持规则过滤和判断计划编译即可。

---

## Phase 3：把 gate 明确建出来

建议在 Stage 1.5 与 Stage 2 之间增加一个更清晰的结构化 gate。

这个 gate 要做的不是替代 LLM，而是：

1. 过滤显然不适用规则；
2. 展开规则例外和依赖；
3. 生成当前 chunk 的检查计划；
4. 只把压缩后的判断问题送入 skill 轨。

这会比继续堆 prompt 更有长期价值。

---

## Phase 4：把 Stage 2.5 做成“闭包式 override”

当前 Stage 2.5 已经有反证基础。  
下一步值得做的不是继续加零散 hardcode，而是把 override 机制规则化。

即：

- violation 初判
- 找规则闭包
- 检查例外是否满足
- 再做最终 verdict

这正是论文里最可迁移、也最适合保险规则场景的一部分。

---

## Phase 5：补一套真正可用的 benchmark

论文的另一大价值是提醒你：

**没有高保真 benchmark，所有升级都可能是错觉。**

建议你的 benchmark 重点覆盖：

- 收益承诺
- 风险淡化
- 排名与证据不足
- 客户经历 vs 当前承诺
- 主体切换
- 例外条款
- 否定语境
- 多规则重叠命中

指标建议至少包括：

- micro-F1
- micro-F2
- 误报率
- span 定位准确率
- reason / reason_code 一致性

---

## 七、最终建议

这篇论文对你项目 **有较强参考价值**，但参考方式必须克制。

最值得吸收的不是“图”本身，而是它背后的判断顺序：

1. 先把规则结构显式化；
2. 再把上下文事实结构化；
3. 让确定性 gate 先做结构判断；
4. 再把剩余语义问题交给 LLM；
5. 最后通过例外闭包做 override。

这条思路和你当前项目是兼容的。

所以我的建议不是：

**“重写成 GraphCompliance”**

而是：

**“把现有保险合规流水线，升级成带轻量图化 gate 的双轨合规系统。”**

如果只保留一句话结论：

**这篇论文值得借鉴，而且可以落地；但正确姿势是轻量吸收它的 gate / closure / anchor 思想，而不是把项目重构成一个完整图合规平台。**
