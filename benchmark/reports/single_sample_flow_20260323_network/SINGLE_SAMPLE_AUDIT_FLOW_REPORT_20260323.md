# 单样本审核流程报告（真实调用版）

日期：2026-03-23
样本：`test_gate_integration`

## 1. 样本与运行配置

- 输入文本：`这款产品收益稳定，适合长期投资。`
- 运行渠道：`siliconflow`
- 主模型：`Qwen/Qwen3.5-27B`
- think：`True`
- Stage 1 Recall Top-K：`20`
- Stage 1 Filter Top-K：`3`
- Stage 2 并发：`2`
- Stage 2 max_tokens：`10000`
- Stage 2 timeout：`240.0` 秒
- 本次样本链路总耗时：约 `146s`

## 2. Stage 0 预处理

- 文档 ID：`test_gate_integration`
- chunk 数：`1`
- span 数：`2`
- chunk 文本：`这款产品收益稳定，适合长期投资。`

**Span 切分**
- `S_chunk_000_00`: `这款产品收益稳定，`
- `S_chunk_000_01`: `适合长期投资。`

## 3. Stage 1 召回与 Filter

**混合召回 Top-20（静态重算）**
- `KB0155` 知识库规则-收益稳定
- `KB0014` 知识库规则-理财 / 理财产品
- `KB0203` 知识库规则-锁定收益
- `KB0348` 知识库规则-新旧对比
- `KB0031` 知识库规则-高现价 / 高现金价值
- `KB0067` 知识库规则-以小博大 / 以小来博大
- `KB0466` 知识库规则-税延养老金
- `KB0440` 知识库规则-综合比较
- `KB0241` 知识库规则-限时权益
- `KB0146` 知识库规则-资管新规
- `KB0173` 知识库规则-都能保
- `KB0522` 知识库规则-成长基金
- `KB0134` 知识库规则-收益性
- `KB0139` 知识库规则-家企隔离
- `KB0344` 知识库规则-不可或缺
- `KB0026` 知识库规则-什么都能保 / 什么都能赔
- `KB0058` 知识库规则-确诊即付 / 确诊即赔
- `KB0025` 知识库规则-分红高，还有保障，这样的产品哪里去找 / 用储…
- `KB0064` 知识库规则-银行和保险公司联合推出 / 银行推出
- `KB0298` 知识库规则-类社保

**Filter Agent 实际筛出的 Top-3**
- `KB0155` 知识库规则-收益稳定
- `KB0134` 知识库规则-收益性
- `KB0014` 知识库规则-理财 / 理财产品

**本次真实 Filter 调用文件**
- 完整 prompt：`benchmark/reports/single_sample_flow_20260323_network/prompts/call_01_filter_agent.txt`
- 结构化结果：`benchmark/reports/single_sample_flow_20260323_network/llm_results/call_01_filter_agent.json`

