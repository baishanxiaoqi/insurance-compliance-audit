# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

保险文本合规审核系统 - 基于 Agno 框架和大语言模型的多阶段审核流水线，用于检测保险营销文本中的合规违规内容，并提供精确到字符级的定位和修改建议。

**核心技术栈**：
- Agno 2.5+ (Workflow + Agent)
- Moonshot API (moonshot-v1-32k)
- FastAPI + Uvicorn
- Pydantic (强类型 Schema)

**SLA 约束**：单次审核耗时 ≤ 3 分钟

## 开发命令

### 环境配置
```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量（需要创建 .env 文件）
# 必需配置：LLM_API_KEY, LLM_API_BASE, LLM_MODEL
```

### 运行审核
```bash
# 使用示例文本审核
python run.py audit

# 审核指定文件
python run.py audit --file data/sample_input.txt

# 保存结果到 JSON
python run.py audit -f input.txt -o result.json

# 详细日志模式
python run.py -v audit
```

### 启动 API 服务
```bash
# 默认端口 8000
python run.py serve

# 自定义端口和热重载
python run.py serve --port 8080 --reload
```

### 测试
```bash
# 运行所有测试
python -m pytest tests/

# 运行单个测试文件
python -m pytest tests/test_core_behaviors.py

# 运行特定测试
python -m pytest tests/test_core_behaviors.py::TestCoreBehaviors::test_stage3_localization_span_only
```

### 知识库导入
```bash
# 从 Excel 转换规则卡片到 JSON
python scripts/import_excel_kb.py
```

## 核心架构

### 双策略混合架构（方案3）

系统采用双策略并行处理，根据规则复杂度自动分发：

**策略A（base 轨）- 快速确定性引擎**
- 适用场景：简单关键词违规、明确的条件词/排除词约束
- 技术栈：纯代码规则引擎（`rule_engine.py`）
- 优势：零成本（无 LLM 调用）、确定性输出、毫秒级响应
- 处理比例：约 65% 的规则

**策略B（skill 轨）- 深度语义理解**
- 适用场景：语境歧义、跨句逻辑、复杂例外条款、主体切换
- 技术栈：LLM Agent + Skills（基础 Skills + 复杂 Skills）
- 优势：语义理解能力强、专业 Few-shot 提升准确率
- 处理比例：约 35% 的规则

**复杂场景专用 Skills（`complex_skills.py`）**
1. 时态上下文判断（temporal_context）：区分"过往经历"vs"当前状态"
2. 主体切换识别（subject_switch）：区分"代理人"vs"客户"
3. 承诺强度判断（commitment_strength）：区分"保证"vs"预期"
4. 跨段落逻辑（cross_paragraph）：需要全文上下文的判定

### 6 阶段流水线 (Agno Workflow)

系统通过 `src/moderation/workflow.py` 编排 6 个串行 Stage：

1. **Stage 0 (预处理)** - `stages/stage0_preprocess.py`
   - 纯代码，无 LLM 调用
   - 文本规范化 + 自适应分块 (80-300字) + Span 切分
   - 生成 `norm_to_raw_map` 坐标映射表和全局 `span_pool`

2. **Stage 1 (召回粗筛)** - `stages/stage1_recall_filter.py`
   - 混合检索：关键词正则 (60%) + TF-IDF (40%)
   - LLM Filter Agent：从 Top-20 筛选到 Top-3
   - 并发处理所有 chunks

3. **Stage 1.5 (事实抽取)** - `stages/stage1_5_fact_extract.py`
   - 纯代码，基于规则的事实信号提取
   - 提取：action/negation/certainty/number_percent 等信号
   - 为 Stage 2.5 反证校验提供结构化输入

4. **Stage 1.8 (路由分发)** - `stages/stage1_8_route_dispatch.py`
   - 纯代码，双轨路由决策
   - base 轨：确定性规则引擎 (`rule_engine.py`)
   - skill 轨：LLM 语义判定 (`skills.py` + `complex_skills.py`)
   - 自动识别复杂场景类型（temporal_context/subject_switch/commitment_strength/cross_paragraph）

5. **Stage 2 (深度精判)** - `stages/stage2_deep_judge.py`
   - 双轨并发：base 轨直接执行规则引擎，skill 轨调用 LLM Agent
   - 复杂场景自动路由到专用 Skill
   - 单规则注入：每个 (chunk, rule) 对独立调用
   - 结构化输出：`JudgmentResult` (verdict/reasoning/evidence_span_ids)
   - unsure 高风险二次审查

6. **Stage 2.5 (反证校验)** - `stages/stage2_5_refute.py`
   - 纯代码，基于事实信号的误报纠偏
   - 检查：否定词、例外条款、主体切换等
   - 将误判的 violation 改写为 compliant

7. **Stage 3 (定位组装)** - `stages/stage3_assemble.py`
   - 纯代码，零幻觉定位
   - 通过 `evidence_span_ids` 从 `span_pool` 获取坐标
   - 坐标还原：norm → raw (通过 `norm_to_raw_map`)
   - 坐标重叠去重 + 组装 `AuditResponse`

### 关键设计原则

1. **绝对定位隔离**：LLM 禁止输出原文或字符索引，只能输出预处理阶段固化的 `span_id`
2. **单规则注入**：Stage 2 每次 LLM 调用只注入单条 RuleCard，避免规则混淆
3. **双轨架构**：确定性规则引擎 (base) + LLM 语义判定 (skill)，提升准确率和可解释性
4. **强类型约束**：全链路 Pydantic Schema，结构化输出锁死 LLM 自由度
5. **并发控制**：`asyncio.Semaphore(3)` 限制 Moonshot 并发上限

