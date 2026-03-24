"""
测试语义预检 pipeline 的工程约束：
1. semantic 候选不会绕过 unified filter
2. merge 顺序是 keyword 优先、semantic 补充
3. provenance 正确记录 keyword/semantic/both
4. feature flag 关闭时行为与旧版一致
"""

import asyncio
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.moderation.schemas import ChunkCandidates
from src.moderation.stages.stage1_2_merge_candidates import merge_candidates


# ============================================================
# merge_candidates 单元测试
# ============================================================

class TestMergeCandidates:

    def test_keyword_only(self):
        """只有 keyword 候选时，结果全部来自 keyword"""
        kw = [ChunkCandidates(chunk_id="c1", candidate_rule_ids=["R001", "R002"])]
        sem = []
        merged, sources = merge_candidates(kw, sem)
        assert len(merged) == 1
        assert merged[0].candidate_rule_ids == ["R001", "R002"]
        assert sources["c1"]["R001"] == "keyword"
        assert sources["c1"]["R002"] == "keyword"

    def test_semantic_only(self):
        """只有 semantic 候选时，结果全部来自 semantic"""
        kw = []
        sem = [ChunkCandidates(chunk_id="c1", candidate_rule_ids=["R010", "R011"])]
        merged, sources = merge_candidates(kw, sem)
        assert len(merged) == 1
        assert merged[0].candidate_rule_ids == ["R010", "R011"]
        assert sources["c1"]["R010"] == "semantic"

    def test_keyword_first_order(self):
        """keyword 规则必须排在 semantic 新增规则之前"""
        kw = [ChunkCandidates(chunk_id="c1", candidate_rule_ids=["R001", "R002"])]
        sem = [ChunkCandidates(chunk_id="c1", candidate_rule_ids=["R003", "R004"])]
        merged, sources = merge_candidates(kw, sem)
        result_ids = merged[0].candidate_rule_ids
        # keyword 的 R001/R002 必须在 R003/R004 之前
        assert result_ids.index("R001") < result_ids.index("R003")
        assert result_ids.index("R002") < result_ids.index("R003")

    def test_provenance_both(self):
        """keyword 和 semantic 都命中同一规则，来源标记为 both"""
        kw = [ChunkCandidates(chunk_id="c1", candidate_rule_ids=["R001", "R002"])]
        sem = [ChunkCandidates(chunk_id="c1", candidate_rule_ids=["R002", "R003"])]
        merged, sources = merge_candidates(kw, sem)
        assert sources["c1"]["R001"] == "keyword"
        assert sources["c1"]["R002"] == "both"
        assert sources["c1"]["R003"] == "semantic"

    def test_dedup(self):
        """合并后不能有重复规则 ID"""
        kw = [ChunkCandidates(chunk_id="c1", candidate_rule_ids=["R001", "R002", "R003"])]
        sem = [ChunkCandidates(chunk_id="c1", candidate_rule_ids=["R002", "R003", "R004"])]
        merged, _ = merge_candidates(kw, sem)
        ids = merged[0].candidate_rule_ids
        assert len(ids) == len(set(ids)), "合并后存在重复 rule_id"

    def test_max_per_chunk_cap(self):
        """超过 max_per_chunk 时截断，keyword 优先保留"""
        kw_ids = [f"KW{i:03d}" for i in range(10)]
        sem_ids = [f"SEM{i:03d}" for i in range(10)]
        kw = [ChunkCandidates(chunk_id="c1", candidate_rule_ids=kw_ids)]
        sem = [ChunkCandidates(chunk_id="c1", candidate_rule_ids=sem_ids)]
        merged, sources = merge_candidates(kw, sem, max_per_chunk=12)
        result_ids = merged[0].candidate_rule_ids
        assert len(result_ids) <= 12
        # 所有 keyword 规则都应被保留
        for kid in kw_ids:
            assert kid in result_ids

    def test_multi_chunk(self):
        """多个 chunk 各自独立处理"""
        kw = [
            ChunkCandidates(chunk_id="c1", candidate_rule_ids=["R001"]),
            ChunkCandidates(chunk_id="c2", candidate_rule_ids=["R002"]),
        ]
        sem = [
            ChunkCandidates(chunk_id="c2", candidate_rule_ids=["R010"]),
        ]
        merged, sources = merge_candidates(kw, sem)
        merged_map = {c.chunk_id: c for c in merged}
        assert "c1" in merged_map
        assert "c2" in merged_map
        assert sources["c1"]["R001"] == "keyword"
        assert sources["c2"]["R002"] == "keyword"
        assert sources["c2"]["R010"] == "semantic"


