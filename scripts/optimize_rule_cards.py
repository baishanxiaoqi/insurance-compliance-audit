#!/usr/bin/env python3
"""
批量优化 rule_cards.json 中的 compliant_basis 和 violation_basis 字段
"""

import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


def generate_compliant_basis(rule: dict) -> str:
    """
    基于规则定义生成合规依据

    核心原则：
    1. 否定语境合规（材料中批评、处罚、禁止该表述时合规）
    2. 列出规则的例外条款
    3. 说明合规的具体情况
    """
    rule_name = rule['rule_name']
    violation_def = rule['violation_definition']
    exceptions = rule.get('exceptions', [])
    exclusion_terms = rule.get('exclusion_terms', [])

    # 提取违规词
    violation_terms = rule.get('violation_terms', [])
    violation_words = '、'.join(violation_terms[:3]) if violation_terms else rule_name.replace('知识库规则-', '')

    basis_parts = []

    # 1. 否定语境（最重要）
    basis_parts.append(
        f"【重要】否定语境合规：材料中批评、处罚、禁止使用'{violation_words}'等表述的行为时合规"
        f"（如'禁止使用{violation_words}'、'因使用{violation_words}被处罚'、'不得使用{violation_words}'），"
        f"因为材料本身在反对该违规行为。"
    )

    # 2. 排除词例外
    if exclusion_terms:
        exclusion_str = '、'.join(exclusion_terms[:5])
        if len(exclusion_terms) > 5:
            exclusion_str += '等'
        basis_parts.append(
            f"出现排除词时合规：{exclusion_str}。"
        )

    # 3. 其他例外条款
    if exceptions:
        # 过滤掉第一条（通常是"没有使用XX"这种废话）
        meaningful_exceptions = [e for e in exceptions if not e.startswith('没有使用') and not e.startswith('不违规')]
        if meaningful_exceptions:
            basis_parts.append(
                f"其他合规情况：{'; '.join(meaningful_exceptions[:3])}。"
            )

    return ' '.join(basis_parts)


def generate_violation_basis(rule: dict) -> str:
    """
    基于规则定义生成违规依据

    核心原则：
    1. 说明为什么违规
    2. 引用监管依据（如果有）
    3. 说明违规的危害
    """
    rule_name = rule['rule_name']
    violation_def = rule['violation_definition']

    # 提取违规词
    violation_terms = rule.get('violation_terms', [])
    violation_words = '、'.join(violation_terms[:3]) if violation_terms else rule_name.replace('知识库规则-', '')

    # 根据规则类型生成不同的违规依据
    basis_parts = []

    # 判断规则类型
    if any(kw in rule_name for kw in ['收益', '分红', '利率', '回报', '稳赚']):
        basis_parts.append(
            f"根据《保险法》和银保监会相关规定，禁止使用'{violation_words}'等表述，"
            f"因为：1) 可能误导消费者对收益的预期；2) 保险产品收益存在不确定性；"
            f"3) 违反如实告知义务。"
        )
    elif any(kw in rule_name for kw in ['最好', '第一', '唯一', '绝对', 'NO.1']):
        basis_parts.append(
            f"根据《广告法》第九条，禁止使用'{violation_words}'等绝对化用语，"
            f"因为：1) 具有排他性，损害公平竞争；2) 缺乏客观依据；"
            f"3) 可能误导消费者。"
        )
    elif any(kw in rule_name for kw in ['停售', '限时', '国家', '监管']):
        basis_parts.append(
            f"根据银保监会相关规定，禁止使用'{violation_words}'等表述，"
            f"因为：1) 可能构成虚假宣传；2) 不当使用监管名义；"
            f"3) 制造紧迫感误导消费者。"
        )
    elif any(kw in rule_name for kw in ['退保', '免责', '理赔', '存款']):
        basis_parts.append(
            f"根据《保险法》和消费者权益保护相关规定，禁止使用'{violation_words}'等表述，"
            f"因为：1) 可能侵害消费者合法权益；2) 隐瞒重要信息；"
            f"3) 误导消费者决策。"
        )
    elif any(kw in rule_name for kw in ['薪', '月入', '年薪', '招募']):
        basis_parts.append(
            f"根据银保监会《保险代理人监管规定》，禁止使用'{violation_words}'等表述，"
            f"因为：1) 代理人收入为佣金制，非固定工资；2) 用收入数字诱导应聘构成虚假宣传；"
            f"3) 误导应聘者对收入的预期。"
        )
    else:
        # 通用违规依据
        basis_parts.append(
            f"根据保险监管相关规定，禁止使用'{violation_words}'等表述，"
            f"因为可能误导消费者、违反广告法或保险法相关规定。"
        )

    return ' '.join(basis_parts)


