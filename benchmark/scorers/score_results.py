"""对离线评测结果做轻量评分。"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from benchmark.config.category_patterns import infer_categories


def normalize_for_match(text: str) -> str:
    return "".join(str(text or "").split()).strip()


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def fbeta(precision: float, recall: float, beta: float) -> float:
    if precision == 0 and recall == 0:
        return 0.0
    beta2 = beta * beta
    return (1 + beta2) * precision * recall / (beta2 * precision + recall)


def score_record(record: dict) -> dict:
    expected_positive = record["label"] == "violation"
    predicted_positive = record["predicted_verdict"] == "violation"
    predicted_categories = infer_categories(
        " ".join(record.get("predicted_rule_ids", [])),
        json.dumps(record.get("response", {}), ensure_ascii=False),
    )

    expected_slices = [normalize_for_match(item) for item in record.get("expected_text_slices", []) if item]
    predicted_slices = [normalize_for_match(item) for item in record.get("predicted_location_slices", []) if item]
    location_hit = None
    if expected_slices:
        location_hit = any(
            expected in predicted or predicted in expected
            for expected in expected_slices
            for predicted in predicted_slices
            if expected and predicted
        )

    category_hit = None
    expected_categories = set(record.get("expected_categories", []))
    if expected_categories:
        category_hit = bool(expected_categories & set(predicted_categories))

    return {
        "verdict_correct": expected_positive == predicted_positive,
        "expected_positive": expected_positive,
        "predicted_positive": predicted_positive,
        "category_hit": category_hit,
        "location_hit": location_hit,
        "predicted_categories": predicted_categories,
    }


def build_summary(records: list[dict]) -> dict:
    tp = fp = fn = tn = 0
    category_total = category_hit = 0
    location_total = location_hit = 0
    by_sheet = defaultdict(lambda: {"total": 0, "correct": 0})
    errors = []

    for record in records:
        scored = score_record(record)
        if scored["expected_positive"] and scored["predicted_positive"]:
            tp += 1
        elif not scored["expected_positive"] and scored["predicted_positive"]:
            fp += 1
        elif scored["expected_positive"] and not scored["predicted_positive"]:
            fn += 1
        else:
            tn += 1

        if scored["category_hit"] is not None:
            category_total += 1
            category_hit += int(scored["category_hit"])

        if scored["location_hit"] is not None:
            location_total += 1
            location_hit += int(scored["location_hit"])

        sheet = record.get("source_sheet", "unknown")
        by_sheet[sheet]["total"] += 1
        by_sheet[sheet]["correct"] += int(scored["verdict_correct"])

        if not scored["verdict_correct"] or scored["category_hit"] is False or scored["location_hit"] is False:
            errors.append(
                {
                    "sample_id": record["sample_id"],
                    "source_sheet": sheet,
                    "expected_label": record["label"],
                    "predicted_verdict": record["predicted_verdict"],
                    "expected_categories": record.get("expected_categories", []),
                    "predicted_categories": scored["predicted_categories"],
                    "expected_text_slices": record.get("expected_text_slices", []),
                    "predicted_location_slices": record.get("predicted_location_slices", []),
                }
            )

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    summary = {
        "total": len(records),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(fbeta(precision, recall, 1.0), 4),
        "f2": round(fbeta(precision, recall, 2.0), 4),
        "category_hit_rate": round(safe_div(category_hit, category_total), 4),
        "location_hit_rate": round(safe_div(location_hit, location_total), 4),
        "by_sheet": {
            sheet: {
                "total": item["total"],
                "accuracy": round(safe_div(item["correct"], item["total"]), 4),
            }
            for sheet, item in sorted(by_sheet.items())
        },
        "error_samples": errors[:50],
    }
    return summary


def write_summary(summary: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(summary: dict, output_path: Path) -> None:
    lines = [
        "# 评测汇总",
        "",
        f"- 总样本数：`{summary['total']}`",
        f"- Precision：`{summary['precision']}`",
        f"- Recall：`{summary['recall']}`",
        f"- F1：`{summary['f1']}`",
        f"- F2：`{summary['f2']}`",
        f"- 类别命中率：`{summary['category_hit_rate']}`",
        f"- 定位命中率：`{summary['location_hit_rate']}`",
        "",
        "## 分 Sheet 准确率",
    ]
    for sheet, item in summary["by_sheet"].items():
        lines.append(f"- `{sheet}`: `{item['accuracy']}` ({item['total']} 条)")
    lines.extend(["", "## 典型问题样本（前 20 条）"])
    for item in summary["error_samples"][:20]:
        lines.append(
            f"- `{item['sample_id']}` | `{item['source_sheet']}` | expected=`{item['expected_label']}` | predicted=`{item['predicted_verdict']}`"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="对离线评测结果进行评分")
    parser.add_argument(
        "--input",
        default="benchmark/reports/latest/raw_results.jsonl",
        help="raw_results.jsonl 路径",
    )
    parser.add_argument(
        "--json-output",
        default="benchmark/reports/latest/summary.json",
        help="summary.json 输出路径",
    )
    parser.add_argument(
        "--md-output",
        default="benchmark/reports/latest/summary.md",
        help="summary.md 输出路径",
    )
    args = parser.parse_args()

    records = []
    with Path(args.input).open("r", encoding="utf-8") as fh:
        for line in fh:
            records.append(json.loads(line))

    summary = build_summary(records)
    write_summary(summary, Path(args.json_output))
    write_markdown(summary, Path(args.md_output))
    print(json.dumps({"total": summary["total"], "f1": summary["f1"], "f2": summary["f2"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
