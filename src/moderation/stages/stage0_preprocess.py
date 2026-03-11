"""
Stage 0: 预处理与资产固化
========================
纯 Python 工程代码，无 LLM 参与。
负责文本清理、规范化、自适应切分 Chunk 和 Span，生成 DocumentState。

自适应 Chunk 切分策略（v2）
-----------------------------
1. 按段落标记（【…】标题行、连续换行）切分为自然段
2. 短段合并：相邻段总长不超过 CHUNK_SIZE 时合并
3. 长段二次切分：超过 CHUNK_SIZE 的段落在句号/分号边界处拆分
4. 上下文回溯重叠：每个 Chunk 开头携带前一个 Chunk 末尾的最后一句作为上下文窗口
"""

import re
import uuid
from typing import Dict, List, Tuple

from ..schemas import Span, Chunk, DocumentState


# ============================================================
# 文本规范化
# ============================================================

def normalize_text(text: str) -> Tuple[str, Dict[int, int]]:
    """
    文本清理与规范化（保留原文格式）：
      - 仅去除 \\r（回车符）
      - 保留所有空白字符（空格/Tab/全角空格/换行），不做合并
      - 生成 norm_to_raw_map（规范化坐标 -> 原始坐标）

    注意：为了确保定位准确，不对原文做任何格式修改，只做最小化清理。
    """
    norm_to_raw: Dict[int, int] = {}
    normalized: List[str] = []
    norm_idx = 0

    for raw_idx, char in enumerate(text):
        # 仅跳过回车符（Windows 换行符的一部分）
        if char == '\r':
            continue

        # 保留所有其他字符（包括空白字符）
        normalized.append(char)
        norm_to_raw[norm_idx] = raw_idx
        norm_idx += 1

    return ''.join(normalized), norm_to_raw


def _build_coordinate_map(source_text: str, target_text: str) -> Dict[int, int]:
    """
    构建 source_text -> target_text 的坐标映射表。

    使用 difflib.SequenceMatcher 构建稳定的字符级对齐映射，
    能够正确处理多字符插入、删除和混合修改场景。

    参数:
        source_text: 源文本（例如 working_text）
        target_text: 目标文本（例如 original_text）

    返回:
        source_idx -> target_idx 的映射表
    """
    import difflib

    coord_map: Dict[int, int] = {}

    # 如果两个文本完全相同，返回恒等映射
    if source_text == target_text:
        for i in range(len(source_text)):
            coord_map[i] = i
        return coord_map

    # 使用 SequenceMatcher 构建块级对齐
    matcher = difflib.SequenceMatcher(None, source_text, target_text)
    matching_blocks = matcher.get_matching_blocks()

    # 根据匹配块建立映射
    for source_start, target_start, size in matching_blocks:
        for offset in range(size):
            coord_map[source_start + offset] = target_start + offset

    # 处理未映射的字符（插入的字符）
    # 策略：将插入的字符映射到最近的已映射位置
    for source_idx in range(len(source_text)):
        if source_idx not in coord_map:
            # 查找最近的已映射位置
            # 优先向前查找
            for i in range(source_idx - 1, -1, -1):
                if i in coord_map:
                    coord_map[source_idx] = coord_map[i]
                    break
            else:
                # 如果前面没有，向后查找
                for i in range(source_idx + 1, len(source_text)):
                    if i in coord_map:
                        coord_map[source_idx] = coord_map[i]
                        break
                else:
                    # 如果都没有，映射到 0
                    coord_map[source_idx] = 0

    return coord_map


# ============================================================
# 自适应 Chunk 切分（v2）
# ============================================================

def _split_into_paragraphs(text: str) -> List[Tuple[str, int, int]]:
    """
    按自然段切分文本。分段依据：
      1. 【标题行】—— 以 【 开头的行作为新段落的起始
      2. 空行（连续换行） —— 段落分隔
      3. 单换行保留在段落内
    返回 [(paragraph_text, start_index, end_index), ...]
    """
    # 先按空行拆段（两个及以上换行 或 【标题标识前）
    # 使用正则：在 \n\n 或 \n(?=【) 处切分
    # 但需要保留位置信息，所以手动遍历

    paragraphs: List[Tuple[str, int, int]] = []
    lines = text.split('\n')

    current_start = 0
    current_parts: List[str] = []
    pos = 0  # 在 text 中的当前位置

    for i, line in enumerate(lines):
        line_start = pos
        line_end = pos + len(line)

        # 检测段落分隔条件
        is_header = line.strip().startswith('【')
        is_blank = line.strip() == ''

        if (is_header or is_blank) and current_parts:
            # 当前累积段落结束
            para_text = '\n'.join(current_parts)
            if para_text.strip():
                paragraphs.append((para_text, current_start, current_start + len(para_text)))

            current_parts = []
            if is_header:
                current_start = line_start
                current_parts.append(line)
            else:
                # 空行：下一个非空行开始新段落
                current_start = line_end + 1  # +1 for \n
        else:
            if not current_parts and not is_blank:
                current_start = line_start
            if not is_blank or current_parts:
                current_parts.append(line)

        pos = line_end + 1  # +1 for \n

    # 处理最后一段
    if current_parts:
        para_text = '\n'.join(current_parts)
        if para_text.strip():
            paragraphs.append((para_text, current_start, current_start + len(para_text)))

    return paragraphs


