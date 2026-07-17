# 代码审查结论（2026-03-26，本地当前快照）

## 一、审查范围

本次审查基于当前**本地未推送代码快照**，重点复核以下升级点：

1. Stage 1 Filter 失败后的候选压缩逻辑  
2. Stage 2.6 全文审核并行启动与收口逻辑  
3. Stage 2 / Stage 2.6 共享并发预算  
4. 长文本 / 语义预检 / 全文审核相关回归测试  

本次未改动业务代码，仅完成只读审查与测试验证。

---

## 二、总体结论

### 结论摘要

当前版本可以作为下一步基线继续推进。  
本轮没有发现新的**高优先级正确性阻塞问题**。

这次 P0 优化整体方向是正确的，尤其是：

- Filter fallback 已从“全量放行 Top-20”收敛为“保头部 + 多样性压缩 + 小上限控制”，能明显减轻后续 Stage 2 的最坏情况放大；
- 全文审核已经从串行尾部执行改成 Stage 0 后并行启动，结构上更合理；
- Stage 2 与 Stage 2.6 已共享并发预算，避免全文审核单独抢占模型调用资源。

从代码稳定性、结构一致性、已有回归结果看，这一版是**正确且可接受的性能优化落地**，没有明显以牺牲审核效果换速度的粗暴改动。

---

## 三、测试结论

本次实际执行并通过的测试：

### 1）定向回归

```bash
python -m pytest tests/test_llm_thinking_controls.py tests/test_stage2_6_full_document.py tests/test_workflow_fulldoc_merge.py tests/test_semantic_prescreen_pipeline.py tests/test_benchmark_runtime_overrides.py tests/test_output_and_benchmark_contracts.py -q
```

结果：

- `44 passed, 3 warnings`

### 2）路由 / 语义预检 / 长文本相关

```bash
python -m pytest tests/test_routing_and_prompt.py tests/test_semantic_prescreen_rules.py tests/test_longdoc_mode.py -q
```

结果：

- `32 passed`

### 3）项目快速基线（排除 integration）

```bash
python -m pytest tests/ -m 'not integration' -q
```

结果：

- `173 passed, 5 deselected, 3 warnings`

结论：  
当前本地快照在**非集成测试范围内**没有发现回归破坏。

---

## 四、重点审查结论

### 4.1 Filter fallback 压缩：实现正确，且比旧版安全

代码位置：

- `src/moderation/stages/stage1_recall_filter.py`

本次新增的 `_compress_fallback_candidates()` 逻辑具备以下优点：

1. 永远保留前排高相关候选，避免过度压缩伤主召回；
2. 再按 `audit_point/category/group/claim_type` 做多样性补充；
3. 最终仍保留顺序补齐，避免过度激进裁剪；
4. 已同时接入 `run_stage1()` 和 `run_stage1_filter_only()` 两条 Filter 失败路径。

这部分实现风格统一、边界清晰、测试覆盖充分。  
我认为这是本轮最稳妥、收益最高的一项优化。

### 4.2 全文审核并行启动：结构合理，接入位置正确

代码位置：

- `src/moderation/workflow.py`
- `src/moderation/stages/stage2_6_full_document.py`

当前实现是在 Stage 0 完成后立即启动全文审核任务，Stage 2.6 只负责等待并收口结果。  
这个依赖关系是正确的，因为全文审核只依赖 `document`，不依赖 Stage 1/2 的中间判定。

这比旧版“全部主流程跑完后再单独启动全文审核”更合理，也更符合你之前提出的并行思路。

### 4.3 Stage 2 / Stage 2.6 共享信号量：实现正确

代码位置：

- `src/moderation/workflow.py`
- `src/moderation/stages/stage2_deep_judge.py`
- `src/moderation/stages/stage2_6_full_document.py`

目前共享并发预算的做法是：

- 使用同一个 `asyncio.Semaphore`
- 上限取 `min(MAX_CONCURRENT_CALLS, STAGE2_MAX_CONCURRENT_CALLS)`

这个策略是对的。  
它避免了“全文审核并行化之后反而把主判定挤慢”的典型副作用。

---

## 五、当前仍建议关注的问题

以下问题**不是高优先级阻塞**，但值得后续继续优化。

### 5.1 Benchmark 仍然是样本级串行，离线评测总耗时仍会很长

代码位置：

- `benchmark/runners/run_sdk.py`

当前 `run_cases()` 仍然是按样本顺序逐条执行。  
这意味着即便单样本内部已经优化了并发，`33` 条、`100+` 条 smoke 的总 wall-clock 依旧会很长。

这不是本轮 P0 的回归问题，但它仍然是离线评测耗时过长的主因之一。

### 5.2 Filter fallback 的“多样性压缩”依赖规则元数据完整度

代码位置：

- `src/moderation/stages/stage1_recall_filter.py`

当前压缩逻辑主要依赖：

- `audit_point_id`
- `primary_category / secondary_category`
- `category_group`
- `claim_type`

如果某些规则这些元数据缺失，压缩就会退化为“前排优先 + 原顺序补齐”。  
这不会造成功能错误，但会让长尾规则的削峰能力不够稳定。

### 5.3 全文审核规则在 Stage 0 即注入 `state.rule_cards`，未来扩展时需防止误入 chunk 召回

代码位置：

- `src/moderation/workflow.py`
- `src/moderation/stages/stage2_6_full_document.py`

当前 `FULLDOC_R001` 本身没有关键词召回字段，所以暂时没有实际问题。  
但从结构上看，全文审核规则已经在 Stage 1 前进入 `state.rule_cards`。

这意味着：  
如果后续再新增带关键词的全文审核规则，而没有显式排除它们进入 chunk 级召回/路由，就可能污染主流程候选集。

这不是当前 bug，但属于后续扩展时需要提前守住的边界。

---

## 六、是否建议继续作为当前基线

建议：**可以。**

当前版本具备以下特点：

- 没有新增高优先级正确性阻塞；
- 关键 P0 变更已通过定向回归和快速基线测试；
- 性能优化是“削峰 + 并行化”，不是通过降模型或砍审核能力换速度；
- 代码结构与现有 Workflow 分层保持一致，可继续演进。

因此，我建议把这版作为后续继续优化的工作基线。

---

## 七、后续优先级建议

如果继续往下做，推荐顺序：

1. **P1：benchmark 样本级有限并行**
   - 解决离线评测总耗时过长问题；
2. **P1：补强规则元数据完整度**
   - 提升 fallback 压缩稳定性；
3. **P1：为全文审核规则增加“仅 document-level 使用”的显式隔离标记**
   - 防止未来全文规则误入 chunk 召回链路。

---

## 最终结论

**本地当前快照审查通过，可继续作为下一步基线。**  
本轮未发现新的高优先级阻塞问题；现有改动整体正确，且没有明显以牺牲审核效果换取性能的风险。
