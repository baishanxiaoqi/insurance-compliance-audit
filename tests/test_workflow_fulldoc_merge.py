import asyncio
import unittest
from unittest.mock import patch

from agno.workflow import StepInput

import src.moderation.workflow as wf_mod
from src.moderation.schemas import (
    AuditResponse,
    DocumentState,
    JudgmentResult,
    WorkflowState,
)


class TestWorkflowFullDocMerge(unittest.TestCase):
    def _base_state(self):
        doc = DocumentState(
            doc_id="DOC_FD",
            original_text="原文",
            working_text="原文",
            normalized_text="原文",
            chunks=[],
            span_pool={},
        )
        main_judgment = JudgmentResult(
            rule_id="KB001",
            chunk_id="chunk_000",
            verdict="violation",
            reasoning_cot="主流程违规判定。",
            evidence_span_ids=[],
            evidence_texts=[],
            reason_codes=[],
        )
        fulldoc_judgment = JudgmentResult(
            rule_id="FULLDOC_R001",
            chunk_id="__fulldoc__",
            verdict="violation",
            reasoning_cot="全文审核判定存在未注明来源的数据引用。",
            evidence_span_ids=[],
            evidence_texts=[],
            reason_codes=[],
        )
        return WorkflowState(
            document=doc,
            rule_cards={},
            stage2_judgments=[main_judgment],
            stage26_full_document_judgments=[fulldoc_judgment],
        )

    def test_stage27_executor_merges_main_and_fulldoc_judgments(self):
        state = self._base_state()
        token = wf_mod._current_state.set(state)
        meta_token = wf_mod._current_meta.set({"start_time": 0})
        captured = {}

        async def fake_run_stage2_7_suggestion(judgments, rule_cards):
            captured["count"] = len(judgments)
            return {}

        try:
            with patch(
                "src.moderation.workflow.run_stage2_7_suggestion",
                side_effect=fake_run_stage2_7_suggestion,
            ):
                asyncio.run(wf_mod._stage27_executor(StepInput(input="")))
        finally:
            wf_mod._current_state.reset(token)
            wf_mod._current_meta.reset(meta_token)

        self.assertEqual(captured["count"], 2)

    def test_stage3_executor_merges_main_and_fulldoc_judgments(self):
        state = self._base_state()
        token = wf_mod._current_state.set(state)
        meta_token = wf_mod._current_meta.set({"start_time": 0})
        captured = {}

        def fake_run_stage3(judgments, document, rule_cards, suggestions, processing_time):
            captured["count"] = len(judgments)
            return AuditResponse(
                doc_id=document.doc_id,
                total_violations=2,
                violations=[],
                processing_time_seconds=processing_time,
            )

        try:
            with patch("src.moderation.workflow.run_stage3", side_effect=fake_run_stage3):
                asyncio.run(wf_mod._stage3_executor(StepInput(input="")))
        finally:
            wf_mod._current_state.reset(token)
            wf_mod._current_meta.reset(meta_token)

        self.assertEqual(captured["count"], 2)


class TestWorkflowFullDocParallel(unittest.IsolatedAsyncioTestCase):
    async def test_stage0_executor_starts_fulldoc_task_and_stage26_reuses_it(self):
        state = WorkflowState(rule_cards={})
        token = wf_mod._current_state.set(state)
        meta_token = wf_mod._current_meta.set({"start_time": 0, "doc_id": "DOC_FD"})

        fulldoc_judgment = JudgmentResult(
            rule_id="FULLDOC_R001",
            chunk_id="__fulldoc__",
            verdict="compliant",
            reasoning_cot="全文审核完成。",
            evidence_span_ids=[],
            evidence_texts=[],
            reason_codes=[],
        )
        call_count = {"count": 0}

        async def fake_run_stage2_6(document, semaphore=None):
            call_count["count"] += 1
            await asyncio.sleep(0)
            return [fulldoc_judgment]

        try:
            with patch(
                "src.moderation.workflow.run_stage2_6",
                side_effect=fake_run_stage2_6,
            ):
                await wf_mod._stage0_executor(StepInput(input="测试文本，引用了第三方数据。"))
                task = wf_mod._get_meta().get(wf_mod._FULDOC_TASK_KEY)
                self.assertIsInstance(task, asyncio.Task)
                await wf_mod._stage26_executor(StepInput(input=""))
        finally:
            wf_mod._current_state.reset(token)
            wf_mod._current_meta.reset(meta_token)

        self.assertEqual(call_count["count"], 1)
        self.assertEqual(len(state.stage26_full_document_judgments), 1)


if __name__ == "__main__":
    unittest.main()
