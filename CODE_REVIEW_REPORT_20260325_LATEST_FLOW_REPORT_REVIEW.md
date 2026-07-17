# 基于最新单样本审核流程报告的代码审查结论

日期：2026-03-25
基于报告：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/benchmark/reports/single_sample_flow_20260324_generated_longdoc/SINGLE_SAMPLE_AUDIT_FLOW_REPORT_20260324_GENERATED_LONGDOC.md`
基于快照：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/benchmark/reports/single_sample_flow_20260324_generated_longdoc/snapshot_current.json`

## 一、总体结论

基于这次长文本单样本真实链路，我认为项目主流程**功能上已经可运行**，但在“长文本审核效果 + 长文本时延控制”两个核心维度上，仍有较明显的代码优化空间。

本次样本的关键现象：
- 总耗时约 `1145.65s`
- `Stage 2` 耗时约 `445.42s`
- `Stage 2.6` 全文审核支路耗时约 `694.12s`
- 最终命中 `2` 条违规，其中 `KB0068` 的命中存在较高的误报风险

这说明当前链路的主要问题已经不是“是否能跑通”，而是：
1. **全文审核支路过重，已经成为长文本主瓶颈**
2. **部分细粒度规则在长文本语境下仍会被通用 skill 放大误判**
3. **长文本增强上下文目前是“全量加料”，但缺少按规则复杂度分层使用**

---

## 二、主要问题与优化建议

### P0：Stage 2.6 全文审核支路直接复用 Judge 重配置，导致长文本 SLA 被全文支路拖垮

**现象证据**
- 报告显示 `stage26_total = 694.1211s`，已经显著高于 `Stage 2` 本体
- 真实调用 `call_13_full_document_audit` 单次耗时 `694.113s`
- 文件：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/benchmark/reports/single_sample_flow_20260324_generated_longdoc/llm_results/call_13_full_document_audit.json`

**代码定位**
- `Stage 2.6` 直接使用 `config.JUDGE_MODEL_PROFILE`：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_6_full_document.py:231`
- 同时沿用了 Judge 的 `max_retries` 与 `timeout_seconds`：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_6_full_document.py:238`
- 全文文本块构造会把“缺来源片段 + 全文来源片段”全部打进 prompt：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_6_full_document.py:124`

**问题判断**
- 当前 `Stage 2.6` 在代码上还没有形成独立的“全文审核 profile”
- 它实际上共享了最重的 Judge 配置，且 prompt 构造会随着命中片段数扩大而继续膨胀
- 在长文本下，这会让全文审核支路直接吞掉大部分总耗时

**建议方向**
- 给 `Stage 2.6` 单独拆 profile，不要直接复用 `JUDGE_MODEL_PROFILE`
- 允许 `Stage 2.6` 使用更轻的模型/更小的 thinking budget/更短的 timeout
- 对全文片段包增加上限控制，不要无差别拼接所有命中窗口
- 对“全文已足够明确违规”的场景增加纯代码提前终止条件，减少无必要的全文 LLM 复核

---

### P1：`KB0068` 这类高语境依赖规则落入通用 skill，长文本下存在误报放大风险

