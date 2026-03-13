# 独立测试模块建设方案

日期：2026-03-13

## 一、建设目标

当前项目已经有 `tests/` 目录下的单元测试、行为测试和回归测试。  
这些测试适合保障代码正确性，但**不适合回答系统真实效果到底怎么样**。

因此，需要单独建设一套**与项目主流程区独立分开**的测试模块，用来解决四个问题：

1. 用**真实、丰富、可持续积累**的样本评估系统效果；
2. 在升级前后做**可对比的离线评测**；
3. 不干扰主业务代码和现有 `tests/` 体系；
4. 让每次样本跑完后都能产出**可读、可比较、可沉淀**的评估结果。

这套模块的定位不是“单元测试加强版”，而是：

> **一个独立的离线评测与基准测试模块（benchmark/eval module）。**

---

## 二、建设原则

### 1. 与主流程区彻底分开

建议不要把这套东西继续堆到 `tests/` 里。  
`tests/` 应继续保留给：

- 单元测试
- 集成测试
- 回归测试
- 代码级行为验证

新的测试模块建议单独放在仓库顶层，例如：

```text
benchmark/
```

或者

```text
evals/
```

推荐使用 `benchmark/`，因为它更符合“独立评测模块”的语义。

### 2. 只通过“公开入口”调用系统

这套模块不要深度依赖内部 stage 细节。  
优先通过以下两类入口调用：

1. **SDK 模式**：调用 `run_audit()` / `run_audit_sync()`
2. **API 模式**：调用 `/api/v1/audit`

这样做的好处是：

- 测出来的是更接近真实运行效果的结果；
- 升级内部实现时，benchmark 模块更稳定；
- 不会和业务代码强耦合。

### 3. 样本优先于技术

这套模块最核心的资产不是 runner，而是样本。

如果样本不真实、不丰富、不规范，那么：

- 指标没有意义；
- 升级前后比较没有意义；
- 模型优化方向容易被带偏。

所以建设重点要放在：

- 样本来源；
- 标注结构；
- 评测口径；
- 报告输出。

### 4. 离线评测优先，不依赖线上人工感觉

任何升级都应该先在这套 benchmark 上跑一遍。  
目标不是“看起来更好”，而是：

- 误报率是否下降；
- 召回率是否提升；
- 定位是否更准；
- `decision_basis` 是否更稳定；
- 成本和耗时是否变差。

---

## 三、模块定位与范围

这套独立测试模块建议覆盖四类评测任务。

## 1. 端到端审核效果评测

输入真实样本，调用完整审核链路，评估：

- 是否识别出应识别的违规；
- 是否误报；
- 规则命中是否正确；
- 定位是否正确；
- 建议是否合理。

这是最核心的一层。

## 2. 重点场景专项评测

针对项目当前最难的边界场景单独建专题集，例如：

- 时态上下文
- 主体切换
- 否定语境
- 排名/收益/历史业绩证据不足
- 退保引导
- 重复文本与定位
- OCR 干扰文本

这类评测不追求覆盖全量规则，但要追求**高价值边界清晰**。

## 3. 升级前后对比评测

每次升级都应支持跑两组结果：

- baseline 版本
- current 版本

然后输出：

- 指标变化
- 典型改进样本
- 典型退化样本

## 4. 成本与性能评测

除了准确率，还要记录：

- 平均耗时
- P95 耗时
- 平均 LLM 调用次数
- 平均命中规则数
- 平均 violation 数

否则“效果更好”可能只是因为系统更激进或更慢。

---

## 四、目录设计

建议采用如下目录结构：

```text
benchmark/
├── README.md
├── config/
│   ├── benchmark.default.yaml
│   └── label_schema.md
├── datasets/
│   ├── manifest.json
│   ├── core/
│   │   ├── samples.jsonl
│   │   └── attachments/
│   ├── edge_cases/
│   │   ├── temporal_context.jsonl
│   │   ├── subject_switch.jsonl
│   │   ├── negation_context.jsonl
│   │   ├── evidence_insufficient.jsonl
│   │   └── localization.jsonl
│   └── smoke/
│       └── samples.jsonl
├── runners/
│   ├── run_sdk.py
│   ├── run_api.py
│   └── batch_runner.py
├── scorers/
│   ├── rule_metrics.py
│   ├── location_metrics.py
│   ├── suggestion_metrics.py
│   └── summary.py
├── reports/
│   ├── latest/
│   └── history/
├── baselines/
│   └── baseline_20260313.json
└── tools/
    ├── validate_dataset.py
    ├── anonymize_samples.py
    └── build_report.py
```

### 设计说明

- `datasets/`：存放样本和标注
- `runners/`：只负责跑系统
- `scorers/`：只负责打分
- `reports/`：存放跑完后的结果
- `baselines/`：存放基线版本结果
- `tools/`：做样本校验、脱敏、报告整理

这能保证模块边界清晰，不会混进主业务目录。

---

## 五、样本建设方案

## 1. 样本必须来自真实业务语料，不要只靠模型造例子

建议样本来源按优先级排序如下：

