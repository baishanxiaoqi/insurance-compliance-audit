# 保险文本合规审核系统代码审查报告（2026-03-11）

## 1. 审查范围

本次仅做只读审查，未修改任何现有业务代码。

审查对象包括：
- 项目说明与入口：`README.md`、`run.py`
- 核心工作流：`src/moderation/workflow.py`
- 核心数据结构：`src/moderation/schemas.py`
- 各阶段实现：`src/moderation/stages/*.py`
- 支撑模块：`src/moderation/rule_engine.py`、`src/moderation/llm_agent.py`、`src/moderation/skills.py`、`src/moderation/complex_skills.py`、`src/moderation/ocr_preprocessor.py`
- 测试：`tests/`、`test_ocr_preprocessor.py`

## 2. 我对项目需求的理解

这是一个面向**保险营销文本合规审核**的多阶段流水线系统，关键目标是：

1. 识别违规内容
2. 返回字符级定位
3. 给出修改建议
4. 控制处理时延（SLA ≤ 3 分钟）

项目最核心的技术约束有两个：

- **定位必须可靠**：LLM 不能直接输出字符坐标，只能输出 `span_id`，再由 Stage 3 还原为坐标。
- **成本和准确率要兼顾**：能用规则引擎解决的走 `base` 轨，复杂语义问题走 `skill` 轨。

从现有代码来看，这个方向是对的，而且模块边界比较清晰：
- Stage 0 做文本资产固化
- Stage 1 做召回
- Stage 1.5 / 1.8 做结构化事实与路由
- Stage 2 做双轨判定
- Stage 2.5 做误报反证
- Stage 3 做最终定位与组装

## 3. 本地验证结果

已执行：

```bash
python -m pytest tests/ test_ocr_preprocessor.py -q
```

结果：
- `25 passed`
- 有 3 条第三方依赖告警（主要来自 `jieba/pkg_resources`），但不影响当前测试通过

说明：
- 当前核心单元测试是健康的
- 但测试覆盖更偏“局部行为正确”，对“工作流级契约”覆盖仍然不足（见第 5 节建议）

## 4. 总体评价

### 优点

1. **架构方向正确**
   - 双策略架构符合业务现实：简单规则不必消耗 LLM，复杂场景交给 Skill。

2. **数据结构清晰**
   - `DocumentState` / `RuleCard` / `JudgmentResult` / `AuditResponse` 分层明确，便于维护。

3. **Stage 3 已经朝正确方向演进**
   - 当前 `src/moderation/stages/stage3_assemble.py` 已实现 `span-only` 定位，这是很关键的正确性改进。

4. **测试基础比一般原型项目好**
   - 已有针对路由、规则引擎、Stage 3 定位、Stage 2.5 反证的测试。

### 当前最值得优先优化的方向

按优先级排序，我认为最重要的是：

1. **修复“原文坐标契约”被 OCR 预处理破坏的问题**
2. **修复 OCR 识别过于激进的问题**
3. **修复 Stage 1 混合召回名义上是 hybrid、实际上高度依赖关键词的问题**
4. **减少每次请求重复构建静态索引的额外开销**

---

## 5. 详细发现

### [高优先级] 发现 1：Stage 0 入口把“处理后的文本”当成了“原始文本”，会破坏 raw 坐标契约

**位置**：
- `src/moderation/workflow.py:115`
- `src/moderation/workflow.py:119`
- `src/moderation/ocr_preprocessor.py:214`

**现象**：
工作流先执行：
- `normalized_text = normalize_text_for_audit(input_text)`

然后又把这个 `normalized_text` 作为：
- `preprocess(original_text=normalized_text, ...)`

也就是说，`DocumentState.original_text` 保存的已经不是用户真正传入的原文，而是 OCR 修复后的文本。

**这会直接影响项目最关键的 API 契约**：
- Stage 3 的 `raw_start/raw_end`
- `original_text_slice`

它们本应对应“用户输入原文”，但现在对应的是“经过 OCR 修补后的文本”。

**本地复现（只读验证）**：

输入：
```text
第一段。第二段。第三段。
```

经过 `normalize_text_for_audit()` 后会变成：
```text
第一段。\n第二段。\n第三段。\n
```

此时 `doc.original_text == raw_input` 为 `False`，而 `doc.original_text == processed_text` 为 `True`。

**风险**：
- 前端高亮位置可能偏移
- 审核结果无法回指用户原文
- 一旦 OCR 修复插入/删除字符，`raw_start/raw_end` 的语义就变了

