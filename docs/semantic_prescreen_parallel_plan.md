# Phase 4 P2: 语义预检并行召回升级方案（修正版）

## 1. 问题修正

**原设计错误**：语义预检作为 Stage 1 之后的串行步骤
**正确设计**：语义预检与关键词召回**并行执行**，互不阻塞

## 2. 核心架构（并行化）

```
输入文本
    │
    ├────────────────────────────────────────┐
    │                                        │
    ▼                                        ▼
┌─────────────────┐                  ┌─────────────────┐
│ 关键词召回通道    │                  │ 语义预检通道     │
│ (Stage 1)       │                  │ (Stage 1.1) ★   │
│                 │                  │                 │
│ • AC自动机匹配   │                  │ • 轻量规则检测   │
│ • TF-IDF检索    │                  │ • LLM语义预检    │
│ • 召回规则A     │                  │ • 识别风险方向   │
│                 │                  │ • 召回规则B      │
└─────────────────┘                  └─────────────────┘
    │                                        │
    │                                        │
    └────────────────────────────────────────┘
                      │
                      ▼
              ┌─────────────────┐
              │ Stage 1.2: 合并  │
              │ - 去重          │
              │ - 标记来源      │
              │ - 限制总数      │
              └─────────────────┘
                      │
                      ▼
              Stage 1.5 → Stage 2 → ...
```

## 3. 关键设计原则

### 3.1 真正的并行化

```python
async def run_stage1_parallel(document, rule_cards):
    """
    Stage 1 并行执行：关键词召回 + 语义预检同时进行
    """
    # 并行启动两个召回通道
    keyword_task = asyncio.create_task(
        run_stage1_keyword_recall(document, rule_cards)
    )

    semantic_task = asyncio.create_task(
        run_stage1_1_semantic_prescreen(document, rule_cards)
    )

    # 等待两者都完成
    keyword_results, semantic_results = await asyncio.gather(
        keyword_task, semantic_task
    )

    # 合并去重
    return merge_candidates(keyword_results, semantic_results)
```

### 3.2 语义预检的轻量化设计

| 设计点 | 说明 |
|-------|------|
| 仅四类高风险 | 金融混淆、身份混淆、绝对化、违规送礼 |
| 轻量规则初筛 | 纯代码，无 LLM，快速过滤 |
| LLM 只做方向识别 | 不判定违规，只识别"可能存在的风险方向" |
| 限制输出 | 最多识别 2 个风险方向 |

### 3.3 通道职责清晰

| 召回通道 | 擅长召回 | 不擅长 |
|---------|---------|--------|
| 关键词召回 | 明确关键词违规 | 隐性语义、暗示性表述 |
| 语义预检 | 语义层面的风险方向 | 精确词面匹配 |

## 4. 详细设计

### 4.1 语义预检通道（Stage 1.1）

