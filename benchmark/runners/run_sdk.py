"""通过 SDK 入口跑离线评测。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.moderation.workflow import run_audit_sync


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
    predicted_location_slices = [
        location["original_text_slice"]
        for item in payload["violations"]
        for location in item["locations"]
    ]
    return {
        "predicted_verdict": "violation" if payload["total_violations"] > 0 else "compliant",
        "predicted_rule_ids": predicted_rule_ids,
        "predicted_location_slices": predicted_location_slices,
        "response": payload,
    }


def run_cases(cases: list[dict], output_path: Path) -> None:
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
    run_cases(cases, Path(args.output))
    print(json.dumps({"cases": len(cases), "output": args.output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
