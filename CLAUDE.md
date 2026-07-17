# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

保险文本合规审核系统 - 基于 Agno 框架和大语言模型的多阶段审核流水线，用于检测保险营销文本中的合规违规内容，并提供精确到字符级的定位和修改建议。

**核心技术栈**：
- Agno 2.5+ (Workflow + Agent)
- Moonshot API (moonshot-v1-32k)
- FastAPI + Uvicorn
- Pydantic (强类型 Schema)
- pyahocorasick (AC 自动机，高效多模式匹配)

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

### 流水线全景 (Agno Workflow) ✨ Phase 4 P1+ & 长文本/全文审核升级

系统通过 `src/moderation/workflow.py` 编排以下串行 Stage（Stage 1A‖1B 并行）：

1. **Stage 0 (预处理)** - `stages/stage0_preprocess.py`
   - 纯代码，无 LLM 调用
   - 文本规范化 + 自适应分块 + Span 切分
   - **长文本模式**：文本长度 ≥ `LONGDOC_THRESHOLD`(1500) 时自动切换为更大 chunk（`LONGDOC_CHUNK_SIZE`=1000 / `LONGDOC_CHUNK_MIN_SIZE`=200），保持细粒度 span 用于定位
   - 生成 `norm_to_raw_map` 坐标映射表和全局 `span_pool`

2. **Stage 1 (召回粗筛)** - `stages/stage1_recall_filter.py` + `stages/stage1_1_semantic_prescreen.py`
   - **Stage 1A（关键词召回）**：AC 自动机关键词匹配 (60%) + TF-IDF (40%)；LLM Filter Agent 从 Top-20 筛到 Top-3
   - **Stage 1B（语义预检）**：`ENABLE_SEMANTIC_PRESCREEN=true` 时并行运行，LLM 扩展联想规则方向，补充语义相关候选；通过 `rule_indexes.py` 反查规则 ID
   - 1A‖1B 结果去重合并，统一进入后续 Stage
   - 使用 5 个独立的 AC 自动机（violation/condition/exclusion/prefix/suffix）

3. **Stage 1.5 (事实抽取)** - `stages/stage1_5_fact_extract.py`
   - 纯代码，基于规则的事实信号提取
   - 提取：action/negation/certainty/number_percent 等信号
   - 为 Stage 1.9 Gate 和 Stage 2.5 Override 提供结构化输入

4. **Stage 1.8 (路由分发)** - `stages/stage1_8_route_dispatch.py`
   - 纯代码，双轨路由决策
   - base 轨：确定性规则引擎 (`rule_engine.py`)
   - skill 轨：LLM 语义判定 (`skills.py` + `complex_skills.py`)
   - 自动识别复杂场景类型（temporal_context/subject_switch/commitment_strength/cross_paragraph）

5. **Stage 1.9 (轻量 Gate)** - `stages/stage1_9_gate.py` ✨ Phase 4 新增
   - 纯代码，前置场景闸门
   - 7 个检查函数（4 个原有 + 3 个新增）：
     - actor_mismatch：主体不匹配检测
     - time_context：时态语境检测
     - evidence_missing：证据缺失检测
     - exception_likely：例外触发检测
     - non_marketing_absolute：非营销绝对化表述（新增）
     - sufficient_disclaimer：充分提示语检测（新增）
     - neutral_vs_sales：中性知识 vs 销售话术（新增）
   - 生成 gate_signals 和 should_skip 标记
   - 为 Stage 2.5 Override 提供 Gate 信号

6. **Stage 2 (深度精判)** - `stages/stage2_deep_judge.py`
   - 双轨并发：base 轨直接执行规则引擎，skill 轨调用 LLM Agent
   - 复杂场景自动路由到专用 Skill
   - 单规则注入：每个 (chunk, rule) 对独立调用
   - 结构化输出：`JudgmentResult` (verdict/reasoning/evidence_span_ids/primary_category/secondary_category)
   - unsure 高风险二次审查
   - ✨ Phase 4 P1+ 升级：不再生成 draft_suggestion，专注判定和证据提取

