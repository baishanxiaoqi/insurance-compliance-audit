# 代码审查问题修复报告

## 修复日期
2026-03-11

## 审查报告来源
CODE_REVIEW_REPORT_20260311_FOLLOWUP.md

## 修复概述

本次修复针对二次审查报告中提出的 3 个高优先级问题和 1 个文档同步问题，所有问题已全部修复并通过测试验证。

---

## 问题 1：fix_ocr_spacing() 吞掉换行符 ✅ 已修复

### 问题描述
`fix_ocr_spacing()` 使用 `\s` 匹配所有空白字符（包括换行），导致正常文本的段落结构被破坏。

### 影响
- 正常文本的换行全部被删除
- 段落边界丢失，影响后续分块和召回质量

### 修复方案
**文件**：`src/moderation/ocr_preprocessor.py:79-106`

**修改内容**：
- 将 `([\u4e00-\u9fff])\s+([\u4e00-\u9fff])` 改为 `([\u4e00-\u9fff])[ \u3000]+([\u4e00-\u9fff])`
- 将 `\s{2,}` 改为 `[ \u3000]{2,}`
- 只匹配普通空格和全角空格，不匹配换行符

### 验证结果
```python
# 测试输入
input_text = "第一段\n\n第二段\n第三段"

# 修复前
output = "第一段第二段第三段"  # ❌ 换行被吞掉

# 修复后
output = "第一段\n\n第二段\n第三段"  # ✅ 换行保留
```

**新增测试**：
- `tests/test_ocr_detection.py::test_fix_ocr_spacing_preserves_newlines`
- `tests/test_ocr_detection.py::test_fix_ocr_spacing_removes_spaces_but_keeps_newlines`

---

## 问题 2：坐标映射对多字符插入不稳定 ✅ 已修复

### 问题描述
`_build_coordinate_map()` 使用贪心式对齐，对多字符插入场景（如 `\n\n`）不稳定，导致坐标整体漂移。

### 影响
- 当 OCR 修复插入多个连续字符时，后续坐标会整体漂移
- 原文定位不准确，可能只定位到部分文本

### 修复方案
**文件**：`src/moderation/stages/stage0_preprocess.py:52-108`

**修改内容**：
- 使用 `difflib.SequenceMatcher` 构建块级映射
- 基于匹配块建立稳定的字符对齐
- 对未映射字符使用最近已映射位置策略

### 验证结果
```python
# 测试场景
original_text = "第一段。第二段。"
working_text = "第一段。\n\n第二段。"  # 插入两个换行

# 修复前
extracted = "段。"  # ❌ 只定位到部分文本

# 修复后
extracted = "第二段。"  # ✅ 完整定位
```

**新增测试**：
- `tests/test_coordinate_contract.py::test_multiple_newlines_insertion_mapping`
- `tests/test_coordinate_contract.py::test_mixed_insertion_deletion_mapping`

---

## 问题 3：Stage 1 缓存键只看 rule_id ✅ 已修复

### 问题描述
`_compute_rules_hash()` 只基于 `rule_id` 列表，规则内容变化时缓存不会失效。

### 影响
- 规则库热更新后召回结果仍然是旧的
- 测试环境中修改规则后可能不生效

### 修复方案
**文件**：`src/moderation/stage1_cache.py:20-25`

**修改内容**：
- 使用 `RuleCard.model_dump()` 获取完整规则数据
- 基于规则完整内容计算 hash
- 确保规则内容变化时 hash 也会变化

### 验证结果
```python
# 测试场景：同一 rule_id，不同内容
rule1 = RuleCard(rule_id="R001", keywords=["退保"], ...)
rule2 = RuleCard(rule_id="R001", keywords=["收益"], ...)

# 修复前
hash1 == hash2  # ❌ hash 相同，缓存不失效

# 修复后
hash1 != hash2  # ✅ hash 不同，缓存正确失效
```

**新增测试**：
- `tests/test_stage1_cache.py::test_cache_key_changes_when_rule_content_changes`
- `tests/test_stage1_cache.py::test_retriever_cache_invalidates_on_content_change`
- `tests/test_stage1_cache.py::test_retriever_cache_reuses_on_same_content`

---

## 问题 4：文档描述与代码不一致 ✅ 已修复

### 问题描述
AGENTS.md 和 CLAUDE.md 中的描述与当前代码实现不一致。

### 修复内容

**1. 更新 DocumentState 字段描述**
```markdown
# 修复前
- `DocumentState`: 文档资产 (original_text/normalized_text/chunks/span_pool/norm_to_raw_map)

# 修复后
- `DocumentState`: 文档资产 (original_text/working_text/normalized_text/chunks/span_pool/norm_to_working_map/working_to_original_map)
```

**2. 更新"当前已知限制"**
```markdown
# 修复前
- Stage 3 定位策略存在优化空间（当前优先 `evidence_texts` 全文匹配，应改为 span-only）

# 修复后
- TF-IDF 对同义表达的召回能力有限，后续可考虑 embedding 检索
```

**修改文件**：
- `AGENTS.md:147, 253`
- `CLAUDE.md:147, 253`

---

## 测试覆盖

### 测试统计
- 总测试数：46 个
- 新增测试：9 个
- 通过率：100%

### 新增测试文件
1. `tests/test_stage1_cache.py` - Stage 1 缓存机制测试（4 个测试）
2. 扩展 `tests/test_ocr_detection.py` - OCR 处理测试（+2 个测试）
3. 扩展 `tests/test_coordinate_contract.py` - 坐标映射测试（+2 个测试）

### 测试运行结果
```bash
$ python -m pytest tests/ -v
======================== 46 passed, 3 warnings in 0.72s ========================
```

---

## 审查报告验证

### 问题确认
创建了 `test_review_issues.py` 验证审查报告中提到的所有问题：

**问题 1 验证**：
```
输入: '第一段\n\n第二段\n第三段'
输出: '第一段\n\n第二段\n第三段'
换行保留: True ✅
```

**问题 2 验证**：
```
期望: '第二段。'
实际: '第二段。'
映射正确: True ✅
```

**问题 3 验证**：
```
规则v1 hash: fe7171cb404394ec4889780bea2f7cf3
规则v2 hash: 20bb3efd7957c15e6c28f8be7d88369a
hash相同: False ✅
```

---

## 修复优先级总结

### 第一优先级（已完成）
1. ✅ 修复 `fix_ocr_spacing()` 对换行的误伤
2. ✅ 重做 `_build_coordinate_map()` 的对齐策略

### 第二优先级（已完成）
3. ✅ 修复 Stage 1 缓存键，基于规则完整内容
4. ✅ 同步文档说明

### 第三优先级（待优化）
5. ⏳ 继续提升向量补召的真实效果（中期优化）

---

## 结论

本次修复解决了审查报告中提出的所有高优先级正确性问题：

1. **换行保留问题**：已修复，正常文本的段落结构不再被破坏
2. **坐标映射问题**：已修复，使用 difflib 构建稳定的字符对齐
3. **缓存失效问题**：已修复，规则内容变化时缓存会正确失效
4. **文档同步问题**：已修复，文档描述与代码实现保持一致

所有修复均通过测试验证，系统在"字符级定位可信度"上已显著提升。

---

## 后续建议

1. **混合召回优化**（中优先级）
   - 短期：调整测试目标，验证关键词扩展词可被补召
   - 中期：考虑规则扩展词表、同义词归一
   - 长期：考虑 embedding 检索

2. **持续监控**
   - 关注 OCR 修复场景下的坐标映射准确性
   - 监控规则库更新后的缓存失效情况
   - 收集更多复杂场景的测试用例
