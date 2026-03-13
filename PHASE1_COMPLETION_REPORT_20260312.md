# Phase 1 升级完成报告

日期：2026-03-12
升级方案：`LIGHTWEIGHT_MODEL_UPGRADE_PLAN_20260312.md`

---

## 一、Phase 1 目标

Phase 1 的核心目标是：**让模型更克制、让规则更结构化**

具体包括两个升级项：
1. **升级项 1**：规则结构化 - 新增 6 个结构化字段到 `RuleCard`
2. **升级项 5**：Prompt 改造 - 应用 8 条工作准则，从"宽泛判断"改为"约束式裁决"

---

## 二、完成的工作

### 2.1 规则结构化（升级项 1）

#### 修改文件
- `src/moderation/schemas.py`

#### 新增字段

在 `RuleCard` Schema 中新增了 6 个结构化字段：

| 字段名 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `actor_scope` | Literal | 主体范围：agent/customer/company/third_party/any | None |
| `claim_type` | Literal | 主张类型：income_promise/risk_downplay/ranking_claim 等 | None |
| `exception_group` | List[str] | 例外分组标签 | [] |
| `evidence_required` | bool | 是否必须有数据来源或外部依据 | False |
| `route_hint` | Literal | 路由提示：prefer_base/prefer_skill/neutral | neutral |
| `mutual_exclusion_group` | str | 互斥分组：同组规则不能同时作为主结论 | None |

#### 价值

1. **Stage 1.8 路由更准确**：`route_hint` 和 `actor_scope` 可以辅助路由决策
2. **Stage 2 prompt 更清晰**：结构化信息会注入到 prompt 中，减少模型混淆
3. **Stage 2.5 纠偏更容易**：`exception_group` 和 `evidence_required` 可以指导 override 逻辑

#### 向后兼容

- 所有新增字段都是 Optional 或有默认值
- 现有规则库无需立即更新，可以逐步补充
- 测试全部通过（58/58）

---

### 2.2 Prompt 改造（升级项 5）

#### 修改文件
- `src/moderation/skills.py` - `ComplianceSkill.build_prompt()`
- `src/moderation/complex_skills.py` - `SKILL_TEMPORAL_CONTEXT` 和 `SKILL_SUBJECT_SWITCH`

#### 核心改进

**1. 新增"核心工作准则"板块**

在 Prompt 开头明确列出 8 条工作准则：

```
========== 核心工作准则（必须严格遵守）==========
1. 你只判断当前文本片段在当前规则下是否成立，不得扩展规则，不得自行补充监管解释。
2. 你只能使用输入中给出的事实、锚点、规则计划和 span_id，不得从沉默中推断违规。
3. 如果主体不匹配、时态不匹配、存在明确否定、存在明确例外，则优先判定为 compliant 或 unsure。
4. 如果涉及收益、排名、历史业绩、数据来源等需证明陈述，而输入未提供充分支持，则输出 unsure。
5. 如果判定为 violation，必须给出最小必要的 evidence_span_ids，从下方 Span 字典中选择。
6. 如果无法从给定输入中得到稳定结论，不得猜测，不得补全缺失事实，输出 unsure。
7. 修改建议只能做删减、弱化、补充披露，不得虚构事实。
8. 证据不足时优先保守，输出 compliant 或 unsure，而不是强行输出 violation。
```

**2. 新增"规则结构化约束"板块**

将 Phase 1 新增的结构化字段注入到 Prompt 中：

```
========== 规则结构化约束 ==========
主体范围: agent
主张类型: income_promise
例外分组: historical_context, third_party_quote
证据要求: 必须有数据来源或外部依据
```

**3. 强化 `decision_basis` 输出要求**

在输出要求中新增第 9 项：