def generate_compliant_case(rule: dict) -> str:
    """生成合规案例"""
    violation_terms = rule.get('violation_terms', [])
    violation_word = violation_terms[0] if violation_terms else rule['rule_name'].replace('知识库规则-', '')

    cases = []

    # 案例1：否定语境
    cases.append(f"案例1：'某公司因使用{violation_word}等表述被处罚'（否定语境，合规）")

    # 案例2：排除词
    exclusion_terms = rule.get('exclusion_terms', [])
    if exclusion_terms:
        cases.append(f"案例2：'没有{violation_word}的风险'（有排除词，合规）")

    # 案例3：例外条款
    exceptions = rule.get('exceptions', [])
    if exceptions and len(exceptions) > 1:
        exc = exceptions[1] if not exceptions[1].startswith('没有') else exceptions[0]
        cases.append(f"案例3：符合例外条款'{exc[:30]}...'的情况（合规）")

    return '；'.join(cases[:3])


def generate_violation_case(rule: dict) -> str:
    """生成违规案例"""
    violation_terms = rule.get('violation_terms', [])
    violation_word = violation_terms[0] if violation_terms else rule['rule_name'].replace('知识库规则-', '')

    cases = []

    # 案例1：直接使用违规词
    cases.append(f"案例1：'本产品{violation_word}'（直接使用违规词，违规）")

    # 案例2：变体表述
    if len(violation_terms) > 1:
        cases.append(f"案例2：'{violation_terms[1]}'（违规词变体，违规）")

    # 案例3：组合表述
    cases.append(f"案例3：'产品特点：{violation_word}'（宣传中使用，违规）")

    return '；'.join(cases[:3])


def optimize_rule_cards(input_file: str, output_file: str = None):
    """
    批量优化 rule_cards.json

    参数:
        input_file: 输入文件路径
        output_file: 输出文件路径（如果为 None，则覆盖原文件）
    """
    # 读取规则
    with open(input_file, 'r', encoding='utf-8') as f:
        rules = json.load(f)

    print(f'总规则数: {len(rules)}')

    # 统计需要优化的规则
    need_optimize = [
        r for r in rules
        if not r.get('compliant_basis') or not r.get('violation_basis')
    ]

    print(f'需要优化的规则数: {len(need_optimize)}')
    print()

    # 批量生成
    optimized_count = 0
    for rule in rules:
        if not rule.get('compliant_basis'):
            rule['compliant_basis'] = generate_compliant_basis(rule)
            optimized_count += 1

        if not rule.get('violation_basis'):
            rule['violation_basis'] = generate_violation_basis(rule)

        if not rule.get('compliant_case'):
            rule['compliant_case'] = generate_compliant_case(rule)

        if not rule.get('violation_case'):
            rule['violation_case'] = generate_violation_case(rule)

    print(f'已优化 {optimized_count} 条规则')

    # 保存
    output_path = output_file or input_file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

    print(f'已保存到: {output_path}')

    # 显示几个示例
    print()
    print('=' * 80)
    print('优化示例（前3条）:')
    print('=' * 80)
    for i, rule in enumerate(need_optimize[:3], 1):
        print(f'\n【规则 {i}】{rule["rule_id"]}: {rule["rule_name"]}')
        print(f'违规定义: {rule["violation_definition"][:60]}...')
        print(f'\n合规依据: {rule["compliant_basis"][:150]}...')
        print(f'\n违规依据: {rule["violation_basis"][:150]}...')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='批量优化 rule_cards.json')
    parser.add_argument('--input', '-i', default='data/rule_cards.json', help='输入文件路径')
    parser.add_argument('--output', '-o', help='输出文件路径（默认覆盖原文件）')
    parser.add_argument('--dry-run', action='store_true', help='试运行，不保存文件')

    args = parser.parse_args()

    if args.dry_run:
        print('【试运行模式】不会保存文件')
        print()

    optimize_rule_cards(
        args.input,
        args.output if not args.dry_run else None
    )
