"""
Stage 1: 路由召回与大模型粗筛
==============================
Hybrid 检索工具 + 32B 大模型 Agent。
1. 混合检索：AC自动机关键词匹配 + 基于 jieba 分词的 TF-IDF 向量检索，为每个 chunk 召回 Top-K 候选 rule_id
2. Agent 过滤：使用 32B 充当 Filter Agent，从 Top-K 中筛选最可能相关的 Top-3
"""

import re
import math
import asyncio
from collections import Counter, defaultdict
from typing import Dict, List, Set, Tuple

import jieba

from .. import config
from ..llm_agent import create_agent, safe_arun
from ..log import get_logger
from ..schemas import (
    Chunk, RuleCard, ChunkCandidates, FilterResult, DocumentState
)
from ..ac_matcher import AhocorasickMatcher

logger = get_logger(__name__)


# ============================================================
# 轻量级 TF-IDF 实现（不依赖 sklearn）
# ============================================================

class SimpleTfidf:
    """基于 jieba 分词的轻量 TF-IDF 向量化器"""

    def __init__(self, custom_terms: List[str] = None):
        self.vocab: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_vectors: List[Dict[str, float]] = []

        # 加载自定义词典（保险领域专业术语）
        if custom_terms:
            for term in custom_terms:
                if term:  # 过滤空字符串
                    jieba.add_word(term)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [w for w in jieba.cut(text) if len(w.strip()) > 0]

    def fit(self, documents: List[str]):
        """构建 IDF 词表"""
        n_docs = len(documents)
        df: Counter = Counter()
        all_tokens: List[List[str]] = []

        for doc in documents:
            tokens = self._tokenize(doc)
            all_tokens.append(tokens)
            unique = set(tokens)
            for t in unique:
                df[t] += 1

        # 构建词表和 IDF
        for i, (term, freq) in enumerate(df.items()):
            self.vocab[term] = i
            self.idf[term] = math.log((n_docs + 1) / (freq + 1)) + 1

        # 构建文档 TF-IDF 向量
        self.doc_vectors = []
        for tokens in all_tokens:
            tf = Counter(tokens)
            vec: Dict[str, float] = {}
            for t, count in tf.items():
                if t in self.idf:
                    vec[t] = (count / len(tokens)) * self.idf[t]
            self.doc_vectors.append(vec)

    def query(self, text: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """查询与 text 最相似的文档，返回 [(doc_idx, score), ...]"""
        tokens = self._tokenize(text)
        tf = Counter(tokens)
        q_vec: Dict[str, float] = {}
        for t, count in tf.items():
            if t in self.idf:
                q_vec[t] = (count / max(len(tokens), 1)) * self.idf[t]

        # 余弦相似度
        scores: List[Tuple[int, float]] = []
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1e-10

        for idx, d_vec in enumerate(self.doc_vectors):
            dot = sum(q_vec.get(t, 0) * v for t, v in d_vec.items())
            d_norm = math.sqrt(sum(v * v for v in d_vec.values())) or 1e-10
            sim = dot / (q_norm * d_norm)
            if sim > 0.01:
                scores.append((idx, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# ============================================================
# 混合检索引擎
# ============================================================

class HybridRetriever:
    """
    混合检索器：关键词正则 + TF-IDF 向量相似度
    对每个 Chunk 召回 Top-K 候选规则
    """

    def __init__(self, rule_cards: Dict[str, RuleCard]):
        self.rule_cards = rule_cards
        self.rule_ids = list(rule_cards.keys())

        # 规则关键词与结构化匹配词表
        self._violation_terms: Dict[str, List[str]] = {}
        self._condition_terms: Dict[str, List[str]] = {}
        self._exclusion_terms: Dict[str, List[str]] = {}
        self._prefix_no_match: Dict[str, List[str]] = {}
        self._suffix_no_match: Dict[str, List[str]] = {}
        self._condition_distance: Dict[str, int | None] = {}
        self._exclusion_distance: Dict[str, int | None] = {}

        for rid, card in rule_cards.items():
            base_terms = card.violation_terms or card.keywords
            self._violation_terms[rid] = [t for t in base_terms if t]
            self._condition_terms[rid] = [t for t in card.condition_terms if t]
            self._exclusion_terms[rid] = [t for t in card.exclusion_terms if t]
            self._prefix_no_match[rid] = [t for t in card.prefix_no_match if t]
            self._suffix_no_match[rid] = [t for t in card.suffix_no_match if t]
            self._condition_distance[rid] = card.condition_distance
            self._exclusion_distance[rid] = card.exclusion_distance

        # 构建 AC自动机（用于高效关键词匹配）
        self._build_ac_matchers()

        # 构建 TF-IDF 索引（传入自定义词典）
        self._build_tfidf_index()

    def _build_ac_matchers(self):
        """构建5个AC自动机用于高效多模式匹配"""
        # 收集所有唯一的terms并建立term→rule_ids映射
        violation_term_to_rules: Dict[str, List[str]] = defaultdict(list)
        condition_term_to_rules: Dict[str, List[str]] = defaultdict(list)
        exclusion_term_to_rules: Dict[str, List[str]] = defaultdict(list)
        prefix_term_to_rules: Dict[str, List[str]] = defaultdict(list)
        suffix_term_to_rules: Dict[str, List[str]] = defaultdict(list)

        for rid in self.rule_ids:
            for term in self._violation_terms.get(rid, []):
                violation_term_to_rules[term].append(rid)
            for term in self._condition_terms.get(rid, []):
                condition_term_to_rules[term].append(rid)
            for term in self._exclusion_terms.get(rid, []):
                exclusion_term_to_rules[term].append(rid)
            for term in self._prefix_no_match.get(rid, []):
                prefix_term_to_rules[term].append(rid)
            for term in self._suffix_no_match.get(rid, []):
                suffix_term_to_rules[term].append(rid)

        # 构建5个独立的AC自动机
        self.ac_violation = AhocorasickMatcher(
            list(violation_term_to_rules.keys()),
            dict(violation_term_to_rules)
        )
        self.ac_condition = AhocorasickMatcher(
            list(condition_term_to_rules.keys()),
            dict(condition_term_to_rules)
        )
        self.ac_exclusion = AhocorasickMatcher(
            list(exclusion_term_to_rules.keys()),
            dict(exclusion_term_to_rules)
        )
        self.ac_prefix = AhocorasickMatcher(
            list(prefix_term_to_rules.keys()),
            dict(prefix_term_to_rules)
        )
        self.ac_suffix = AhocorasickMatcher(
            list(suffix_term_to_rules.keys()),
            dict(suffix_term_to_rules)
        )

        logger.info(
            f"AC自动机构建完成: "
            f"violation={self.ac_violation.term_count}, "
            f"condition={self.ac_condition.term_count}, "
            f"exclusion={self.ac_exclusion.term_count}, "
            f"prefix={self.ac_prefix.term_count}, "
            f"suffix={self.ac_suffix.term_count}"
        )

    def _build_tfidf_index(self):
        """为所有规则的 violation_definition 构建 TF-IDF 向量"""
        # 提取所有违规词作为自定义词典（保险领域专业术语）
        all_violation_terms = []
        for rid in self.rule_ids:
            all_violation_terms.extend(self._violation_terms[rid])

        # 去重
        unique_violation_terms = list(set(all_violation_terms))

        rule_texts = []
        for rid in self.rule_ids:
            card = self.rule_cards[rid]
            text = " ".join([
                card.rule_name,
                card.violation_definition,
                " ".join(card.keywords),
                " ".join(card.violation_terms),
                " ".join(card.condition_terms),
                card.violation_basis,
                card.compliant_basis,
                card.violation_case,
                card.compliant_case,
            ])
            rule_texts.append(text)

        # 初始化 SimpleTfidf 并传入自定义词典
        self.tfidf = SimpleTfidf(custom_terms=unique_violation_terms)
        self.tfidf.fit(rule_texts)

    @staticmethod
    def _find_positions(text: str, term: str) -> List[int]:
        if not term:
            return []
        return [m.start() for m in re.finditer(re.escape(term), text, re.IGNORECASE)]

    @staticmethod
    def _has_near_pair(a_positions: List[int], b_positions: List[int], distance: int | None) -> bool:
        if not a_positions or not b_positions:
            return False
        if distance is None:
            return True
        for a in a_positions:
            for b in b_positions:
                if abs(a - b) <= distance:
                    return True
        return False

    def _filter_positions_by_no_match(
        self,
        text: str,
        term: str,
        positions: List[int],
        prefixes: List[str],
        suffixes: List[str],
    ) -> List[int]:
        """
        前缀/后缀不匹配规则：拼接词命中时，该位置不计入违规词命中。
        例：违规词=免税，后缀不匹配=店，命中"免税店"则该次命中剔除。
        """
        blocked_positions: Set[int] = set()

        # 使用AC自动机匹配前缀和后缀
        all_prefix_matches = self.ac_prefix.find_all(text)
        all_suffix_matches = self.ac_suffix.find_all(text)

        for p in prefixes:
            phrase = f"{p}{term}"
            # 查找拼接词的位置
            for idx in self._find_positions(text, phrase):
                # 阻断的是term的起始位置（即prefix之后）
                blocked_positions.add(idx + len(p))

        for s in suffixes:
            phrase = f"{term}{s}"
            # 查找拼接词的位置
            for idx in self._find_positions(text, phrase):
                # 阻断的是term的起始位置
                blocked_positions.add(idx)

        return [pos for pos in positions if pos not in blocked_positions]

    def _keyword_recall(self, chunk_text: str) -> Dict[str, float]:
        """结构化关键词匹配，返回 {rule_id: score}

        优化策略：
        1. 使用 AC 自动机一次性扫描所有违规词、条件词、排除词
        2. 在规则循环中直接使用预计算的匹配结果
        3. 避免在规则循环内重复调用 find_all()
        """
        # 一次性扫描所有词汇（移到规则循环外部）
        all_violation_matches = self.ac_violation.find_all(chunk_text)
        all_condition_matches = self.ac_condition.find_all(chunk_text)
        all_exclusion_matches = self.ac_exclusion.find_all(chunk_text)

        scores: Dict[str, float] = {}
        for rid in self.rule_ids:
            violation_terms = self._violation_terms.get(rid, [])
            if not violation_terms:
                continue

            v_positions_map: Dict[str, List[int]] = {}
            total_hits = 0

            # 从预计算的 AC 结果中提取该规则的违规词匹配
            for term in violation_terms:
                positions = all_violation_matches.get(term, [])
                if not positions:
                    continue

                # 应用前后缀过滤
                positions = self._filter_positions_by_no_match(
                    text=chunk_text,
                    term=term,
                    positions=positions,
                    prefixes=self._prefix_no_match.get(rid, []),
                    suffixes=self._suffix_no_match.get(rid, []),
                )
                if positions:
                    v_positions_map[term] = positions
                    total_hits += len(positions)

            if total_hits == 0:
                continue

            all_v_positions = [p for arr in v_positions_map.values() for p in arr]

            # 条件词：违规词 + 条件词 同时出现才有效
            condition_terms = self._condition_terms.get(rid, [])
            if condition_terms:
                # 直接使用预计算的条件词匹配结果
                cond_positions: List[int] = []
                for cond in condition_terms:
                    cond_positions.extend(all_condition_matches.get(cond, []))

                if not self._has_near_pair(
                    all_v_positions,
                    cond_positions,
                    self._condition_distance.get(rid),
                ):
                    continue

            # 排除词：违规词 + 排除词 同时出现则排除
            exclusion_terms = self._exclusion_terms.get(rid, [])
            if exclusion_terms:
                # 直接使用预计算的排除词匹配结果
                excl_positions: List[int] = []
                for ex in exclusion_terms:
                    excl_positions.extend(all_exclusion_matches.get(ex, []))

                if self._has_near_pair(
                    all_v_positions,
                    excl_positions,
                    self._exclusion_distance.get(rid),
                ):
                    continue

            # 命中评分：违规词覆盖率 + 命中密度
            matched_term_ratio = len(v_positions_map) / max(len(violation_terms), 1)
            density = min(total_hits / 5.0, 1.0)
            scores[rid] = 0.7 * matched_term_ratio + 0.3 * density
        return scores

    def _vector_recall(self, chunk_text: str, top_k: int = 20) -> Dict[str, float]:
        """TF-IDF 向量检索，返回 {rule_id: similarity_score}"""
        results = self.tfidf.query(chunk_text, top_k=top_k)
        scores: Dict[str, float] = {}
        for idx, sim in results:
            scores[self.rule_ids[idx]] = sim
        return scores

    def recall(self, chunk_text: str, top_k: int = 20) -> List[str]:
        """
        双通道混合检索：
        - 关键词通道（保精度）：对强结构化规则（有 condition/exclusion/prefix/suffix 约束）严格要求关键词命中
        - 向量通道（补召回）：对简单规则或复杂语义规则，允许向量检索补召

        最后融合排序返回 Top-K rule_ids
        """
        kw_scores = self._keyword_recall(chunk_text)
        vec_scores = self._vector_recall(chunk_text, top_k * 2)  # 向量通道多召回一些候选

        # 识别强结构化规则：有 condition/exclusion/prefix/suffix 约束的规则
        structured_rules: Set[str] = set()
        for rid in self._violation_terms.keys():
            if (self._condition_terms.get(rid) or
                self._exclusion_terms.get(rid) or
                self._prefix_no_match.get(rid) or
                self._suffix_no_match.get(rid)):
                structured_rules.add(rid)

        # 双通道融合
        all_rule_ids: Set[str] = set(kw_scores.keys()) | set(vec_scores.keys())
        merged: List[Tuple[str, float]] = []

        for rid in all_rule_ids:
            kw_s = kw_scores.get(rid, 0.0)
            vec_s = vec_scores.get(rid, 0.0)

            # 关键词通道：强结构化规则必须先通过关键词门槛
            if rid in structured_rules and kw_s <= 0:
                continue

            # 向量通道：简单规则或复杂语义规则允许向量补召
            # 如果关键词未命中但向量分数高，仍然保留（补召回能力）
            if kw_s <= 0 and vec_s > 0.3:  # 向量分数阈值 0.3
                # 纯向量召回，降低权重
                merged.append((rid, 0.4 * vec_s))
            else:
                # 关键词 + 向量融合
                merged.append((rid, 0.6 * kw_s + 0.4 * vec_s))

        # 按分数降序排列
        merged.sort(key=lambda x: x[1], reverse=True)
        return [rid for rid, _ in merged[:top_k]]


# ============================================================
# 大模型过滤 Agent
# ============================================================

def build_filter_agent():
    """构建 Stage 1 的 Filter Agent（Agno Agent）"""
    return create_agent(
        output_schema=FilterResult,
        name="filter_agent",
        instructions=[
            "你是一个保险合规审核助手。",
            "你的任务是从候选规则列表中，排除明显无关的规则，仅返回最可能与给定文本相关的规则ID列表。",
            "无需输出解释，仅返回相关的 rule_id 列表。",
            "如果没有任何规则相关，返回空列表。",
        ],
    )


def build_filter_prompt(
    chunk_text: str,
    candidate_rules: List[RuleCard],
    top_k: int = 3
) -> str:
    """构建 Filter Agent 的 Prompt"""
    rules_desc = "\n".join([
        f"- {r.rule_id}: {r.rule_name} — {r.violation_definition[:80]}..."
        for r in candidate_rules
    ])

    return f"""请阅读以下保险文本片段，并从候选规则中选出最可能相关的 Top-{top_k} 条规则。

【文本片段】
{chunk_text}

【候选规则】
{rules_desc}

请仅返回最相关的 rule_id 列表（最多{top_k}条），无需解释。如果文本片段与所有候选规则都不相关，返回空列表。"""


# ============================================================
# Stage 1 主函数
# ============================================================

async def _filter_single_chunk(
    chunk: Chunk,
    retriever: HybridRetriever,
    filter_agent,
    rule_cards: Dict[str, RuleCard],
    top_k_recall: int,
    top_k_filter: int,
    semaphore: asyncio.Semaphore,
) -> ChunkCandidates | None:
    """对单个 chunk 执行混合检索 + LLM 过滤（并发安全）"""
    async with semaphore:
        logger.info(f"Stage 1 处理 Chunk: {chunk.chunk_id}")

        # Step 1: 混合检索 Top-K 候选（纯计算，不需要异步）
        candidate_ids = retriever.recall(chunk.chunk_text, top_k=top_k_recall)

        if not candidate_ids:
            logger.info(f"  Chunk {chunk.chunk_id}: 无候选规则")
            return None

        # Step 2: LLM 过滤
        candidate_cards = [rule_cards[rid] for rid in candidate_ids if rid in rule_cards]
        prompt = build_filter_prompt(chunk.chunk_text, candidate_cards, top_k=top_k_filter)

        try:
            filter_result: FilterResult = await safe_arun(filter_agent, prompt)

            # 验证返回的 rule_id 在候选列表中
            valid_ids = [
                rid for rid in filter_result.relevant_rule_ids
                if rid in candidate_ids
            ]

            if valid_ids:
                logger.info(f"  Chunk {chunk.chunk_id}: 筛选出 {len(valid_ids)} 条规则 -> {valid_ids}")
                return ChunkCandidates(
                    chunk_id=chunk.chunk_id,
                    candidate_rule_ids=valid_ids
                )
            else:
                logger.info(f"  Chunk {chunk.chunk_id}: LLM 过滤后无相关规则")
                return None

        except Exception as e:
            logger.warning(f"  Chunk {chunk.chunk_id} LLM 过滤失败: {e}")
            # 降级：直接使用混合检索的 top-3
            fallback_ids = candidate_ids[:top_k_filter]
            logger.info(f"  降级使用检索 Top-{top_k_filter}: {fallback_ids}")
            return ChunkCandidates(
                chunk_id=chunk.chunk_id,
                candidate_rule_ids=fallback_ids
            )


async def run_stage1(
    document: DocumentState,
    rule_cards: Dict[str, RuleCard],
    top_k_recall: int = 20,
    top_k_filter: int = 3,
    max_concurrent: int = 10,
) -> List[ChunkCandidates]:
    """
    Stage 1 执行逻辑（并发优化版 + 缓存优化）：
    1. 对每个 Chunk 进行混合检索，召回 Top-K 候选规则
    2. 使用 Filter Agent 并发过滤，从候选中筛选 Top-3
    返回 List[ChunkCandidates]

    性能优化：
      - 使用缓存的 HybridRetriever（避免重复构建 TF-IDF 索引）
      - 使用缓存的 Filter Agent（避免重复创建 Agent）
    """
    from ..stage1_cache import get_cached_retriever, get_cached_filter_agent

    retriever = get_cached_retriever(rule_cards)
    filter_agent = get_cached_filter_agent()
    semaphore = asyncio.Semaphore(max_concurrent)

    # 并发处理所有 chunk
    tasks = [
        _filter_single_chunk(
            chunk, retriever, filter_agent, rule_cards,
            top_k_recall, top_k_filter, semaphore
        )
        for chunk in document.chunks
    ]

    raw_results = await asyncio.gather(*tasks)

    # 过滤 None 结果，保持 chunk 顺序
    results = [r for r in raw_results if r is not None]
    return results