7. **Stage 2.5 (审查点 Override 层)** - `stages/stage2_5_refute.py` ✨ Phase 4 升级
   - 纯代码，配置化 override 规则系统
   - 7 个 override 规则（优先级 10-110）：
     - absolute_low_risk_exception：绝对化低风险例外
     - surrender_disclaimer_sufficient：减保提示语充分
     - regulatory_objective_description：监管客观描述
     - background_comparison_context：背景对比
     - non_recruitment_context：非销售招募语境
     - deterministic_hard_block：可执行规则硬阻断
     - negation_context：否定语境
   - 接收 Stage 1.9 Gate 信号，实现 Gate 依赖型 override
   - 将误判的 violation 改写为 compliant

8. **Stage 2.6 (全文审核子流水线)** - `stages/stage2_6_full_document.py` ✨ 新增
   - 与主流程并行，专门检测文档级违规
   - 纯代码信号提取优先：正则检测数据引用（百分比/排名/增速等）+ 来源说明缺失判断
   - 无数据引用或全部有来源时直接跳过（零 LLM 成本）
   - 存在缺少来源的数据引用时调用 LLM 精判（`FULLDOC_R001`）
   - `chunk_id="__fulldoc__"`，`evidence_span_ids` 指向 `span_pool` 真实 span
   - 合成 `FULLDOC_R001` RuleCard 注入 `state.rule_cards`
   - 结果存入 `stage26_full_document_judgments`，在 Stage 2.7/Stage 3 前与主流程结果合并

9. **Stage 2.7 (建议生成层)** - `stages/stage2_7_suggestion.py` ✨ Phase 4 P1+ 新增
   - 纯代码，审核层与展示层解耦
   - 合并 `stage2_judgments` + `stage26_full_document_judgments` 后统一生成建议
   - 优先使用 RuleCard 的 suggestion_template
   - 根据违规类型智能生成默认建议
   - 结合 evidence_texts 提供具体修改指导
   - 输出 `SuggestionResult` (suggestion/suggestion_type)

10. **Stage 3 (定位组装)** - `stages/stage3_assemble.py`
    - 纯代码，零幻觉定位
    - 合并主流程 + 全文审核判定后统一处理
    - 通过 `evidence_span_ids` 从 `span_pool` 获取坐标
    - 坐标还原：norm → raw (通过 `norm_to_raw_map`)
    - 从 Stage 2.7 的 suggestions 字典获取建议
    - 坐标重叠去重 + 组装 `AuditResponse`

### 关键设计原则

1. **绝对定位隔离**：LLM 禁止输出原文或字符索引，只能输出预处理阶段固化的 `span_id`
2. **单规则注入**：Stage 2 每次 LLM 调用只注入单条 RuleCard，避免规则混淆
3. **双轨架构**：确定性规则引擎 (base) + LLM 语义判定 (skill)，提升准确率和可解释性
4. **强类型约束**：全链路 Pydantic Schema，结构化输出锁死 LLM 自由度
5. **并发控制**：`asyncio.Semaphore(10)` 
6. **AC 自动机优化**：使用 Aho-Corasick 算法进行多模式字符串匹配，性能提升 10-50 倍

### 核心数据结构 (`schemas.py`)

