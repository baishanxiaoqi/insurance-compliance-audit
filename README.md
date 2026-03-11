# 保险文本合规审核系统

基于 Agno 框架和大语言模型的智能合规审核系统，用于检测保险营销文本中的违规内容，提供精确到字符级的定位和修改建议。

## 项目背景

### 业务需求

保险行业受到严格的监管约束，营销材料必须符合银保监会的各项规定。传统的人工审核方式存在以下问题：

- **效率低下**：单篇 5000 字文档需要 30-60 分钟人工审核
- **标准不一**：不同审核员对规则的理解存在差异
- **遗漏风险**：612 条合规规则难以全部记忆和应用
- **成本高昂**：需要大量专业审核人员

### 核心目标

构建一套自动化合规审核系统，实现：

1. **精准识别**：准确识别文本中的违规内容
2. **精确定位**：输出违规片段在原文中的字符级坐标
3. **智能建议**：提供针对性的合规修改建议
4. **高效处理**：单篇文档审核时间 ≤ 3 分钟

### 技术挑战

#### 1. 语境歧义问题

合规判定高度依赖上下文。例如：
- ❌ 违规："我现在月薪 3 万"（代理人介绍当前收入）
- ✅ 合规："我之前在银行工作时月薪 3 万"（描述过往经历）

传统关键词匹配无法区分这种语义差异。

#### 2. 精确定位难题

需要输出违规内容在原文中的准确位置（字符索引），但：
- LLM 对字符级索引天然不敏感
- 直接让 LLM 输出坐标容易产生"幻觉"
- 文本预处理（规范化）会导致坐标偏移

#### 3. 规则复杂度高

- 612 条合规规则无法全部塞入单个 Prompt
- 规则之间存在复杂的条件约束和例外条款
- 部分规则需要跨段落的全文理解

#### 4. 误报控制

向语义层面升级时，LLM 的泛化能力容易导致：
- 相似但合规的表述被错误召回
- 需要精确控制语义识别的边界

## 解决方案

### 核心架构：双策略混合 + 6 阶段流水线

系统采用 **确定性规则引擎** + **LLM 语义理解** 的双轨架构，通过 6 个串行阶段完成审核：

```
原始文本
    ↓
[Stage 0] 预处理与资产固化（纯代码）
    ├─ 文本规范化 + 坐标映射
    ├─ 自适应分块（80-300字）
    └─ Span 切分（最小语义单元）
    ↓
[Stage 1] 召回粗筛（混合检索 + LLM）
    ├─ 关键词正则 + TF-IDF 检索
    └─ LLM Filter：Top-20 → Top-3
    ↓
[Stage 1.5] 事实抽取（纯代码）
    └─ 提取否定词、数字、时态等信号
    ↓
[Stage 1.8] 路由分发（纯代码）
    ├─ base 轨：确定性规则引擎（65%）
    └─ skill 轨：LLM 语义判定（35%）
    ↓
[Stage 2] 深度精判（双轨并发）
    ├─ base 轨：规则引擎执行
    └─ skill 轨：LLM Agent + Skills
    ↓
[Stage 2.5] 反证校验（纯代码）
    └─ 基于事实信号的误报纠偏
    ↓
[Stage 3] 定位组装（纯代码）
    ├─ 零幻觉定位（span_id → 坐标）
    ├─ 坐标还原（norm → raw）
    └─ 重叠去重 + 结果聚合
    ↓
审核报告（JSON）
```

### 关键技术创新

#### 1. 零幻觉定位机制

**问题**：LLM 直接输出字符索引容易产生幻觉。

**解决方案**：
- Stage 0 预处理时，将文本切分为最小语义单元（Span），每个 Span 分配唯一 ID
- LLM 只能输出预定义的 `span_id`，禁止输出原文或字符索引
- Stage 3 通过 `span_id` 从 `span_pool` 查找坐标，确保定位准确

