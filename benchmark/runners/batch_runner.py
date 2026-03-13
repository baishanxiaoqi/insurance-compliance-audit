"""一键执行离线评测跑批与评分。"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="一键执行轻量离线评测")
    parser.add_argument("--dataset", default="benchmark/datasets/case_eval_seed.jsonl")
    parser.add_argument("--output-dir", default="benchmark/reports/latest")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--label", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    raw_results = output_dir / "raw_results.jsonl"
    summary_json = output_dir / "summary.json"
    summary_md = output_dir / "summary.md"

    sdk_command = [
        "python",
        "-m",
        "benchmark.runners.run_sdk",
        "--dataset",
        args.dataset,
        "--output",
        str(raw_results),
    ]
    if args.limit is not None:
        sdk_command.extend(["--limit", str(args.limit)])
    if args.label:
        sdk_command.extend(["--label", args.label])

    score_command = [
        "python",
        "-m",
        "benchmark.scorers.score_results",
        "--input",
        str(raw_results),
        "--json-output",
        str(summary_json),
        "--md-output",
        str(summary_md),
    ]

    run_command(sdk_command)
    run_command(score_command)

    print(
        json.dumps(
            {
                "raw_results": str(raw_results),
                "summary_json": str(summary_json),
                "summary_md": str(summary_md),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
