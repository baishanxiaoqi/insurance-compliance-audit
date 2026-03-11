# 保险文本合规审核系统 - 架构文档

## 1. 系统概述

基于 Agno 框架和大语言模型的多阶段审核流水线，用于检测保险营销文本中的合规违规内容，并提供精确到字符级的定位和修改建议。

**核心特性**：
- 双策略混合架构（确定性规则引擎 + LLM 语义理解）
- 6 阶段流水线处理
- 零幻觉定位机制
- SLA 约束：单次审核 ≤ 3 分钟

**技术栈**：
- Agno 2.5+ (Workflow + Agent)
- Moonshot API (moonshot-v1-32k)
- FastAPI + Uvicorn
- Pydantic (强类型 Schema)

---

## 2. 核心架构

### 2.1 双策略混合架构（方案3）

系统采用双轨并行处理，根据规则复杂度自动分发：

```
                    ┌─────────────────┐
                    │  Stage 1.8      │
                    │  路由分发        │
                    └────────┬────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
        ┌───────▼────────┐       ┌───────▼────────┐
        │  策略A (base)   │       │  策略B (skill)  │
        │  规则引擎       │       │  LLM Agent      │
        └───────┬────────┘       └───────┬────────┘
                │                         │
                │  65% 规则               │  35% 规则
                │  零成本                 │  语义理解
                │  毫秒级                 │  复杂场景
                │                         │
                └────────────┬────────────┘
                             │
                    ┌────────▼────────┐
                    │  Stage 3        │
                    │  定位组装        │
                    └─────────────────┘
```

#### 策略A（base 轨）- 快速确定性引擎
- **适用场景**：简单关键词违规、明确的条件词/排除词约束
- **技术实现**：纯代码规则引擎（`rule_engine.py`）
- **优势**：零成本（无 LLM 调用）、确定性输出、毫秒级响应
- **处理比例**：约 65% 的规则

#### 策略B（skill 轨）- 深度语义理解
- **适用场景**：语境歧义、跨句逻辑、复杂例外条款、主体切换
- **技术实现**：LLM Agent + Skills（基础 Skills + 复杂 Skills）
- **优势**：语义理解能力强、专业 Few-shot 提升准确率
- **处理比例**：约 35% 的规则

#### 复杂场景专用 Skills
1. **时态上下文判断**（temporal_context）：区分"过往经历" vs "当前状态"
2. **主体切换识别**（subject_switch）：区分"代理人" vs "客户" vs "公司"
3. **承诺强度判断**（commitment_strength）：区分"保证/承诺" vs "预期/可能"
4. **跨段落逻辑**（cross_paragraph）：需要全文上下文的复杂判定

---

### 2.2 六阶段流水线

系统通过 `src/moderation/workflow.py` 编排 6 个串行 Stage：

```
┌──────────────────────────────────────────────────────────────┐
│                     审核流水线                                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Stage 0: 预处理                                             │
│  ├─ 文本规范化                                               │
│  ├─ 自适应分块 (80-300字)                                    │
│  ├─ Span 切分                                                │
│  └─ 生成坐标映射表 (norm_to_raw_map + span_pool)             │
│                                                              │
│  Stage 1: 召回粗筛                                           │
│  ├─ 混合检索：关键词正则 (60%) + TF-IDF (40%)                │
│  ├─ Top-20 候选规则                                          │
│  └─ LLM Filter Agent 筛选到 Top-3                            │
│                                                              │
│  Stage 1.5: 事实抽取                                         │
│  ├─ 提取事实信号 (action/negation/certainty/number_percent)  │
│  └─ 为 Stage 2.5 反证校验提供结构化输入                       │
│                                                              │
│  Stage 1.8: 路由分发                                         │
│  ├─ 规则复杂度评估                                           │
│  ├─ base 轨：确定性规则引擎                                   │
│  ├─ skill 轨：LLM 语义判定                                    │
│  └─ 复杂场景类型识别                                          │
│                                                              │
│  Stage 2: 深度精判                                           │
│  ├─ 双轨并发执行                                             │
│  ├─ 单规则注入（每个 chunk-rule 对独立调用）                  │
│  ├─ 结构化输出：JudgmentResult                               │
│  └─ unsure 高风险二次审查                                     │
│                                                              │
│  Stage 2.5: 反证校验                                         │
│  ├─ 基于事实信号的误报纠偏                                    │
│  ├─ 检查否定词、例外条款、主体切换                            │
│  └─ 将误判的 violation 改写为 compliant                       │
│                                                              │
│  Stage 3: 定位组装                                           │
│  ├─ 通过 evidence_span_ids 从 span_pool 获取坐标             │
│  ├─ 坐标还原：norm → raw (通过 norm_to_raw_map)              │
│  ├─ 坐标重叠去重                                             │
│  └─ 组装 AuditResponse                                       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 核心模块

### 3.1 数据结构层 (`schemas.py`)

```python
DocumentState          # 文档资产容器
├─ original_text       # 原始文本
├─ normalized_text     # 规范化文本
├─ chunks              # 文本块列表
├─ span_pool           # 全局 Span 池
└─ norm_to_raw_map     # 坐标映射表