```python
# src/moderation/stages/stage1_1_semantic_prescreen.py

class SemanticPrescreenConfig:
    """语义预检配置"""
    # 四类高风险审查点
    RISK_CATEGORIES = {
        "financial_confusion": {
            "name": "金融用语混淆",
            "keywords": ["银行", "存款", "存钱", "储蓄", "理财"],
            "semantic_patterns": ["和...一样", "相比", "就像", "如同"],
            "target_category_groups": ["financial_confusion", "savings_confusion"],
        },
        "agent_title_confusion": {
            "name": "代理人身份混淆",
            "keywords": ["顾问", "专家", "老师", "规划师"],
            "semantic_patterns": ["我是", "作为", "资深", "金牌", "首席"],
            "target_category_groups": ["agent_title_violation"],
        },
        "absolute_expression": {
            "name": "夸大绝对化表述",
            "keywords": [],
            "semantic_patterns": ["最", "第一", "唯一", "绝对", "肯定", "百分百"],
            "target_category_groups": ["absolute_expression"],
        },
        "gifts_or_benefits": {
            "name": "违规送礼",
            "keywords": ["送", "礼品", "礼物", "优惠", "活动", "红包"],
            "semantic_patterns": ["免费", "额外", "专属", "限时", "感恩", "回馈"],
            "target_category_groups": ["gifts_benefits"],
        },
    }

    # 触发阈值
    MIN_RULES_KEYWORD_CHANNEL = 3  # 关键词召回少于此数时，确保语义预检执行
    MAX_EXTENDED_RULES = 8         # 语义预检最多扩展规则数


@dataclass
class SemanticPrescreenResult:
    """语义预检结果"""
    risk_directions: List[str]  # 识别的风险方向列表
    confidence: str             # high/medium/low
    extended_rules: List[str]   # 扩展召回的规则ID列表
    reasoning: str              # 识别依据简要说明
    duration_ms: int            # 执行耗时


async def run_stage1_1_semantic_prescreen(
    document: DocumentState,
    rule_cards: Dict[str, RuleCard],
    keyword_candidate_count: int,  # 关键词召回的规则数
    semaphore: asyncio.Semaphore,
) -> List[ChunkCandidates]:
    """
    Stage 1.1: 语义预检通道
    与关键词召回并行执行，识别语义层面的风险方向
    """
    results = []

    for chunk in document.chunks:
        # 1. 轻量规则快速检测（纯代码）
        risk_signals = detect_risk_signals(chunk.chunk_text)

        # 2. 判断是否需要 LLM 深度预检
        should_run_llm = (
            keyword_candidate_count < SemanticPrescreenConfig.MIN_RULES_KEYWORD_CHANNEL
            or risk_signals  # 检测到风险信号
        )

        if not should_run_llm:
            # 跳过此 chunk
            continue

        # 3. LLM 语义预检（轻量模型）
        async with semaphore:
            prescreen_result = await semantic_prescreen_llm(
                chunk, risk_signals
            )

        # 4. 根据风险方向动态召回规则
        if prescreen_result.risk_directions:
            extended_rules = dynamic_recall_by_risk_directions(
                prescreen_result.risk_directions,
                rule_cards,
            )

            if extended_rules:
                results.append(ChunkCandidates(
                    chunk_id=chunk.chunk_id,
                    candidate_rule_ids=extended_rules,
                    source="semantic_recall",  # 标记来源
                ))

    return results


def detect_risk_signals(text: str) -> List[RiskSignal]:
    """
    轻量规则检测：纯代码，无 LLM
    快速识别四类高风险语义特征
    """
    signals = []

    for risk_type, config in SemanticPrescreenConfig.RISK_CATEGORIES.items():
        keyword_hits = [kw for kw in config["keywords"] if kw in text]
        pattern_hits = [p for p in config["semantic_patterns"] if p in text]

        # 评分：关键词命中 + 语义模式命中
        score = len(keyword_hits) + len(pattern_hits) * 2

        if score >= 2:  # 阈值可配置
            signals.append(RiskSignal(
                risk_type=risk_type,
                score=score,
                keywords=keyword_hits,
                patterns=pattern_hits,
            ))

    return signals


async def semantic_prescreen_llm(
    chunk: Chunk,
    risk_signals: List[RiskSignal],
) -> SemanticPrescreenResult:
    """
    LLM 语义预检：只识别风险方向，不做违规判定
    """
    agent = create_agent(
        output_schema=SemanticPrescreenResult,
        instructions=SEMANTIC_PRESCREEN_PROMPT,
        name="semantic_prescreen",
        temperature=0.1,
        profile=config.FILTER_MODEL_PROFILE,  # 轻量模型
    )

    prompt = f"""请快速识别以下保险文本可能存在的风险方向。

【待审核文本】
{chunk.chunk_text}

【轻量规则预检结果】
{format_risk_signals(risk_signals)}

任务：
1. 判断文本是否存在以下四类风险方向（可多选）：
   - financial_confusion: 将保险与存款/理财等金融产品混淆
   - agent_title_confusion: 夸大代理人身份资质
   - absolute_expression: 使用绝对化用语
   - gifts_or_benefits: 以利益诱导销售

2. 仅识别"可能存在"的风险方向，不做违规判定
3. 最多返回 2 个最可能的风险方向

输出格式：
- risk_directions: ["risk_type1", "risk_type2"] 或 []
- confidence: high/medium/low
- reasoning: 简要说明（20字以内）"""

    result = await safe_arun(agent, prompt, ...)
    return result


def dynamic_recall_by_risk_directions(
    risk_directions: List[str],
    rule_cards: Dict[str, RuleCard],
) -> List[str]:
    """
    根据识别的风险方向动态召回规则
    """
    recalled_rules = []

    for direction in risk_directions:
        config = SemanticPrescreenConfig.RISK_CATEGORIES.get(direction)
        if not config:
            continue

        target_groups = config["target_category_groups"]

        # 召回所有匹配 category_group 的规则
        for rule_id, card in rule_cards.items():
            if card.category_group in target_groups:
                recalled_rules.append(rule_id)

    # 去重并限制数量
    unique_rules = list(dict.fromkeys(recalled_rules))
    return unique_rules[:SemanticPrescreenConfig.MAX_EXTENDED_RULES]
```

