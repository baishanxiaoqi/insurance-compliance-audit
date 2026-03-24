"""通过 SDK 入口跑离线评测。"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

_BENCHMARK_OVERRIDE_DEFAULTS = {
    "MAX_CONCURRENT_CALLS": "4",
    "STAGE2_MAX_CONCURRENT_CALLS": "1",
    "FILTER_MODEL_ENABLE_THINKING": "false",
    "FILTER_MODEL_MAX_TOKENS": "10000",
    "FILTER_MODEL_TIMEOUT_SECONDS": "15",
    "FILTER_MODEL_MAX_RETRIES": "1",
    "JUDGE_MODEL_ENABLE_THINKING": "true",
    "JUDGE_MODEL_THINKING_BUDGET": "32",
    "JUDGE_MODEL_MAX_TOKENS": "10000",
    "JUDGE_MODEL_TIMEOUT_SECONDS": "240",
    "JUDGE_MODEL_MAX_RETRIES": "2",
    "SUGGESTION_USE_LLM_RENDERER": "false",
    "SUGGESTION_MODEL_ENABLE_THINKING": "false",
    "SUGGESTION_MODEL_MAX_TOKENS": "10000",
}


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def apply_benchmark_runtime_overrides() -> dict[str, str]:
    applied: dict[str, str] = {}
    stable_mode = _is_truthy(os.getenv("BENCHMARK_STABLE_MODE"))

    for target_key, stable_default in _BENCHMARK_OVERRIDE_DEFAULTS.items():
        benchmark_key = f"BENCHMARK_{target_key}"
        if stable_mode:
            value = os.getenv(benchmark_key, stable_default)
        else:
            value = os.getenv(benchmark_key)
        if value is None or not value.strip():
            continue
        os.environ[target_key] = value.strip()
        applied[target_key] = value.strip()

    return applied


def load_cases(path: Path, limit: int | None = None, label: str | None = None) -> list[dict]:
    cases: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            if label and record["label"] != label:
                continue
            cases.append(record)
            if limit and len(cases) >= limit:
                break
    return cases


def flatten_response(response) -> dict:
    payload = response.model_dump()
    predicted_rule_ids = [item["rule_id"] for item in payload["violations"]]
    predicted_audit_point_ids = []
    predicted_location_slices = [
        location["original_text_slice"]
        for item in payload["violations"]
        for location in item["locations"]
    ]
    predicted_categories = []
    predicted_decision_bases = []
    predicted_suggestion_types = []
    for item in payload["violations"]:
        audit_point_id = item.get("audit_point_id")
        if audit_point_id and audit_point_id not in predicted_audit_point_ids:
            predicted_audit_point_ids.append(audit_point_id)
        for category in [item.get("primary_category"), item.get("secondary_category")]:
            if category and category not in predicted_categories:
                predicted_categories.append(category)
        decision_basis = item.get("decision_basis")
        if decision_basis and decision_basis not in predicted_decision_bases:
            predicted_decision_bases.append(decision_basis)
        suggestion_type = item.get("suggestion_type")
        if suggestion_type and suggestion_type not in predicted_suggestion_types:
            predicted_suggestion_types.append(suggestion_type)
    return {
        "predicted_verdict": "violation" if payload["total_violations"] > 0 else "compliant",
        "predicted_rule_ids": predicted_rule_ids,
        "predicted_audit_point_ids": predicted_audit_point_ids,
        "predicted_location_slices": predicted_location_slices,
        "predicted_categories": predicted_categories,
        "predicted_decision_bases": predicted_decision_bases,
        "predicted_suggestion_types": predicted_suggestion_types,
        "response": payload,
    }


def run_cases(cases: list[dict], output_path: Path) -> None:
    apply_benchmark_runtime_overrides()
    from src.moderation.workflow import run_audit_sync

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Phase 4 优化：删除旧文件，避免重复写入
    if output_path.exists():
        output_path.unlink()
    with output_path.open("w", encoding="utf-8") as fh:
        for case in cases:
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
            duration = round(time.time() - started_at, 4)
            fh.write(
                json.dumps(
                    {
                        "sample_id": case["sample_id"],
                        "label": case["label"],
                        "expected_categories": case.get("expected_categories", []),
                        "expected_audit_point_id": case.get("expected_audit_point_id", ""),
                        "expected_text_slices": case.get("expected_text_slices", []),
                        "source_sheet": case.get("source_sheet", ""),
                        "quality_status": case.get("quality_status", ""),
                        "status": status,
                        "error": error,
                        "duration_seconds": duration,
                        **result,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="通过 SDK 跑离线评测")
    parser.add_argument(
        "--dataset",
        default="benchmark/datasets/case_eval_seed.jsonl",
        help="输入数据集 jsonl",
    )
    parser.add_argument(
        "--output",
        default="benchmark/reports/latest/raw_results.jsonl",
        help="输出结果 jsonl",
    )
    parser.add_argument("--limit", type=int, default=None, help="限制运行样本数")
    parser.add_argument("--label", default=None, help="仅运行指定标签")
    args = parser.parse_args()

    cases = load_cases(Path(args.dataset), limit=args.limit, label=args.label)
    overrides = apply_benchmark_runtime_overrides()
    run_cases(cases, Path(args.output))
    print(
        json.dumps(
            {
                "cases": len(cases),
                "output": args.output,
                "runtime_overrides": overrides,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
