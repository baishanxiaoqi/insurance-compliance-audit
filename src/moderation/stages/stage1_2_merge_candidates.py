"""
Stage 1.2: 合并 keyword raw candidates 与 semantic candidates
=============================================================
核心职责：
1. 合并 keyword raw candidates 和 semantic candidates
2. 去重（保留首次出现顺序）
3. 保留顺序：关键词优先，语义补充在后
4. 限制总量（per chunk）
5. 产出 provenance：stage12_rule_sources[chunk_id][rule_id] = "keyword"|"semantic"|"both"
"""

from typing import Dict, List, Literal

from ..log import get_logger
from ..schemas import ChunkCandidates

logger = get_logger(__name__)

# provenance 标签类型
RuleSource = Literal["keyword", "semantic", "both"]


def merge_candidates(
    keyword_candidates: List[ChunkCandidates],
    semantic_candidates: List[ChunkCandidates],
    max_per_chunk: int = 30,
) -> tuple[List[ChunkCandidates], Dict[str, Dict[str, RuleSource]]]:
    """
    合并关键词召回候选和语义预检候选。

    Args:
        keyword_candidates: Stage 1A 的 raw recall 输出
        semantic_candidates: Stage 1B 的 semantic prescreen 输出
        max_per_chunk: 每个 chunk 合并后最大候选数量

    Returns:
        (merged_candidates, rule_sources)
        - merged_candidates: List[ChunkCandidates]，已合并去重，keyword 优先
        - rule_sources: Dict[chunk_id, Dict[rule_id, "keyword"|"semantic"|"both"]]
    """
    # 建立 semantic 候选索引 {chunk_id: set(rule_ids)}
    semantic_index: Dict[str, List[str]] = {}
    for cands in semantic_candidates:
        semantic_index[cands.chunk_id] = list(cands.candidate_rule_ids)

    # 建立 keyword 候选索引 {chunk_id: list(rule_ids)}
    keyword_index: Dict[str, List[str]] = {}
    for cands in keyword_candidates:
        keyword_index[cands.chunk_id] = list(cands.candidate_rule_ids)

    # 合并所有涉及的 chunk_id
    all_chunk_ids: List[str] = []
    seen_chunks = set()
    for cands in keyword_candidates:
        if cands.chunk_id not in seen_chunks:
            all_chunk_ids.append(cands.chunk_id)
            seen_chunks.add(cands.chunk_id)
    for cands in semantic_candidates:
        if cands.chunk_id not in seen_chunks:
            all_chunk_ids.append(cands.chunk_id)
            seen_chunks.add(cands.chunk_id)

    merged_candidates: List[ChunkCandidates] = []
    rule_sources: Dict[str, Dict[str, RuleSource]] = {}

    for chunk_id in all_chunk_ids:
        kw_rules = keyword_index.get(chunk_id, [])
        sem_rules = semantic_index.get(chunk_id, [])

        # keyword 规则集合，用于快速查重
        kw_set = set(kw_rules)
        sem_set = set(sem_rules)

        # 合并：keyword 优先，semantic 补充（去重）
        merged: List[str] = []
        sources: Dict[str, RuleSource] = {}

        for rid in kw_rules:
            if rid not in sources:
                merged.append(rid)
                sources[rid] = "keyword"

        for rid in sem_rules:
            if rid in sources:
                # 关键词和语义都命中
                sources[rid] = "both"
            else:
                merged.append(rid)
                sources[rid] = "semantic"

        # 限制总量
        if len(merged) > max_per_chunk:
            # 保留 keyword 优先，semantic 补充到上限
            kw_part = [r for r in merged if sources[r] in ("keyword", "both")]
            sem_part = [r for r in merged if sources[r] == "semantic"]
            remaining = max_per_chunk - len(kw_part)
            merged = kw_part + sem_part[:max(remaining, 0)]

        if merged:
            merged_candidates.append(ChunkCandidates(
                chunk_id=chunk_id,
                candidate_rule_ids=merged,
            ))
            rule_sources[chunk_id] = {rid: sources[rid] for rid in merged}

            sem_added = sum(1 for r in merged if sources.get(r) == "semantic")
            both_count = sum(1 for r in merged if sources.get(r) == "both")
            logger.debug(
                f"  [merge] Chunk {chunk_id}: total={len(merged)}, "
                f"keyword={len(kw_rules)}, semantic_added={sem_added}, both={both_count}"
            )

    logger.info(
        f"Stage 1.2 完成: {len(merged_candidates)} chunks, "
        f"total_pairs={sum(len(c.candidate_rule_ids) for c in merged_candidates)}"
    )
    return merged_candidates, rule_sources