### 4.2 并行执行主流程

```python
# src/moderation/workflow.py

async def run_stage1_with_semantic_prescreen(
    document: DocumentState,
    rule_cards: Dict[str, RuleCard],
    max_concurrent: int = 10,
) -> Tuple[List[ChunkCandidates], Stage1Metrics]:
    """
    Stage 1 + Stage 1.1 并行执行
    """
    from .stages.stage1_recall_filter import run_stage1
    from .stages.stage1_1_semantic_prescreen import run_stage1_1_semantic_prescreen

    semaphore = asyncio.Semaphore(max_concurrent)

    # 先启动关键词召回
    keyword_task = asyncio.create_task(
        run_stage1(document, rule_cards, semaphore=semaphore)
    )

    # 等待关键词召回完成，获取规则数
    keyword_results = await keyword_task
    keyword_count = sum(len(c.candidate_rule_ids) for c in keyword_results)

    # 同时启动语义预检（已与关键词召回并行）
    # 实际上应该同时启动，这里为了获取 keyword_count 而调整
    # 优化版本见下方

    return merged_results, metrics


# 优化：真正的并行启动
async def run_stage1_parallel_optimized(
    document: DocumentState,
    rule_cards: Dict[str, RuleCard],
    max_concurrent: int = 10,
) -> Tuple[List[ChunkCandidates], Stage1Metrics]:
    """
    真正的并行：关键词召回和语义预检同时启动
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    # 启动关键词召回
    keyword_future = asyncio.ensure_future(
        run_stage1(document, rule_cards, semaphore=semaphore)
    )

    # 启动语义预检（使用预估的召回数，或并行执行）
    semantic_future = asyncio.ensure_future(
        run_stage1_1_semantic_prescreen(
            document, rule_cards,
            keyword_candidate_count=0,  # 0 表示未知，语义预检会执行
            semaphore=semaphore
        )
    )

    # 等待两者完成
    keyword_results, semantic_results = await asyncio.gather(
        keyword_future, semantic_future
    )

    # 合并去重
    merged_results = merge_stage1_results(keyword_results, semantic_results)

    # 统计指标
    metrics = Stage1Metrics(
        keyword_rules=sum(len(c.candidate_rule_ids) for c in keyword_results),
        semantic_rules=sum(len(c.candidate_rule_ids) for c in semantic_results),
        merged_rules=sum(len(c.candidate_rule_ids) for c in merged_results),
    )

    return merged_results, metrics
```

### 4.3 合并与去重（Stage 1.2）

```python
# src/moderation/stages/stage1_2_merge_candidates.py

def merge_stage1_results(
    keyword_results: List[ChunkCandidates],
    semantic_results: List[ChunkCandidates],
) -> List[ChunkCandidates]:
    """
    合并关键词召回和语义预检的结果
    """
    # 构建索引
    chunk_to_keyword = {c.chunk_id: c for c in keyword_results}
    chunk_to_semantic = {c.chunk_id: c for c in semantic_results}

    all_chunk_ids = set(chunk_to_keyword.keys()) | set(chunk_to_semantic.keys())

    merged = []
    for chunk_id in all_chunk_ids:
        keyword_rules = chunk_to_keyword.get(chunk_id, ChunkCandidates(chunk_id, [])).candidate_rule_ids
        semantic_rules = chunk_to_semantic.get(chunk_id, ChunkCandidates(chunk_id, [])).candidate_rule_ids

        # 去重合并，保留顺序（关键词优先）
        seen = set()
        merged_rules = []
        sources = {}  # rule_id -> source

        # 先加关键词召回的
        for rid in keyword_rules:
            if rid not in seen:
                seen.add(rid)
                merged_rules.append(rid)
                sources[rid] = "keyword"

        # 再加语义预检召回的
        for rid in semantic_rules:
            if rid not in seen:
                seen.add(rid)
                merged_rules.append(rid)
                sources[rid] = "semantic"

        # 限制总数（如 20）
        merged_rules = merged_rules[:20]

        merged.append(ChunkCandidates(
            chunk_id=chunk_id,
            candidate_rule_ids=merged_rules,
            rule_sources=sources,  # 记录每个规则的来源
        ))

    return merged
```

