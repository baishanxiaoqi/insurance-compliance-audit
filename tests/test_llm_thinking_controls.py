import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from src.moderation import config
from src.moderation.llm_agent import create_model, safe_arun
from src.moderation.schemas import Chunk, FilterResult, RuleCard, Span
from src.moderation.stages.stage1_recall_filter import (
    _compress_fallback_candidates,
    _filter_single_chunk,
    build_filter_agent,
)


class _DummyRetriever:
    def recall(self, _text: str, top_k: int = 20):
        return ["KB_TEST"][:top_k]


class _MultiRetriever:
    def recall(self, _text: str, top_k: int = 20):
        return ["KB_A", "KB_B", "KB_C"][:top_k]


class _DummyRunOutput:
    def __init__(self, content, *, messages=None, reasoning_content=None, metrics=None):
        self.content = content
        self.messages = messages or []
        self.reasoning_content = reasoning_content
        self.metrics = metrics


class _DummyMessage:
    def __init__(self, content: str, role: str = "assistant", reasoning_content: str | None = None):
        self.content = content
        self.role = role
        self.reasoning_content = reasoning_content

    def get_content_string(self) -> str:
        return self.content


class TestLlmThinkingControls(unittest.TestCase):
    def test_provider_and_preset_registry(self):
        siliconflow = config.get_provider_profile("siliconflow")
        glm = config.get_provider_profile("glm")
        preset = config.get_model_preset("qwen35_27b_siliconflow")

        self.assertEqual(siliconflow.api_base, "https://api.siliconflow.cn/v1")
        self.assertEqual(glm.api_base, "https://open.bigmodel.cn/api/paas/v4")
        self.assertTrue(bool(glm.api_key))
        self.assertIsNotNone(preset)
        self.assertEqual(preset.provider, "siliconflow")
        self.assertEqual(preset.model, "Qwen/Qwen3.5-27B")

    def test_create_model_supports_thinking_override(self):
        thinking_model = create_model(thinking_enabled=True)
        plain_model = create_model(thinking_enabled=False)

        self.assertEqual(thinking_model.extra_body, {"enable_thinking": True})
        self.assertEqual(plain_model.extra_body, {"enable_thinking": False})

    def test_create_model_supports_thinking_budget(self):
        thinking_model = create_model(thinking_enabled=True, thinking_budget=64)

        self.assertEqual(
            thinking_model.extra_body,
            {"enable_thinking": True, "thinking_budget": 64},
        )

    def test_create_model_supports_task_specific_profile(self):
        profile = config.ModelProfile(
            name="judge",
            api_base="https://example.com/v1",
            api_key="sk-test",
            model="judge-model",
            thinking_enabled=True,
            thinking_budget=96,
            max_tokens=512,
            timeout_seconds=30.0,
            max_retries=2,
        )

        model = create_model(profile=profile)

        self.assertEqual(model.id, "judge-model")
        self.assertEqual(model.base_url, "https://example.com/v1")
        self.assertEqual(model.api_key, "sk-test")
        self.assertEqual(model.max_tokens, 512)
        self.assertEqual(model.extra_body, {"enable_thinking": True, "thinking_budget": 96})

    def test_global_profile_uses_selected_provider_preset(self):
        self.assertEqual(config.GLOBAL_MODEL_PROFILE.provider, "siliconflow")
        self.assertEqual(config.GLOBAL_MODEL_PROFILE.model, "Qwen/Qwen3.5-27B")
        self.assertEqual(
            config.GLOBAL_MODEL_PROFILE.model_preset,
            "qwen35_27b_siliconflow",
        )

    def test_suggestion_profile_targets_glm_with_own_provider_credentials(self):
        self.assertEqual(config.SUGGESTION_MODEL_PROFILE.provider, "glm")
        self.assertEqual(config.SUGGESTION_MODEL_PROFILE.model, "GLM-4-Air")
        self.assertTrue(config.is_model_profile_configured(config.SUGGESTION_MODEL_PROFILE))
        self.assertEqual(
            config.SUGGESTION_MODEL_PROFILE.api_key,
            config.get_provider_profile("glm").api_key,
        )

    def test_filter_agent_uses_stage1_specific_limits(self):
        agent = build_filter_agent()

        self.assertEqual(agent.model.max_tokens, config.STAGE1_FILTER_MAX_TOKENS)
        expected_extra_body = (
            {"enable_thinking": True}
            if config.STAGE1_FILTER_ENABLE_THINKING
            else {"enable_thinking": False}
        )
        self.assertEqual(agent.model.extra_body, expected_extra_body)