def _sentence_split(text: str) -> List[str]:
    """
    按句子边界切分文本。
    在 。；！？.!?; 后切分，保留标点在前一句。
    """
    pattern = r'(?<=[。；！？.!?;])'
    parts = re.split(pattern, text)
    return [p for p in parts if p.strip()]


def _split_long_paragraph(para_text: str, para_start: int, max_size: int) -> List[Tuple[str, int, int]]:
    """
    将超长段落按句号/分号/感叹号/问号边界二次切分。
    每个子块尽量接近但不超过 max_size。
    """
    sentences = _sentence_split(para_text)

    if len(sentences) <= 1:
        # 只有一句话且超长，直接按字数硬切（兜底）
        chunks = []
        start = 0
        while start < len(para_text):
            end = min(start + max_size, len(para_text))
            chunks.append((para_text[start:end], para_start + start, para_start + end))
            start = end
        return chunks

    result: List[Tuple[str, int, int]] = []
    current_text = ""
    current_pos = para_start

    for sent in sentences:
        if len(current_text) + len(sent) > max_size and current_text:
            # 当前块已满，提交
            result.append((current_text, current_pos, current_pos + len(current_text)))
            current_pos = current_pos + len(current_text)
            current_text = sent
        else:
            current_text += sent

    if current_text:
        result.append((current_text, current_pos, current_pos + len(current_text)))

    return result


def adaptive_split_chunks(
    text: str,
    max_size: int = 300,
    min_size: int = 80,
) -> List[Tuple[str, int, int]]:
    """
    自适应 Chunk 切分：
    1. 按自然段切分
    2. 短段合并（合并后不超过 max_size）
    3. 长段在句子边界处二次切分
    4. 上下文回溯重叠：每个 Chunk 开头追加前一个 Chunk 的最后一句（不超过 min_size 字）

    参数:
      max_size: 单个 Chunk 的最大字数（默认 300）
      min_size: 低于此字数的段落尝试与相邻段合并（默认 80）

    返回 [(chunk_text, start_index, end_index), ...]
    """
    # Step 1: 按自然段切分
    paragraphs = _split_into_paragraphs(text)
    if not paragraphs:
        return [(text, 0, len(text))] if text.strip() else []

    # Step 2: 短段合并 + 长段拆分 -> 得到初步 chunk 列表
    raw_chunks: List[Tuple[str, int, int]] = []
    buffer_text = ""
    buffer_start = paragraphs[0][1]

    for para_text, p_start, p_end in paragraphs:
        if not buffer_text:
            buffer_start = p_start

        candidate = (buffer_text + "\n" + para_text).strip() if buffer_text else para_text

        if len(candidate) <= max_size:
            # 合并
            buffer_text = candidate
        else:
            # 先提交已有 buffer
            if buffer_text:
                if len(buffer_text) > max_size:
                    raw_chunks.extend(_split_long_paragraph(buffer_text, buffer_start, max_size))
                else:
                    raw_chunks.append((buffer_text, buffer_start, buffer_start + len(buffer_text)))

            # 新段作为新 buffer
            buffer_text = para_text
            buffer_start = p_start

    # 提交最后的 buffer
    if buffer_text:
        if len(buffer_text) > max_size:
            raw_chunks.extend(_split_long_paragraph(buffer_text, buffer_start, max_size))
        else:
            raw_chunks.append((buffer_text, buffer_start, buffer_start + len(buffer_text)))

    # Step 3: 上下文回溯重叠 —— 每个 chunk（除第一个）在头部追加前一个 chunk 的最后一句
    if len(raw_chunks) <= 1:
        return raw_chunks

    final_chunks: List[Tuple[str, int, int]] = [raw_chunks[0]]
    for i in range(1, len(raw_chunks)):
        prev_text = raw_chunks[i - 1][0]
        curr_text, curr_start, curr_end = raw_chunks[i]

        # 取前一个 chunk 的最后一句作为上下文
        prev_sentences = _sentence_split(prev_text)
        if prev_sentences:
            overlap_sentence = prev_sentences[-1].strip()
            if len(overlap_sentence) > min_size:
                # 句子太长，截断
                overlap_sentence = overlap_sentence[-min_size:]
            # 在原始文本中定位 overlap 的起始位置
            prev_chunk_end = raw_chunks[i - 1][1] + len(prev_text)
            overlap_start = prev_chunk_end - len(overlap_sentence)
            full_text = overlap_sentence + "\n" + curr_text
            final_chunks.append((full_text, overlap_start, curr_end))
        else:
            final_chunks.append((curr_text, curr_start, curr_end))

    return final_chunks