1. **真实历史营销文案**
2. **真实审核修改记录**
3. **真实代理人口播话术转写**
4. **真实宣传海报 / 长图 OCR 文本**
5. **真实培训材料摘录**
6. **基于真实样本改写的匿名样本**

不建议用纯模型生成样本直接做主评测集。  
模型生成样本可以用于补边界，但不能成为主数据集。

## 2. 样本必须脱敏与匿名化

所有样本进入 benchmark 之前，必须统一做：

- 客户姓名脱敏
- 公司名脱敏（如有必要）
- 电话、地址、证件号脱敏
- 产品编号与内部流水号脱敏
- 渠道标识脱敏

如果样本来自真实业务，建议保留**语义事实**，但移除可识别信息。

## 3. 样本层级设计

建议样本分成三层。

### A. `smoke`：冒烟集

用途：

- 快速验证系统是否跑通
- 用于日常开发

建议规模：

- 20 ～ 30 条

特点：

- 规则清晰
- 结果稳定
- 覆盖核心主链路

### B. `core`：主评测集

用途：

- 版本对比
- 效果评估
- 升级验收

建议规模：

- 第一阶段：150 ～ 200 条
- 第二阶段：300 ～ 500 条

特点：

- 真实业务覆盖面广
- 样本结构均衡
- 同时有违规与合规样本
- 有轻度、中度、重度难度分层

### C. `edge_cases`：边界专题集

用途：

- 检验模型升级是否真的解决难题
- 防止边界回归

建议每个专题：

- 20 ～ 50 条

建议专题包括：

1. `temporal_context`
2. `subject_switch`
3. `negation_context`
4. `evidence_insufficient`
5. `localization`
6. `ocr_noise`
7. `cross_paragraph`

---

## 六、样本标注结构

建议每条样本采用 `jsonl` 结构，每行一条记录。

推荐字段如下：

```json
{
  "sample_id": "CORE_0001",
  "source_type": "marketing_copy",
  "channel": "wechat",
  "product_type": "annuity",
  "difficulty": "medium",
  "text": "待审核文本……",
  "expected": {
    "overall_verdict": "violation",
    "violated_rule_ids": ["KB0101", "KB0223"],
    "non_violated_rule_ids": [],
    "locations": [
      {
        "rule_id": "KB0101",
        "text_slice": "保证收益",
        "raw_start": 18,
        "raw_end": 22
      }
    ],
    "decision_basis": [
      {
        "rule_id": "KB0101",
        "basis": "explicit_violation"
      }
    ],
    "review_required": false
  },
  "tags": [
    "income_promise",
    "tone_guarantee"
  ],
  "notes": "真实话术脱敏改写"
}
```

### 标注最低要求

每条样本至少要标：

1. `overall_verdict`
2. `violated_rule_ids`
3. 核心 `location`
4. `tags`
5. `difficulty`

### 标注增强项

条件允许时建议继续标：

- `decision_basis`
- `review_required`
- `false_positive_sensitive`
- `evidence_required`
- `expected_suggestion_type`

这会让后续评估更有价值。

---

## 七、样本覆盖要求

独立测试模块不能只堆“典型违规例子”，必须覆盖以下结构。

## 1. 标签覆盖

建议主评测集中至少覆盖：

- 收益承诺类
- 风险淡化类
- 排名宣传类
- 历史业绩类
- 退保引导类
- 对比宣传类
- 主观夸大类
- 免责误导类

## 2. 正负样本平衡

建议比例：

- 违规样本：50%
- 合规样本：35%
- 边界 / unsure / 人工复核样本：15%

如果全部是违规样本，系统会被错误优化成“越激进越好”。

## 3. 难度分层

每个主评测集样本建议分三档：

- `easy`
- `medium`
- `hard`

建议比例：

- easy：30%
- medium：50%
- hard：20%

## 4. 样本形态覆盖

建议覆盖以下输入形态：

- 正常营销文案
- OCR 后文本
- 招聘文案
- 朋友圈口语化文案
- 海报式短句文本
- 多段落长文
- 混合合规/违规文本

---

## 八、评估指标设计

评估要分层，不要只看“命中了没有”。

## 1. 规则层指标

核心指标：

- `rule_precision`
- `rule_recall`
- `rule_f1`
- `rule_f2`

说明：

- `F2` 对这个项目非常重要，因为漏报代价高
- `F1` 和 `F2` 要同时保留

## 2. 样本层指标

每条样本评估：

- 是否整体判断正确
- 是否漏掉关键违规
- 是否出现明显误报

建议指标：

- `sample_accuracy`
- `high_risk_miss_rate`
- `false_positive_rate`

## 3. 定位层指标

这是项目差异化能力，必须单独评估。

建议指标：

- `location_exact_match`
- `location_overlap_iou`
- `location_span_recall`

说明：

- 不要求所有样本都完全 exact match
- 但要能区分“定位完全错”与“范围略宽”

## 4. 解释层指标

建议先做半结构化评估，不要一开始就做复杂 NLP 打分。

可评估项：

- `decision_basis_match_rate`
- `reason_code_match_rate`
- `suggestion_type_match_rate`