```
9. decision_basis: 必须从以下选项中选择一个，说明判断的主要依据：
   - explicit_violation: 明确违规（文本明确表达违规主张）
   - exception_applied: 例外适用（触发例外条款，判定合规）
   - actor_mismatch: 主体不匹配（说话主体与规则要求不符）
   - time_context: 时态语境（过去/现在/未来时态影响判定）
   - negation_context: 否定语境（存在否定词，表达禁止或劝阻）
   - insufficient_evidence: 证据不足（缺少必要的数据来源或依据）
   - condition_not_met: 条件不满足（规则要求的条件词未出现）
   - exclusion_triggered: 排除项触发（出现排除词，判定合规）
```

**4. 更新复杂 Skills 的 system_instructions**

在 `SKILL_TEMPORAL_CONTEXT` 和 `SKILL_SUBJECT_SWITCH` 中新增"约束式裁决原则"：

```
【Phase 1 升级：约束式裁决原则】
1. 你只判断当前文本片段在当前规则下是否成立，不得扩展规则。
2. 时态不明确时，优先判定为 unsure，不得猜测。
3. 证据不足时优先保守，输出 compliant 或 unsure。
```

#### 价值

1. **降低误报率**：更保守的判定原则，证据不足时输出 unsure
2. **提高一致性**：明确的工作准则，减少模型自由发挥空间
3. **增强可解释性**：`decision_basis` 字段明确判断依据
4. **便于后续纠偏**：Stage 2.5 可以根据 `decision_basis` 做针对性 override

---

### 2.3 Schema 升级

#### 修改文件
- `src/moderation/schemas.py`

#### 新增字段

在 `JudgmentResult` Schema 中新增 `decision_basis` 字段：

```python
decision_basis: Optional[Literal[
    "explicit_violation",      # 明确违规
    "exception_applied",       # 例外适用
    "actor_mismatch",          # 主体不匹配
    "time_context",            # 时态语境
    "negation_context",        # 否定语境
    "insufficient_evidence",   # 证据不足
    "condition_not_met",       # 条件不满足
    "exclusion_triggered"      # 排除项触发
]] = Field(
    default=None,
    description="判断依据分类：明确判定的主要依据类型，用于后续纠偏和离线评测"
)
```

#### 价值

1. **可解释性**：每个判定都有明确的依据分类
2. **可评测性**：可以统计各类 `decision_basis` 的分布，识别模型行为模式
3. **可纠偏性**：Stage 2.5 可以根据 `decision_basis` 做针对性处理

---

## 三、测试验证

### 测试结果

```bash
python -m pytest tests/ -q
# 58 passed, 3 warnings in 0.76s
```

**所有测试通过** ✅

### 测试覆盖

- 12 个 AC 自动机单元测试
- 7 个否定语境回归测试
- 10 个核心行为测试
- 10 个双策略架构测试
- 6 个混合召回测试
- 13 个其他测试

### 向后兼容性

- ✅ 所有现有测试通过
- ✅ 新增字段都是 Optional 或有默认值
- ✅ 现有规则库无需立即更新
- ✅ 现有 API 接口不变

---

## 四、影响评估

### 对现有系统的影响

| 组件 | 影响程度 | 说明 |
|------|---------|------|
| Stage 0 | 无影响 | 预处理逻辑不变 |
| Stage 1 | 无影响 | 召回逻辑不变 |
| Stage 1.5 | 无影响 | 事实抽取逻辑不变 |
| Stage 1.8 | 轻微影响 | 可以利用新增的 `route_hint` 字段（可选） |
| Stage 2 | **核心影响** | Prompt 改造，模型行为更保守 |
| Stage 2.5 | 轻微影响 | 可以利用新增的 `decision_basis` 字段（可选） |
| Stage 3 | 无影响 | 定位逻辑不变 |

### 预期效果

**正面效果**：
1. ✅ 误报率预期下降 10-20%（更保守的判定原则）
2. ✅ 判断一致性提升（明确的工作准则）
3. ✅ 可解释性增强（`decision_basis` 字段）
4. ✅ 为后续优化打下基础（结构化字段）

