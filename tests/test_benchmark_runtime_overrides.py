import os
import unittest
from unittest.mock import patch

from benchmark.runners.run_sdk import apply_benchmark_runtime_overrides


class TestBenchmarkRuntimeOverrides(unittest.TestCase):
    def test_stable_mode_applies_default_overrides(self):
        with patch.dict(os.environ, {"BENCHMARK_STABLE_MODE": "true"}, clear=True):
            overrides = apply_benchmark_runtime_overrides()

        self.assertEqual(overrides["MAX_CONCURRENT_CALLS"], "4")
        self.assertEqual(overrides["STAGE2_MAX_CONCURRENT_CALLS"], "1")
        self.assertEqual(overrides["FILTER_MODEL_ENABLE_THINKING"], "false")
        self.assertEqual(overrides["JUDGE_MODEL_ENABLE_THINKING"], "true")
        self.assertEqual(overrides["FULLDOC_MODEL_ENABLE_THINKING"], "true")
        self.assertEqual(overrides["SUGGESTION_USE_LLM_RENDERER"], "false")

    def test_explicit_benchmark_values_override_stable_defaults(self):
        with patch.dict(
            os.environ,
            {
                "BENCHMARK_STABLE_MODE": "true",
                "BENCHMARK_MAX_CONCURRENT_CALLS": "2",
                "BENCHMARK_JUDGE_MODEL_ENABLE_THINKING": "false",
                "BENCHMARK_FULLDOC_MODEL_TIMEOUT_SECONDS": "120",
            },
            clear=True,
        ):
            overrides = apply_benchmark_runtime_overrides()

        self.assertEqual(overrides["MAX_CONCURRENT_CALLS"], "2")
        self.assertEqual(overrides["JUDGE_MODEL_ENABLE_THINKING"], "false")
        self.assertEqual(overrides["FULLDOC_MODEL_TIMEOUT_SECONDS"], "120")

    def test_non_stable_mode_only_applies_explicit_values(self):
        with patch.dict(
            os.environ,
            {"BENCHMARK_MAX_CONCURRENT_CALLS": "1"},
            clear=True,
        ):
            overrides = apply_benchmark_runtime_overrides()

        self.assertEqual(overrides, {"MAX_CONCURRENT_CALLS": "1"})
