#!/usr/bin/env python3
"""运行33条样本测试，使用优化后的配置"""
import os
import sys
import json
import time
from pathlib import Path

# 确保使用优化后的并发配置
os.environ["MAX_CONCURRENT_CALLS"] = "6"
os.environ["STAGE2_MAX_CONCURRENT_CALLS"] = "6"
os.environ["FILTER_FALLBACK_KEEP_HEAD"] = "4"
os.environ["FILTER_FALLBACK_MAX_RULES"] = "8"

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.runners.run_sdk import load_cases, run_cases, apply_benchmark_runtime_overrides, flatten_response
from src.moderation.workflow import run_audit_sync

def run_with_timing():
    """运行33条样本并记录详细耗时"""
    dataset_path = PROJECT_ROOT / "benchmark/datasets/smoke/case_eval_smoke.jsonl"
    output_path = PROJECT_ROOT / "benchmark/reports/smoke_33_optimized/raw_results.jsonl"

    # 应用运行时覆盖（但保留我们的并发配置）
    overrides = apply_benchmark_runtime_overrides()
    print(f"Runtime overrides: {overrides}")

    # 加载33条样本
    cases = load_cases(dataset_path, limit=33)
    print(f"Loaded {len(cases)} cases")

    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 删除旧结果
    if output_path.exists():
        output_path.unlink()

    # 运行测试并记录详细耗时
    results = []
    total_start = time.time()

    for i, case in enumerate(cases, 1):
        print(f"\n[{i}/{len(cases)}] Processing: {case['sample_id']}")
        started_at = time.time()

        try:
            response = run_audit_sync(case["text"], case["sample_id"])
            result = flatten_response(response)
            status = "ok"
            error = ""
        except Exception as exc:
            result = {
                "predicted_verdict": "error",
                "predicted_rule_ids": [],
                "predicted_location_slices": [],
                "response": {},
            }
            status = "error"
            error = str(exc)
            print(f"  Error: {error}")

        duration = round(time.time() - started_at, 2)
        print(f"  Duration: {duration}s, Status: {status}, Violations: {result.get('predicted_verdict')}")

        results.append({
            "sample_id": case["sample_id"],
            "label": case["label"],
            "status": status,
            "error": error,
            "duration_seconds": duration,
            **result
        })

        # 实时写入文件
        with output_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(results[-1], ensure_ascii=False) + "\n")

    total_duration = round(time.time() - total_start, 2)

    # 统计结果
    durations = [r["duration_seconds"] for r in results if r["status"] == "ok"]
    errors = [r for r in results if r["status"] == "error"]
    violations = [r for r in results if r["predicted_verdict"] == "violation"]

    summary = {
        "total_cases": len(cases),
        "successful": len(durations),
        "errors": len(errors),
        "violations_detected": len(violations),
        "total_duration_seconds": total_duration,
        "avg_duration_seconds": round(sum(durations) / len(durations), 2) if durations else 0,
        "max_duration_seconds": round(max(durations), 2) if durations else 0,
        "min_duration_seconds": round(min(durations), 2) if durations else 0,
        "output_path": str(output_path),
    }

    # 保存汇总报告
    summary_path = output_path.parent / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Total cases: {summary['total_cases']}")
    print(f"Successful: {summary['successful']}")
    print(f"Errors: {summary['errors']}")
    print(f"Violations detected: {summary['violations_detected']}")
    print(f"Total duration: {summary['total_duration_seconds']}s")
    print(f"Avg duration: {summary['avg_duration_seconds']}s")
    print(f"Max duration: {summary['max_duration_seconds']}s")
    print(f"Min duration: {summary['min_duration_seconds']}s")
    print(f"Output: {summary['output_path']}")
    print("=" * 60)

    return summary

if __name__ == "__main__":
    summary = run_with_timing()
    sys.exit(0 if summary["errors"] == 0 else 1)
