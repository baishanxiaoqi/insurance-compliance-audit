"""
验证审查报告中提到的问题
"""
import sys
sys.path.insert(0, 'src')

from moderation.ocr_preprocessor import fix_ocr_spacing, preprocess_ocr_text
from moderation.stages.stage0_preprocess import _build_coordinate_map


def test_issue1_newline_removal():
    """问题1：fix_ocr_spacing() 会吞掉正常文本中的换行"""
    print("\n=== 测试问题1：换行被吞掉 ===")

    # 测试1：多段文本
    input_text = "第一段\n\n第二段\n第三段"
    result = fix_ocr_spacing(input_text)
    print(f"输入: {repr(input_text)}")
    print(f"输出: {repr(result)}")
    print(f"换行保留: {input_text.count(chr(10)) == result.count(chr(10))}")

    # 测试2：通过 preprocess_ocr_text
    result2, source_type = preprocess_ocr_text(input_text)
    print(f"\n通过 preprocess_ocr_text:")
    print(f"源类型: {source_type}")
    print(f"输出: {repr(result2)}")
    print(f"换行保留: {input_text.count(chr(10)) == result2.count(chr(10))}")


def test_issue2_coordinate_mapping():
    """问题2：坐标映射对多字符插入不稳"""
    print("\n\n=== 测试问题2：多字符插入坐标映射 ===")

    original_text = "第一段。第二段。"
    working_text = "第一段。\n\n第二段。"

    print(f"原文: {repr(original_text)}")
    print(f"工作文本: {repr(working_text)}")

    # 构建映射
    coord_map = _build_coordinate_map(working_text, original_text)

    # 测试"第二段。"的定位
    # 在 working_text 中，"第二段。" 从索引 6 开始
    working_start = 6
    working_end = 10

    print(f"\n工作文本中 '第二段。' 的位置: [{working_start}:{working_end}]")
    print(f"工作文本切片: {repr(working_text[working_start:working_end])}")

    # 映射到原文
    if working_start in coord_map and working_end - 1 in coord_map:
        original_start = coord_map[working_start]
        original_end = coord_map[working_end - 1] + 1

        print(f"映射到原文位置: [{original_start}:{original_end}]")
        print(f"原文切片: {repr(original_text[original_start:original_end])}")

        # 验证是否正确
        expected = "第二段。"
        actual = original_text[original_start:original_end]
        print(f"\n期望: {repr(expected)}")
        print(f"实际: {repr(actual)}")
        print(f"映射正确: {expected == actual}")
    else:
        print("映射表中缺少关键索引")

    # 打印部分映射表
    print(f"\n映射表示例:")
    for i in range(min(12, len(working_text))):
        target_idx = coord_map.get(i, -1)
        working_char = working_text[i] if i < len(working_text) else '?'
        original_char = original_text[target_idx] if 0 <= target_idx < len(original_text) else '?'
        print(f"  {i} -> {target_idx}: '{working_char}' -> '{original_char}'")


def test_issue3_cache_key():
    """问题3：缓存键只看 rule_id，规则内容变了也不会失效"""
    print("\n\n=== 测试问题3：缓存键问题 ===")

    from moderation.stage1_cache import _compute_rules_hash, clear_cache
    from moderation.schemas import RuleCard

    # 创建两个内容不同但 rule_id 相同的规则
    rule1 = RuleCard(
        rule_id="R001",
        rule_name="退保规则",
        risk_level="high",
        violation_definition="禁止承诺退保",
        keywords=["退保"],
        violation_terms=["退保"],
        condition_terms=[],
        exclusion_terms=[]
    )

    rule2 = RuleCard(
        rule_id="R001",
        rule_name="收益规则",
        risk_level="high",
        violation_definition="禁止承诺收益",
        keywords=["收益"],
        violation_terms=["收益"],
        condition_terms=[],
        exclusion_terms=[]
    )

    rules_v1 = {"R001": rule1}
    rules_v2 = {"R001": rule2}

    hash1 = _compute_rules_hash(rules_v1)
    hash2 = _compute_rules_hash(rules_v2)

    print(f"规则v1 hash: {hash1}")
    print(f"规则v2 hash: {hash2}")
    print(f"hash相同: {hash1 == hash2}")

    if hash1 == hash2:
        print(f"\n问题确认: 规则内容变了，但 hash 仍然相同，缓存不会失效")
    else:
        print(f"\n问题已修复: 规则内容变化后，hash 也会变化，缓存会正确失效")


if __name__ == "__main__":
    test_issue1_newline_removal()
    test_issue2_coordinate_mapping()
    test_issue3_cache_key()
