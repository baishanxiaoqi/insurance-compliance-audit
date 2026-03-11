# AC 自动机引入后的项目代码审查报告（2026-03-11）

## 1. 审查范围

本次是在你“引入新的 AC 自动机机制”之后，对整个项目做的新一轮只读审查。

本次未修改任何业务代码，只做了：
- 复查 AC 自动机实现本身
- 复查 AC 在 Stage 1 / Rule Engine / Stage 2.5 中的接入质量
- 运行全量测试
- 做若干定向探针验证边界场景
- 输出新的审查报告文件

---

## 2. 总体结论

整体来看，这次 AC 自动机接入是**有价值的正向改动**：

1. `src/moderation/ac_matcher.py` 封装清晰
2. Stage 1 / Rule Engine / Stage 2.5 都已经接入了统一 matcher
3. 测试、README、项目说明都同步得比较完整
4. 全量测试通过

本地验证命令：

```bash
python -m pytest -q
```

结果：`66 passed`

但是，我这次仍然发现 **1 个高优先级正确性问题** 和 **2 个中优先级性能/设计问题**。

---

## 3. 本次确认做得好的地方

### 3.1 AC 封装本身比较干净

相关文件：
- `src/moderation/ac_matcher.py`
- `tests/test_ac_matcher.py`

优点：
- 提供统一接口：`find_all` / `find_positions` / `has_match`
- 支持大小写不敏感匹配
- 有 regex fallback 设计
- 单元测试覆盖了基本匹配、重叠匹配、空输入等场景

### 3.2 Stage 1 已把违规词全量匹配迁移到 AC

相关文件：
- `src/moderation/stages/stage1_recall_filter.py`

优点：
- `ac_violation` / `ac_condition` / `ac_exclusion` / `ac_prefix` / `ac_suffix` 已经纳入检索器生命周期
- 关键词粗筛从“逐词正则查找”向“统一匹配器”演进，方向正确

### 3.3 文档和测试同步意识不错

相关文件：
- `README.md`
- `CLAUDE.md`
- `tests/test_ac_matcher.py`

优点：
- 这次不是“只改代码不改说明”
- 说明、测试、依赖都跟上了，这点比很多原型项目做得好

---

## 4. 发现的问题

### [高优先级] 问题 1：Stage 2.5 的否定语境检测出现回归，无法识别“多空格/换行分隔”的否定结构

**相关文件**：
- `src/moderation/stages/stage2_5_refute.py:33-48`

**问题描述**：
在 AC 引入前，否定判定使用的是正则：
- `否定词 + \s* + 违规词`

这意味着它可以识别：
- `不要退保`
- `不要 退保`
- `不要   退保`
- `不要\n退保`

但现在的实现改成了构造固定字符串模式：
- `不要退保`
- `不要 退保`

于是只覆盖了：
- 无空格
- 单个空格

却**丢失了多空格和换行**场景。

**我本地探针结果**：

```text
'不要退保'      => True
'不要 退保'     => True
'不要   退保'   => False
'不要\n退保'    => False
```

我还做了一个小型端到端验证：
- 输入：`请不要\n退保，建议保留原保单`
- Stage 2.5 最终没有改判，结果仍是 `violation`

这说明这不是“理论风险”，而是**已经影响真实判定行为的回归**。

**为什么这个问题重要**：
- 你的项目本身就有 OCR 修复和换行处理
- 换行、多个空格在真实文本里并不少见
- Stage 2.5 本来就是误报纠偏层，这类漏判会直接削弱它的价值

**建议**：
- 否定语境这里不适合硬拼字符串模式
- 更合理的方式是：
  1. 保留 AC 负责识别“否定词”和“违规词”本身
  2. 再做位置级距离/空白容忍判断
  3. 或者局部继续用正则处理 `\s*`

**结论**：
这是本轮最重要的问题，建议优先修复。

---

### [中优先级] 问题 2：Stage 1 的 AC 性能收益被部分抵消，`condition/exclusion` 仍在按规则重复全量扫描

**相关文件**：
- `src/moderation/stages/stage1_recall_filter.py:315-336`
- `src/moderation/stages/stage1_recall_filter.py:255-273`