**Filter Prompt 摘要**
```text
请阅读以下保险文本片段，并从候选规则中选出最可能相关的 Top-3 条规则。

【文本片段】
这款产品收益稳定，适合长期投资。

【候选规则】
- KB0155: 知识库规则-收益稳定 — 宣传或暗示保险具有收益稳定的作用。...
- KB0014: 知识库规则-理财 / 理财产品 — 直接宣传保险产品具备投资理财功能，使用具有投资属性的术语或其变体、缩略形式介绍保险，或者将个人养老金与理财产品进行关联。...
- KB0203: 知识库规则-锁定收益 — 使用锁定收益等表述宣传或暗示保险的收益稳定...
- KB0348: 知识库规则-新旧对比 — 将保险与其他产品或行业进行对比，暗示或宣传保险的优势。...
- KB0031: 知识库规则-高现价 / 高现金价值 — 使用高现金价值的表述宣传保险产品，或暗示长期保险产品可以通过高现金短期使用作为卖点。...
- KB0067: 知识库规则-以小博大 / 以小来博大 — 使用投机、赌博的专用术语介绍或宣传保险产品的功能属性...
- KB0466: 知识库规则-税延养老金 — 宣传或暗示个人养老金保险有税延的概念。...
- KB0440: 知识库规则-综合比较 — 将保险与其他产品或行业进行对比，暗示或宣传保险或某款产品的优势。...
- KB0241: 知识库规则-限时权益 — 以限时、限量、限额为卖点进行炒作宣传，宣传保险产品即将停售，给客户造成一种购买紧迫感的语气，引诱客户购买的意思。...
- KB0146: 知识库规则-资管新规 — 提及具体监管规定并进行产品对比的表述...
- KB0173: 知识库规则-都能保 — 使用“都能保”等过于绝对、夸张的词汇，描述宣传或暗示夸大保险的保障责任。...
- KB0522: 知识库规则-成长基金 — 使用成长基金等理财产品专用词与保险内容进行关联，将保险产品混同于储蓄/理财/投资产品的意思。...
- KB0134: 知识库规则-收益性 — 使用收益、收益性等表述宣传或暗示保险是投资理财等金融产品的意思...
- KB0139: 知识库规则-家企隔离 — 宣传保险有把家庭资产和企业资产隔离开的功能的意思...
- KB0344: 知识库规则-不可或缺 — 使用不可或缺、唯有或必然等表述，绝对化的宣传保险的作用...
- KB0026: 知识库规则-什么都能保 / 什么都能赔 — 夸大曲解保险的责任和功能，使用夸张型的语言进行宣传...
- KB0058: 知识库规则-确诊即付 / 确诊即赔 — 宣传或暗示使用夸大性的语言去承诺理赔效果，没有明确理赔的限定条件。...
- KB0025: 知识库规则-分红高，还有保障，这样的产品哪里去找 / 用储… — 将保险与其他产品或行业进行对比，暗示或宣传保险的优势。...
- KB0064: 知识库规则-银行和保
```

## 4. Stage 1.5 事实抽取

- chunk 摘要：`claim_income_promise: 收益; claim_risk_downplay: 稳定; evidence_need: 收益`
- 信号明细：
- `claim_income_promise` = `收益` spans=['S_chunk_000_00']
- `claim_risk_downplay` = `稳定` spans=['S_chunk_000_00']
- `evidence_need` = `收益` spans=['S_chunk_000_00']

## 5. Stage 1.8 路由分发

- `KB0155` | `知识库规则-收益稳定` | strategy=`skill` | skill_type=`commitment_strength` | reason=`rule_route_hint=prefer_skill`
- `KB0134` | `知识库规则-收益性` | strategy=`skill` | skill_type=`financial_confusion` | reason=`rule_route_hint=prefer_skill`
- `KB0014` | `知识库规则-理财 / 理财产品` | strategy=`base` | skill_type=`base/basic` | reason=`rule_route_hint=prefer_base`

**skills 调用方式说明**
- `KB0014`：`base` 轨，先走规则引擎，再走 `base_verify_llm`
- `KB0155`：`skill` 轨，`skill_type=commitment_strength`，实际调用 `skill_承诺强度判断`
- `KB0134`：`skill` 轨，`skill_type=financial_confusion`，实际调用 `skill_金融用语混淆识别`

## 6. Stage 1.9 Gate

- `KB0155` | skip=`False` | priority=`medium` | positive_evidence=`True` | signals=guaranteed_return_missing_anchor(0.6)
- `KB0134` | skip=`False` | priority=`high` | positive_evidence=`False` | signals=none
- `KB0014` | skip=`False` | priority=`high` | positive_evidence=`True` | signals=none

说明：本样本 `Gate` 没有提前跳过任何候选；只有 `KB0155` 收到一个 `guaranteed_return_missing_anchor(0.75)` 信号，但仍继续进入 Stage 2。

## 7. 规则引擎前置证据（用于 base / override）

- `KB0155` | hard_block=`False` | has_violation_hit=`True` | summary=`通过可执行规则前置校验` | violation_terms=['收益稳定']
- `KB0134` | hard_block=`True` | has_violation_hit=`False` | summary=`无有效违规词命中（或被前后缀不匹配规则过滤）` | violation_terms=[]
- `KB0014` | hard_block=`False` | has_violation_hit=`True` | summary=`通过可执行规则前置校验` | violation_terms=['投资']

关键点：
- `KB0014` 规则引擎命中了 `投资`，因此 base 轨先判 `violation`，再交给 `base_verify_llm` 复核。
- `KB0134` 规则引擎其实是 `hard_block=True`，说明它并没有可执行规则级正向命中；后续虽然 skill 轨判了 `violation`，但在 Stage 2.5 被 `deterministic_hard_block` 改判回 `compliant`。

