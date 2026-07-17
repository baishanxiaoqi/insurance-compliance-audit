# 单样本审核流程报告（当前代码真实调用版）

日期：2026-03-24
样本：`test_gate_integration_current`

## 1. 样本与运行配置

- 输入文本：`这款产品收益稳定，适合长期投资。`
- provider：`siliconflow`
- model：`Qwen/Qwen3.5-27B`
- llm_enable_thinking：`True`
- top_k_rules：`20`
- top_k_filter：`3`
- max_concurrent_calls：`1`
- stage2_max_concurrent_calls：`1`
- stage2_max_tokens：`2048`
- stage2_timeout_seconds：`90.0`
- semantic_prescreen_enabled：`True`
- semantic_prescreen_groups：`['financial_confusion', 'absolute_expression']`
- 总墙钟耗时：`52.5182s`

## 2. 各阶段耗时

- `stage0_total`：`0.002s`
- `stage1a_raw_recall`：`0.3594s`
- `stage1b_semantic_prescreen`：`9.9838s`
- `stage1c_merge`：`0.0001s`
- `stage1d_filter`：`4.7644s`
- `stage1_total`：`15.1086s`
- `stage15_fact_extract_body`：`0.0002s`
- `stage15_total`：`0.0003s`
- `stage18_route_body`：`0.0002s`
- `stage18_total`：`0.0003s`
- `stage19_gate_body`：`0.0004s`
- `stage19_total`：`0.0006s`
- `stage2_body`：`36.3872s`
- `stage2_total`：`36.3875s`
- `stage25_body`：`0.0017s`
- `stage25_total`：`0.0021s`
- `stage27_body`：`0.0001s`
- `stage27_total`：`0.0004s`
- `stage3_body`：`0.0003s`
- `stage3_total`：`0.0021s`

## 3. Stage 0 预处理

- 文档 ID：`test_gate_integration_current`
- chunk 数：`1`
- span 数：`2`
- chunk `chunk_000`：`这款产品收益稳定，适合长期投资。`
- span `S_chunk_000_00`：`这款产品收益稳定，`
- span `S_chunk_000_01`：`适合长期投资。`

## 4. Stage 1A 原始召回

- chunk `chunk_000` raw Top-20：`['KB0155', 'KB0014', 'KB0203', 'KB0348', 'KB0031', 'KB0067', 'KB0466', 'KB0440', 'KB0241', 'KB0146', 'KB0173', 'KB0522', 'KB0134', 'KB0139', 'KB0344', 'KB0026', 'KB0058', 'KB0025', 'KB0064', 'KB0298']`

## 5. Stage 1B 语义预检

- chunk `chunk_000` 风险方向：`['financial_confusion']` | 置信度：`0.75`
- 语义预检说明：`文本将保险产品描述为'收益稳定'且'适合长期投资'，容易让消费者误认为其等同于银行存款或理财产品，存在混淆产品属性的风险。`
- 语义扩展规则：`['KB0014', 'KB0257', 'KB0258', 'KB0301']`

## 6. Stage 1C 合并与来源

- chunk `chunk_000` merge 后候选数：`23`
- merge 候选：`['KB0155', 'KB0014', 'KB0203', 'KB0348', 'KB0031', 'KB0067', 'KB0466', 'KB0440', 'KB0241', 'KB0146', 'KB0173', 'KB0522', 'KB0134', 'KB0139', 'KB0344', 'KB0026', 'KB0058', 'KB0025', 'KB0064', 'KB0298', 'KB0257', 'KB0258', 'KB0301']`
- 来源标记：`{'KB0155': 'keyword', 'KB0014': 'both', 'KB0203': 'keyword', 'KB0348': 'keyword', 'KB0031': 'keyword', 'KB0067': 'keyword', 'KB0466': 'keyword', 'KB0440': 'keyword', 'KB0241': 'keyword', 'KB0146': 'keyword', 'KB0173': 'keyword', 'KB0522': 'keyword', 'KB0134': 'keyword', 'KB0139': 'keyword', 'KB0344': 'keyword', 'KB0026': 'keyword', 'KB0058': 'keyword', 'KB0025': 'keyword', 'KB0064': 'keyword', 'KB0298': 'keyword', 'KB0257': 'semantic', 'KB0258': 'semantic', 'KB0301': 'semantic'}`

## 7. Stage 1D Filter 结果

- chunk `chunk_000` Filter Top-3：`['KB0155', 'KB0134', 'KB0014']`

## 8. Stage 1.5 事实抽取

- chunk `chunk_000` 摘要：`claim_income_promise: 收益; claim_risk_downplay: 稳定; evidence_need: 收益`
- signal `claim_income_promise` = `收益` spans=`['S_chunk_000_00']`
- signal `claim_risk_downplay` = `稳定` spans=`['S_chunk_000_00']`
- signal `evidence_need` = `收益` spans=`['S_chunk_000_00']`

## 9. Stage 1.8 路由与 Skills 调用方式

