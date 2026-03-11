#!/usr/bin/env python3
"""
增强 rule_cards.json 中的 compliant_basis，添加否定语境说明
"""

import json
import sys
from pathlib import Path


def enhance_compliant_basis(rule: dict) -> str:
    """
    增强 compliant_basis，添加否定语境说明

    保留原有内容，在前面添加【重要】否定语境说明
    """
    current_basis = rule.get('compliant_basis', '')

    # 如果已经有【重要】标记，不需要增强
    if '【重要】' in current_basis or '否定语境' in current_basis:
        return current_basis

    # 提取违规词
    violation_terms = rule.get('violation_terms', [])
    rule_name = rule['rule_name'].replace('知识库规则-', '')

    # 选择代表性的违规词
    if violation_terms:
        # 取前3个违规词
        violation_words = '、'.join(violation_terms[:3])
        if len(violation_terms) > 3:
            violation_words += '等'
    else:
        violation_words = rule_name

    # 构建否定语境说明
    negative_context = (
        f"【重要】否定语境合规：材料中批评、处罚、禁止使用'{violation_words}'等表述的行为时合规"
        f"（如'禁止使用{violation_words}'、'因使用{violation_words}被处罚'、'不得使用{violation_words}'），"
        f"因为材料本身在反对该违规行为。"
    )

    # 如果原有 basis 不为空，保留并追加
    if current_basis and current_basis.strip():
        return f"{negative_context} {current_basis}"
    else:
        return negative_context


def enhance_violation_basis(rule: dict) -> str:
    """
    增强 violation_basis，使其更具体
    """
    current_basis = rule.get('violation_basis', '')

    # 如果已经比较详细（超过50字），不需要增强
    if len(current_basis) > 50:
        return current_basis

    # 提取违规词
    violation_terms = rule.get('violation_terms', [])
    rule_name = rule['rule_name'].replace('知识库规则-', '')

    if violation_terms:
        violation_words = '、'.join(violation_terms[:3])
        if len(violation_terms) > 3:
            violation_words += '等'
    else:
        violation_words = rule_name

    # 根据规则类型生成违规依据
    if any(kw in rule_name for kw in ['收益', '分红', '利率', '回报', '稳赚', '增值', '理财', '投资']):
        enhanced = (
            f"根据《保险法》和银保监会相关规定，禁止使用'{violation_words}'等表述，"
            f"因为：1) 可能误导消费者对收益的预期；2) 保险产品收益存在不确定性；"
            f"3) 违反如实告知义务。"
        )
    elif any(kw in rule_name for kw in ['最好', '第一', '唯一', '绝对', 'NO.1', '顶级', '完美']):
        enhanced = (
            f"根据《广告法》第九条，禁止使用'{violation_words}'等绝对化用语，"
            f"因为：1) 具有排他性，损害公平竞争；2) 缺乏客观依据；"
            f"3) 可能误导消费者。"
        )
    elif any(kw in rule_name for kw in ['停售', '限时', '国家', '监管', '政策']):
        enhanced = (
            f"根据银保监会相关规定，禁止使用'{violation_words}'等表述，"
            f"因为：1) 可能构成虚假宣传；2) 不当使用监管名义；"
            f"3) 制造紧迫感误导消费者。"
        )
    elif any(kw in rule_name for kw in ['退保', '免责', '理赔', '存款', '银行']):
        enhanced = (
            f"根据《保险法》和消费者权益保护相关规定，禁止使用'{violation_words}'等表述，"
            f"因为：1) 可能侵害消费者合法权益；2) 隐瞒重要信息；"
            f"3) 误导消费者决策。"
        )
    elif any(kw in rule_name for kw in ['薪', '月入', '年薪', '招募', '收入']):
        enhanced = (
            f"根据银保监会《保险代理人监管规定》，禁止使用'{violation_words}'等表述，"
            f"因为：1) 代理人收入为佣金制，非固定工资；2) 用收入数字诱导应聘构成虚假宣传；"
            f"3) 误导应聘者对收入的预期。"
        )
    elif any(kw in rule_name for kw in ['避税', '避债', '遗产', '财产', '破产']):
        enhanced = (
            f"根据保险监管相关规定，禁止使用'{violation_words}'等表述，"
            f"因为：1) 夸大保险功能；2) 可能涉及违法违规行为；"
            f"3) 误导消费者对保险功能的理解。"
        )
    else:
        # 保留原有内容或使用通用模板
        if current_basis and current_basis.strip():
            return current_basis
        else:
            enhanced = (
                f"根据保险监管相关规定，禁止使用'{violation_words}'等表述，"
                f"因为可能误导消费者、违反广告法或保险法相关规定。"
            )

    return enhanced


def enhance_rule_cards(input_file: str, output_file: str = None):
    """
    批量增强 rule_cards.json
    """
    # 读取规则
    with open(input_file, 'r', encoding='utf-8') as f:
        rules = json.load(f)

    print(f'总规则数: {len(rules)}')

    # 统计需要增强的规则
    need_enhance_compliant = 0
    need_enhance_violation = 0

    for rule in rules:
        cb = rule.get('compliant_basis', '')
        vb = rule.get('violation_basis', '')

        if not cb or ('【重要】' not in cb and '否定语境' not in cb):
            need_enhance_compliant += 1

        if not vb or len(vb) < 50:
            need_enhance_violation += 1

    print(f'需要增强 compliant_basis 的规则: {need_enhance_compliant}')
    print(f'需要增强 violation_basis 的规则: {need_enhance_violation}')
    print()

    # 批量增强
    enhanced_compliant = 0
    enhanced_violation = 0

    for rule in rules:
        old_cb = rule.get('compliant_basis', '')
        old_vb = rule.get('violation_basis', '')

        # 增强 compliant_basis
        new_cb = enhance_compliant_basis(rule)
        if new_cb != old_cb:
            rule['compliant_basis'] = new_cb
            enhanced_compliant += 1

        # 增强 violation_basis
        new_vb = enhance_violation_basis(rule)
        if new_vb != old_vb:
            rule['violation_basis'] = new_vb
            enhanced_violation += 1

    print(f'已增强 compliant_basis: {enhanced_compliant} 条')
    print(f'已增强 violation_basis: {enhanced_violation} 条')

    # 保存
    output_path = output_file or input_file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

    print(f'已保存到: {output_path}')

    # 显示几个示例
    print()
    print('=' * 80)
    print('增强示例（前3条）:')
    print('=' * 80)

    enhanced_rules = [r for r in rules if '【重要】' in r.get('compliant_basis', '')][:3]
    for i, rule in enumerate(enhanced_rules, 1):
        print(f'\n【规则 {i}】{rule["rule_id"]}: {rule["rule_name"]}')
        print(f'\n合规依据: {rule["compliant_basis"][:200]}...')
        print(f'\n违规依据: {rule["violation_basis"][:200]}...')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='增强 rule_cards.json 的 basis 字段')
    parser.add_argument('--input', '-i', default='data/rule_cards.json', help='输入文件路径')
    parser.add_argument('--output', '-o', help='输出文件路径（默认覆盖原文件）')
    parser.add_argument('--dry-run', action='store_true', help='试运行，不保存文件')

    args = parser.parse_args()

    if args.dry_run:
        print('【试运行模式】不会保存文件')
        print()
        # 创建临时文件用于试运行
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            tmp_path = tmp.name

        enhance_rule_cards(args.input, tmp_path)

        import os
        os.unlink(tmp_path)
    else:
        enhance_rule_cards(args.input, args.output)