Span                   # 最小语义单元
├─ span_id             # 唯一标识
├─ span_text           # 文本内容
├─ start_index         # 起始位置
└─ end_index           # 结束位置

RuleCard               # 规则卡片
├─ rule_id             # 规则ID
├─ violation_definition # 违规定义
├─ keywords            # 关键词列表
├─ violation_terms     # 违规词
├─ condition_terms     # 条件词
└─ exclusion_terms     # 排除词

JudgmentResult         # 判定结果
├─ verdict             # 判定结论 (violation/compliant/unsure)
├─ reasoning_cot       # 推理链
├─ evidence_span_ids   # 证据 Span ID 列表
└─ reason_codes        # 原因代码

AuditResponse          # 最终输出
├─ violations          # 违规列表
├─ locations           # 定位信息
└─ processing_time     # 处理耗时
```

### 3.2 规则引擎 (`rule_engine.py`)

确定性规则执行器，支持：

```python
RuleEngineReport
├─ hard_block          # 硬性阻断（前后缀拼接词）
├─ has_violation_hit   # 违规词命中
├─ condition_pass      # 条件词距离检查通过
└─ exclusion_blocked   # 排除词距离检查阻断

支持的约束类型：
- violation_terms: 违规词命中检测
- condition_terms + condition_distance: 条件词距离约束
- exclusion_terms + exclusion_distance: 排除词距离约束
- prefix_no_match / suffix_no_match: 前后缀拼接词过滤
```

### 3.3 Skills 技能系统

#### 基础 Skills (`skills.py`)
覆盖 R001-R012 规则：
- 收益类违规检测 (R001, R003)
- 用语合规检测 (R002, R009)
- 信息真实性检测 (R006, R007)
- 消费者保护检测 (R008, R010, R011)
- 营销合规检测 (R004, R005, R012)

#### 复杂 Skills (`complex_skills.py`)
处理复杂场景：
- `temporal_context`: 时态上下文判断
- `subject_switch`: 主体切换识别
- `commitment_strength`: 承诺强度判断
- `cross_paragraph`: 跨段落逻辑

#### 自动路由机制
```python
get_skill_for_rule(rule_card) -> str
├─ 知识库规则 (KB*) 通过关键词自动分桶到基础 Skill
├─ 复杂场景通过规则特征自动识别并路由到复杂 Skill
└─ 每个 Skill 包含专业系统提示 + Few-shot 正反例
```

### 3.4 LLM Agent 层 (`llm_agent.py`)

```python
Agno Agent 封装
├─ Moonshot API 适配
├─ 429 退避重试机制
├─ json_mode 结构化输出
├─ asyncio.Semaphore(3) 并发控制
└─ output_schema 强类型约束
```

---

## 4. 关键设计原则

### 4.1 绝对定位隔离
- LLM 禁止输出原文或字符索引
- 只能输出预处理阶段固化的 `span_id`
- 通过 `span_pool` 查找坐标，再通过 `norm_to_raw_map` 还原

### 4.2 单规则注入
- Stage 2 每次 LLM 调用只注入单条 RuleCard
- 避免规则混淆和交叉干扰

### 4.3 双轨架构
- 确定性规则引擎 (base) + LLM 语义判定 (skill)
- 提升准确率和可解释性
- 节省 30% API 成本

### 4.4 强类型约束
- 全链路 Pydantic Schema
- 结构化输出锁死 LLM 自由度

### 4.5 并发控制
- `asyncio.Semaphore(3)` 限制 Moonshot 并发上限
- 所有 LLM 调用共享同一信号量

---

## 5. 数据流图

```
┌─────────────┐
│ 原始文本     │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│ Stage 0: 预处理                      │
│ ├─ normalized_text                  │
│ ├─ chunks (80-300字)                │
│ ├─ span_pool (全局 Span 池)         │
│ └─ norm_to_raw_map (坐标映射表)     │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ Stage 1: 召回粗筛                    │
│ ├─ 混合检索 (关键词 + TF-IDF)       │
│ ├─ Top-20 候选规则                  │
│ └─ LLM Filter → Top-3               │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ Stage 1.5: 事实抽取                  │
│ └─ fact_signals (结构化事实信号)     │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ Stage 1.8: 路由分发                  │
│ ├─ base 轨 (65% 规则)               │
│ └─ skill 轨 (35% 规则)              │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ Stage 2: 深度精判                    │
│ ├─ base 轨: rule_engine.py          │
│ ├─ skill 轨: LLM Agent + Skills     │
│ └─ JudgmentResult (verdict + spans) │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ Stage 2.5: 反证校验                  │
│ └─ 基于 fact_signals 纠偏误报       │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ Stage 3: 定位组装                    │
│ ├─ evidence_span_ids → span_pool    │
│ ├─ norm 坐标 → raw 坐标              │
│ └─ AuditResponse                    │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────┐
│ 审核结果     │
└─────────────┘
```

---

## 6. API 接口

### 6.1 审核接口
```http
POST /api/v1/audit
Content-Type: application/json

