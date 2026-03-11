"""
OCR 文本预处理模块
==================
处理从 PDF、PPT、图片 OCR 识别出的文本，这些文本可能存在以下问题：
1. 缺少换行符（整段文本连在一起）
2. 版面结构错乱（表格、多栏布局被打乱）
3. 多余的空格和特殊字符
4. 标点符号识别错误
5. 数字和字母识别错误

本模块提供智能修复和规范化功能。
"""

import re
from typing import Tuple


def detect_text_source(text: str) -> str:
    """
    检测文本来源类型（多信号联合判断，偏保守）

    返回:
        "ocr": OCR 识别文本（缺少换行、版面混乱）
        "normal": 正常文本（有换行、结构清晰）

    策略：需要同时满足多个 OCR 特征才判定为 OCR 文本，避免误判正常文本
    """
    if not text or len(text) < 50:
        return "normal"  # 短文本默认为正常文本

    # 特征 1：换行符密度
    has_newlines = "\n" in text
    newline_count = text.count("\n")
    avg_line_length = len(text) / (newline_count + 1)

    # 特征 2：中文字符间异常空格比例
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    chinese_with_space = re.findall(r'[\u4e00-\u9fff]\s+[\u4e00-\u9fff]', text)
    abnormal_space_ratio = len(chinese_with_space) / len(chinese_chars) if chinese_chars else 0

    # 特征 3：标点缺失或错乱
    # 正常文本应该有合理的标点密度（每 50-100 字符至少 1 个标点）
    punctuation_count = len(re.findall(r'[，。；！？、：]', text))
    punctuation_density = punctuation_count / len(text) if text else 0

    # 特征 4：表格/多栏痕迹（连续多个空格或 Tab）
    has_table_markers = bool(re.search(r'\s{3,}|\t', text))

    # OCR 判定规则：需要同时满足至少 2 个强特征
    ocr_signals = 0

    # 信号 1：无换行且超长（>500 字符）
    if not has_newlines and len(text) > 500:
        ocr_signals += 1

    # 信号 2：平均行长度过长（>300 字符）
    if avg_line_length > 300:
        ocr_signals += 1

    # 信号 3：中文间异常空格比例高（>20%）
    if abnormal_space_ratio > 0.2:
        ocr_signals += 1

    # 信号 4：标点密度异常低（<0.01，即每 100 字符少于 1 个标点）
    if punctuation_density < 0.01 and len(text) > 100:
        ocr_signals += 1

    # 信号 5：明显的表格/多栏痕迹
    if has_table_markers:
        ocr_signals += 1

    # 需要至少 2 个信号才判定为 OCR 文本
    if ocr_signals >= 2:
        return "ocr"

    return "normal"


def fix_ocr_spacing(text: str) -> str:
    """
    修复 OCR 文本中的空格问题

    OCR 常见问题：
    - 中文之间多余的空格："保 险 产 品" -> "保险产品"
    - 数字和单位之间缺少空格："100元" -> "100 元"
    - 英文单词之间缺少空格："HelloWorld" -> "Hello World"

    注意：此函数只处理空格问题，不处理换行符，以保留文本的段落结构。
    """
    # 1. 循环移除中文字符之间的空格（只匹配普通空格和全角空格，不匹配换行）
    max_iterations = 10
    for _ in range(max_iterations):
        # 只匹配普通空格 \x20 和全角空格 \u3000
        new_text = re.sub(r'([\u4e00-\u9fff])[ \u3000]+([\u4e00-\u9fff])', r'\1\2', text)
        if new_text == text:
            break  # 收敛，没有更多空格可移除
        text = new_text

    # 2. 移除中文标点前后的空格（只处理普通空格和全角空格）
    text = re.sub(r'[ \u3000]+([，。；！？、：])', r'\1', text)
    text = re.sub(r'([，。；！？、：])[ \u3000]+', r'\1', text)

    # 3. 确保数字和单位之间有空格（可选）
    # text = re.sub(r'(\d+)(元|万|亿|%|年|月|日)', r'\1 \2', text)

    # 4. 压缩连续的普通空格和全角空格（不处理换行符）
    text = re.sub(r'[ \u3000]{2,}', ' ', text)

    return text


def fix_ocr_punctuation(text: str) -> str:
    """
    修复 OCR 文本中的标点符号问题

    OCR 常见问题：
    - 标点符号缺失
    - 标点符号重复
    """
    # 1. 移除重复的标点符号
    text = re.sub(r'([，。；！？])\1+', r'\1', text)

    # 2. 修复常见的标点符号错误
    text = text.replace('。。', '。')
    text = text.replace('，，', '，')

    return text