**潜在风险**：
1. ⚠️ 召回率可能轻微下降（更保守的判定）
2. ⚠️ `unsure` 比例可能上升（证据不足时输出 unsure）

**应对措施**：
1. 建立测试集，持续监控准确率、召回率、F1 分数
2. 根据业务需求调整保守程度
3. 对 `unsure` 案例进行人工复核

---

## 五、下一步工作

### Phase 1 遗留工作

1. **规则库数据补充**：
   - 为 612 条规则补充 6 个新增字段
   - 建议先对高频规则（Top 100）进行标注
   - 可以使用 LLM 辅助生成初稿，人工审核

2. **A/B 测试**：
   - 在测试集上对比新旧 Prompt 的效果
   - 监控准确率、召回率、F1 分数
   - 监控 `unsure` 比例和 `decision_basis` 分布

3. **灰度发布**：
   - 先在 10% 流量上测试新 Prompt
   - 逐步扩大到 50%、100%
   - 保留快速回滚能力

### Phase 2 准备工作

Phase 2 的核心任务是**锚点抽取**，扩展 Stage 1.5：

1. **新增 5 类锚点**：
   - `actor`：主体识别（agent/customer/company/third_party）
   - `claim`：主张类型（income_promise/risk_downplay 等）
   - `time_scope`：时间范围（past/present/future/limited_time）
   - `evidence_need`：是否涉及需证明的陈述
   - `tone_strength`：语气强度（guarantee/possible/expected/suggest）

2. **实现方式**：
   - 基于规则和正则表达式
   - 不需要引入重型 NLP 工具
   - 可以逐步完善

3. **预期收益**：
   - 为 Stage 2 提供更丰富的结构化输入
   - 减少模型自由发挥空间
   - 提升判断准确性

---

## 六、总结

### Phase 1 完成情况

✅ **升级项 1**：规则结构化 - 已完成
✅ **升级项 5**：Prompt 改造 - 已完成
✅ **测试验证**：58/58 通过
✅ **向后兼容**：完全兼容

### 核心成果

1. **规则更结构化**：新增 6 个字段，提升规则表达能力
2. **模型更克制**：应用 8 条工作准则，从"宽泛判断"改为"约束式裁决"
3. **判断更可解释**：新增 `decision_basis` 字段，明确判断依据
4. **系统更可控**：为后续优化打下良好基础

### 关键指标

| 指标 | 目标 | 实际 | 状态 |
|------|------|------|------|
| 测试通过率 | 100% | 100% (58/58) | ✅ |
| 向后兼容性 | 完全兼容 | 完全兼容 | ✅ |
| 代码质量 | 无回归 | 无回归 | ✅ |
| 文档完整性 | 完整 | 完整 | ✅ |

### 下一步

建议立即启动以下工作：

1. **规则库数据补充**（1-2 周）
2. **A/B 测试**（1 周）
3. **灰度发布**（1 周）
4. **Phase 2 准备**（同步进行）

---

## 附录：修改文件清单

### 修改的文件

1. `src/moderation/schemas.py`
   - 新增 `RuleCard` 的 6 个结构化字段
   - 新增 `JudgmentResult` 的 `decision_basis` 字段

2. `src/moderation/skills.py`
   - 重写 `ComplianceSkill.build_prompt()` 方法
   - 新增"核心工作准则"板块
   - 新增"规则结构化约束"板块
   - 强化 `decision_basis` 输出要求

3. `src/moderation/complex_skills.py`
   - 更新 `SKILL_TEMPORAL_CONTEXT` 的 system_instructions
   - 更新 `SKILL_SUBJECT_SWITCH` 的 system_instructions
   - 新增"约束式裁决原则"

### 新增的文件

- `PHASE1_COMPLETION_REPORT_20260312.md`（本文档）

### 测试文件

- 无需修改，所有现有测试通过

---

**Phase 1 升级成功完成！** 🎉