**问题描述**：
在 `_keyword_recall()` 里：
- `self.ac_violation.find_all(chunk_text)` 只做了一次，这是好的
- 但 `self.ac_condition.find_all(chunk_text)` 和 `self.ac_exclusion.find_all(chunk_text)` 仍然放在**规则循环内部**

这意味着：
- 每遇到一条带 `condition_terms` 的规则，就重新扫描一次全文
- 每遇到一条带 `exclusion_terms` 的规则，也重新扫描一次全文

而当前规则库里我本地统计到：
- `condition_terms` 规则：`98` 条
- `exclusion_terms` 规则：`63` 条

也就是说，单个 chunk 最坏情况下可能出现 **161 次额外 AC 全文扫描**。

这会明显稀释 AC 一次扫描多模式匹配的收益。

**另外一个伴随问题**：
`_filter_positions_by_no_match()` 里虽然先调用了：
- `self.ac_prefix.find_all(text)`
- `self.ac_suffix.find_all(text)`

但这两个结果实际上**没有被使用**，后续仍旧回退到拼接短语再做正则查找。

因此：
- prefix/suffix AC 自动机目前更多只是“建了”，没有真正承担核心工作

**建议**：
- 将 `all_condition_matches` / `all_exclusion_matches` 提前到每个 chunk 的单次预计算
- `prefix/suffix` 这块要么真正利用 AC 结果，要么不要重复扫描

**结论**：
这是一个比较典型的“机制已经引入，但收益还没完全兑现”的问题。

---

### [中优先级] 问题 3：`term_to_rules` 已构建但未真正利用，当前检索仍然主要靠“遍历所有规则回填”

**相关文件**：
- `src/moderation/ac_matcher.py:41-50`
- `src/moderation/stages/stage1_recall_filter.py:143-181`
- `src/moderation/stages/stage1_recall_filter.py:281-347`

**问题描述**：
`AhocorasickMatcher` 在初始化时接收了 `term_to_rules`，说明设计上已经考虑到：
- 匹配到 term 后，可以直接知道它关联哪些规则

但当前实现里，这个映射并没有真正被拿来加速候选规则生成。

目前流程仍然是：
1. AC 先返回所有 term 命中
2. 然后再对每条规则，逐个检查它有哪些 term 被命中

所以从工程上看，现在 AC 自动机主要替代了“字符串查找”，但**没有把“命中 term 直接映射到 rule”这一步也吃掉**。

**影响**：
- AC 的价值没有完全释放
- 当前仍保留较明显的“按规则遍历”结构

**建议**：
- 后续可以考虑直接以 `matched_term -> rule_ids` 生成候选 rule 集合
- 再对这些候选做条件词、排除词和重排序

这会更符合 AC 自动机在规则检索里的典型用法。

---

## 5. 测试层面的建议

### 建议补 1：Stage 2.5 的“否定+多空白”回归测试

当前缺少下面这些场景：
- `不要   退保`
- `不要\n退保`
- `不得\n误导`

这类测试应该直接加在 `Stage 2.5` 相关测试里，而不是只测 AC matcher 本身。

### 建议补 2：AC fallback 路径测试

当前 `tests/test_ac_matcher.py` 主要覆盖 AC 正常路径，
但没有显式验证：
- 当 `pyahocorasick` 不可用时，regex fallback 是否仍保持行为一致

这不是当前最急的问题，但从可维护性角度值得补。

---

## 6. 总体评价

如果只看“是否成功把 AC 自动机接进项目”，答案是：**是的，已经接进去了**。

如果看“是否已经把 AC 的收益吃满”，我的判断是：**还没有完全吃满**。

更具体地说：
- **正确性层面**：有一个明确回归点（否定+换行/多空格）
- **性能层面**：Stage 1 里还有重复扫描，AC 价值被部分抵消
- **架构层面**：`term_to_rules` 已经准备好了，但还没被真正利用起来

所以这轮 AC 集成我给出的判断是：

- **方向正确**
- **集成完整度不错**
- **但仍有一个必须优先修的正确性问题**
- **以及两处值得继续优化的性能/设计问题**