```python
# LLM 输出示例
{
  "verdict": "violation",
  "evidence_span_ids": ["S_chunk001_03", "S_chunk001_04"],  # 只能选择预定义的 ID
  "reasoning": "..."
}

# Stage 3 定位
span = span_pool["S_chunk001_03"]  # O(1) 查找
raw_start = norm_to_raw_map[span.start_index]  # 坐标还原
```

#### 2. 双策略混合架构

**问题**：部分规则可用确定性逻辑处理，全部调用 LLM 浪费成本。

**解决方案**：
- **base 轨**（65%）：简单关键词违规 → 规则引擎处理（零成本、毫秒级）
- **skill 轨**（35%）：复杂语义场景 → LLM 判定（高准确率）

```python
# 规则引擎示例（base 轨）
if "免税" in text and "免税店" not in text:  # 前后缀过滤
    if distance("免税", "收益") < 50:  # 距离约束
        return "violation"
```

#### 3. Skills 技能分发

**问题**：通用 Prompt 难以处理边界 case。

**解决方案**：
- 将规则按类型分组为 5 个基础 Skill + 4 个复杂 Skill
- 每个 Skill 包含专业系统提示 + Few-shot 正反例
- 自动路由到对应 Skill，提升判定准确率

```python
# 复杂场景 Skill 示例
temporal_context_skill = {
    "system_prompt": "你是时态上下文判断专家，需要区分'过往经历'和'当前状态'...",
    "few_shot_examples": [
        {"text": "我之前月薪3万", "verdict": "compliant"},  # 过往
        {"text": "我现在月薪3万", "verdict": "violation"},  # 当前
    ]
}
```

#### 4. 自适应分块策略

**问题**：固定长度切分会在句子中间断开，破坏语义完整性。

**解决方案**：
- 按段落标记（`【标题】`、空行）切分自然段
- 短段合并（< 80 字），长段在句子边界二次拆分
- 上下文回溯重叠（携带前一个 Chunk 的末句）

#### 5. AC 自动机高效匹配

**问题**：612 条规则包含 1000+ 个关键词，逐个正则匹配性能低下。

**解决方案**：
- 使用 Aho-Corasick 算法实现多模式字符串匹配
- 一次扫描匹配所有关键词，时间复杂度从 O(n×m×k) 降至 O(n+m)
- 性能提升 10-50 倍，特别是在 Stage 1 召回和规则引擎中

```python
# AC 自动机示例
matcher = AhocorasickMatcher(["保证", "承诺", "收益"])
result = matcher.find_all("我们保证高收益")
# 一次扫描匹配所有词汇，返回 {"保证": [2], "收益": [5]}
```

## 技术栈

- **框架**：Agno 2.5+ (Workflow + Agent)
- **LLM**：Moonshot API (moonshot-v1-32k)
- **API**：FastAPI + Uvicorn
- **数据校验**：Pydantic
- **中文分词**：jieba
- **多模式匹配**：pyahocorasick (AC 自动机)
- **异步并发**：asyncio

## 快速开始

### 环境要求

- Python 3.10+
- Moonshot API Key（或其他 OpenAI 兼容 API）

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd claude-moderation

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 API Key
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

### API 调用示例

```bash
curl -X POST http://localhost:8000/api/v1/audit \
  -H "Content-Type: application/json" \
  -d '{
    "text": "我们的产品收益比银行存款高出好几倍，绝对保本保息！",
    "doc_id": "test_001"
  }'
```

## 测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行单个测试文件
python -m pytest tests/test_core_behaviors.py

