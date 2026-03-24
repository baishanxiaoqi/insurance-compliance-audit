# 103条 smoke 跑批阶段性整理

- 状态：`全量跑批被中断，先汇总当前已落盘结果`
- 已落盘样本：`98 / 103`
- 完整分片：`5 / 6`
- 未完成分片：`part_01`（已落盘 `13` 条，剩余 `5` 条未完成）
- 部分汇总 JSON：`benchmark/reports/smoke_run_20260320_audit_points_103_partial_after_abort/summary.json`
- 部分汇总 Markdown：`benchmark/reports/smoke_run_20260320_audit_points_103_partial_after_abort/summary.md`
- 部分原始结果：`benchmark/reports/smoke_run_20260320_audit_points_103_partial_after_abort/raw_results.jsonl`

## 阶段性总指标

- `total`: `98`
- `tp`: `17`
- `fp`: `1`
- `fn`: `32`
- `tn`: `48`
- `precision`: `0.9444`
- `recall`: `0.3469`
- `f1`: `0.5075`
- `f2`: `0.3972`
- `category_hit_rate`: `0.1633`
- `audit_point_hit_rate`: `0.0816`
- `location_exact_hit_rate`: `0.0`
- `location_fuzzy_hit_rate`: `0.2041`

## 分片完成情况

- `part_00`: 完成，`18` 条，Precision `1.0`，Recall `0.4444`，F1 `0.6154`
- `part_01`: 未完成，当前已落盘 `13` 条
- `part_02`: 完成，`18` 条，Precision `1.0`，Recall `0.3333`，F1 `0.5`
- `part_03`: 完成，`18` 条，Precision `1.0`，Recall `0.4444`，F1 `0.6154`
- `part_04`: 完成，`18` 条，Precision `1.0`，Recall `0.2222`，F1 `0.3636`
- `part_05`: 完成，`13` 条，Precision `0.0`，Recall `0.0`，F1 `0.0`

## 当前判断

- 当前阶段性结果表现为：`误报极低，但召回明显不足`
- 目前 `FP=1`，说明保守性很强；但 `FN=32`，说明三级审查点覆盖和复杂语义召回仍是主要短板
- 结构化类别与审查点命中仍偏弱：`category_hit_rate=0.1633`，`audit_point_hit_rate=0.0816`
- 定位仍然不是强项：`location_exact_hit_rate=0.0`，`location_fuzzy_hit_rate=0.2041`

## 典型问题方向

- `financial_product_confusion`：如 `审查点违规_1_1_3` 仍被判合规
- `responsibility_exaggeration`：`2.x` 多条样本漏报严重
- `agent_title_violation` / `regulatory_misinterpretation`：`12.x`、`13.x` 仍有明显漏报
- 个别样本会出现 `predicted_verdict=error`，如 `审查点违规_14_1_1`

## 说明

- 这份报告是中断时刻的阶段性快照，不代表最终 `103` 条全量结果
- 如果后续继续补跑 `part_01` 剩余 5 条，应重新合并并重算总分