- rule `KB0155` | strategy=`skill` | skill_type=`commitment_strength` | reason=`rule_route_hint=prefer_skill`
- rule `KB0134` | strategy=`skill` | skill_type=`financial_confusion` | reason=`rule_route_hint=prefer_skill`
- rule `KB0014` | strategy=`base` | skill_type=`None` | reason=`rule_route_hint=prefer_base`

## 10. Stage 1.9 Gate

- rule `KB0155` | skip=`False` | priority=`medium` | positive_evidence=`True`
- gate_signals：`[{'signal_type': 'guaranteed_return_missing_anchor', 'confidence': 0.6, 'reason': '未检测到收益承诺锚点（硬承诺或软承诺），可能不构成收益承诺', 'evidence_labels': ['missing_anchor']}]`
- rule `KB0134` | skip=`False` | priority=`high` | positive_evidence=`False`
- gate_signals：`[]`
- rule `KB0014` | skip=`False` | priority=`high` | positive_evidence=`True`
- gate_signals：`[]`

## 11. 真实 LLM 调用清单

- `call_01` `semantic_prescreen_agent` | module=`stage1_1_semantic_prescreen` | 耗时=`9.9788s`
  - Prompt：`benchmark/reports/single_sample_flow_20260324_debug_semantic/prompts/call_01_semantic_prescreen_agent.txt`
  - Result：`benchmark/reports/single_sample_flow_20260324_debug_semantic/llm_results/call_01_semantic_prescreen_agent.json`
- `call_02` `filter_agent` | module=`stage1_recall_filter` | 耗时=`4.762s`
  - Prompt：`benchmark/reports/single_sample_flow_20260324_debug_semantic/prompts/call_02_filter_agent.txt`
  - Result：`benchmark/reports/single_sample_flow_20260324_debug_semantic/llm_results/call_02_filter_agent.json`
- `call_03` `base_verify_llm` | module=`stage2_deep_judge` | 耗时=`20.7105s`
  - Prompt：`benchmark/reports/single_sample_flow_20260324_debug_semantic/prompts/call_03_base_verify_llm.txt`
  - Result：`benchmark/reports/single_sample_flow_20260324_debug_semantic/llm_results/call_03_base_verify_llm.json`
- `call_04` `skill_承诺强度判断` | module=`stage2_deep_judge` | 耗时=`7.6049s`
  - Prompt：`benchmark/reports/single_sample_flow_20260324_debug_semantic/prompts/call_04_skill_承诺强度判断.txt`
  - Result：`benchmark/reports/single_sample_flow_20260324_debug_semantic/llm_results/call_04_skill_承诺强度判断.json`
- `call_05` `skill_金融用语混淆识别` | module=`stage2_deep_judge` | 耗时=`8.0632s`
  - Prompt：`benchmark/reports/single_sample_flow_20260324_debug_semantic/prompts/call_05_skill_金融用语混淆识别.txt`
  - Result：`benchmark/reports/single_sample_flow_20260324_debug_semantic/llm_results/call_05_skill_金融用语混淆识别.json`

## 12. LLM 结果摘要

- `call_01` `semantic_prescreen_agent`：`{'risk_directions': ['financial_confusion'], 'confidence': 0.75, 'reasoning': "文本将保险产品描述为'收益稳定'且'适合长期投资'，容易让消费者误认为其等同于银行存款或理财产品，存在混淆产品属性的风险。"}`
- `call_02` `filter_agent`：`{'relevant_rule_ids': ['KB0155', 'KB0134', 'KB0014']}`
- `call_03` `base_verify_llm`：`{'rule_id': 'KB0014', 'chunk_id': 'chunk_000', 'verdict': 'violation', 'reasoning_cot': "规则引擎命中'投资'一词，出现在文本片段'适合长期投资'中。该片段主语为'这款产品'，直接指向待审保险产品。文本将保险产品描述为'适合长期投资'，直接宣传了产品的投资理财功能，使用了具有投资属性的术语。该表述不属于负面说明、禁令说明、培训材料或客观背景介绍，而是直接的营销宣传语。因此，该证据构成规则定义的直接违规宣传，属于将保险产品与投资理财功能混淆。", 'evidence_span_ids': ['S_chunk_000_01'], 'evidence_texts': ['适合长期投资'], 'reason_codes': ['financial_confusion'], 'decision_basis': 'explicit_violation', 'primary_category': 'financial_confusion', 'secondary_category': 'investment_function_claim'}`
- `call_04` `skill_承诺强度判断`：`{'rule_id': 'KB0155', 'chunk_id': 'chunk_000', 'verdict': 'violation', 'reasoning_cot': "原文中明确表述'这款产品收益稳定'，直接使用了规则禁止的'收益稳定'词汇，暗示保险产品具有确定性收益。经排查，文本中未出现'没有'、'不是'、'不能'、'可能'、'希望'、'致力于'、'追求'等排除词，且不存在否定语境或风险提示。该表述直接违反了禁止宣传或暗示保险具有收益稳定作用的规则，属于明确违规。", 'evidence_span_ids': ['S_chunk_000_00'], 'evidence_texts': ['收益稳定'], 'reason_codes': ['RC_KB0155'], 'decision_basis': 'explicit_violation', 'primary_category': 'guaranteed_return', 'secondary_category': 'stable_return_implication'}`
- `call_05` `skill_金融用语混淆识别`：`{'rule_id': 'KB0134', 'chunk_id': 'chunk_000', 'verdict': 'violation', 'reasoning_cot': "文本中明确出现'收益稳定'和'适合长期投资'的表述。'收益稳定'直接暗示了保险产品的确定性收益，违反了保险收益不确定性的监管要求；'适合长期投资'将保险产品直接定义为投资工具，混淆了保险保障与投资理财的界限。经排查，文本不存在否定语境、培训语境或主体不匹配等例外情况，属于直接的销售违规主张。", 'evidence_span_ids': ['S_chunk_000_00', 'S_chunk_000_01'], 'evidence_texts': ['收益稳定', '适合长期投资'], 'reason_codes': ['RC_KB0134'], 'decision_basis': 'explicit_violation', 'primary_category': 'financial_product_confusion', 'secondary_category': 'stable_return_implication'}`

