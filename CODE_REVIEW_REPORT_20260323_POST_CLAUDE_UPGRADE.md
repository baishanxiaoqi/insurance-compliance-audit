# 项目代码审查与测试报告（2026-03-23）

## 1. 审查范围

本次审查基于当前工作区未提交改动，重点覆盖：

- `src/moderation/workflow.py`
- `src/moderation/stages/stage2_deep_judge.py`
- `src/moderation/stages/stage1_9_gate.py`
- `src/moderation/stages/stage1_8_route_dispatch.py`
- `src/moderation/llm_agent.py`
- `src/moderation/config.py`
- `src/moderation/schemas.py`
- 相关测试文件与知识库变更

## 2. 核心结论

当前版本已经明显朝“规则提证 + LLM 复核”方向演进，但还**不能算完全收口**。主要有三类问题：

1. **测试未全绿**：当前 `tests/` 全量执行存在 2 个失败点。
2. **知识库元数据存在一处结构冲突**：`KB0634` 同时把同一词放进 `keywords` 和 `condition_terms`。
3. **策略A 仍未完全满足“所有证据都走 LLM 分类”**：当前只有部分歧义类别进入 `base_verify_llm`，且 LLM 失败时会回退到规则直判 `violation`。

## 3. 测试结果

### 3.1 全量测试

执行命令：

```bash
python -m pytest tests/ -q
```

结果：

- 发现 2 个失败点
- 其余测试大面积通过

### 3.2 已确认失败点

#### 失败点 1：知识库关键词约束冲突

失败测试：

- `tests/test_core_behaviors.py::TestCoreBehaviors::test_rule_cards_keywords_primary_only`

问题表现：

- `KB0634` 的 `keywords` 中包含 `上不封顶`、`收益无上限`
- 同时这两个词也出现在 `condition_terms`

当前数据：

- `data/rule_cards.json` 中仅发现 **1 条** 规则存在这种交叉
- 即：`KB0634`

影响：

- 这会破坏“关键词是主命中词、condition_terms 是附加约束词”的语义边界
- Stage 1 / 规则引擎 / 测试的口径不再一致

#### 失败点 2：Gate Helper 契约未同步

失败测试：

- `tests/test_phase4_upgrades.py::TestPhase4Gates::test_neutral_vs_sales_detection`

问题表现：

- `_check_neutral_vs_sales()` 当前签名是：
  - `(_rule_card, chunk_fact, text_content)`
- 但测试仍按旧签名调用：
  - `(_rule_card, chunk_fact)`

影响：

- 这是典型的“实现升级了，测试契约没同步”
- 不一定影响线上主链路，但说明当前测试套还没完全跟上这轮重构

### 3.3 排除已知失败点后的验证

排除以上 2 个失败点后，其余测试未暴露新的失败：

```bash
python -m pytest tests/ -q -k 'not rule_cards_keywords_primary_only and not neutral_vs_sales_detection'
```

从已跑出的结果看，其余链路基本稳定。

## 4. 代码审查发现

### 4.1 策略A 已部分升级，但没有完全闭环

当前 `Stage 2` 中，base 轨逻辑变成：

- 规则引擎先提证据
- 仅当 `rule_card.category_group in _AMBIGUOUS_CATEGORY_GROUPS` 时，再进入 `base_verify_llm`

现状：

- `financial_confusion`
- `comparison_violation`
- `responsibility_exaggeration`

这三类会走 `base_verify_llm`。

但这并不等于“所有命中证据都走 LLM 分类”。

当前代码仍保留了这条逻辑：

- 非上述类别的 base 结果，仍会直接输出最终 `JudgmentResult`
- 若 `base_verify_llm` 调用失败，还会回退到规则引擎原判 `violation`

影响：

- 这和“所有证据都走一层 LLM 分类”的目标仍有差距
- 在 LLM 超时 / provider 波动时，仍可能回退成规则硬判

### 4.2 Gate 仍然具备较强前置裁决能力

当前 `Gate` 仍会在高置信度下直接 `should_skip=True`，例如：

- `financial_confusion_missing_anchor`
- `financial_confusion_negative_subject`
- `guaranteed_return_missing_anchor`
- `responsibility_exaggeration_missing_anchor`
- `neutral_knowledge`

影响：

- 这意味着某些候选还没进入最终分类器，就已经在 Gate 被裁掉
- 如果你的目标是“只要有证据，就统一让 LLM 分类”，那 Gate 还需要进一步降权

### 4.3 这轮改造最大的积极变化

这次升级有几个明显正向点：

1. `base_verify_llm` 已经落地，说明架构已经从“纯规则直判”往目标方案靠拢。
2. `Stage 2.7` 建议生成拆分保留，审核层和展示层继续解耦。
3. 配置层、调用层、结构化输出恢复链条都更完整了。
4. 绝对化/金融混淆等复杂类别的 skill 和 Gate 已有更细化建模。

## 5. 当前最重要的待收口点

### P0-1：把“部分歧义类别走 LLM”升级成“所有命中证据走 LLM”

当前还只是半收口。

建议目标：

- 规则引擎只负责提证
- 所有 `has_positive_evidence=True` 的 pair 都进入轻量分类器
- 规则引擎不再直接输出最终 `violation`

### P0-2：Gate 从 skip-first 改成 hint-first

建议目标：

- `Gate` 主要产出 `hint`
- 对已有正向证据的 pair，不直接 skip
- 只对“无证据 + 高置信度明显例外”的场景允许跳过

### P0-3：修复测试与知识库契约

建议至少先收口这两个点：

- `KB0634` 的 `keywords` / `condition_terms` 冲突
- `_check_neutral_vs_sales()` 的测试调用契约

## 6. 总结

当前版本属于：

- **方向正确**
- **实现已有明显进展**
- **但还没完全达到你想要的最终形态**

如果按你要的目标来判断：

> “规则引擎先提证据，再让所有证据统一过一层轻量 LLM 做最终违规分类”

那么现在的代码还只是 **部分实现**，尚未完全落地。