## 8. 真实 LLM 调用清单

- `call_01` `filter_agent` -> `benchmark/reports/single_sample_flow_20260323_network/prompts/call_01_filter_agent.txt` -> `benchmark/reports/single_sample_flow_20260323_network/llm_results/call_01_filter_agent.json`
- `call_02` `base_verify_llm` -> `benchmark/reports/single_sample_flow_20260323_network/prompts/call_02_base_verify_llm.txt` -> `benchmark/reports/single_sample_flow_20260323_network/llm_results/call_02_base_verify_llm.json`
- `call_03` `skill_承诺强度判断` -> `benchmark/reports/single_sample_flow_20260323_network/prompts/call_03_skill_承诺强度判断.txt` -> `benchmark/reports/single_sample_flow_20260323_network/llm_results/call_03_skill_承诺强度判断.json`
- `call_04` `skill_金融用语混淆识别` -> `benchmark/reports/single_sample_flow_20260323_network/prompts/call_03_skill_金融用语混淆识别.txt` -> `benchmark/reports/single_sample_flow_20260323_network/llm_results/call_03_skill_金融用语混淆识别.json`

## 9. 各次 LLM Prompt 与结果

### 9.1 Filter Agent
- Prompt：`benchmark/reports/single_sample_flow_20260323_network/prompts/call_01_filter_agent.txt`
- Result：`benchmark/reports/single_sample_flow_20260323_network/llm_results/call_01_filter_agent.json`
- 结论：从 20 条候选里筛出 `KB0155 / KB0134 / KB0014`

### 9.2 base_verify_llm（KB0014）
- Prompt：`benchmark/reports/single_sample_flow_20260323_network/prompts/call_02_base_verify_llm.txt`
- Result：`benchmark/reports/single_sample_flow_20260323_network/llm_results/call_02_base_verify_llm.json`

**Prompt 摘要**
```text
【规则 ID】KB0014
【规则名称】知识库规则-理财 / 理财产品
【违规定义】直接宣传保险产品具备投资理财功能，使用具有投资属性的术语或其变体、缩略形式介绍保险，或者将个人养老金与理财产品进行关联。
【类别分组】financial_confusion

【待审文本 chunk_id=chunk_000】
这款产品收益稳定，适合长期投资。

【规则引擎命中的违规词/片段】
投资

【文本 Span 列表（用于填写 evidence_span_ids）】
  S_chunk_000_00: 这款产品收益稳定，
  S_chunk_000_01: 适合长期投资。

请严格按判断顺序裁决：这些证据是否构成本规则定义的直接违规宣传？
```

### 9.3 skill_承诺强度判断（KB0155）
- Prompt：`benchmark/reports/single_sample_flow_20260323_network/prompts/call_03_skill_承诺强度判断.txt`
- Result：`benchmark/reports/single_sample_flow_20260323_network/llm_results/call_03_skill_承诺强度判断.json`

