#!/usr/bin/env python3
"""将合规知识库 Excel 转换为项目规则库 JSON。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


def normalize_column_name(name: str) -> str:
    return str(name).replace("\n", "").replace("\r", "").strip()


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    text = str(value).strip()
    return text == "" or text.lower() == "nan"


def split_terms(value: Any) -> list[str]:
    if is_empty(value):
        return []
    text = str(value).strip()
    parts = re.split(r"[|｜]", text)
    cleaned = []
    for part in parts:
        item = part.strip()
        if not item:
            continue
        cleaned.append(item)

    deduped = []
    seen = set()
    for item in cleaned:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def pick_primary_term(value: Any) -> str:
    terms = split_terms(value)
    return terms[0] if terms else ""


def to_int_or_none(value: Any) -> int | None:
    if is_empty(value):
        return None
    try:
        number = int(float(str(value).strip()))
        if number <= 0:
            return None
        return number
    except Exception:
        return None


def shorten_name(terms: list[str], max_len: int = 24) -> str:
    if not terms:
        return "未命名规则"
    text = " / ".join(terms[:2])
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def build_violation_definition(
    violation_terms: list[str],
    condition_terms: list[str],
    condition_distance: int | None,
    exclusion_terms: list[str],
    exclusion_distance: int | None,
    violation_basis: str,
) -> str:
    if violation_basis:
        return violation_basis

    segments: list[str] = []
    if violation_terms:
        segments.append(f"出现以下违规词：{'、'.join(violation_terms)}")
    if condition_terms:
        if condition_distance is None:
            segments.append(f"且同时出现条件词：{'、'.join(condition_terms)}")
        else:
            segments.append(
                f"且在{condition_distance}字符范围内出现条件词：{'、'.join(condition_terms)}"
            )
    if exclusion_terms:
        if exclusion_distance is None:
            segments.append(f"若同时出现排除词则不违规：{'、'.join(exclusion_terms)}")
        else:
            segments.append(
                f"若在{exclusion_distance}字符范围内出现排除词则不违规：{'、'.join(exclusion_terms)}"
            )

    return "；".join(segments) if segments else "命中知识库违规表达时判定为违规。"


def convert_excel_to_rules(excel_path: Path) -> list[dict[str, Any]]:
    df = pd.read_excel(excel_path)
    df = df.rename(columns={c: normalize_column_name(c) for c in df.columns})

    required_columns = [
        "违规词",
        "条件词",
        "条件词限定距离",
        "排除词",
        "排除词限定距离",
        "前缀不匹配",
        "后缀不匹配",
        "合规依据",
        "合规case",
        "违规依据",
        "违规case",
        "合规建议",
    ]
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Excel 缺少必要列: {missing}")

    rules: list[dict[str, Any]] = []

    for idx, row in df.iterrows():
        # 修复：保留所有违规词，而不是只保留第一个
        violation_terms = split_terms(row.get("违规词"))
        if not violation_terms:
            continue

        primary_violation_term = violation_terms[0]

        condition_terms = split_terms(row.get("条件词"))
        exclusion_terms = split_terms(row.get("排除词"))
        prefix_no_match = split_terms(row.get("前缀不匹配"))
        suffix_no_match = split_terms(row.get("后缀不匹配"))

        condition_distance = to_int_or_none(row.get("条件词限定距离"))
        exclusion_distance = to_int_or_none(row.get("排除词限定距离"))

        compliant_basis = "" if is_empty(row.get("合规依据")) else str(row.get("合规依据")).strip()
        compliant_case = "" if is_empty(row.get("合规case")) else str(row.get("合规case")).strip()
        violation_basis = "" if is_empty(row.get("违规依据")) else str(row.get("违规依据")).strip()
        violation_case = "" if is_empty(row.get("违规case")) else str(row.get("违规case")).strip()
        suggestion_template = "" if is_empty(row.get("合规建议")) else str(row.get("合规建议")).strip()

        rule_id = f"KB{idx + 1:04d}"
        rule_name = f"知识库规则-{shorten_name(violation_terms)}"
        keywords = [primary_violation_term]

        exceptions = []
        if compliant_basis:
            exceptions.append(compliant_basis)
        if exclusion_terms:
            exceptions.append(f"出现排除词时不违规：{'、'.join(exclusion_terms)}")
        if prefix_no_match or suffix_no_match:
            phrase_notes = []
            if prefix_no_match:
                phrase_notes.append(f"前缀不匹配：{'、'.join(prefix_no_match)}")
            if suffix_no_match:
                phrase_notes.append(f"后缀不匹配：{'、'.join(suffix_no_match)}")
            exceptions.append("；".join(phrase_notes))

        violation_definition = build_violation_definition(
            violation_terms=violation_terms,
            condition_terms=condition_terms,
            condition_distance=condition_distance,
            exclusion_terms=exclusion_terms,
            exclusion_distance=exclusion_distance,
            violation_basis=violation_basis,
        )

        rules.append(
            {
                "rule_id": rule_id,
                "rule_name": rule_name,
                "risk_level": "high",
                "violation_definition": violation_definition,
                "exceptions": exceptions,
                "keywords": keywords,
                "reason_codes": [f"RC_{rule_id}"],
                "suggestion_template": suggestion_template,
                "violation_terms": violation_terms,
                "condition_terms": condition_terms,
                "condition_distance": condition_distance,
                "exclusion_terms": exclusion_terms,
                "exclusion_distance": exclusion_distance,
                "prefix_no_match": prefix_no_match,
                "suffix_no_match": suffix_no_match,
                "compliant_basis": compliant_basis,
                "compliant_case": compliant_case,
                "violation_basis": violation_basis,
                "violation_case": violation_case,
            }
        )

    return rules


def main() -> None:
    parser = argparse.ArgumentParser(description="将合规知识库 Excel 转换为规则库 JSON")
    parser.add_argument(
        "--excel",
        default="合规知识库体系.xlsx",
        help="Excel 文件路径",
    )
    parser.add_argument(
        "--output",
        default="data/rule_cards.json",
        help="输出 JSON 路径",
    )
    args = parser.parse_args()

    excel_path = Path(args.excel)
    output_path = Path(args.output)

    if not excel_path.exists():
        raise FileNotFoundError(f"Excel 文件不存在: {excel_path}")

    rules = convert_excel_to_rules(excel_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rules, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"已生成规则数: {len(rules)}")
    print(f"输出文件: {output_path}")


if __name__ == "__main__":
    main()