**现象证据**
- 最终命中 `KB0068`，证据为：`报销范围`
- 真实结果文件：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/benchmark/reports/single_sample_flow_20260324_generated_longdoc/llm_results/call_06_skill_通用合规检测.json`
- 当前 reasoning 是：因为“医疗险”在直播语境中指商业保险，所以“报销范围”构成违规

**代码定位**
- `KB0068` 规则本身有较强例外边界：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/data/rule_cards.json`
- 该规则当前 `category_group = other`，没有进入更专门的 consumer / medical / terminology 路由
- 通用 prompt 会统一注入 chunk、规则依据、例外、facts、长文本上下文：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/skills.py:46`

**问题判断**
- 这类规则不是简单的“命中报销就违规”，而是高度依赖：
  - 当前是在解释服务流程，还是在销售宣传
  - 当前说的是社保/医保，还是商业保险
  - 当前是不是在中性介绍“报销范围”“理赔流程”等服务边界
- 现在它通过 `skill_通用合规检测` 来承接，在长文本教育/培训/直播脚本语境下，容易把中性功能说明放大成违规主张

**建议方向**
- 将 `KB0068` 这一簇规则从 `通用合规检测` 中拆出去，进入更窄的术语/责任边界类 skill
- 或者在路由前增加更强的“服务说明 / 条款解释 / 理赔流程”负向信号保护
- 这类规则优先做“最小违规主张识别”，避免通用 prompt 对整段直播语境做过度主观解释

---

### P1：长文本上下文增强目前是“所有 Stage 2 调用统一加邻近上下文”，收益和成本不成比例

**现象证据**
- 本次样本 `Stage 1.8` 路由后全部进入 skill，`base=0`
- `Stage 2` 共进行了 9 次精判，其中多个调用超过 `80s`，最长达到 `445.398s`
- 相关调用见流程报告中的 `call_04 ~ call_12`

**代码定位**
- 长文本上下文包构造：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_deep_judge.py:104`
- prompt 始终会注入 `context_bundle`（若存在）：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/skills.py:129`

**问题判断**
- 当前实现是“只要进入长文本模式，就为 Stage 2 调用普遍增加上下文包”
- 这对 `cross_paragraph`、`subject_switch`、`tax_or_law_misinterpretation` 这类复杂规则有帮助
- 但对很多局部就能裁决的规则（例如部分术语、绝对化、简单金融混淆）来说，额外上下文会显著增大 prompt，却不一定显著提升判断质量

**建议方向**
- 将 longdoc context bundle 改为按 `skill_type / rule_route_hint / complexity_level` 条件启用
- 只有确实依赖跨块语义的规则才拼接前后文摘要
- 对本地即可裁决的规则，默认只给当前 chunk 与最小 facts，避免长文本模式把所有规则都变成重判定

---

### P1：全文审核输出类别仍允许模型自由漂移，后续评测和统计会不稳定

**现象证据**
- `call_13_full_document_audit` 返回的是：
  - `primary_category = data_compliance`
  - `secondary_category = unverified_statistics`
- 但代码只在字段为空时才回填默认值

**代码定位**
- 默认回填逻辑：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage2_6_full_document.py:248`

**问题判断**
- 这意味着全文审核支路虽然规则 ID 已被统一成 `FULLDOC_RULE_ID_THIRD_PARTY_SOURCE`
- 但类别体系仍可能随模型输出而漂移
- 对 benchmark、聚类分析、审查点命中统计都会造成口径不稳定

**建议方向**
- `Stage 2.6` 对外输出的类别建议直接强制归一，不要接受模型自由填写的 category label
- 将全文审核结果的 `primary_category / secondary_category` 固化为项目内部标准枚举

---

### P2：当前长文本样本中 skill 路由占比过高，说明“长文本模式”仍更像“全量深判”而不是“重点深判”

**现象证据**
- 本次样本 `Stage 1.8` 路由的 9 个 pair 全部为 `skill`
- 文件：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/benchmark/reports/single_sample_flow_20260324_generated_longdoc/SINGLE_SAMPLE_AUDIT_FLOW_REPORT_20260324_GENERATED_LONGDOC.md`

**代码定位**
- 路由决策逻辑：`/Users/junqi/Desktop/工作/01-demo/03-demo/claude-moderation/src/moderation/stages/stage1_8_route_dispatch.py:44`
- 其中 `route_hint=prefer_skill`、`complexity_level=complex`、`inferred_complex_skill` 都会直接把 pair 推向 skill 轨

**问题判断**
- 在长文本模式下，如果召回到的候选绝大部分都直接走 skill，系统会迅速退化成“全量大模型精判”
- 这会抵消之前 base 轨和 Gate 设计的性能收益

**建议方向**
- 长文本模式下单独复核 `prefer_skill` 的使用范围
- 将一部分“结构化边界已经很强”的规则重新压回 base + verify 轻量路径
- 对同类规则做 chunk 内去重或证据合并，避免同一长文本内重复深判相似规则

---

## 三、结论归纳

基于这份最新流程报告，我认为当前项目代码**没有新的致命断链问题**，但有 4 个非常值得优先优化的点：

1. `Stage 2.6` 需要独立轻量 profile，否则长文本一定被全文审核拖慢
2. `KB0068` 这类高语境规则不宜继续由通用 skill 承接，误报风险偏高
3. 长文本上下文增强应改成“按规则选择性注入”，而不是“长文本下一律加料”
4. 全文审核输出类别应强制归一，避免模型自由漂移

从优先级看，最值得先处理的是：
- **P0：Stage 2.6 profile 与 prompt 体积控制**
- **P1：KB0068 及同类术语边界规则的专门化路由/skill 收口**