# ============================================================
# Span 切分（保持不变）
# ============================================================

def split_into_spans(
    chunk_text: str,
    chunk_id: str,
    chunk_start: int,
    normalized_text: str = None
) -> List[Span]:
    """
    在 Chunk 内部按标点（逗号、句号、分号、问号、感叹号、换行）
    切分为最小语义单元 Span，并生成全局唯一的 span_id。

    注意：chunk_text 可能包含 overlap 上下文，但 chunk_start 是实际内容的起始位置。
    为了确保坐标正确，我们需要找到 chunk_text 在 normalized_text 中的实际位置。
    """
    # 按标点分割，保留分隔符
    pattern = r'(?<=[，。；！？,;!?\n])'
    parts = re.split(pattern, chunk_text)

    spans: List[Span] = []
    current_pos = 0
    span_idx = 0

    for part in parts:
        stripped = part.strip()
        if not stripped:
            current_pos += len(part)
            continue

        span_id = f"S_{chunk_id}_{span_idx:02d}"
        abs_start = chunk_start + current_pos
        abs_end = abs_start + len(part)

        # 如果提供了 normalized_text，验证坐标是否正确
        # 如果不匹配，尝试在 normalized_text 中查找正确位置
        if normalized_text is not None:
            expected_text = normalized_text[abs_start:abs_end] if abs_end <= len(normalized_text) else ""
            if expected_text != part:
                # 坐标不匹配，尝试在 chunk 范围内查找
                # 这通常发生在有 overlap 的情况下
                search_start = max(0, chunk_start - 100)  # 向前搜索一定范围
                search_end = min(len(normalized_text), chunk_start + len(chunk_text) + 100)
                search_text = normalized_text[search_start:search_end]

                # 在搜索范围内查找 part
                idx = search_text.find(part)
                if idx != -1:
                    abs_start = search_start + idx
                    abs_end = abs_start + len(part)

        spans.append(Span(
            span_id=span_id,
            span_text=part,
            start_index=abs_start,
            end_index=abs_end,
            chunk_id=chunk_id
        ))

        current_pos += len(part)
        span_idx += 1

    return spans


# ============================================================
# Stage 0 主函数
# ============================================================

def preprocess(
    original_text: str,
    working_text: str,
    doc_id: str | None = None,
    chunk_size: int = 300,
    chunk_min_size: int = 80,
) -> DocumentState:
    """
    Stage 0 主函数：
    1. 文本清理与规范化，生成 norm_to_working_map
    2. 自适应切分为 chunks（语义边界优先，带上下文回溯重叠）
    3. 在每个 Chunk 内部按标点切分为 spans，生成全局唯一 span_id
    4. 构建并返回完整的 DocumentState 对象

    参数:
      original_text: 用户输入的原始文本（未经任何处理）
      working_text: 经过 OCR 修复后的工作文本（用于审核处理）
      chunk_size: 单个 Chunk 的最大字数
      chunk_min_size: 低于此字数的段落尝试合并

    注意：自适应切分使用句级回溯重叠策略，不再使用固定 overlap 参数
    """
    if doc_id is None:
        doc_id = f"DOC_{uuid.uuid4().hex[:8]}"

    # Step 1: 生成 working_text -> original_text 的坐标映射
    working_to_original_map = _build_coordinate_map(working_text, original_text)

    # Step 2: 对 working_text 进行规范化
    normalized_text, norm_to_working_map = normalize_text(working_text)

    # Step 3: 自适应切分 chunks
    raw_chunks = adaptive_split_chunks(
        normalized_text,
        max_size=chunk_size,
        min_size=chunk_min_size,
    )

    # Step 4: 在每个 chunk 内切分 spans
    chunks: List[Chunk] = []
    span_pool: Dict[str, Span] = {}

    for idx, (chunk_text, start, end) in enumerate(raw_chunks):
        chunk_id = f"chunk_{idx:03d}"
        spans = split_into_spans(chunk_text, chunk_id, start, normalized_text)

        chunk = Chunk(
            chunk_id=chunk_id,
            chunk_text=chunk_text,
            spans=spans
        )
        chunks.append(chunk)

        for span in spans:
            span_pool[span.span_id] = span

    return DocumentState(
        doc_id=doc_id,
        original_text=original_text,
        working_text=working_text,
        normalized_text=normalized_text,
        norm_to_raw_map=norm_to_working_map,
        working_to_original_map=working_to_original_map,
        chunks=chunks,
        span_pool=span_pool
    )