**建议**：
- 把“用户原始输入文本”和“审核工作文本”彻底分开保存
- `DocumentState.original_text` 应始终保存用户原文
- OCR 修复结果应作为独立字段，例如 `working_text` / `preprocessed_text`
- 如果 OCR 修复会改写字符，必须额外维护一套“工作文本 -> 原文”的映射，而不是覆盖原文

**结论**：
这是当前审查中最重要的问题之一，建议优先修复。

---

### [高优先级] 发现 2：OCR 文本检测过于激进，正常单行文本也会被当成 OCR 文本处理

**位置**：
- `src/moderation/ocr_preprocessor.py:35`
- `src/moderation/ocr_preprocessor.py:103`
- `src/moderation/ocr_preprocessor.py:220`

**现象**：
`detect_text_source()` 当前逻辑是：
- 只要**没有换行**，就判定为 OCR 文本
- 或平均行长 > 200，也判定为 OCR 文本

这会导致大量正常输入被误判。

**本地验证示例**：

输入：
```text
这是普通的一行营销文案，没有换行，但并不是OCR文本。
```

结果会被识别为 `ocr`，并被自动改写为：
```text
这是普通的一行营销文案，没有换行，但并不是OCR文本。\n
```

另一个例子：
```text
第一段。第二段。第三段。
```
会被自动改写成多行文本。

**风险**：
- 正常文本被错误“修复”
- 与发现 1 叠加后，坐标契约进一步恶化
- 文本召回与分块行为被人为改变

**建议**：
- OCR 检测至少改成“多信号联合判断”，不要只靠“无换行”这一条
- 可以要求同时满足 2~3 个特征，例如：
  - 无换行且超长
  - 中文间异常空格比例高
  - 标点缺失/错乱明显
  - 表格/多栏痕迹明显
- 默认应偏保守：**宁可少修，不要误修正常文本**

**结论**：
这属于正确性问题，不只是体验问题。

---

### [高优先级] 发现 3：Stage 1 的“混合召回”在当前数据下几乎退化成“关键词召回 + 向量重排”

**位置**：
- `src/moderation/stages/stage1_recall_filter.py:268`
- `src/moderation/stages/stage1_recall_filter.py:282`

**现象**：
在 `recall()` 中，代码规定：
- 如果某条规则存在 `violation_terms`
- 且关键词分 `kw_s <= 0`
- 就直接 `continue`

而我本地统计 `data/rule_cards.json` 后发现：
- 总规则数：`612`
- 含 `violation_terms` 的规则数：`612`

也就是说，**所有规则都会受这个门槛影响**。

这会导致：
- TF-IDF 向量检索无法补回“语义相关但未命中关键词”的候选规则
- 向量分数更多只是给“已命中关键词的规则”做重排
- 与 README / 架构说明里的“关键词 + TF-IDF 混合召回”存在明显实现偏差

**风险**：
- 对表述改写、同义表达、弱显式词场景，召回能力会偏弱
- 复杂 Skill 的上游候选可能直接缺失

**建议**：
可考虑以下折中方案之一：

1. **双通道召回**
   - 关键词通道：保精度
   - 向量通道：补召回
   - 最后做并集 + rerank

2. **仅对“强结构化规则”使用关键词硬门槛**
   - 比如有 `condition_terms` / `exclusion_terms` / `prefix_no_match` / `suffix_no_match` 的规则继续严格要求关键词先命中
   - 其他规则允许向量补召

3. **仅对高风险 complex 规则开放 vector-only 候选**
   - 控制成本，同时提升复杂语义召回能力

**结论**：
这是一个比较典型的“文档上是 hybrid，代码上更像 keyword-first strict gate”的问题，建议尽快校正设计与实现的一致性。

---

### [中优先级] 发现 4：Stage 1 的静态索引和 Agent 每次请求都重建，存在可避免的延迟开销

**位置**：
- `src/moderation/stages/stage1_recall_filter.py:404`
- `src/moderation/stages/stage1_recall_filter.py:405`

**现象**：
每次执行 `run_stage1()` 都会新建：
- `HybridRetriever(rule_cards)`
- `build_filter_agent()`

其中 `HybridRetriever` 会重新构建 TF-IDF 索引。

**本地粗测**：
- 以当前 612 条规则做 20 次构建
- 平均每次约 `0.135s`

单次看不大，但在 API 场景下会成为稳定的请求固定成本。

**建议**：
- 基于规则文件路径或 hash 做进程内缓存
- 当规则库未变化时，复用 `HybridRetriever`
- Filter Agent 也可以做懒加载单例或缓存工厂

**收益**：
- 降低固定首段耗时
- 对 SLA 更友好
- 请求越频繁，收益越明显

---

### [中优先级] 发现 5：复杂场景分类逻辑出现重复实现，后续容易漂移

