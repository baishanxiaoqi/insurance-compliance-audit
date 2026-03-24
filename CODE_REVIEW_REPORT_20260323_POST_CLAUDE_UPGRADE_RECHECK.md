# 项目代码复审报告（Claude Code 升级后二次复审）

日期：2026-03-23
结论：本轮修改明显修复了上一轮复审中暴露的两个直接问题，且策略A已经进一步向“规则提证 + LLM 最终分类”靠拢。当前版本整体质量较高，但还不能直接宣告“完全最优”；主要剩余风险点集中在 `Stage 1.9 Gate` 仍然具备前置跳过能力，以及端到端集成测试仍未稳定收口。

---

## 一、本轮已确认修复的点

### 1. 知识库 `keywords` / `condition_terms` 交叉问题已修复
上一轮失败测试 `test_rule_cards_keywords_primary_only` 的根因，是 `KB0634` 的 `keywords` 与 `condition_terms` 有交叉，破坏了规则字段契约。

本轮已重新校验 `data/rule_cards.json`，当前 `keywords ∩ condition_terms = 0`，说明该问题已修复。

### 2. Gate 辅助函数兼容性已恢复
上一轮失败测试 `test_neutral_vs_sales_detection` 的根因，是 `_check_neutral_vs_sales()` 的签名升级后，旧测试仍按旧接口调用。

当前实现已兼容旧调用方式：即使不显式传入 `text_content`，函数也能从 `chunk_fact.signals` 中回退组装文本。因此这一问题已修复。

### 3. 策略A 已不再是“纯规则直判”
这是本轮最重要的结构性变化。

`Stage 2` 当前实现里，所有 base 轨先由规则引擎提证；只要规则引擎产出 `violation`，就会统一进入 `base_verify_llm` 做最终语义裁决，而不是直接把规则命中结果输出为最终违规结论。

这说明系统已经从“规则直判”升级到更接近“规则提证 + 轻量 LLM 最终分类”的形态，方向是对的，也比上一轮更符合项目当前对审核效果的要求。

---

## 二、本轮测试情况

### 1. 定向回归测试
已执行：

```bash
python -m pytest tests/test_phase4_upgrades.py tests/test_core_behaviors.py tests/test_audit_point_mapping.py tests/test_output_and_benchmark_contracts.py tests/test_routing_and_prompt.py -q
```

结果：

- 45 passed
- 3 warnings

说明上一轮暴露的两个显性失败点已经收口，同时核心契约、路由、输出、审查点映射等相关回归测试也都通过。

### 2. 全量测试
已尝试执行：

```bash
python -m pytest tests/ -q
python -m pytest tests/ -q --maxfail=1 -x
```

当前观察到：

- 大部分测试文件都能快速结束
- `tests/test_pipeline_integration.py` 执行时间明显偏长，导致全量 `pytest` 在本轮检查中未能稳定收口

进一步按文件拆跑后，其余测试文件都在可接受时间内通过；唯一明显拖慢全量套件的是 `tests/test_pipeline_integration.py`。

因此，这一轮并没有发现新的稳定失败断言，但“全量测试是否完全稳定收口”仍需要继续盯 `pipeline_integration` 这一组端到端测试。

---

## 三、当前代码的正面评价

### 1. 策略A 的方向已经明显改善
本轮最值得肯定的是：

- 规则引擎先提证
- base 轨命中后统一过 `base_verify_llm`
- 规则引擎不再承担全部最终裁决职责

这使得系统明显弱化了“关键词硬判”的风险，尤其对：

- 绝对化夸大表述
- 金融用语混淆
- 责任夸大类表达

这类高歧义场景，是正确方向。

### 2. 结构化输出闭环继续保持完整
从当前回归通过情况看：

- 审查点映射还在
- 输出结构字段还在
- benchmark 契约没有被新改动破坏

这说明本轮修改没有把之前已经建立起来的结构化链路打散。

### 3. 兼容性处理更稳了
Gate 辅助函数恢复向后兼容，说明这轮改动比上一轮更注意测试契约和已有调用方的稳定性。

---

## 四、当前仍建议关注的点

### 1. `Stage 1.9 Gate` 仍然具备前置 `should_skip` 能力
虽然策略A已经升级，但 `Gate` 仍然不是纯 `hint-first` 机制。

当前实现里，`Gate` 依旧可以把某些候选直接标成 `should_skip=True`；而 `Stage 2` 会在进入深判前先过滤这些组合。

这意味着：

- 某些候选可能还没走到最终分类器，就在前置闸门被拦掉
- 如果 `Gate` 对某些审查点的锚点要求仍偏严，它仍可能继续伤召回

因此，从“所有有价值证据都应该进入最终分类”这个目标看，`Gate` 仍然是下一阶段最值得继续收紧和改造的点。

### 2. `pipeline_integration` 仍然是当前测试收口的主要风险点
当前不是断言失败，而是执行时长和稳定性问题。

如果这组测试依赖真实模型调用、长链路推理或高 token 设置，那么它很容易成为：

- 全量 CI 不稳定来源
- 本地无法快速回归的来源
- 判断“本轮代码已完全收口”时的盲区

因此，即使业务代码本身在本轮没有出现新的红灯，这一组集成测试仍然值得单独做一次收口治理。

---

## 五、最终结论

本轮代码修改是有效的，而且修复了上一轮复审里最明确的两个问题：

1. 规则字段契约冲突已修复
2. Gate 兼容性问题已修复

更重要的是，策略A 当前已经不再是简单的“规则直判”，而是更接近：

- 规则引擎先提证
- LLM 做最终违规分类

这说明整体方案方向进一步正确化了。

但从“是否已经最优”这个标准看，我当前的判断仍然是：

**还不能直接说已经最优，但已经比上一轮更接近最优形态。**

当前剩余最主要的两个关注点是：

1. `Stage 1.9 Gate` 仍可能前置丢候选，继续影响召回
2. `tests/test_pipeline_integration.py` 仍然没有在本轮检查里稳定收口

如果下一步继续优化，我建议优先顺序是：

1. 先检查 `Gate -> Stage 2` 的真实丢样本比例
2. 再把 `pipeline_integration` 做成可稳定回归的端到端测试

---

## 六、相关文件

- `data/rule_cards.json`
- `src/moderation/stages/stage1_9_gate.py`
- `src/moderation/stages/stage2_deep_judge.py`
- `tests/test_core_behaviors.py`
- `tests/test_phase4_upgrades.py`
- `tests/test_pipeline_integration.py`
