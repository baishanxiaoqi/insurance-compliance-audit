# 保险文本合规审核系统复查报告（Follow-up，2026-03-11）

## 1. 复查说明

本次是对你“已按要求修改后的代码”进行二次复查。

我没有修改任何现有业务代码；本次只做：
- 复查关键修复点是否真正闭环
- 运行测试验证现状
- 做额外的定向探针，寻找测试未覆盖的问题
- 输出新的审查报告文件

## 2. 当前整体结论

整体上，这一轮修改是**明显向好的**，尤其是下面几项已经有效落地：

1. **原文/工作文本已解耦**
   - `DocumentState` 现在明确区分了：
     - `original_text`：用户原文
     - `working_text`：OCR 修复后的工作文本
   - 这比之前直接覆盖原文的做法正确得多。

2. **Stage 3 已接入两级坐标映射**
   - 坐标链路变成：`normalized_text -> working_text -> original_text`
   - 设计方向是正确的。

3. **复杂场景分类逻辑已抽取为单独模块**
   - `src/moderation/complex_classifier.py`
   - 避免了之前双份实现漂移的问题。

4. **Stage 1 已增加缓存层**
   - `src/moderation/stage1_cache.py`
   - 这是有价值的性能优化方向。

5. **测试覆盖进一步增强**
   - 我本地执行：
     ```bash
     python -m pytest tests/ test_ocr_preprocessor.py -q
     ```
   - 结果：`43 passed`

但复查后我仍然发现 **3 个值得优先处理的问题**，其中前 2 个属于高优先级正确性问题。

---

## 3. 已确认修复的部分

### 3.1 原文坐标契约：方向已修正

**相关文件**：
- `src/moderation/workflow.py:115-125`
- `src/moderation/schemas.py:31-49`
- `src/moderation/stages/stage0_preprocess.py:371-436`
- `src/moderation/stages/stage3_assemble.py:26-49`

**结论**：
- 之前“把 OCR 修复文本当成 original_text”的问题，主路径上已经修掉了。
- 新增的 `tests/test_coordinate_contract.py` 也说明你已经意识到这个契约的重要性，这点很好。

### 3.2 混合召回：实现已经比上一版更接近设计目标

**相关文件**：
- `src/moderation/stages/stage1_recall_filter.py:268-311`

**结论**：
- 现在不是所有规则都被关键词硬门槛卡死了。
- 对“强结构化规则”保守，对其他规则允许向量补召，这个方向是合理的。

### 3.3 重复分类逻辑：已收敛

**相关文件**：
- `src/moderation/complex_classifier.py:10-50`
- `src/moderation/stages/stage1_8_route_dispatch.py:19`
- `tests/test_dual_strategy.py:12`

**结论**：
- 这部分可维护性明显提高。

---

## 4. 仍需优化的问题

### [高优先级] 问题 1：`fix_ocr_spacing()` 会吞掉正常文本中的换行，导致段落结构被破坏

**相关文件**：
- `src/moderation/ocr_preprocessor.py:79-106`
- `src/moderation/ocr_preprocessor.py:226-230`

**问题描述**：
虽然 OCR 检测策略已经更保守，但当文本被识别为 `normal` 时，代码仍然会执行：
- `fix_ocr_spacing(text)`
- `fix_ocr_punctuation(text)`

而 `fix_ocr_spacing()` 当前使用了：
- `([\u4e00-\u9fff])\s+([\u4e00-\u9fff])`
- `\s{2,}`

这里的 `\s` 会匹配**空格、Tab、换行**。因此只要是“中文 + 换行 + 中文”，换行就会被直接删掉。

**本地复现**：
输入：
```text
第一段

第二段
第三段
```

实际输出：
```text
第一段第二段第三段
```

我本地直接验证了：
- `fix_ocr_spacing()` 会把换行吞掉
- `preprocess_ocr_text()` 在 `normal` 路径下也会产生同样问题

**影响**：
- 正常文本的段落边界被破坏
- Stage 0 的自然段切分会失真
- 上下文结构、召回质量、复杂场景判断都可能受影响
- 这实际上引入了一个新的正确性回归

**建议**：
- `fix_ocr_spacing()` 应只处理“空格类”问题，不应误处理换行
- 最安全的做法是：
  - 中文间异常空格只匹配普通空格/全角空格，不匹配 `\n`
  - 连续空白压缩也不要覆盖换行
- 另外建议补一个测试：
  - “normal 多行文本经过 `preprocess_ocr_text()` 后，换行结构仍保留”

**结论**：
这是这次复查中最优先建议修的一个问题。

---

### [高优先级] 问题 2：坐标映射算法对“多字符插入”仍不稳，原文定位还没有完全闭环

**相关文件**：
- `src/moderation/stages/stage0_preprocess.py:52-108`
- `src/moderation/stages/stage3_assemble.py:26-49`
- `tests/test_coordinate_contract.py:62-110`

**问题描述**：
你现在新增了 `working_to_original_map`，这一步是对的；但 `_build_coordinate_map()` 的实现仍然是一个**贪心式近似对齐**。

它对“单个字符插入/删除”常常能工作，但对**多个连续插入字符**不稳定。

**本地复现**：
- `original_text = "第一段。第二段。"`
- `working_text  = "第一段。\n\n第二段。"`

然后对 `第二段。` 对应 span 做定位，实际提取结果只剩：
```text
'段'
```

也就是说，坐标已经明显错了。

**为什么会这样**：
- 当前算法只看“source + 1 / target + 1”这类局部跳步
- 一旦 OCR 修复产生两个连续插入字符（例如 `\n\n`），后续对齐就可能整体漂移

