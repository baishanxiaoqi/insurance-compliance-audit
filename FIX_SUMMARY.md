# 代码审查问题修复总结

## 修复日期
2026-03-11

## 修复概述
根据 Codex 的代码审查报告（CODE_REVIEW_REPORT_20260311.md），完成了所有高优先级和中优先级问题的修复。

## 已完成的修复

### 第一批（高优先级 - 正确性问题）

#### 1. ✅ 修复原文坐标契约被破坏的问题
**问题**：`DocumentState.original_text` 保存的是 OCR 处理后的文本，导致 Stage 3 返回的坐标无法对应用户真正的输入。

**修复方案**：
- 在 `DocumentState` 中分离 `original_text`（用户原文）和 `working_text`（OCR 修复后的工作文本）
- 添加 `working_to_original_map` 坐标映射表
- 修改 `preprocess()` 函数接收两个文本参数
- 修改 `workflow.py` 正确传递原文和工作文本
- 修改 Stage 3 的 `_norm_to_raw()` 函数实现两级坐标映射（norm → working → original）
- 添加集成测试验证坐标契约（`tests/test_coordinate_contract.py`）

**影响文件**：
- `src/moderation/schemas.py`
- `src/moderation/stages/stage0_preprocess.py`
- `src/moderation/workflow.py`
- `src/moderation/stages/stage3_assemble.py`
- 所有测试文件（更新 `preprocess()` 调用）

#### 2. ✅ 调整 OCR 检测策略，减少误判
**问题**：OCR 检测过于激进，正常的单行文本也会被误判为 OCR 文本。

**修复方案**：
- 改为多信号联合判断（需要至少 2 个信号才判定为 OCR）
- 信号包括：无换行且超长、平均行长度过长、中文间异常空格比例高、标点密度异常低、表格/多栏痕迹
- 短文本（<50 字符）默认为正常文本
- 改进 `fix_ocr_spacing()` 使用循环收敛策略移除中文间空格
- 删除无效的引号替换代码
- 添加测试验证 OCR 检测准确性（`tests/test_ocr_detection.py`）

**影响文件**：
- `src/moderation/ocr_preprocessor.py`

#### 3. ✅ 重新设计 Stage 1 混合召回机制
**问题**：混合召回退化成"关键词召回 + 向量重排"，向量检索无法补召语义相关但未命中关键词的规则。

**修复方案**：
- 实现真正的双通道召回：
  - 关键词通道（保精度）：对强结构化规则（有 condition/exclusion/prefix/suffix 约束）严格要求关键词命中
  - 向量通道（补召回）：对简单规则允许向量补召，向量分数 > 0.3 即可
- 向量通道多召回一些候选（top_k * 2）
- 纯向量召回的规则降低权重（0.4 * vec_s）
- 添加测试验证双通道召回能力（`tests/test_hybrid_recall.py`）

**影响文件**：
- `src/moderation/stages/stage1_recall_filter.py`

### 第二批（中优先级 - 性能 + 可维护性）

#### 4. ✅ 合并重复的复杂场景分类逻辑
**问题**：`stage1_8_route_dispatch.py` 和 `complex_skills.py` 中有完全相同的 `classify_complex_scenario()` 函数。

**修复方案**：
- 创建统一的 `src/moderation/complex_classifier.py` 模块
- 两个文件都导入并使用统一的分类器
- 更新测试文件的导入

**影响文件**：
- `src/moderation/complex_classifier.py`（新建）
- `src/moderation/stages/stage1_8_route_dispatch.py`
- `src/moderation/complex_skills.py`
- `tests/test_dual_strategy.py`

#### 5. ✅ 缓存静态索引和 Agent
**问题**：每次请求都重建 `HybridRetriever` 和 `Filter Agent`，存在可避免的延迟开销（约 0.135s）。

**修复方案**：
- 创建 `src/moderation/stage1_cache.py` 缓存模块
- 基于规则文件 hash 做进程内缓存
- `HybridRetriever` 缓存：当规则库未变化时复用已构建的 TF-IDF 索引
- `Filter Agent` 缓存：全局单例复用
- 修改 `run_stage1()` 使用缓存

