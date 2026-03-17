"""从 Excel 样本构建轻量评测数据集。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from benchmark.config.category_patterns import (
    count_disclaimer_hits,
    count_risk_hits,
    has_compliant_review_pattern,
    infer_categories,
)
from benchmark.schemas import CaseRecord


def normalize_text(text: str) -> str:
    text = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
        .replace("\u0085", "\n")
        .replace("\u3000", " ")
    )
    lines = [line.rstrip() for line in text.split("\n")]
    normalized = "\n".join(lines).strip()
    while "\n\n\n" in normalized:
        normalized = normalized.replace("\n\n\n", "\n\n")
    return normalized


def normalize_list_text(raw: str) -> list[str]:
    if not raw:
        return []
    items = [item.strip() for item in str(raw).replace("；", "，").split("，")]
    return [item for item in items if item and item.lower() != "nan"]


def build_record(
    *,
    sample_id: str,
    label: str,
    text: str,
    source_sheet: str,
    source_row: int,
    source_column: str,
    reason_raw: str = "",
    expected_text_slices: list[str] | None = None,
    expected_keywords: list[str] | None = None,
    tags: list[str] | None = None,
) -> CaseRecord:
    norm_text = normalize_text(text)
    record = CaseRecord(
        sample_id=sample_id,
        label=label,
        text=norm_text,
        source_sheet=source_sheet,
        source_row=source_row,
        source_column=source_column,
        reason_raw=str(reason_raw or "").strip(),
        expected_categories=infer_categories(
            reason_raw,
            " ".join(expected_keywords or []),
        ),
        expected_text_slices=expected_text_slices or [],
        expected_keywords=expected_keywords or [],
        tags=tags or [],
    )
    return record


def parse_violation_sheet_basic(xl: pd.ExcelFile, sheet_name: str, text_col: str) -> list[CaseRecord]:
    df = xl.parse(sheet_name)
    records: list[CaseRecord] = []
    for row_idx, row in df.iterrows():
        text = str(row.get(text_col, "") or "").strip()
        reason = str(row.get("违规原因", "") or "").strip()
        if not text or not reason or text.lower() == "nan" or reason.lower() == "nan":
            continue
        records.append(
            build_record(
                sample_id=f"{sheet_name}_{row_idx+1:04d}",
                label="violation",
                text=text,
                source_sheet=sheet_name,
                source_row=row_idx + 2,
                source_column=text_col,
                reason_raw=reason,
            )
        )
    return records


def parse_compliant_sheet(xl: pd.ExcelFile, sheet_name: str) -> list[CaseRecord]:
    df = xl.parse(sheet_name)
    records: list[CaseRecord] = []
    seq = 1
    for col in df.columns:
        for row_idx, value in df[col].items():
            text = str(value or "").strip()
            if not text or text.lower() == "nan":
                continue
            records.append(
                build_record(
                    sample_id=f"{sheet_name}_{seq:04d}",
                    label="compliant",
                    text=text,
                    source_sheet=sheet_name,
                    source_row=row_idx + 2,
                    source_column=str(col),
                    tags=["compliant_seed"],
                )
            )
            seq += 1
    return records


def parse_violation_sheet_structured(xl: pd.ExcelFile, sheet_name: str) -> list[CaseRecord]:
    df = xl.parse(sheet_name)
    records: list[CaseRecord] = []
    for row_idx, row in df.iterrows():
        text = str(row.get("文本", "") or "").strip()
        reason = str(row.get("违规原因", "") or "").strip()
        verdict = str(row.get("是否合规", "") or "").strip()
        if verdict != "否" or not text or not reason or text.lower() == "nan" or reason.lower() == "nan":
            continue
        records.append(
            build_record(
                sample_id=f"{sheet_name}_{row_idx+1:04d}",
                label="violation",
                text=text,
                source_sheet=sheet_name,
                source_row=row_idx + 2,
                source_column="文本",
                reason_raw=reason,
                expected_text_slices=normalize_list_text(str(row.get("违规内容", "") or "").strip()),
                expected_keywords=normalize_list_text(str(row.get("违规关键词", "") or "").strip()),
                tags=["structured_violation"],
            )
        )
    return records


def parse_badcase_sheet(xl: pd.ExcelFile, sheet_name: str) -> list[CaseRecord]:
    df = xl.parse(sheet_name)
    records: list[CaseRecord] = []
    for row_idx, row in df.iterrows():
        text = str(row.get("AI定位违规词（红字部分）", "") or "").strip()
        note = str(row.get("badcase情况标注", "") or "").strip()
        keyword = str(row.get("违规词", "") or "").strip()
        if not text or not note or text.lower() == "nan" or note.lower() == "nan":
            continue
        records.append(
            build_record(
                sample_id=f"{sheet_name}_{row_idx+1:04d}",
                label="compliant",
                text=text,
                source_sheet=sheet_name,
                source_row=row_idx + 2,
                source_column="AI定位违规词（红字部分）",
                reason_raw=note,
                expected_keywords=normalize_list_text(keyword),
                tags=["false_positive_regression"],
            )
        )
    return records


def assess_quality(records: list[CaseRecord]) -> tuple[list[CaseRecord], list[CaseRecord], list[CaseRecord]]:
    accepted: list[CaseRecord] = []
    review: list[CaseRecord] = []
    rejected: list[CaseRecord] = []
    seen_hashes: dict[str, str] = {}

    for record in records:
        reasons: list[str] = []
        text_len = len(record.text)
        text_hash = hashlib.md5(record.text.encode("utf-8")).hexdigest()

        if text_len < 20:
            record.quality_status = "rejected"
            record.quality_reasons = ["text_too_short"]
            rejected.append(record)
            continue

        if text_hash in seen_hashes:
            record.quality_status = "rejected"
            record.quality_reasons = [f"duplicate_exact_text:{seen_hashes[text_hash]}"]
            rejected.append(record)
            continue
        seen_hashes[text_hash] = record.sample_id

        if text_len > 4000:
            reasons.append("text_too_long")

        if record.label == "violation" and not record.reason_raw:
            reasons.append("missing_violation_reason")

        if record.label == "compliant" and record.source_sheet == "合规样本":
            risk_hits = count_risk_hits(record.text)
            disclaimer_hits = count_disclaimer_hits(record.text)
            if risk_hits >= 2 and disclaimer_hits == 0:
                reasons.append("compliant_sample_high_risk_without_disclaimer")
            if has_compliant_review_pattern(record.text) and disclaimer_hits == 0:
                reasons.append("compliant_sample_financial_marketing_style")
            if text_len > 1200 and disclaimer_hits == 0:
                reasons.append("compliant_sample_too_long_for_seed")

        if record.label == "compliant" and record.source_sheet == "badcase":
            record.tags.append("high_confidence_badcase")

        if not record.expected_categories and record.reason_raw:
            reasons.append("category_not_mapped")

        if reasons:
            record.quality_status = "review"
            record.quality_reasons = reasons
            review.append(record)
        else:
            record.quality_status = "accepted"
            accepted.append(record)

    return accepted, review, rejected


def write_jsonl(path: Path, records: list[CaseRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def write_summary(
    path: Path,
    accepted: list[CaseRecord],
    review: list[CaseRecord],
    rejected: list[CaseRecord],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    all_records = accepted + review + rejected
    by_sheet = Counter(record.source_sheet for record in all_records)
    by_label = Counter(record.label for record in all_records)
    by_status = Counter(record.quality_status for record in all_records)
    by_reason = Counter(reason for record in review + rejected for reason in record.quality_reasons)
    by_category = Counter(category for record in accepted for category in record.expected_categories)

    lines = [
        "# 数据清洗摘要",
        "",
        f"- 总记录数：`{len(all_records)}`",
        f"- 接受样本：`{len(accepted)}`",
        f"- 待复核样本：`{len(review)}`",
        f"- 拒绝样本：`{len(rejected)}`",
        "",
        "## 按来源 Sheet 统计",
    ]
    for sheet, count in sorted(by_sheet.items()):
        lines.append(f"- `{sheet}`: `{count}`")
    lines.extend(["", "## 按标签统计"])
    for label, count in sorted(by_label.items()):
        lines.append(f"- `{label}`: `{count}`")
    lines.extend(["", "## 按质量状态统计"])
    for status, count in sorted(by_status.items()):
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## 接受样本类别分布（Top 15）"])
    for category, count in by_category.most_common(15):
        lines.append(f"- `{category}`: `{count}`")
    lines.extend(["", "## 复核/拒绝原因（Top 15）"])
    for reason, count in by_reason.most_common(15):
        lines.append(f"- `{reason}`: `{count}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_dataset(input_path: Path, output_dir: Path) -> dict[str, int]:
    xl = pd.ExcelFile(input_path)
    sheet_names = set(xl.sheet_names)
    records: list[CaseRecord] = []

    legacy_sheets = {"违规样本1", "违规样本2", "合规样本", "违规样本3", "badcase"}
    curated_sheets = {"合规", "违规"}

    if legacy_sheets.issubset(sheet_names):
        records.extend(parse_violation_sheet_basic(xl, "违规样本1", "审核文本"))
        records.extend(parse_violation_sheet_basic(xl, "违规样本2", "文本"))
        records.extend(parse_compliant_sheet(xl, "合规样本"))
        records.extend(parse_violation_sheet_structured(xl, "违规样本3"))
        records.extend(parse_badcase_sheet(xl, "badcase"))
    elif curated_sheets.issubset(sheet_names):
        records.extend(parse_compliant_sheet(xl, "合规"))
        records.extend(parse_violation_sheet_structured(xl, "违规"))
    else:
        raise ValueError(
            "不支持的 Excel 结构，需包含旧版样本页 "
            f"{sorted(legacy_sheets)} 或新版样本页 {sorted(curated_sheets)}"
        )

    accepted, review, rejected = assess_quality(records)

    datasets_dir = output_dir / "datasets"
    reports_dir = output_dir / "reports"
    write_jsonl(datasets_dir / "case_eval_seed.jsonl", accepted)
    write_jsonl(datasets_dir / "case_eval_review.jsonl", review)
    write_jsonl(datasets_dir / "case_eval_rejected.jsonl", rejected)
    write_summary(reports_dir / "dataset_cleaning_summary.md", accepted, review, rejected)

    return {
        "total": len(records),
        "accepted": len(accepted),
        "review": len(review),
        "rejected": len(rejected),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="构建轻量离线评测数据集")
    parser.add_argument("--input", default="plan/case验证数据.xlsx", help="输入 Excel 路径")
    parser.add_argument("--output-dir", default="benchmark", help="输出目录")
    args = parser.parse_args()

    stats = build_dataset(Path(args.input), Path(args.output_dir))
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
