# Benchmark 模块

这是一个与主业务流程独立的轻量离线评测模块。

## 目标

- 不改动主项目逻辑
- 使用真实脱敏样本做离线评测
- 跑完样本后自动生成评分结果

## 目录

- `benchmark/datasets/`：清洗后的种子集、复核集、拒绝集
- `benchmark/runners/`：通过 SDK 跑批
- `benchmark/scorers/`：对运行结果打分
- `benchmark/reports/`：清洗摘要、运行结果、评分报告

## 1. 从 Excel 构建数据集

```bash
python -m benchmark.tools.prepare_dataset \
  --input plan/case验证数据.xlsx \
  --output-dir benchmark
```

输出：

- `benchmark/datasets/case_eval_seed.jsonl`
- `benchmark/datasets/case_eval_review.jsonl`
- `benchmark/datasets/case_eval_rejected.jsonl`
- `benchmark/reports/dataset_cleaning_summary.md`

## 2. 构建 smoke 小样本集

```bash
python -m benchmark.tools.build_smoke_set \
  --input benchmark/datasets/case_eval_seed.jsonl \
  --output benchmark/datasets/smoke/case_eval_smoke.jsonl \
  --summary benchmark/reports/smoke_build_summary.md
```

输出：

- `benchmark/datasets/smoke/case_eval_smoke.jsonl`
- `benchmark/reports/smoke_build_summary.md`

## 3. 运行 SDK 评测

```bash
python -m benchmark.runners.run_sdk \
  --dataset benchmark/datasets/case_eval_seed.jsonl \
  --output benchmark/reports/latest/raw_results.jsonl \
  --limit 20
```

## 4. 对结果评分

```bash
python -m benchmark.scorers.score_results \
  --input benchmark/reports/latest/raw_results.jsonl \
  --json-output benchmark/reports/latest/summary.json \
  --md-output benchmark/reports/latest/summary.md
```

## 5. 一键跑批

```bash
python -m benchmark.runners.batch_runner \
  --dataset benchmark/datasets/case_eval_seed.jsonl \
  --output-dir benchmark/reports/latest
```

## 当前设计边界

这套模块当前是轻量版，主要支持：

- 样本清洗
- verdict 级评估
- 粗粒度类别匹配
- sheet 维度准确率统计
- 结构化定位片段命中

它暂时不做：

- 复杂人工标注平台
- 图形化看板
- 多模型并行基准
- 重型数据平台