**位置**：
- `src/moderation/stages/stage1_8_route_dispatch.py:25`
- `src/moderation/complex_skills.py:295`

**现象**：
复杂场景识别逻辑（`temporal_context / subject_switch / commitment_strength / cross_paragraph`）在两个模块中各写了一份，规则几乎相同。

**风险**：
- 后续只改一处，另一处忘记同步
- 路由结果和 Skill 获取逻辑可能逐渐不一致

**建议**：
- 抽到单一模块，例如 `src/moderation/complex_classifier.py`
- Stage 1.8 和 Complex Skill 注册都只依赖这一份逻辑

这是典型的可维护性问题，应该尽早消除。

---

### [中优先级] 发现 6：`CHUNK_OVERLAP` 配置已经名存实亡，但仍然被读取、传递和打印

**位置**：
- `src/moderation/config.py:30`
- `src/moderation/api.py:50`
- `src/moderation/workflow.py:124`
- `src/moderation/stages/stage0_preprocess.py:317`
- `src/moderation/stages/stage0_preprocess.py:329`

**现象**：
- 配置项 `CHUNK_OVERLAP` 仍存在
- API 启动日志仍会打印这个值
- Workflow 仍把它传给 `preprocess()`
- 但 `preprocess()` 注释已经明确写了“已弃用”

**风险**：
- 运维/调用方误以为调这个配置会改变行为
- 实际行为由“句级回溯重叠 + `chunk_min_size` 截断”决定，和配置不一致

**建议**：
二选一：
- 要么彻底删掉这个配置与日志输出
- 要么重新接入真实逻辑，让配置生效

目前这种状态会增加排查成本。

---

### [低优先级] 发现 7：OCR 清洗里有无效代码和“部分修复”的情况

**位置**：
- `src/moderation/ocr_preprocessor.py:50`
- `src/moderation/ocr_preprocessor.py:76`

**现象 A：引号替换是无效代码**

`fix_ocr_punctuation()` 里：
- `text.replace('"', '"')`
- `text.replace("'", "'")`

这两行实际上是 no-op，不会产生任何效果。

**现象 B：中文字符间空格修复不彻底**

例如本地测试：
```text
保 险 产 品 收 益 稳 健，预期年化3%。
```
处理后会变成：
```text
保险 产品 收益 稳健，预期年化3%。
```

说明当前正则只能“部分消空格”，不能把整串 OCR 拆开的中文词完全恢复。

**建议**：
- 删除 no-op 代码，避免误导维护者
- 对中文间空格修复改为循环收敛或更稳健的规则
- 增补对应测试用例

---

## 6. 测试层面的观察

当前测试总体不错，但我认为还缺两类高价值测试：

### 建议补充 1：工作流级“原文坐标契约”测试

建议新增一个集成测试，验证：
- 输入原文被 OCR 预处理改写时
- 最终返回的 `raw_start/raw_end` 仍对应原始输入文本

这是本项目最关键的契约之一，应该有专门测试守住。

### 建议补充 2：Stage 1 语义补召回测试

建议新增测试验证：
- 某段文本与规则语义相关，但不直接命中 `violation_terms`
- 系统是否还能通过向量通道把该规则召回

目前这条链路在实现上基本被硬门槛堵住了，建议用测试把设计目标写死。

---

## 7. 推荐的优化优先级

### 第一批（建议优先处理）

1. 修复 `original_text` 被 OCR 处理结果覆盖的问题
2. 调整 OCR 检测策略，减少误判正常文本
3. 重新设计 Stage 1 的 hybrid recall，使向量检索真正发挥补召作用

### 第二批（性能 / 可维护性）

4. 缓存 `HybridRetriever` / Filter Agent
5. 合并重复的复杂场景分类逻辑
6. 清理 `CHUNK_OVERLAP` 的配置漂移

### 第三批（代码洁净度）

7. 清理 OCR no-op 逻辑和局部无效修复逻辑
8. 顺手统一注释/文档中“5 阶段 / 6 阶段 / 7 步骤”的表述

---

## 8. 结论

这个项目的**总体架构思路是成熟的**，特别是：
- 双轨策略
- span-only 定位
- 结构化输出约束
- Stage 2.5 反证纠偏

这些设计都体现了比较强的工程意识。

但从“真正可上线、可稳定给出字符级定位”的角度看，当前最关键的问题不是模型效果，而是：

- **文本预处理和原文坐标契约还没有完全隔离好**
- **Stage 1 混合召回的实现与设计目标不完全一致**

如果先把这两个点修好，整个系统的可信度和可维护性都会明显上一个台阶。