**Prompt 摘要**
```text
你是一位保险合规审核裁判，负责判断当前文本片段在当前规则下是否成立。

========== 核心工作准则（必须严格遵守）==========
1. 你只判断当前文本片段在当前规则下是否成立，不得扩展规则，不得自行补充监管解释。
2. 你只能使用输入中给出的原文、规则条款、span_id、结构化事实信号和辅助信息，不得假设存在未给出的例外或免责场景。
3. 只有在输入中出现明确的主体不匹配、时态不匹配、否定语境、排除项或例外条款时，才能优先判定为 compliant 或 unsure。
4. 如果文本本身已经直接表达当前规则禁止的主张，不要等待额外外部证明；只有当规则明确要求外部依据且文本只是转述、比较或引用时，才输出 unsure。
5. 如果判定为 violation，必须给出最小必要的 evidence_span_ids，从下方 Span 字典中选择。
6. 如果无法从给定输入中得到稳定结论，不得猜测，不得补全缺失事实，输出 unsure。
7. 修改建议只能做删减、弱化、补充披露，不得虚构事实。
8. 不要因为前置规则引擎未命中就默认 compliant；文本直接违规时优先依据原文和规则裁决。

========== 裁决优先级（按顺序执行，必须严格遵守）==========
【第一步：识别违规主张】
1. 先判断原文是否直接表达了当前规则禁止的主张。
2. 如果存在直接违规主张，记录最小违规证据（核心违规词/短语）。
3. 不要将功能性描述、中性陈述、背景说明误判为违规主张。

【第二步：检查例外与推翻证据】
4. 若存在直接违规主张，再检查是否有明确的主体不匹配、时态不匹配、否定语境、排除项或例外条款可以推翻。
5. 只有当这些推翻证据在当前输入中明确出现时，才能输出 compliant。
6. 如果违规主张存在，但推翻证据不明确，不要为了保守直接放过，应输出 violation 或 unsure，并在 reasoning_cot 中说明依据。

【第三步：最小证据提取】
7. 如果判定为 violation，必须提取最小必要证据：
   - 只选择包含核心违规词的 span，不要选择上下文、修饰词、连接词
   - 不要将"保险可以提供补偿或保障"等功能性描述作为违规证据
   - 不要将"金融产品""财务保障"等中性词汇作为违规证据
   - 只选择明确表达违规主张的最短语义单元

【第四步：最终裁决】
8. 如果需要外部证明的只是排名、收益、历史业绩等支持性陈述，而原文并未直接作出违规承诺，才考虑 insufficient_evidence。
9. 在 reasoning_cot 中必须明确说明：识别到的违规主张是什么、为什么是违规、选择的证据为什么是最小必要证据。

========== 待审核文本 ==========
这款产品收益稳定，适合长期投资。

========== 合规规则 ==========
规则ID: KB0155
规则名称: 知识库规则-收益稳定
风险等级: high
违规定义: 宣传或暗示保险具有收益稳定的作用。
例外条款（以下情况不算违规）:
  - 没有宣传暗示或否定保险具有收益稳定的作用。
  - 出现排除词时不违规：没有、不是、不能、可能、希望、致力于、追求
建议模板: 保险产品的收益通常不是固定的，应避免承诺或暗示稳定的收益。

========== 规则结构化约束 ==========
主张类型: income_promise

========== 结构化关键词规则 ==========

```

### 9.4 skill_金融用语混淆识别（KB0134）
- Prompt：`benchmark/reports/single_sample_flow_20260323_network/prompts/call_03_skill_金融用语混淆识别.txt`
- Result：`benchmark/reports/single_sample_flow_20260323_network/llm_results/call_03_skill_金融用语混淆识别.json`

**Prompt 摘要**
```text
你是一位保险合规审核裁判，负责判断当前文本片段在当前规则下是否成立。

========== 核心工作准则（必须严格遵守）==========
1. 你只判断当前文本片段在当前规则下是否成立，不得扩展规则，不得自行补充监管解释。
2. 你只能使用输入中给出的原文、规则条款、span_id、结构化事实信号和辅助信息，不得假设存在未给出的例外或免责场景。
3. 只有在输入中出现明确的主体不匹配、时态不匹配、否定语境、排除项或例外条款时，才能优先判定为 compliant 或 unsure。
4. 如果文本本身已经直接表达当前规则禁止的主张，不要等待额外外部证明；只有当规则明确要求外部依据且文本只是转述、比较或引用时，才输出 unsure。
5. 如果判定为 violation，必须给出最小必要的 evidence_span_ids，从下方 Span 字典中选择。
6. 如果无法从给定输入中得到稳定结论，不得猜测，不得补全缺失事实，输出 unsure。
7. 修改建议只能做删减、弱化、补充披露，不得虚构事实。
8. 不要因为前置规则引擎未命中就默认 compliant；文本直接违规时优先依据原文和规则裁决。

========== 裁决优先级（按顺序执行，必须严格遵守）==========
【第一步：识别违规主张】
1. 先判断原文是否直接表达了当前规则禁止的主张。
2. 如果存在直接违规主张，记录最小违规证据（核心违规词/短语）。
3. 不要将功能性描述、中性陈述、背景说明误判为违规主张。

【第二步：检查例外与推翻证据】
4. 若存在直接违规主张，再检查是否有明确的主体不匹配、时态不匹配、否定语境、排除项或例外条款可以推翻。
5. 只有当这些推翻证据在当前输入中明确出现时，才能输出 compliant。
6. 如果违规主张存在，但推翻证据不明确，不要为了保守直接放过，应输出 violation 或 unsure，并在 reasoning_cot 中说明依据。

【第三步：最小证据提取】
7. 如果判定为 violation，必须提取最小必要证据：
   - 只选择包含核心违规词的 span，不要选择上下文、修饰词、连接词
   - 不要将"保险可以提供补偿或保障"等功能性描述作为违规证据
   - 不要将"金融产品""财务保障"等中性词汇作为违规证据
   - 只选择明确表达违规主张的最短语义单元

【第四步：最终裁决】
8. 如果需要外部证明的只是排名、收益、历史业绩等支持性陈述，而原文并未直接作出违规承诺，才考虑 insufficient_evidence。
9. 在 reasoning_cot 中必须明确说明：识别到的违规主张是什么、为什么是违规、选择的证据为什么是最小必要证据。

========== 待审核文本 ==========
这款产品收益稳定，适合长期投资。

========== 合规规则 ==========
规则ID: KB0134
规则名称: 知识库规则-收益性
风险等级: high
违规定义: 使用收益、收益性等表述宣传或暗示保险是投资理财等金融产品的意思
例外条款（以下情况不算违规）:
  - 非保险场景或没有暗示保险产品与储蓄、理财和投资等其他金融产品混乱的风险。
建议模板: 应改为“保障性”或“利益”。

========== 规则结构化约束 ==========
主张类型: misleading_statement

========== 结构化关键词规则 ==========
违规词: 收益性
条件词: 无
条
```

