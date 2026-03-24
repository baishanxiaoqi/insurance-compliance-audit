# 项目代码复审与测试报告（2026-03-23，二次复核）

## 1. 结论

这轮我重新复审了升级后的主链路与测试状态，结论比上一轮明显更积极：

- 上一轮发现的两个显性问题已经修复：
  - `KB0634` 的 `keywords` / `condition_terms` 交叉问题已消除
  - `_check_neutral_vs_sales()` 与测试契约已重新对齐
- 定向测试已经全绿
- 从这轮代码状态看，当前版本已经基本收口到“可继续做效果验证”的阶段

不过从架构目标看，仍有一个重要观察：

- 当前策略A虽然已经引入 `base_verify_llm`，但还不是“所有命中证据统一走 LLM 分类”的最终形态
- 现在仍然是“部分歧义类别走 LLM 验证，其他 base 结果直接输出”

所以当前我会把它定义为：

- **工程质量明显提升，测试状态健康**
- **方向正确，已经可进入下一轮效果评估**
- **但还没有完全达到你定义的最终架构目标**

## 2. 本轮验证结果

### 2.1 已确认修复

#### 修复 1：知识库关键词结构冲突

我重新检查了 `data/rule_cards.json`：

- `keywords ∩ condition_terms = 0`
- 之前 `KB0634` 的冲突已不存在

#### 修复 2：Gate Helper 契约

当前 `_check_neutral_vs_sales()` 签名为：

- `(_rule_card, chunk_fact, text_content="")`

并且在 `text_content` 为空时，会自动从 `chunk_fact.signals` 拼接文本，所以旧测试调用方式已可兼容。

## 3. 测试结果

### 3.1 定向测试

执行命令：

```bash
python -m pytest tests/test_phase4_upgrades.py tests/test_core_behaviors.py tests/test_audit_point_mapping.py tests/test_output_and_benchmark_contracts.py tests/test_routing_and_prompt.py -q
```

结果：

- `45 passed`
- `3 warnings`

### 3.2 全量测试

执行过：

```bash
python -m pytest tests/ -q
```

以及：

```bash
python -m pytest tests/ -q --maxfail=1 -x
```

从当前运行输出看，已不再出现上一轮那两个失败点；本轮重点检查未见新的显性失败。

## 4. 代码审查判断

### 4.1 当前版本已经做对的部分

1. `Stage 2.7` 建议层继续保持独立，审核与展示解耦仍成立。
2. `Gate` 与测试契约已恢复一致。
3. 知识库字段约束比上一轮更干净。
4. `base_verify_llm` 已经真正接进 Stage 2，说明 base 轨不再是完全的纯规则直判。

### 4.2 仍然建议继续关注的点

#### 观察点 1：策略A 还不是“全证据统一过 LLM”

当前代码里，`base_verify_llm` 仍然只覆盖 `_AMBIGUOUS_CATEGORY_GROUPS`：

- `financial_confusion`
- `comparison_violation`
- `responsibility_exaggeration`

这意味着：

- 部分类别已经进入“规则提证 + LLM 确认”
- 但还不是“所有正向证据候选都统一过 LLM 分类”

如果你的最终目标没变，这仍是后续架构演进点，而不是当前 bug。

#### 观察点 2：Gate 仍保留 skip 能力

`Stage 1.9 Gate` 仍然可以把某些候选直接标成 `should_skip=True`。

这不一定是错误，但从“所有证据都让 LLM 判一次”的目标看，它依旧偏强。

## 5. 当前建议

如果你当前阶段的目标是：

- 先保证主链路稳定
- 先保证知识库与测试契约一致
- 先进入新一轮效果评测

那么我认为这版代码已经可以继续往前走。

如果你当前阶段的目标是：

- 完整实现“规则引擎只提证据，所有正向证据统一过轻量 LLM 分类”

那么这版还不是终态，但已经接近。

## 6. 最终判断

本轮结论是：

- **代码质量较上一轮明显提升**
- **当前没有发现新的高优先级正确性问题**
- **测试状态基本恢复健康**
- **可以进入下一轮效果评测 / smoke 验证**

但如果按你前面定义的目标衡量：

> 规则引擎先提证据，再加一个轻量 LLM 做最终违规分类，所有证据都需要走一遍 LLM 分类

那么当前版本仍是 **阶段性高质量版本**，而不是最终完成版。