**影响文件**：
- `src/moderation/stage1_cache.py`（新建）
- `src/moderation/stages/stage1_recall_filter.py`

#### 6. ✅ 清理 CHUNK_OVERLAP 配置漂移
**问题**：`CHUNK_OVERLAP` 配置已弃用但仍在传递和打印，实际行为由句级回溯重叠决定。

**修复方案**：
- 从 `config.py` 删除配置项（保留注释说明已弃用）
- 从 `api.py` 删除日志输出
- 从 `workflow.py` 删除参数传递
- 从 `stage0_preprocess.py` 删除参数定义
- 更新文档字符串说明

**影响文件**：
- `src/moderation/config.py`
- `src/moderation/api.py`
- `src/moderation/workflow.py`
- `src/moderation/stages/stage0_preprocess.py`

#### 7. ✅ 清理 OCR 无效代码
**问题**：`fix_ocr_punctuation()` 中有无效的引号替换代码（no-op）。

**修复方案**：
- 删除无效的引号替换代码
- 已在任务 2 中一并完成

**影响文件**：
- `src/moderation/ocr_preprocessor.py`

## 测试覆盖

### 新增测试文件
1. `tests/test_coordinate_contract.py`（3 个测试）
   - 验证原文坐标契约
   - 测试 OCR 修复后的坐标映射

2. `tests/test_ocr_detection.py`（9 个测试）
   - 验证 OCR 检测不会误判正常文本
   - 验证 OCR 文本能被正确识别
   - 验证空格修复逻辑

3. `tests/test_hybrid_recall.py`（6 个测试）
   - 验证双通道召回机制
   - 验证强结构化规则的关键词门槛
   - 验证简单规则的向量补召

### 测试结果
- **总测试数**：38 个
- **通过率**：100%
- **新增测试**：18 个
- **原有测试**：20 个（全部通过）

## 性能改进

1. **Stage 1 缓存优化**：
   - 避免每次请求重建 TF-IDF 索引（节省约 0.135s）
   - 避免重复创建 Filter Agent
   - 对频繁请求场景收益明显

2. **OCR 检测优化**：
   - 减少误判，避免不必要的文本修复
   - 保持原文完整性

3. **混合召回优化**：
   - 向量通道补召能力提升
   - 对同义表达、改写表述的召回能力增强

## 代码质量改进

1. **可维护性**：
   - 消除重复代码（复杂场景分类逻辑）
   - 清理配置漂移（CHUNK_OVERLAP）
   - 删除无效代码（OCR 引号替换）

2. **正确性**：
   - 修复原文坐标契约（核心功能）
   - 修复 OCR 检测误判
   - 修复混合召回退化

3. **测试覆盖**：
   - 新增 18 个测试用例
   - 覆盖所有修复的问题
   - 确保回归测试通过

## 未修复的问题

无。所有 Codex 审查报告中提到的高优先级和中优先级问题均已修复。

## 建议的后续优化

1. **Stage 1 语义召回能力**：
   - 当前 TF-IDF 对同义表达的召回能力有限
   - 建议考虑使用 embedding 模型（如 text-embedding-3-small）提升语义理解能力

2. **Stage 2.5 反证校验覆盖度**：
   - 建议增加更多误报模式的测试
   - 验证事实信号提取的准确性

3. **双策略路由准确率**：
   - 建议增加路由决策的准确率测试
   - 监控误路由情况

4. **LLM 调用容错性**：
   - 建议增加超时控制
   - 考虑降级策略（LLM 失败时回退到规则引擎）

## 总结

本次修复完成了 Codex 审查报告中所有高优先级和中优先级问题的修复，共涉及 7 个任务：

- ✅ 修复原文坐标契约被破坏的问题（最高优先级）
- ✅ 调整 OCR 检测策略，减少误判
- ✅ 重新设计 Stage 1 混合召回机制
- ✅ 合并重复的复杂场景分类逻辑
- ✅ 缓存静态索引和 Agent
- ✅ 清理 CHUNK_OVERLAP 配置漂移
- ✅ 清理 OCR 无效代码

所有修复均通过了完整的测试套件（38 个测试，100% 通过率），确保了系统的正确性、性能和可维护性。