### 核心数据结构 (`schemas.py`)

- `DocumentState`: 文档资产 (original_text/working_text/normalized_text/chunks/span_pool/norm_to_working_map/working_to_original_map)
- `Span`: 最小语义单元 (span_id/span_text/start_index/end_index)
- `Chunk`: 文本块 (chunk_id/chunk_text/spans)
- `RuleCard`: 规则卡片 (rule_id/violation_definition/keywords/violation_terms/condition_terms/exclusion_terms)
- `JudgmentResult`: 判定结果 (verdict/reasoning_cot/evidence_span_ids/reason_codes)
- `AuditResponse`: 最终输出 (violations/locations/processing_time)

### Skills 技能分发 (`skills.py` + `complex_skills.py`)

**基础 Skills（覆盖 R001-R012）**：
- 收益类违规检测 (R001, R003)
- 用语合规检测 (R002, R009)
- 信息真实性检测 (R006, R007)
- 消费者保护检测 (R008, R010, R011)
- 营销合规检测 (R004, R005, R012)

**复杂 Skills（处理复杂场景）**：
- 时态上下文判断：区分"过往经历"vs"当前状态"（如薪资场景）
- 主体切换识别：区分"代理人"vs"客户"vs"公司"
- 承诺强度判断：区分"保证/承诺"vs"预期/可能"
- 跨段落逻辑：需要全文上下文的复杂判定

**自动路由机制**：
- 知识库规则 (KB0001-KB0612) 通过关键词自动分桶到基础 Skill
- 复杂场景通过规则特征自动识别并路由到复杂 Skill
- 每个 Skill 包含专业系统提示 + Few-shot 正反例

### 规则引擎 (`rule_engine.py`)

确定性规则执行器，支持：
- `violation_terms`: 违规词命中检测
- `condition_terms` + `condition_distance`: 条件词距离约束
- `exclusion_terms` + `exclusion_distance`: 排除词距离约束
- `prefix_no_match` / `suffix_no_match`: 前后缀拼接词过滤（如"免税店"）

输出 `RuleEngineReport` (hard_block/has_violation_hit/condition_pass/exclusion_blocked)。

## 配置项 (`.env`)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_API_BASE` | `https://api.openai.com/v1` | LLM API 地址 |
| `LLM_API_KEY` | - | API Key (必需) |
| `LLM_MODEL` | `gpt-4o-mini` | 模型标识 |
| `CHUNK_SIZE` | 300 | Chunk 最大字数 |
| `CHUNK_MIN_SIZE` | 80 | 短段合并阈值 |
| `TOP_K_RULES` | 20 | 混合检索 Top-K |
| `TOP_K_FILTER` | 3 | LLM 粗筛保留数 |
| `MAX_CONCURRENT_CALLS` | 3 | 最大并发 LLM 调用 |
| `ENABLE_TRACE_LOG` | true | 审计轨迹日志开关 |

## 重要文件路径

- `data/rule_cards.json`: 全量规则库 (612 条)，由 Excel 转换生成
- `data/sample_input.txt`: 测试用保险营销文本
- `src/moderation/llm_agent.py`: Agno Agent 封装 + Moonshot 适配 + 429 退避
- `src/moderation/audit_trace.py`: 结构化审计轨迹日志 (TRACE::stage2.*)

## API 接口

### POST `/api/v1/audit`
审核文本合规性。

**请求体**：
```json
{
  "text": "待审核的保险文本...",
  "doc_id": "可选文档ID"
}
```

**响应体**：`AuditResponse` (violations/locations/processing_time)

### GET `/api/v1/health`
健康检查。

## 开发注意事项

1. **双策略架构**：系统自动根据规则复杂度分发到 base 轨或 skill 轨，无需手动干预

2. **复杂场景识别**：Stage 1.8 会自动识别 4 种复杂场景（temporal_context/subject_switch/commitment_strength/cross_paragraph）

3. **定位策略**：Stage 3 必须优先使用 `evidence_span_ids` 定位，禁止依赖 `evidence_texts` 全文匹配（会导致重复文本定位错误）

4. **Skills 扩展**：
   - 新增简单规则：通过 `get_skill_for_rule()` 的自动路由分桶
   - 新增复杂场景：在 `complex_skills.py` 中定义新 Skill 并注册

5. **并发限制**：Moonshot 免费版并发上限为 3，所有 LLM 调用共享同一 `Semaphore`

6. **坐标映射**：所有 LLM 输出的 `span_id` 必须通过 `span_pool` 查找，再通过 `norm_to_raw_map` 还原到原始文本坐标

7. **结构化输出**：Agno Agent 使用 `json_mode` (Moonshot 不支持 native structured outputs)，必须传入 `output_schema`

8. **审计轨迹**：Stage 2 的决策过程通过 `audit_trace.trace_event()` 输出结构化日志，包含策略类型和 Skill 信息

9. **测试覆盖**：
   - `tests/test_core_behaviors.py`：核心行为测试
   - `tests/test_dual_strategy.py`：双策略架构测试

10. **性能优化**：base 轨处理约 65% 的规则，节省 30% API 成本

## 当前已知限制

- TF-IDF 召回使用自研 `SimpleTfidf`（sklearn 在 Python 3.13 上有兼容问题）
- Skills 仅覆盖 R001-R012，知识库规则 (KB*) 通过自动路由分桶
- TF-IDF 对同义表达的召回能力有限，后续可考虑 embedding 检索