## 10. Stage 2 判定结果（Override 前）

- `KB0014` | verdict=`violation` | evidence=['适合长期投资'] | category=`financial_confusion/investment_function_claim`
- `KB0155` | verdict=`violation` | evidence=['收益稳定'] | category=`guaranteed_return/stable_return_implication`
- `KB0134` | verdict=`violation` | evidence=['收益稳定', '适合长期投资'] | category=`financial_product_confusion/stable_return_implication`

## 11. Stage 2.5 Override 后

- `KB0014` | verdict=`violation` | evidence=['适合长期投资'] | category=`financial_confusion/investment_function_claim`
- `KB0155` | verdict=`violation` | evidence=['收益稳定'] | category=`guaranteed_return/stable_return_implication`
- `KB0134` | verdict=`compliant` | evidence=[] | category=`financial_product_confusion/stable_return_implication`

说明：
- `KB0134` 被 `deterministic_hard_block` 改判为 `compliant`
- 最终保留的违规只剩 `KB0155` 与 `KB0014`

## 12. Stage 2.7 建议生成

- `chunk_000_KB0014` | type=`weaken` | suggestion=`理财、投资等表述存在将保险与投资理财等金融产品混淆的风险，建议修改为保险相关表述。如将投资、理财修改为财富管理。 具体违规表述：「适合长期投资」`
- `chunk_000_KB0155` | type=`rephrase` | suggestion=`保险产品的收益通常不是固定的，应避免承诺或暗示稳定的收益。 具体违规表述：「收益稳定」`

## 13. Stage 3 最终输出

- 最终违规数：`2`
- 最终结果：
- `KB0155` | `知识库规则-收益稳定` | location=`这款产品收益稳定` | suggestion=`保险产品的收益通常不是固定的，应避免承诺或暗示稳定的收益。 具体违规表述：「收益稳定」`
- `KB0014` | `知识库规则-理财 / 理财产品` | location=`适合长期投资` | suggestion=`理财、投资等表述存在将保险与投资理财等金融产品混淆的风险，建议修改为保险相关表述。如将投资、理财修改为财富管理。 具体违规表述：「适合长期投资」`

## 14. 结论与观察

1. 这条样本的真实链路并不是“Top-20 全部进深判”，因为 Stage 1 Filter 成功把候选压缩到了 3 条。
2. 最终输出是两条违规：
   - `KB0155`：`收益稳定`
   - `KB0014`：`适合长期投资`
3. `KB0134` 虽然 skill 轨判了违规，但被 Stage 2.5 根据规则引擎硬阻断改判回合规，这说明当前系统仍是“LLM 判定 + 代码约束纠偏”的混合闭环。
4. 如果线上慢，往往不是这类“Filter 成功压缩到 3 条”的样本，而是 Filter 失败后把 Top-20 候选全集送进 Stage 2 的样本。

## 15. 附件

- 可机读快照：`benchmark/reports/single_sample_flow_20260323_network/snapshot_fixed.json`
- 本报告涉及的完整 prompt 与结构化输出都已保存在当前目录下。