## 13. Stage 2 / 2.5 / 2.7

- Stage 2 judgments：
  - `KB0014` -> verdict=`violation` | evidence=`['适合长期投资']` | category=`financial_confusion`/`investment_function_claim`
  - `KB0155` -> verdict=`violation` | evidence=`['收益稳定']` | category=`guaranteed_return`/`stable_return_implication`
  - `KB0134` -> verdict=`violation` | evidence=`['收益稳定', '适合长期投资']` | category=`financial_product_confusion`/`stable_return_implication`
- Stage 2.5 judgments：
  - `KB0014` -> verdict=`violation` | evidence=`['适合长期投资']`
  - `KB0155` -> verdict=`violation` | evidence=`['收益稳定']`
  - `KB0134` -> verdict=`compliant` | evidence=`[]`
- Stage 2.7 suggestions：`{'chunk_000_KB0014': {'rule_id': 'KB0014', 'chunk_id': 'chunk_000', 'suggestion': '理财、投资等表述存在将保险与投资理财等金融产品混淆的风险，建议修改为保险相关表述。如将投资、理财修改为财富管理。 具体违规表述：「适合长期投资」', 'suggestion_type': 'weaken'}, 'chunk_000_KB0155': {'rule_id': 'KB0155', 'chunk_id': 'chunk_000', 'suggestion': '保险产品的收益通常不是固定的，应避免承诺或暗示稳定的收益。 具体违规表述：「收益稳定」', 'suggestion_type': 'rephrase'}}`

## 14. Stage 3 最终输出

- total_violations：`2`
- processing_time_seconds：`51.51`
- rule `KB0155` | 标准类=`guaranteed_return` | 定位=`[{'span_ids': ['S_chunk_000_00'], 'original_text_slice': '这款产品收益稳定', 'norm_start': 0, 'norm_end': 9, 'raw_start': 0, 'raw_end': 8}]` | 建议=`保险产品的收益通常不是固定的，应避免承诺或暗示稳定的收益。 具体违规表述：「收益稳定」`
- rule `KB0014` | 标准类=`other` | 定位=`[{'span_ids': ['S_chunk_000_01'], 'original_text_slice': '适合长期投资', 'norm_start': 9, 'norm_end': 16, 'raw_start': 9, 'raw_end': 15}]` | 建议=`理财、投资等表述存在将保险与投资理财等金融产品混淆的风险，建议修改为保险相关表述。如将投资、理财修改为财富管理。 具体违规表述：「适合长期投资」`

## 15. 产物文件

- 详细快照：`benchmark/reports/single_sample_flow_20260324_debug_semantic/snapshot_current.json`
- Prompt：`benchmark/reports/single_sample_flow_20260324_debug_semantic/prompts/call_01_semantic_prescreen_agent.txt`
- Result：`benchmark/reports/single_sample_flow_20260324_debug_semantic/llm_results/call_01_semantic_prescreen_agent.json`
- Prompt：`benchmark/reports/single_sample_flow_20260324_debug_semantic/prompts/call_02_filter_agent.txt`
- Result：`benchmark/reports/single_sample_flow_20260324_debug_semantic/llm_results/call_02_filter_agent.json`
- Prompt：`benchmark/reports/single_sample_flow_20260324_debug_semantic/prompts/call_03_base_verify_llm.txt`
- Result：`benchmark/reports/single_sample_flow_20260324_debug_semantic/llm_results/call_03_base_verify_llm.json`
- Prompt：`benchmark/reports/single_sample_flow_20260324_debug_semantic/prompts/call_04_skill_承诺强度判断.txt`
- Result：`benchmark/reports/single_sample_flow_20260324_debug_semantic/llm_results/call_04_skill_承诺强度判断.json`
- Prompt：`benchmark/reports/single_sample_flow_20260324_debug_semantic/prompts/call_05_skill_金融用语混淆识别.txt`
- Result：`benchmark/reports/single_sample_flow_20260324_debug_semantic/llm_results/call_05_skill_金融用语混淆识别.json`