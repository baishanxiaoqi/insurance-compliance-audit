import importlib
import warnings
from unittest.mock import patch

from src.moderation import config as config_mod


def test_default_pytest_env_uses_test_profile():
    assert config_mod.APP_ENV == "test"


def test_missing_yaml_config_falls_back_to_env_defaults():
    with patch.dict(
        "os.environ",
        {
            "APP_ENV": "missing",
            "LLM_MODEL": "env-model",
            "LLM_API_BASE": "https://example.com/v1",
        },
        clear=False,
    ):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            reloaded = importlib.reload(config_mod)

        assert reloaded.APP_ENV == "missing"
        assert reloaded.LLM_MODEL == "env-model"
        assert reloaded.LLM_API_BASE == "https://example.com/v1"
        assert any("Config file not found" in str(item.message) for item in caught)

    with patch.dict("os.environ", {"APP_ENV": "test"}, clear=False):
        importlib.reload(config_mod)
