#!/usr/bin/env python3
"""
测试 OCR 文本预处理功能
"""

import sys
from pathlib import Path

# 添加项目路径
ROOT_DIR = Path(__file__).parent
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from moderation.ocr_preprocessor import (
    detect_text_source,
    fix_ocr_spacing,
    fix_ocr_punctuation,
    add_smart_newlines,
    preprocess_ocr_text,
)


def test_detect_text_source():
    """测试文本来源检测"""
    print("=" * 60)
    print("测试1：文本来源检测")
    print("=" * 60)

    # 正常文本（有换行）
    normal_text = """保险产品介绍
本产品为终身寿险。
保障范围包括身故和全残。"""
    print(f"正常文本: {detect_text_source(normal_text)}")

    # OCR 文本（无换行）
    ocr_text = "保险产品介绍本产品为终身寿险保障范围包括身故和全残投保年龄为18-65周岁保险期间为终身缴费期间为10年20年30年可选"
    print(f"OCR 文本: {detect_text_source(ocr_text)}")
    print()


def test_fix_ocr_spacing():
    """测试空格修复"""
    print("=" * 60)
    print("测试2：空格修复")
    print("=" * 60)

    test_cases = [
        "保 险 产 品",
        "月 薪 2 万 元",
        "保险产品 ， 月薪2万元 。",
    ]

    for text in test_cases:
        fixed = fix_ocr_spacing(text)
        print(f"原文: {text}")
        print(f"修复: {fixed}")
        print()


def test_fix_ocr_punctuation():
    """测试标点符号修复"""
    print("=" * 60)
    print("测试3：标点符号修复")
    print("=" * 60)

    test_cases = [
        '保险产品"介绍"',
        "月薪2万元。。",
        "保险产品，，月薪2万元",
    ]

    for text in test_cases:
        fixed = fix_ocr_punctuation(text)
        print(f"原文: {text}")
        print(f"修复: {fixed}")
        print()


def test_add_smart_newlines():
    """测试智能换行"""
    print("=" * 60)
    print("测试4：智能换行")
    print("=" * 60)

    ocr_text = "一、产品介绍本产品为终身寿险。保障范围包括身故和全残。二、投保须知投保年龄为18-65周岁。保险期间为终身。三、产品特色1. 保底年利率2.5%。2. 身故保障全面。"

    fixed = add_smart_newlines(ocr_text)
    print("原文:")
    print(ocr_text)
    print()
    print("修复后:")
    print(fixed)
    print()


def test_preprocess_ocr_text():
    """测试完整的 OCR 预处理"""
    print("=" * 60)
    print("测试5：完整 OCR 预处理")
    print("=" * 60)

    # 模拟 OCR 识别的文本（无换行、有多余空格、标点错误）
    ocr_text = """【XX保险公司2024年度代理人招募计划】一、优秀代理人案例分享张经理的成长故事：张经理在加入我司之前 ， 曾在某知名外企担任销售总监 ， 月 薪 2 万 元 ， 年薪约25万。。2020年 ， 他选择了保险行业 ， 现在已成为我司的金牌代理人。。他说："保险行业让我找到了事业的第二春。"李总监的收入见证：李总监目前在我司担任高级代理人 ， 凭借专业的服务和出色的业绩 ， 月收入稳定在3-5万元区间。。他表示："只要用心服务客户 ， 收入自然水到渠成。"二、明星产品推荐【金福年年终身寿险】产品特色：1. 保底年利率2.5% ， 根据公司经营状况每年分红 ， 预期综合年化收益率可达4%-6%（以实际结算为准 ， 过往业绩不代表未来表现）2. 身故保障：基本保额+累计红利 ， 让家人无后顾之忧3. 现金价值稳定增长 ， 如同在银行存钱一样安全 ， 但收益更可观"""

    processed, source_type = preprocess_ocr_text(ocr_text)

    print(f"文本来源: {source_type}")
    print()
    print("原文（前200字）:")
    print(ocr_text[:200])
    print()
    print("处理后（前200字）:")
    print(processed[:200])
    print()
    print("完整处理后文本:")
    print(processed)


if __name__ == "__main__":
    test_detect_text_source()
    test_fix_ocr_spacing()
    test_fix_ocr_punctuation()
    test_add_smart_newlines()
    test_preprocess_ocr_text()

    print()
    print("=" * 60)
    print("所有测试完成")
    print("=" * 60)