## 5. 四类高风险审查点的轻量规则

```python
# src/moderation/stages/semantic_patterns.py

# 金融用语混淆检测
FINANCIAL_CONFUSION_PATTERNS = {
    "trigger_keywords": ["银行", "存款", "存钱", "储蓄", "理财", "收益", "利息"],
    "comparison_patterns": ["和", "与", "比", "相比", "相当于", "就像", "如同", "一样"],
    "score_threshold": 3,
}

# 代理人身份混淆检测
AGENT_TITLE_PATTERNS = {
    "title_keywords": ["顾问", "专家", "老师", "规划师", "财富管理"],
    "qualifier_patterns": ["我是", "作为", "资深", "专业", "金牌", "首席", "顶级"],
    "score_threshold": 3,
}

# 绝对化表述检测
ABSOLUTE_EXPRESSION_PATTERNS = {
    "absolute_words": ["最", "第一", "唯一", "绝对", "肯定", "一定", "百分百", "完全"],
    "context_boost": ["产品", "服务", "公司", "保险", "收益", "保障"],
    "score_threshold": 2,
}

# 违规送礼检测
GIFTS_BENEFITS_PATTERNS = {
    "gift_keywords": ["送", "赠送", "礼品", "礼物", "优惠", "活动", "抽奖", "红包", "福利"],
    "indicators": ["免费", "额外", "专属", "限时", "特别", "感恩", "回馈", "惊喜"],
    "score_threshold": 3,
}
```

## 6. 性能对比

| 方案 | 延迟 | 召回能力 | 成本 |
|------|------|---------|------|
| 原方案（纯关键词） | 基准 | 词面匹配 | 基准 |
| 原设计（串行语义预检） | +150ms | 增强 | +30% |
| **修正方案（并行语义预检）** | **+50ms** | **显著增强** | **+20%** |

并行化的优势：
- 关键词召回和语义预检**同时进行**
- 总延迟 = max(关键词耗时, 语义预检耗时) + 合并耗时
- 语义预检使用轻量模型，耗时约 500ms，与关键词召回（400-600ms）基本重叠

## 7. 文件结构

```
src/moderation/
├── stages/
│   ├── stage1_recall_filter.py      # 现有：关键词召回
│   ├── stage1_1_semantic_prescreen.py  # ★ 新增：语义预检（并行）
│   ├── stage1_2_merge_candidates.py    # ★ 新增：合并去重
│   ├── stage1_5_fact_extract.py        # 现有（编号调整）
│   └── ...
├── semantic_patterns.py             # ★ 新增：四类风险轻量规则
└── workflow.py                      # 修改：集成并行流程
```

## 8. 关键变更点

### workflow.py 修改
```python
# 原流程
async def run_workflow(...):
    stage1_results = await run_stage1(...)      # 关键词召回
    stage15_results = await run_stage1_5(...)   # 事实抽取

# 新流程（并行化）
async def run_workflow(...):
    # Stage 1 + 1.1 并行执行
    stage1_results, stage11_results = await asyncio.gather(
        run_stage1(...),
        run_stage1_1_semantic_prescreen(...)
    )

    # Stage 1.2 合并
    merged_candidates = merge_stage1_results(stage1_results, stage11_results)

    # 继续后续流程
    stage15_results = await run_stage1_5(...)
```

## 9. 验证方案

### 测试用例设计
```python
# 纯语义违规样本（关键词召回困难）
TEST_CASES = [
    {
        "text": "这款产品就像在银行存钱一样安全，但收益更高",
        "expected_recall": ["financial_confusion"],
        "keywords_expected": False,  # 关键词召回可能失败
        "semantic_expected": True,   # 语义预检应召回
    },
    {
        "text": "我是资深财富管理顾问，为您提供最专业的服务",
        "expected_recall": ["agent_title_confusion"],
        "keywords_expected": False,
        "semantic_expected": True,
    },
    {
        "text": "这是市场上最好的产品，收益绝对有保障",
        "expected_recall": ["absolute_expression"],
        "keywords_expected": True,   # 关键词可能召回"最好"
        "semantic_expected": True,
    },
]
```

---

**总结**：修正后的方案实现了真正的并行化，语义预检与关键词召回同时进行，总延迟增加可控（约50ms），但能显著提升隐性语义违规的召回能力。