- `DocumentState`: 文档资产 (original_text/working_text/normalized_text/chunks/span_pool/norm_to_working_map/working_to_original_map)
- `Span`: 最小语义单元 (span_id/span_text/start_index/end_index)
- `Chunk`: 文本块 (chunk_id/chunk_text/spans)
- `RuleCard`: 规则卡片 (rule_id/violation_definition/keywords/violation_terms/condition_terms/exclusion_terms/actor_scope/claim_type/evidence_required) ✨ Phase 4 新增字段
- `JudgmentResult`: 判定结果 (verdict/reasoning_cot/evidence_span_ids/reason_codes/primary_category/secondary_category) ✨ Phase 4 新增分类字段
- `WorkflowState`: 工作流状态 (document/rule_cards/stage1_candidates/stage15_facts/stage18_routes/stage19_gate_results/stage2_judgments/stage26_full_document_judgments/final_response) ✨ 新增 stage26_full_document_judgments
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
| `CHUNK_SIZE` | 300 | 普通文本 Chunk 最大字数 |
| `CHUNK_MIN_SIZE` | 80 | 普通文本短段合并阈值 |
| `LONGDOC_THRESHOLD` | 1500 | 触发长文本模式的字符数阈值 |
| `LONGDOC_CHUNK_SIZE` | 1000 | 长文本模式 Chunk 最大字数 |
| `LONGDOC_CHUNK_MIN_SIZE` | 200 | 长文本模式短段合并阈值 |
| `TOP_K_RULES` | 20 | 混合检索 Top-K |
| `TOP_K_FILTER` | 3 | LLM 粗筛保留数 |
| `MAX_CONCURRENT_CALLS` | 3 | 最大并发 LLM 调用 |
| `ENABLE_TRACE_LOG` | true | 审计轨迹日志开关 |
| `ENABLE_SEMANTIC_PRESCREEN` | false | 语义预检（Stage 1B）开关 |
| `SEMANTIC_PRESCREEN_ENABLE_LLM` | false | 语义预检是否启用 LLM 扩展 |
| `SEMANTIC_PRESCREEN_MAX_DIRECTIONS` | 2 | 语义预检最大联想方向数 |
| `SEMANTIC_PRESCREEN_MAX_EXTENDED_RULES` | 4 | 语义预检最大扩展规则数 |
| `SEMANTIC_PRESCREEN_TIMEOUT_SECONDS` | 15 | 语义预检超时秒数 |

## 重要文件路径

- `data/rule_cards.json`: 全量规则库 (612 条)，由 Excel 转换生成
- `data/sample_input.txt`: 测试用保险营销文本
- `src/moderation/llm_agent.py`: Agno Agent 封装 + Moonshot 适配 + 429 退避
- `src/moderation/ac_matcher.py`: AC 自动机封装，高效多模式字符串匹配
- `src/moderation/audit_trace.py`: 结构化审计轨迹日志 (TRACE::stage2.*)
- `src/moderation/rule_indexes.py`: 规则索引，供语义预检反查规则 ID
- `src/moderation/stages/stage1_1_semantic_prescreen.py`: Stage 1B 语义预检
- `src/moderation/stages/stage2_6_full_document.py`: Stage 2.6 全文审核子流水线

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
   - `tests/test_ac_matcher.py`：AC 自动机单元测试
   - `tests/test_semantic_prescreen_rules.py`：语义预检规则索引测试
   - `tests/test_stage2_6_full_document.py`：Stage 2.6 全文审核纯代码信号提取测试
   - 运行快速回归（跳过 LLM 集成测试）：`python -m pytest tests/ -m 'not integration' -q`

10. **性能优化**：
    - base 轨处理约 65% 的规则，节省 30% API 成本
    - AC 自动机匹配性能提升 10-50 倍（vs 正则表达式）

11. **AC 自动机使用**：
    - Stage 1 召回：5 个独立的 AC 自动机（violation/condition/exclusion/prefix/suffix）
    - 规则引擎：动态构建 AC 自动机进行词汇匹配
    - Stage 2.5 反证：使用 AC 自动机检测否定模式
    - 自动回退：如果 pyahocorasick 未安装，自动回退到正则表达式

12. **证据选择约束（Phase 4 P1+ 升级）**：
    - Skill Prompt 已强化四步计划式裁决流程
    - 严格排除中性描述：功能性描述、中性词汇、修饰性表述
    - 只选择明确表达违规主张的最短语义单元
    - 示例：不要选择"保险可以提供补偿或保障"等功能性描述
    - 示例：提取"本金计息"而非整段功能性描述

## 当前已知限制

- TF-IDF 召回使用自研 `SimpleTfidf`（sklearn 在 Python 3.13 上有兼容问题）
- Skills 仅覆盖 R001-R012，知识库规则 (KB*) 通过自动路由分桶
- TF-IDF 对同义表达的召回能力有限，后续可考虑 embedding 检索