def add_smart_newlines(text: str) -> str:
    """
    为缺少换行符的 OCR 文本智能添加换行符

    策略：
    1. 在句号、问号、感叹号后添加换行
    2. 在标题后添加换行（如"一、"、"（一）"等）
    3. 在列表项后添加换行（如"1."、"①"等）
    4. 保持原有的换行符
    """
    # 如果已经有足够的换行符，不需要处理
    if text.count('\n') > len(text) / 100:  # 平均每100字符至少1个换行
        return text

    # 1. 在句号、问号、感叹号后添加换行（如果后面不是换行符）
    text = re.sub(r'([。！？])\s*(?!\n)', r'\1\n', text)

    # 2. 在标题标记后添加换行
    # 匹配：一、二、三、... 或 （一）（二）... 或 1、2、3、...
    text = re.sub(r'([一二三四五六七八九十]+、)', r'\n\1', text)
    text = re.sub(r'(（[一二三四五六七八九十]+）)', r'\n\1', text)
    text = re.sub(r'(\d+、)', r'\n\1', text)

    # 3. 在列表项标记后添加换行
    # 匹配：①②③... 或 1. 2. 3. ...
    text = re.sub(r'([①②③④⑤⑥⑦⑧⑨⑩])', r'\n\1', text)
    text = re.sub(r'(\d+\.)\s+', r'\n\1 ', text)

    # 4. 移除多余的连续换行符（保留最多2个）
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 5. 移除行首行尾的空白
    lines = text.split('\n')
    lines = [line.strip() for line in lines]
    text = '\n'.join(lines)

    return text


def fix_ocr_numbers(text: str) -> str:
    """
    修复 OCR 文本中的数字识别错误

    OCR 常见问题：
    - 数字 0 识别为字母 O
    - 数字 1 识别为字母 l 或 I
    - 数字 5 识别为字母 S
    """
    # 这个功能比较危险，可能会误修复正常的字母
    # 只在明确的数字上下文中修复

    # 修复百分号前的字母 O -> 0
    text = re.sub(r'([^\d])O(%)', r'\g<1>0\2', text)

    # 修复金额中的字母（如"1OO元" -> "100元"）
    text = re.sub(r'(\d+)O(\d*)(元|万|亿)', r'\g<1>0\2\3', text)

    return text


def reconstruct_table_structure(text: str) -> str:
    """
    尝试重建表格结构

    OCR 常见问题：
    - 表格被识别为连续文本
    - 单元格内容混在一起

    策略：
    - 识别表格特征（如多个连续的数字、对齐的文本）
    - 添加适当的分隔符
    """
    # 简单策略：识别连续的"项目名称 + 数字"模式，添加换行
    # 例如："保额100万保费1万元" -> "保额100万\n保费1万元"

    # 匹配：中文 + 数字 + 单位，后面紧跟中文
    text = re.sub(
        r'([\u4e00-\u9fff]+\d+(?:元|万|亿|%|年|月|日)?)([\u4e00-\u9fff]{2,})',
        r'\1\n\2',
        text
    )

    return text


def preprocess_ocr_text(text: str, aggressive: bool = False) -> Tuple[str, str]:
    """
    预处理 OCR 文本

    参数:
        text: 原始文本
        aggressive: 是否使用激进的修复策略（可能会误修复）

    返回:
        (processed_text, source_type)
    """
    # 检测文本来源
    source_type = detect_text_source(text)

    if source_type == "normal":
        # 正常文本，只做基本清理
        text = fix_ocr_spacing(text)
        text = fix_ocr_punctuation(text)
        return text, source_type

    # OCR 文本，需要更多处理
    # 1. 修复空格
    text = fix_ocr_spacing(text)

    # 2. 修复标点符号
    text = fix_ocr_punctuation(text)

    # 3. 添加智能换行
    text = add_smart_newlines(text)

    # 4. 重建表格结构
    text = reconstruct_table_structure(text)

    # 5. 修复数字（可选，激进模式）
    if aggressive:
        text = fix_ocr_numbers(text)

    return text, source_type


def normalize_text_for_audit(text: str) -> str:
    """
    为审核系统规范化文本

    这是审核系统的入口函数，会自动检测文本类型并应用适当的预处理
    """
    processed_text, source_type = preprocess_ocr_text(text, aggressive=False)

    # 记录处理信息（可选）
    if source_type == "ocr":
        # 可以在这里添加日志
        pass

    return processed_text