# 运行特定测试
python -m pytest tests/test_core_behaviors.py::TestCoreBehaviors::test_stage3_localization_span_only
```

## 性能指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 处理速度 | ≤ 3 分钟 | 单篇 5000 字文档 |
| 准确率 | ~85% | 基于测试集评估 |
| 召回率 | ~80% | 基于测试集评估 |
| API 成本节省 | ~30% | 双轨架构优化 |
| 关键词匹配性能 | 10-50x | AC 自动机 vs 正则表达式 |
| 并发上限 | 3 | Moonshot 免费版限制 |

## 项目结构

```
claude-moderation/
├── run.py                      # CLI 入口
├── requirements.txt            # 依赖配置
├── .env.example                # 环境变量模板
├── README.md                   # 项目说明（本文档）
├── CLAUDE.md                   # 开发指引
├── AC_INTEGRATION_REPORT.md    # AC 自动机集成报告
├── data/
│   ├── rule_cards.json         # 规则库（612 条）
│   └── sample_input.txt        # 测试文本
├── scripts/
│   └── import_excel_kb.py      # Excel → JSON 转换
├── src/moderation/
│   ├── config.py               # 全局配置
│   ├── schemas.py              # 数据结构
│   ├── workflow.py             # Workflow 编排
│   ├── llm_agent.py            # LLM Agent 封装
│   ├── skills.py               # 基础 Skills
│   ├── complex_skills.py       # 复杂 Skills
│   ├── rule_engine.py          # 规则引擎
│   ├── ac_matcher.py           # AC 自动机封装
│   ├── audit_trace.py          # 审计日志
│   ├── api.py                  # FastAPI 接口
│   └── stages/
│       ├── stage0_preprocess.py
│       ├── stage1_recall_filter.py
│       ├── stage1_5_fact_extract.py
│       ├── stage1_8_route_dispatch.py
│       ├── stage2_deep_judge.py
│       ├── stage2_5_refute.py
│       └── stage3_assemble.py
└── tests/
    ├── test_core_behaviors.py
    ├── test_dual_strategy.py
    ├── test_hybrid_recall.py
    ├── test_ac_matcher.py
    └── ...
```

## 配置说明

所有配置通过 `.env` 文件设置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_API_BASE` | `https://api.openai.com/v1` | LLM API 地址 |
| `LLM_API_KEY` | - | API Key（必需） |
| `LLM_MODEL` | `gpt-4o-mini` | 模型标识 |
| `CHUNK_SIZE` | 300 | Chunk 最大字数 |
| `CHUNK_MIN_SIZE` | 80 | 短段合并阈值 |
| `TOP_K_RULES` | 20 | 混合检索 Top-K |
| `TOP_K_FILTER` | 3 | LLM 粗筛保留数 |
| `MAX_CONCURRENT_CALLS` | 3 | 最大并发 LLM 调用 |
| `ENABLE_TRACE_LOG` | true | 审计轨迹日志开关 |

## 规则库管理

### 从 Excel 导入规则

```bash
# 将 Excel 规则库转换为 JSON
python scripts/import_excel_kb.py
```

### 规则卡片结构

每条规则包含以下字段：

- `rule_id`：唯一标识（如 R001）
- `rule_name`：规则名称
- `risk_level`：风险等级（high/medium/low）
- `violation_definition`：违规定义
- `exceptions`：例外条款
- `keywords`：检索关键词
- `violation_terms`：违规词列表
- `condition_terms`：条件词（需与违规词同时出现）
- `exclusion_terms`：排除词（出现则不违规）
- `suggestion_template`：合规建议模板

## 常见问题

### Q: 如何提升准确率？

A:
1. 优化 Skills 的 Few-shot 示例
2. 调整规则卡片的例外条款
3. 增加 Stage 2.5 的反证规则

### Q: 如何降低 API 成本？

A:
1. 增加 base 轨规则比例（优化规则引擎）
2. 调低 `TOP_K_FILTER` 参数（减少 Stage 2 调用）
3. 使用更便宜的模型（如 gpt-4o-mini）

### Q: 如何处理超长文本？

A:
1. 调整 `CHUNK_SIZE` 参数（默认 300 字）
2. 系统会自动分块处理，无需手动切分
3. 注意 3 分钟 SLA 约束

## 许可证

[待补充]

## 联系方式

[待补充]
