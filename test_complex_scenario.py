#!/usr/bin/env python3
"""
复杂场景验证测试脚本
====================
测试超高难度的真实保险营销文本，验证双策略架构的效果。
"""

import sys
from pathlib import Path

# 添加项目路径
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))

from moderation.workflow import run_audit_sync
from moderation.log import setup_logging

def main():
    # 设置详细日志
    setup_logging(verbose=True)

    # 读取复杂测试文本
    test_file = ROOT_DIR / "data" / "complex_test_input.txt"
    if not test_file.exists():
        print(f"错误: 测试文件不存在 - {test_file}")
        sys.exit(1)

    input_text = test_file.read_text(encoding="utf-8")
    print("=" * 80)
    print("复杂场景验证测试")
    print("=" * 80)
    print(f"文本长度: {len(input_text)} 字")
    print(f"测试文件: {test_file}")
    print("=" * 80)

    # 执行审核
    print("\n开始审核...\n")
    response = run_audit_sync(input_text, doc_id="COMPLEX_TEST_001")

    # 输出结果
    print("\n" + "=" * 80)
    print("审核结果汇总")
    print("=" * 80)
    print(f"文档ID: {response.doc_id}")
    print(f"违规总数: {response.total_violations}")
    print(f"处理耗时: {response.processing_time_seconds} 秒")

    if response.violations:
        print("\n" + "-" * 80)
        print("违规详情:")
        print("-" * 80)

        for i, v in enumerate(response.violations, 1):
            print(f"\n【违规 {i}】")
            print(f"规则ID: {v.rule_id}")
            print(f"规则名称: {v.rule_name}")
            print(f"风险等级: {v.risk_level}")
            print(f"判定: {v.verdict}")

            print(f"\n推理过程:")
            print(f"  {v.reasoning[:200]}..." if len(v.reasoning) > 200 else f"  {v.reasoning}")

            print(f"\n违规位置:")
            for j, loc in enumerate(v.locations, 1):
                text_preview = loc.original_text_slice[:100]
                if len(loc.original_text_slice) > 100:
                    text_preview += "..."
                print(f"  位置 {j}: [{loc.raw_start}-{loc.raw_end}]")
                print(f"    内容: \"{text_preview}\"")

            print(f"\n修改建议:")
            suggestion_preview = v.suggestion[:150]
            if len(v.suggestion) > 150:
                suggestion_preview += "..."
            print(f"  {suggestion_preview}")

            if v.reason_codes:
                print(f"\n理由码: {', '.join(v.reason_codes)}")

            print("-" * 80)
    else:
        print("\n✓ 未发现违规内容")

    # 保存结果
    output_file = ROOT_DIR / "result_complex_test.json"
    output_file.write_text(
        response.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\n完整结果已保存到: {output_file}")

    # 分析预期场景
    print("\n" + "=" * 80)
    print("预期场景分析")
    print("=" * 80)

    expected_scenarios = [
        {
            "text": "张经理在加入我司之前...月薪2万元",
            "expected": "✅ compliant",
            "scenario": "temporal_context",
            "reason": "过往经历（合规）"
        },
        {
            "text": "李总监目前...月收入稳定在3-5万元",
            "expected": "❌ violation",
            "scenario": "temporal_context",
            "reason": "当前收入承诺（违规）"
        },
        {
            "text": "保底年利率2.5%",
            "expected": "✅ compliant",
            "scenario": "commitment_strength",
            "reason": "合同约定（合规）"
        },
        {
            "text": "如同在银行存钱一样安全",
            "expected": "⚠️ 需要看后续说明",
            "scenario": "cross_paragraph",
            "reason": "可能银保混淆"
        },
        {
            "text": "位居行业前列之一",
            "expected": "✅ compliant",
            "scenario": "basic",
            "reason": "有'之一'限定词（合规）"
        },
    ]

    print("\n预期复杂场景:")
    for i, scenario in enumerate(expected_scenarios, 1):
        print(f"\n{i}. {scenario['text'][:40]}...")
        print(f"   预期判定: {scenario['expected']}")
        print(f"   场景类型: {scenario['scenario']}")
        print(f"   原因: {scenario['reason']}")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

if __name__ == "__main__":
    main()
