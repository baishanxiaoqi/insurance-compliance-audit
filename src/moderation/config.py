"""
全局配置模块
从环境变量 / .env 文件中读取配置项
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None


@dataclass(frozen=True)
class ProviderProfile:
    """调用方 / 供应商配置。"""

    name: str
    api_base: str
    api_key: str
    default_model: str


@dataclass(frozen=True)
class ModelPreset:
    """预置模型档案。"""

    name: str
    provider: str
    model: str


@dataclass(frozen=True)
class ModelProfile:
    """按任务拆分的模型配置。"""

    name: str
    api_base: str
    api_key: str
    model: str
    thinking_enabled: bool
    thinking_budget: int | None
    max_tokens: int
    timeout_seconds: float
    max_retries: int
    provider: str = "default"
    model_preset: str | None = None


# 加载 .env 文件（向上查找到项目根目录）
_PKG_DIR = Path(__file__).parent
_PROJECT_ROOT = _PKG_DIR.parent.parent
_env_path = _PROJECT_ROOT / ".env"
load_dotenv(_env_path)

# ==================== LLM 基础兼容配置 ====================
# 保留 LLM_* 作为向后兼容兜底；新配置优先走 provider / preset。
LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "sk-xxx")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", os.getenv("LLM_CALLER", "default")).strip().lower()
LLM_MODEL_PRESET: str = os.getenv("LLM_MODEL_PRESET", "").strip().lower()
LLM_ENABLE_THINKING: bool = _to_bool(os.getenv("LLM_ENABLE_THINKING"), default=False)

# ==================== 调用方 / 供应商档案 ====================
OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_DEFAULT_MODEL: str = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini")

DASHSCOPE_API_BASE: str = os.getenv(
    "DASHSCOPE_API_BASE",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_DEFAULT_MODEL: str = os.getenv("DASHSCOPE_DEFAULT_MODEL", "qwen3.5-27b")

SILICONFLOW_API_BASE: str = os.getenv("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1")
SILICONFLOW_API_KEY: str = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_DEFAULT_MODEL: str = os.getenv(
    "SILICONFLOW_DEFAULT_MODEL",
    "Qwen/Qwen3.5-27B",
)

GLM_API_BASE: str = os.getenv("GLM_API_BASE", "https://open.bigmodel.cn/api/paas/v4")
GLM_API_KEY: str = os.getenv("GLM_API_KEY", "")
GLM_DEFAULT_MODEL: str = os.getenv("GLM_DEFAULT_MODEL", "glm-4.5-flash")

_PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    "default": ProviderProfile("default", LLM_API_BASE, LLM_API_KEY, LLM_MODEL),
    "openai": ProviderProfile(
        "openai",
        OPENAI_API_BASE,
        OPENAI_API_KEY,
        OPENAI_DEFAULT_MODEL,
    ),
    "dashscope": ProviderProfile(
        "dashscope",
        DASHSCOPE_API_BASE,
        DASHSCOPE_API_KEY,
        DASHSCOPE_DEFAULT_MODEL,
    ),
    "siliconflow": ProviderProfile(
        "siliconflow",
        SILICONFLOW_API_BASE,
        SILICONFLOW_API_KEY,
        SILICONFLOW_DEFAULT_MODEL,
    ),
    "glm": ProviderProfile(
        "glm",
        GLM_API_BASE,
        GLM_API_KEY,
        GLM_DEFAULT_MODEL,
    ),
}

_MODEL_PRESETS: dict[str, ModelPreset] = {
    "openai_default": ModelPreset("openai_default", "openai", OPENAI_DEFAULT_MODEL),
    "qwen35_27b_dashscope": ModelPreset(
        "qwen35_27b_dashscope",
        "dashscope",
        DASHSCOPE_DEFAULT_MODEL,
    ),
    "qwen3_dashscope": ModelPreset(
        "qwen3_dashscope",
        "dashscope",
        DASHSCOPE_DEFAULT_MODEL,
    ),
    "qwen35_27b_siliconflow": ModelPreset(
        "qwen35_27b_siliconflow",
        "siliconflow",
        SILICONFLOW_DEFAULT_MODEL,
    ),
    "qwen3_siliconflow": ModelPreset(
        "qwen3_siliconflow",
        "siliconflow",
        SILICONFLOW_DEFAULT_MODEL,
    ),
    "glm_default": ModelPreset("glm_default", "glm", GLM_DEFAULT_MODEL),
    "glm4_default": ModelPreset("glm4_default", "glm", GLM_DEFAULT_MODEL),
}


def get_provider_profile(name: str | None) -> ProviderProfile:
    normalized = (name or "default").strip().lower()
    return _PROVIDER_PROFILES.get(normalized, _PROVIDER_PROFILES["default"])


def get_model_preset(name: str | None) -> ModelPreset | None:
    normalized = (name or "").strip().lower()
    if not normalized:
        return None
    return _MODEL_PRESETS.get(normalized)


def is_model_profile_configured(profile: ModelProfile) -> bool:
    return bool(profile.api_base and profile.api_key and profile.model)


# ==================== 按阶段模型调用控制 ====================
STAGE1_FILTER_ENABLE_THINKING: bool = _to_bool(
    os.getenv("STAGE1_FILTER_ENABLE_THINKING"),
    default=False,
)
STAGE1_FILTER_MAX_TOKENS: int = int(os.getenv("STAGE1_FILTER_MAX_TOKENS", "10000"))
STAGE1_FILTER_TIMEOUT_SECONDS: float = float(
    os.getenv("STAGE1_FILTER_TIMEOUT_SECONDS", "15")
)
STAGE1_FILTER_MAX_RETRIES: int = int(os.getenv("STAGE1_FILTER_MAX_RETRIES", "1"))

STAGE2_MAX_CONCURRENT_CALLS: int = int(os.getenv("STAGE2_MAX_CONCURRENT_CALLS", "4"))
STAGE2_MAX_TOKENS: int = int(os.getenv("STAGE2_MAX_TOKENS", "10000"))
STAGE2_TIMEOUT_SECONDS: float = float(os.getenv("STAGE2_TIMEOUT_SECONDS", "90"))
STAGE2_MAX_RETRIES: int = int(os.getenv("STAGE2_MAX_RETRIES", "1"))
STAGE2_THINKING_BUDGET: int = int(os.getenv("STAGE2_THINKING_BUDGET", "128"))

SUGGESTION_USE_LLM_RENDERER: bool = _to_bool(
    os.getenv("SUGGESTION_USE_LLM_RENDERER"),
    default=False,
)
SUGGESTION_MODEL_MAX_TOKENS: int = int(os.getenv("SUGGESTION_MODEL_MAX_TOKENS", "10000"))
SUGGESTION_MODEL_TIMEOUT_SECONDS: float = float(
    os.getenv("SUGGESTION_MODEL_TIMEOUT_SECONDS", "45")
)
SUGGESTION_MODEL_MAX_RETRIES: int = int(os.getenv("SUGGESTION_MODEL_MAX_RETRIES", "1"))
SUGGESTION_MODEL_ENABLE_THINKING: bool = _to_bool(
    os.getenv("SUGGESTION_MODEL_ENABLE_THINKING"),
    default=False,
)
_suggestion_budget_raw = os.getenv("SUGGESTION_MODEL_THINKING_BUDGET")
SUGGESTION_MODEL_THINKING_BUDGET: int | None = (
    int(_suggestion_budget_raw) if _suggestion_budget_raw else None
)

# ==================== 文本处理参数 ====================
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "300"))
CHUNK_MIN_SIZE: int = int(os.getenv("CHUNK_MIN_SIZE", "80"))

# ==================== 规则召回参数 ====================
TOP_K_RULES: int = int(os.getenv("TOP_K_RULES", "20"))
TOP_K_FILTER: int = int(os.getenv("TOP_K_FILTER", "3"))

# ==================== 并发控制 ====================
MAX_CONCURRENT_CALLS: int = int(os.getenv("MAX_CONCURRENT_CALLS", "3"))

# ==================== Benchmark 稳定性运行模式 ====================
BENCHMARK_STABLE_MODE: bool = _to_bool(
    os.getenv("BENCHMARK_STABLE_MODE"),
    default=False,
)

# ==================== 数据路径 ====================
BASE_DIR: Path = _PROJECT_ROOT
RULE_CARDS_PATH: str = os.getenv("RULE_CARDS_PATH", str(BASE_DIR / "data" / "rule_cards.json"))
AUDIT_POINT_WORKBOOK_PATH: str = os.getenv(
    "AUDIT_POINT_WORKBOOK_PATH",
    str(BASE_DIR / "plan" / "smoke数据构造种子集.xlsx"),
)

# ==================== API 服务配置 ====================
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# ==================== 审计轨迹日志 ====================
ENABLE_TRACE_LOG: bool = _to_bool(os.getenv("ENABLE_TRACE_LOG"), default=True)


def _build_model_profile(
    profile_name: str,
    prefix: str,
    *,
    default_thinking_enabled: bool,
    default_thinking_budget: int | None,
    default_max_tokens: int,
    default_timeout_seconds: float,
    default_max_retries: int,
) -> ModelProfile:
    """构建按任务拆分的模型配置，未单独配置时回落到全局 provider / preset。"""

    explicit_provider = _first_env(f"{prefix}_PROVIDER", f"{prefix}_CALLER")
    explicit_preset_name = _first_env(f"{prefix}_MODEL_PRESET", f"{prefix}_PRESET")
    explicit_api_base = _first_env(f"{prefix}_API_BASE")
    explicit_api_key = _first_env(f"{prefix}_API_KEY")
    explicit_model = _first_env(f"{prefix}_MODEL")

    inherited_provider = None if prefix == "LLM" else LLM_PROVIDER
    inherited_preset_name = None if prefix == "LLM" else LLM_MODEL_PRESET

    preset_name = explicit_preset_name or inherited_preset_name or ""
    preset = get_model_preset(preset_name)

    provider_name = explicit_provider or inherited_provider or (preset.provider if preset else "default")
    provider = get_provider_profile(provider_name)

    api_base = explicit_api_base or provider.api_base or LLM_API_BASE
    api_key = explicit_api_key or provider.api_key or ""
    model = explicit_model or (preset.model if preset else "") or provider.default_model or LLM_MODEL

    thinking_enabled = _to_bool(
        os.getenv(f"{prefix}_ENABLE_THINKING"),
        default=default_thinking_enabled,
    )

    thinking_budget_raw = os.getenv(f"{prefix}_THINKING_BUDGET")
    if thinking_budget_raw is not None and thinking_budget_raw.strip():
        thinking_budget = int(thinking_budget_raw)
    else:
        thinking_budget = default_thinking_budget

    max_tokens = int(os.getenv(f"{prefix}_MAX_TOKENS", str(default_max_tokens)))
    timeout_seconds = float(
        os.getenv(f"{prefix}_TIMEOUT_SECONDS", str(default_timeout_seconds))
    )
    max_retries = int(os.getenv(f"{prefix}_MAX_RETRIES", str(default_max_retries)))

    return ModelProfile(
        name=profile_name,
        api_base=api_base,
        api_key=api_key,
        model=model,
        thinking_enabled=thinking_enabled,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        provider=provider.name,
        model_preset=preset.name if preset else None,
    )


GLOBAL_MODEL_PROFILE = _build_model_profile(
    "global",
    "LLM",
    default_thinking_enabled=LLM_ENABLE_THINKING,
    default_thinking_budget=None,
    default_max_tokens=10000,
    default_timeout_seconds=60.0,
    default_max_retries=1,
)

FILTER_MODEL_PROFILE = _build_model_profile(
    "filter",
    "FILTER_MODEL",
    default_thinking_enabled=STAGE1_FILTER_ENABLE_THINKING,
    default_thinking_budget=None,
    default_max_tokens=STAGE1_FILTER_MAX_TOKENS,
    default_timeout_seconds=STAGE1_FILTER_TIMEOUT_SECONDS,
    default_max_retries=STAGE1_FILTER_MAX_RETRIES,
)

JUDGE_MODEL_PROFILE = _build_model_profile(
    "judge",
    "JUDGE_MODEL",
    default_thinking_enabled=LLM_ENABLE_THINKING,
    default_thinking_budget=STAGE2_THINKING_BUDGET,
    default_max_tokens=STAGE2_MAX_TOKENS,
    default_timeout_seconds=STAGE2_TIMEOUT_SECONDS,
    default_max_retries=STAGE2_MAX_RETRIES,
)

SUGGESTION_MODEL_PROFILE = _build_model_profile(
    "suggestion",
    "SUGGESTION_MODEL",
    default_thinking_enabled=SUGGESTION_MODEL_ENABLE_THINKING,
    default_thinking_budget=SUGGESTION_MODEL_THINKING_BUDGET,
    default_max_tokens=SUGGESTION_MODEL_MAX_TOKENS,
    default_timeout_seconds=SUGGESTION_MODEL_TIMEOUT_SECONDS,
    default_max_retries=SUGGESTION_MODEL_MAX_RETRIES,
)
