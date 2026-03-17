"""从清洗后的种子集构建轻量 smoke 数据集。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from benchmark.config.category_patterns import count_disclaimer_hits, count_risk_hits


def load_records(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def sort_key(record: dict) -> tuple:
    return (
        len(record["text"]),
        record["source_sheet"],
        record["sample_id"],
    )


def pick_violation(records: list[dict], target: int) -> list[dict]:
    selected: list[dict] = []
    used_categories: defaultdict[str, int] = defaultdict(int)
    used_texts: set[str] = set()

    priority_groups = [
        [
            record for record in records
            if record["label"] == "violation"
            and "structured_violation" in record.get("tags", [])
            and 60 <= len(record["text"]) <= 900
        ],
        [
            record for record in records
            if record["label"] == "violation"
            and 60 <= len(record["text"]) <= 700
        ],
    ]

    for group in priority_groups:
        for record in sorted(group, key=sort_key):
            if len(selected) >= target:
                break
            text_key = record["text"]
            if text_key in used_texts:
                continue
            categories = record.get("expected_categories", [])
            if categories:
                dominant = categories[0]
                if used_categories[dominant] >= 2:
                    continue
                used_categories[dominant] += 1
            selected.append(record)
            used_texts.add(text_key)
        if len(selected) >= target:
            break

    return selected[:target]


def pick_compliant(records: list[dict], target: int) -> list[dict]:
    selected: list[dict] = []
    used_texts: set[str] = set()

    badcases = [
        record for record in records
        if record["label"] == "compliant"
        and record["source_sheet"] == "badcase"
        and 20 <= len(record["text"]) <= 500
    ]
    general = [
        record for record in records
        if record["label"] == "compliant"
        and record["source_sheet"] in {"合规样本", "合规"}
        and 60 <= len(record["text"]) <= 600
        and count_risk_hits(record["text"]) <= 1
        and count_disclaimer_hits(record["text"]) >= 1
    ]

    for group in [badcases, general]:
        for record in sorted(group, key=sort_key):
            if len(selected) >= target:
                break
            if record["text"] in used_texts:
                continue
            selected.append(record)
            used_texts.add(record["text"])
        if len(selected) >= target:
            break

    return selected[:target]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_summary(path: Path, records: list[dict]) -> None:
    by_label: defaultdict[str, int] = defaultdict(int)
    by_sheet: defaultdict[str, int] = defaultdict(int)
    by_category: defaultdict[str, int] = defaultdict(int)
    for record in records:
        by_label[record["label"]] += 1
        by_sheet[record["source_sheet"]] += 1
        for category in record.get("expected_categories", []):
            by_category[category] += 1

    lines = [
        "# Smoke 集构建摘要",
        "",
        f"- 总样本数：`{len(records)}`",
        "",
        "## 按标签分布",
    ]
    for label, count in sorted(by_label.items()):
        lines.append(f"- `{label}`: `{count}`")
    lines.extend(["", "## 按来源分布"])
    for sheet, count in sorted(by_sheet.items()):
        lines.append(f"- `{sheet}`: `{count}`")
    lines.extend(["", "## 类别覆盖"])
    for category, count in sorted(by_category.items()):
        lines.append(f"- `{category}`: `{count}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 smoke 小样本集")
    parser.add_argument(
        "--input",
        default="benchmark/datasets/case_eval_seed.jsonl",
        help="种子集路径",
    )
    parser.add_argument(
        "--output",
        default="benchmark/datasets/smoke/case_eval_smoke.jsonl",
        help="smoke 输出路径",
    )
    parser.add_argument(
        "--summary",
        default="benchmark/reports/smoke_build_summary.md",
        help="smoke 摘要路径",
    )
    parser.add_argument("--violation-count", type=int, default=16)
    parser.add_argument("--compliant-count", type=int, default=12)
    args = parser.parse_args()

    records = load_records(Path(args.input))
    if len(records) <= 40:
        selected = sorted(records, key=lambda item: (item["label"], item["source_sheet"], item["sample_id"]))
    else:
        selected = pick_violation(records, args.violation_count) + pick_compliant(records, args.compliant_count)
        selected = sorted(selected, key=lambda item: (item["label"], item["source_sheet"], item["sample_id"]))
    write_jsonl(Path(args.output), selected)
    write_summary(Path(args.summary), selected)
    print(json.dumps({"smoke_total": len(selected), "output": args.output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
