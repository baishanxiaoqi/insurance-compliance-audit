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
    predicted_audit_point_ids = record.get("predicted_audit_point_ids") or []
    predicted_categories = record.get("predicted_categories") or []
    if not predicted_categories:
        response = record.get("response", {}) or {}
        structured_categories = []
        for item in response.get("violations", []):
            for category in [item.get("primary_category"), item.get("secondary_category")]:
                if category and category not in structured_categories:
                    structured_categories.append(category)
        predicted_categories = structured_categories or infer_categories(
            " ".join(record.get("predicted_rule_ids", [])),
            json.dumps(response, ensure_ascii=False),
        )

    expected_slices = [normalize_for_match(item) for item in record.get("expected_text_slices", []) if item]
    predicted_slices = [normalize_for_match(item) for item in record.get("predicted_location_slices", []) if item]

    # 优化：区分精确匹配和模糊匹配
    location_exact_match = None
    location_fuzzy_match = None

    if expected_slices:
        # 精确匹配：完全相等
        location_exact_match = any(
            expected == predicted
            for expected in expected_slices
            for predicted in predicted_slices
            if expected and predicted
        )

        # 模糊匹配：包含关系
        location_fuzzy_match = any(
            expected in predicted or predicted in expected
            for expected in expected_slices
            for predicted in predicted_slices
            if expected and predicted
        )

    category_hit = None
    expected_categories = set(record.get("expected_categories", []))
    if expected_categories:
        category_hit = bool(expected_categories & set(predicted_categories))

    audit_point_hit = None
    expected_audit_point_id = record.get("expected_audit_point_id") or ""
    if expected_audit_point_id:
        audit_point_hit = expected_audit_point_id in set(predicted_audit_point_ids)

    return {
        "verdict_correct": expected_positive == predicted_positive,
        "expected_positive": expected_positive,
        "predicted_positive": predicted_positive,
        "category_hit": category_hit,
        "audit_point_hit": audit_point_hit,
        "location_exact_match": location_exact_match,  # 新增：精确匹配
        "location_fuzzy_match": location_fuzzy_match,  # 新增：模糊匹配
        "predicted_categories": predicted_categories,
    }


def build_summary(records: list[dict]) -> dict:
    tp = fp = fn = tn = 0
    category_total = category_hit = 0
    audit_point_total = audit_point_hit = 0
    location_exact_total = location_exact_hit = 0  # 新增：精确匹配统计
    location_fuzzy_total = location_fuzzy_hit = 0  # 新增：模糊匹配统计
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

        if scored["audit_point_hit"] is not None:
            audit_point_total += 1
            audit_point_hit += int(scored["audit_point_hit"])

        # 新增：精确匹配统计
        if scored["location_exact_match"] is not None:
            location_exact_total += 1
            location_exact_hit += int(scored["location_exact_match"])

        # 新增：模糊匹配统计
        if scored["location_fuzzy_match"] is not None:
            location_fuzzy_total += 1
            location_fuzzy_hit += int(scored["location_fuzzy_match"])

        sheet = record.get("source_sheet", "unknown")
        by_sheet[sheet]["total"] += 1
        by_sheet[sheet]["correct"] += int(scored["verdict_correct"])

        # 更新错误判断逻辑：使用模糊匹配作为定位判断依据
        if not scored["verdict_correct"] or scored["category_hit"] is False or scored["location_fuzzy_match"] is False:
            errors.append(
                {
                    "sample_id": record["sample_id"],
                    "source_sheet": sheet,
                    "expected_label": record["label"],
                    "predicted_verdict": record["predicted_verdict"],
                    "expected_categories": record.get("expected_categories", []),
                    "expected_audit_point_id": record.get("expected_audit_point_id", ""),
                    "predicted_audit_point_ids": record.get("predicted_audit_point_ids", []),
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
        "audit_point_hit_rate": round(safe_div(audit_point_hit, audit_point_total), 4),
        "location_exact_hit_rate": round(safe_div(location_exact_hit, location_exact_total), 4),  # 新增
        "location_fuzzy_hit_rate": round(safe_div(location_fuzzy_hit, location_fuzzy_total), 4),  # 新增
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
        f"- 审查点命中率：`{summary['audit_point_hit_rate']}`",
        f"- 定位精确匹配率：`{summary['location_exact_hit_rate']}`",
        f"- 定位模糊匹配率：`{summary['location_fuzzy_hit_rate']}`",
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