{
  "text": "待审核的保险文本...",
  "doc_id": "可选文档ID"
}
```

**响应**：
```json
{
  "violations": [
    {
      "rule_id": "R001",
      "violation_definition": "...",
      "locations": [
        {
          "start": 10,
          "end": 20,
          "text": "违规文本"
        }
      ]
    }
  ],
  "processing_time": 2.5
}
```

### 6.2 健康检查
```http
GET /api/v1/health
```

---

## 7. 配置管理

### 7.1 环境变量 (`.env`)

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

### 7.2 规则库
- **路径**：`data/rule_cards.json`
- **规模**：612 条规则
- **来源**：由 Excel 转换生成（`scripts/import_excel_kb.py`）

---

## 8. 性能优化

### 8.1 成本优化
- base 轨处理 65% 规则，零 LLM 调用成本
- 节省约 30% API 成本

### 8.2 并发优化
- Stage 1 并发处理所有 chunks
- Stage 2 双轨并发执行
- `asyncio.Semaphore(3)` 控制 Moonshot 并发上限

### 8.3 召回优化
- 混合检索：关键词正则 (60%) + TF-IDF (40%)
- Top-20 → Top-3 两阶段筛选

---

## 9. 审计与可观测性

### 9.1 审计轨迹 (`audit_trace.py`)
结构化日志输出：
```
TRACE::stage2.chunk_1.rule_R001::strategy=base::verdict=violation
TRACE::stage2.chunk_2.rule_R003::strategy=skill::skill=detect_income_promise::verdict=compliant
```

### 9.2 日志级别
- `INFO`: 阶段进度
- `DEBUG`: 详细执行信息
- `TRACE`: 审计轨迹（需开启 `ENABLE_TRACE_LOG`）

---

## 10. 已知限制与改进方向

### 10.1 当前限制
- TF-IDF 召回使用自研 `SimpleTfidf`（sklearn 在 Python 3.13 上有兼容问题）
- Skills 仅覆盖 R001-R012，知识库规则 (KB*) 通过自动路由分桶
- Stage 3 定位策略存在优化空间（当前优先 `evidence_texts` 全文匹配，应改为 span-only）

### 10.2 改进方向
- 引入向量检索提升召回准确率
- 扩展复杂 Skills 覆盖更多场景
- 优化 Stage 3 定位策略为纯 span-based
- 支持流式输出降低首字节延迟

---

## 11. 目录结构

```
claude-moderation/
├── src/
│   └── moderation/
│       ├── workflow.py              # 主流水线编排
│       ├── schemas.py               # 数据结构定义
│       ├── llm_agent.py             # Agno Agent 封装
│       ├── rule_engine.py           # 确定性规则引擎
│       ├── skills.py                # 基础 Skills
│       ├── complex_skills.py        # 复杂 Skills
│       ├── audit_trace.py           # 审计轨迹日志
│       └── stages/
│           ├── stage0_preprocess.py
│           ├── stage1_recall_filter.py
│           ├── stage1_5_fact_extract.py
│           ├── stage1_8_route_dispatch.py
│           ├── stage2_deep_judge.py
│           ├── stage2_5_refute.py
│           └── stage3_assemble.py
├── data/
│   ├── rule_cards.json              # 规则库 (612 条)
│   └── sample_input.txt             # 测试文本
├── tests/
│   ├── test_core_behaviors.py       # 核心行为测试
│   └── test_dual_strategy.py        # 双策略架构测试
├── scripts/
│   └── import_excel_kb.py           # Excel 规则导入
├── run.py                           # CLI 入口
└── CLAUDE.md                        # 项目指南
```

---

## 12. 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cat > .env << EOF
LLM_API_KEY=your_moonshot_api_key
LLM_API_BASE=https://api.moonshot.cn/v1
LLM_MODEL=moonshot-v1-32k
EOF

# 3. 运行审核
python run.py audit --file data/sample_input.txt

# 4. 启动 API 服务
python run.py serve --port 8000

# 5. 运行测试
python -m pytest tests/
```

---

**文档版本**: v1.0
**最后更新**: 2026-03-11