**这不是纯理论问题**：
- `add_smart_newlines()`、标题换行、表格重建等步骤都可能引入多个新增字符
- 因此这是一个真实风险，不是边角 case

**当前测试的不足**：
- `tests/test_coordinate_contract.py` 只覆盖了“单个换行插入”的场景
- 还没有覆盖“连续换行 / 多字符插入 / 插入 + 删除混合”的场景

**建议**：
- `_build_coordinate_map()` 不建议继续靠手写贪心推进
- 更稳的方案：
  1. 使用 `difflib.SequenceMatcher` 构建块级映射
  2. 或使用 LCS / 编辑路径回溯建立更稳的字符对齐
- 至少要新增以下测试：
  - 连续两个换行插入
  - OCR 去空格 + 加换行混合修改
  - 表格重建导致的新增分隔符

**结论**：
“原文坐标契约”已经修到一半，但还没有完全稳住；这一点仍然建议高优先级处理。

---

### [中优先级] 问题 3：Stage 1 缓存键只看 `rule_id`，规则内容变了也不会失效

**相关文件**：
- `src/moderation/stage1_cache.py:20-25`
- `src/moderation/stage1_cache.py:28-42`

**问题描述**：
`_compute_rules_hash()` 当前只基于：
- 排序后的 `rule_id` 列表

这意味着：
- 如果规则内容变了，但 `rule_id` 没变
- 缓存仍然命中
- `HybridRetriever` 会继续复用旧索引

**本地复现**：
我做了一个最小实验：
1. 先创建 `R1=退保规则`
2. 再创建 `R1=收益规则`（rule_id 不变，只改内容）
3. 第二次取缓存时，返回的是**同一个 retriever 对象**
4. 结果依然能召回“退保”，却不能召回“收益”

验证结果包括：
- `same object = True`
- `v2 recall收益 = []`
- `v2 recall退保 = ['R1']`

**影响**：
- 规则库热更新后召回结果可能仍然是旧的
- 测试环境/脚本环境里如果重载规则，也可能出现“明明改了规则却不生效”的假象

**建议**：
缓存键至少应包含以下之一：
- 规则完整内容的 hash
- 规则文件的 mtime + size
- `RuleCard.model_dump()` 结果的稳定 hash

并建议新增测试：
- “同一 rule_id、不同规则内容时，缓存应失效并重建索引”

---

### [中优先级] 问题 4：混合召回新增了“向量补召”机制，但关键测试还没有真正锁住行为

**相关文件**：
- `tests/test_hybrid_recall.py:39-65`
- `src/moderation/stages/stage1_recall_filter.py:300-307`

**问题描述**：
`test_simple_rule_allows_vector_recall()` 里，核心断言目前还是注释掉的：
- `self.assertIn("R_SIMPLE", result)` 被注释了

我本地也做了一个探针，像下面这种表述：
- “建议您解除当前保单并购买新产品”
- “建议您终止现有合同后选择新方案”

当前仍然召不回目标规则。

**这说明**：
- 机制层面已经放开了 vector-only 补召
- 但现有 TF-IDF + 阈值对“同义表达”依然不够强
- 这更像“实现了通道”，还没有真正实现稳定补召能力

**建议**：
- 如果你短期内仍坚持用 TF-IDF，就把测试目标改得更务实一些：
  - 验证“相关关键词扩展词”可被补召
  - 不要把“真正同义改写”作为 TF-IDF 的硬指标
- 如果你希望覆盖“解除保单/终止合同/更换保险计划”这类表达，后续应考虑：
  - 规则扩展词表
  - 同义词归一
  - 或 embedding 检索

**结论**：
这是能力边界问题，不像前两个问题那样属于硬 bug，但仍值得继续优化。

---

### [低优先级] 问题 5：文档说明还有少量漂移

**相关文件**：
- `AGENTS.md:147`
- `CLAUDE.md:147`
- `AGENTS.md:253`
- `CLAUDE.md:253`

**问题描述**：
文档里还有一些旧描述，例如：
- `DocumentState` 仍写成旧字段结构
- Stage 3 仍写着“当前优先 evidence_texts 全文匹配，应改为 span-only”

而代码实际上已经：
- 拆分出 `working_text` / `working_to_original_map`
- Stage 3 也已是 span-only

**建议**：
- 下次改代码时顺手同步文档，避免后续维护者被旧说明误导

---

## 5. 建议优先级

### 第一优先级
1. 修复 `fix_ocr_spacing()` 对换行的误伤
2. 重做 `_build_coordinate_map()` 的对齐策略，补上“多字符插入”测试

### 第二优先级
3. 修复 Stage 1 缓存键，只看 `rule_id` 不够
4. 给缓存失效补回归测试

### 第三优先级
5. 继续提升向量补召的真实效果
6. 同步文档说明

---

## 6. 最终结论

这一轮修改**总体是有效的**，尤其是：
- `original_text / working_text` 拆分
- 复杂分类逻辑抽取
- Stage 1 缓存引入
- 新增坐标契约测试

这些都说明项目在往“可维护、可验证”的方向走。

但从“是否已经完全稳妥”来看，我的结论是：

- **主方向修对了**
- **仍有两个高优先级正确性问题没有彻底解决**：
  1. 正常文本换行会被 OCR spacing 修复吞掉
  2. 坐标映射对多字符插入仍不稳

如果先把这两个问题收掉，这个项目在“字符级定位可信度”上会再上一个台阶。