如果后续样本足够丰富，再加人工评估：

- 推理是否合理
- 建议是否可执行

## 5. 性能层指标

建议每次跑批都记录：

- 平均耗时
- P95 耗时
- 平均 violation 数
- 平均命中 rule 数
- 平均输出 location 数

如果未来能拿到调用日志，还可以继续记：

- 平均 LLM 调用次数
- 平均 token 消耗

---

## 九、跑批输出与评估结果

样本跑完后，必须自动生成评估结果，不能只留原始 JSON。

建议每次运行输出三类结果。

## 1. 原始运行结果

例如：

```text
benchmark/reports/history/20260313_103000/raw_results.jsonl
```

内容包括：

- 输入样本
- 系统输出
- 耗时
- 元信息

## 2. 结构化评分结果

例如：

```text
benchmark/reports/history/20260313_103000/scored_results.jsonl
```

每条样本增加：

- 命中规则对不对
- 定位对不对
- 是否误报
- 是否漏报
- 错误类型是什么

## 3. 汇总报告

例如：

```text
benchmark/reports/history/20260313_103000/summary.md
benchmark/reports/latest/summary.md
```

建议汇总报告至少包含：

1. 总样本数
2. rule-level Precision / Recall / F1 / F2
3. location 指标
4. 高风险漏报率
5. Top 10 退化样本
6. Top 10 典型误报样本
7. Top 10 典型漏报样本
8. 与 baseline 的对比表

这一步非常关键。  
没有汇总报告，跑样本就只是“执行”，不是“评估”。

---

## 十、推荐的运行模式

建议支持三种运行模式。

## 1. `smoke` 模式

用途：

- 开发自测
- 跑得快

建议命令形式：

```bash
python -m benchmark.runners.run_sdk --dataset smoke
```

## 2. `core` 模式

用途：

- 版本验收
- 方案评估

建议命令形式：

```bash
python -m benchmark.runners.batch_runner --dataset core
```

## 3. `regression` 模式

用途：

- 跑专题集
- 看某个升级是否回归

例如：

```bash
python -m benchmark.runners.batch_runner --dataset edge_cases/temporal_context
```

---

## 十一、标注与评审流程

为了让样本质量可靠，建议采用最小可执行标注流程。

## 第一步：样本收集

来源：

- 合规同事历史案例
- 业务修改前后版本
- 真实营销语料脱敏稿
- 现有测试文本沉淀

## 第二步：初标

由业务/产品/研发联合完成：

- 是否违规
- 违规规则
- 核心位置
- 标签

## 第三步：复核

至少一轮双人复核：

- 是否存在标注歧义
- 是否存在多规则冲突
- 是否存在定位范围争议

## 第四步：冻结

进入 `core` 主评测集的样本需要冻结版本。  
一旦冻结，不应随意改标签，除非有明确复核记录。

---

## 十二、建议的样本规模目标

建议按两个阶段建设。

## 第一阶段（2 周可落地）

目标：先跑起来。

建议规模：

- `smoke`：20 条
- `core`：120 条
- `edge_cases`：每类 15～20 条

总量：

- 200 条左右

## 第二阶段（持续建设）

目标：形成真正可比较的 benchmark。

建议规模：

- `core`：300～500 条
- `edge_cases`：每类 30～50 条

总量：

- 500～800 条

这个规模已经足够支持：

- 升级前后效果比较
- 典型问题归因
- 主体 / 时态 / 证据不足等专题分析

---

## 十三、与现有 `tests/` 的分工

建议明确分工如下：

### `tests/`

负责：

- 单元测试
- 回归测试
- 合同测试
- stage 行为正确性

### `benchmark/`

负责：

- 真实样本评测
- 端到端效果分析
- 升级前后对比
- 误报/漏报统计
- 定位效果评估

这样分开后，项目结构会更清晰：

- `tests/` 证明代码没坏
- `benchmark/` 证明效果有没有变好

---

## 十四、建设优先级建议

如果只按最小可落地路线推进，建议顺序如下：

### Phase A：先建目录和样本协议

先完成：

- `benchmark/` 目录
- `datasets/` 结构
- `jsonl` 样本协议
- `summary.md` 输出协议

### Phase B：先建 120 条主评测集

优先收真实脱敏样本，不求一次很多，但求可用。

### Phase C：先做 SDK 跑批 + 评分 + 汇总报告

只要能跑：

- 输入样本
- 得到输出
- 打分
- 出报告

就已经有很大价值。

### Phase D：再补 API 模式和专题集

等基础稳定后，再增加：

- API 跑批
- 专题 regression 集
- baseline 对比

---

## 十五、最终建议

这套测试模块建设的重点，不是做一个很复杂的测试平台，而是：

1. **独立目录**
2. **真实样本**
3. **统一标注协议**
4. **稳定跑批**
5. **自动评估报告**

如果只保留一句话作为实施原则：

> **把“代码是否正确”和“系统效果是否变好”彻底分开评估。**

当前 `tests/` 已经足够承担前者；  
现在缺的，是一个真正独立、能沉淀真实样本并输出效果评估的 `benchmark` 模块。