class TestStage1FilterTimeoutControls(unittest.IsolatedAsyncioTestCase):
    async def test_filter_chunk_uses_stage1_timeout_and_retries(self):
        chunk = Chunk(
            chunk_id="chunk_001",
            chunk_text="锁定收益",
            spans=[
                Span(
                    span_id="S_chunk_001_00",
                    span_text="锁定收益",
                    start_index=0,
                    end_index=4,
                    chunk_id="chunk_001",
                )
            ],
        )
        rule_card = RuleCard(
            rule_id="KB_TEST",
            rule_name="测试规则",
            risk_level="high",
            violation_definition="测试",
            keywords=["锁定"],
            violation_terms=["锁定"],
        )
        semaphore = asyncio.Semaphore(1)
        safe_arun_mock = AsyncMock(return_value=FilterResult(relevant_rule_ids=["KB_TEST"]))

        with patch(
            "src.moderation.stages.stage1_recall_filter.safe_arun",
            safe_arun_mock,
        ):
            result = await _filter_single_chunk(
                chunk=chunk,
                retriever=_DummyRetriever(),
                filter_agent=object(),
                rule_cards={"KB_TEST": rule_card},
                top_k_recall=20,
                top_k_filter=3,
                semaphore=semaphore,
            )

        self.assertIsNotNone(result)
        self.assertEqual(result.candidate_rule_ids, ["KB_TEST"])
        _, kwargs = safe_arun_mock.call_args
        self.assertEqual(kwargs["timeout_seconds"], config.STAGE1_FILTER_TIMEOUT_SECONDS)
        self.assertEqual(kwargs["max_retries"], config.STAGE1_FILTER_MAX_RETRIES)

    async def test_filter_chunk_fails_open_with_full_candidates(self):
        chunk = Chunk(
            chunk_id="chunk_001",
            chunk_text="锁定收益",
            spans=[
                Span(
                    span_id="S_chunk_001_00",
                    span_text="锁定收益",
                    start_index=0,
                    end_index=4,
                    chunk_id="chunk_001",
                )
            ],
        )
        rule_cards = {
            rid: RuleCard(
                rule_id=rid,
                rule_name=f"规则-{rid}",
                risk_level="high",
                violation_definition="测试",
                keywords=["锁定"],
                violation_terms=["锁定"],
            )
            for rid in ["KB_A", "KB_B", "KB_C"]
        }
        semaphore = asyncio.Semaphore(1)

        with patch(
            "src.moderation.stages.stage1_recall_filter.safe_arun",
            AsyncMock(side_effect=ValueError("parse failed")),
        ):
            result = await _filter_single_chunk(
                chunk=chunk,
                retriever=_MultiRetriever(),
                filter_agent=object(),
                rule_cards=rule_cards,
                top_k_recall=20,
                top_k_filter=3,
                semaphore=semaphore,
            )

        self.assertIsNotNone(result)
        self.assertEqual(result.candidate_rule_ids, ["KB_A", "KB_B", "KB_C"])

    def test_compress_fallback_candidates_keeps_head_and_reduces_duplicates(self):
        rule_cards = {
            "KB_A": RuleCard(
                rule_id="KB_A",
                rule_name="规则-A",
                risk_level="high",
                violation_definition="测试",
                keywords=["收益"],
                violation_terms=["收益"],
                audit_point_id="1.1.1",
                primary_category="financial_product_confusion",
                secondary_category="investment_terminology_usage",
                category_group="financial_confusion",
            ),
            "KB_B": RuleCard(
                rule_id="KB_B",
                rule_name="规则-B",
                risk_level="high",
                violation_definition="测试",
                keywords=["收益"],
                violation_terms=["收益"],
                audit_point_id="1.1.1",
                primary_category="financial_product_confusion",
                secondary_category="investment_terminology_usage",
                category_group="financial_confusion",
            ),
            "KB_C": RuleCard(
                rule_id="KB_C",
                rule_name="规则-C",
                risk_level="high",
                violation_definition="测试",
                keywords=["收益"],
                violation_terms=["收益"],
                audit_point_id="1.2.1",
                primary_category="guaranteed_return",
                secondary_category="stable_return_implication",
                category_group="guaranteed_return",
            ),
            "KB_D": RuleCard(
                rule_id="KB_D",
                rule_name="规则-D",
                risk_level="high",
                violation_definition="测试",
                keywords=["收益"],
                violation_terms=["收益"],
                audit_point_id="6.5.2",
                primary_category="gifts_or_extra_benefits",
                secondary_category="warm_service",
                category_group="gifts_benefits",
            ),
        }
        candidate_ids = ["KB_A", "KB_B", "KB_C", "KB_D", "KB_B", "KB_C"]

        compressed = _compress_fallback_candidates(
            candidate_ids,
            rule_cards,
            keep_head=2,
            max_rules=3,
        )

        self.assertEqual(compressed[:2], ["KB_A", "KB_B"])
        self.assertEqual(len(compressed), 3)
        self.assertIn("KB_C", compressed)

    async def test_safe_arun_retries_after_timeout(self):
        agent = Mock()
        agent.name = "timeout_test_agent"
        agent.arun = AsyncMock(
            side_effect=[
                asyncio.TimeoutError(),
                _DummyRunOutput(FilterResult(relevant_rule_ids=["KB_TEST"])),
            ]
        )

        with patch("src.moderation.llm_agent.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await safe_arun(
                agent,
                "prompt",
                max_retries=1,
                timeout_seconds=1.0,
            )

        self.assertEqual(result.relevant_rule_ids, ["KB_TEST"])
        self.assertEqual(agent.arun.await_count, 2)
        sleep_mock.assert_awaited()

    async def test_safe_arun_recovers_json_from_assistant_message(self):
        agent = Mock()
        agent.name = "recover_json_agent"
        agent.output_schema = FilterResult
        agent.model = SimpleNamespace(max_tokens=128)
        agent.arun = AsyncMock(
            return_value=_DummyRunOutput(
                "",
                messages=[_DummyMessage("```json\n{\"relevant_rule_ids\": [\"KB_TEST\"]}\n```")],
            )
        )

        result = await safe_arun(agent, "prompt", max_retries=0, timeout_seconds=1.0)

        self.assertEqual(result.relevant_rule_ids, ["KB_TEST"])

    async def test_safe_arun_expands_budget_when_reasoning_consumes_output(self):
        agent = Mock()
        agent.name = "budget_retry_agent"
        agent.output_schema = FilterResult
        agent.model = SimpleNamespace(max_tokens=128, extra_body={"enable_thinking": True})
        first = _DummyRunOutput(
            "",
            reasoning_content="thinking",
            metrics=SimpleNamespace(output_tokens=128),
        )
        second = _DummyRunOutput(FilterResult(relevant_rule_ids=["KB_TEST"]))
        agent.arun = AsyncMock(side_effect=[first, second])

        with patch("src.moderation.llm_agent.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await safe_arun(agent, "prompt", max_retries=1, timeout_seconds=1.0)

        self.assertEqual(result.relevant_rule_ids, ["KB_TEST"])
        self.assertEqual(agent.model.max_tokens, 384)
        self.assertEqual(agent.arun.await_count, 2)
        sleep_mock.assert_awaited()

    async def test_safe_arun_can_disable_thinking_as_final_structured_rescue(self):
        agent = Mock()
        agent.name = "thinking_rescue_agent"
        agent.output_schema = FilterResult
        agent.model = SimpleNamespace(max_tokens=3072, extra_body={"enable_thinking": True, "thinking_budget": 32})
        first = _DummyRunOutput(
            "",
            reasoning_content="thinking",
            metrics=SimpleNamespace(output_tokens=3072),
        )
        second = _DummyRunOutput(
            "",
            reasoning_content="thinking",
            metrics=SimpleNamespace(output_tokens=9216),
        )
        third = _DummyRunOutput(
            "",
            reasoning_content="thinking",
            metrics=SimpleNamespace(output_tokens=10000),
        )
        fourth = _DummyRunOutput(FilterResult(relevant_rule_ids=["KB_TEST"]))
        agent.arun = AsyncMock(side_effect=[first, second, third, fourth])

        with patch("src.moderation.llm_agent.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await safe_arun(agent, "prompt", max_retries=3, timeout_seconds=1.0)

        self.assertEqual(result.relevant_rule_ids, ["KB_TEST"])
        self.assertEqual(agent.model.extra_body, {"enable_thinking": False})
        self.assertEqual(agent.arun.await_count, 4)
        sleep_mock.assert_awaited()