# ============================================================
# feature flag 测试
# ============================================================

class TestFeatureFlag:

    def test_flag_off_uses_run_stage1(self):
        """
        ENABLE_SEMANTIC_PRESCREEN=False 时，_stage1_executor 应调用 run_stage1
        而不是 run_stage1_with_semantic_prescreen。
        验证方式：patch run_stage1 并确认它被调用。
        """
        from src.moderation import config as cfg

        original = cfg.ENABLE_SEMANTIC_PRESCREEN
        try:
            # 通过 object.__setattr__ 绕过 frozen dataclass（config 是模块级变量，直接赋值即可）
            import src.moderation.config as cfg_mod
            cfg_mod.ENABLE_SEMANTIC_PRESCREEN = False

            called = {}

            async def fake_run_stage1(**kwargs):
                called["run_stage1"] = True
                return []

            async def fake_semantic(**kwargs):
                called["semantic"] = True
                return [], {}

            with patch("src.moderation.workflow.run_stage1", side_effect=fake_run_stage1), \
                 patch("src.moderation.workflow.run_stage1_1_semantic_prescreen", side_effect=fake_semantic):

                from src.moderation.workflow import _stage1_executor
                from src.moderation.schemas import WorkflowState, DocumentState
                from agno.workflow import StepInput
                from contextvars import ContextVar
                import src.moderation.workflow as wf_mod

                # 构建最简 state
                doc = DocumentState(
                    doc_id="test",
                    original_text="x",
                    working_text="x",
                    normalized_text="x",
                    chunks=[],
                )
                state = WorkflowState(document=doc)
                token = wf_mod._current_state.set(state)
                token2 = wf_mod._current_meta.set({"start_time": 0})
                try:
                    asyncio.get_event_loop().run_until_complete(
                        _stage1_executor(StepInput(input=""))
                    )
                finally:
                    wf_mod._current_state.reset(token)
                    wf_mod._current_meta.reset(token2)

            assert called.get("run_stage1"), "flag=off 时应调用 run_stage1"
            assert not called.get("semantic"), "flag=off 时不应调用 semantic prescreen"
        finally:
            import src.moderation.config as cfg_mod
            cfg_mod.ENABLE_SEMANTIC_PRESCREEN = original


# ============================================================
# semantic 候选必须经过 filter（工程约束测试）
# ============================================================

class TestSemanticMustGoThroughFilter:

    def test_semantic_candidates_go_through_filter(self):
        """
        验证 run_stage1_with_semantic_prescreen 中，
        semantic 扩展规则必须经过 run_stage1_filter_only，
        不能直接出现在最终 stage1_candidates 中（bypass 禁止）。
        通过 mock filter 返回空列表，验证最终结果为空。
        """
        import src.moderation.workflow as wf_mod
        import src.moderation.config as cfg_mod

        cfg_mod.ENABLE_SEMANTIC_PRESCREEN = True
        try:
            from src.moderation.schemas import WorkflowState, DocumentState
            from src.moderation.stages.stage0_preprocess import preprocess

            doc = preprocess(
                original_text="这款产品就像银行存款一样安全，收益更高",
                working_text="这款产品就像银行存款一样安全，收益更高",
                doc_id="test_filter",
            )
            state = WorkflowState(document=doc, rule_cards={})

            async def fake_raw_recall(**kwargs):
                return []

            async def fake_semantic(chunks, **kwargs):
                # semantic 扩展了一条规则
                return (
                    [ChunkCandidates(chunk_id=chunks[0].chunk_id, candidate_rule_ids=["R999"])]
                    if chunks else []
                ), {}

            async def fake_filter(raw_candidates, **kwargs):
                # filter 返回空，模拟过滤掉所有候选
                return []

            with patch("src.moderation.workflow.run_stage1_raw_recall", side_effect=fake_raw_recall), \
                 patch("src.moderation.workflow.run_stage1_1_semantic_prescreen", side_effect=fake_semantic), \
                 patch("src.moderation.workflow.run_stage1_filter_only", side_effect=fake_filter):

                asyncio.get_event_loop().run_until_complete(
                    wf_mod.run_stage1_with_semantic_prescreen(state)
                )

            # filter 返回空，最终候选必须为空（semantic 没有绕过 filter）
            assert state.stage1_candidates == [], \
                "semantic 候选绕过了 unified filter，违反工程约束"
        finally:
            cfg_mod.ENABLE_SEMANTIC_PRESCREEN = False
