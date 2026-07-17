"""
全局配置模块
从 configs/config.{APP_ENV}.yaml 读取配置项。
敏感值（API Key）可通过同名环境变量覆盖，例如：
  export OPENAI_API_KEY=sk-xxx
环境选择：APP_ENV=dev|test|prod（默认 dev）
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
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


# ==================== 加载 YAML 配置文件 ====================
_PKG_DIR = Path(__file__).parent
_PROJECT_ROOT = _PKG_DIR.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_APP_ENV: str = os.getenv("APP_ENV", "dev").strip().lower()
APP_ENV: str = _APP_ENV
_CONFIG_PATH = _PROJECT_ROOT / "configs" / f"config.{_APP_ENV}.yaml"

if _CONFIG_PATH.exists():
    with _CONFIG_PATH.open(encoding="utf-8") as _f:
        _cfg: dict[str, Any] = yaml.safe_load(_f) or {}
else:
    warnings.warn(
        (
            f"Config file not found: {_CONFIG_PATH}. "
            "Fallback to environment variables and built-in defaults."
        ),
        RuntimeWarning,
    )
    _cfg = {}


def _c(*keys: str, default: Any = None) -> Any:
    """从 YAML 嵌套结构中安全取值。"""
    node = _cfg
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
        if node is None:
            return default
    return node


def _env_or(env_name: str, yaml_value: Any) -> str:
    """环境变量优先；YAML 值作为回退（用于 API Key 等敏感配置）。"""
    env_val = os.getenv(env_name, "").strip()
    return env_val if env_val else str(yaml_value or "")

# ==================== LLM 基础兼容配置 ====================
LLM_API_BASE: str = _env_or("LLM_API_BASE", _c("llm", "api_base", default="https://api.openai.com/v1"))
LLM_API_KEY: str = _env_or("LLM_API_KEY", _c("llm", "api_key", default=""))
LLM_MODEL: str = _env_or("LLM_MODEL", _c("llm", "model", default="gpt-4o-mini"))
LLM_PROVIDER: str = (_env_or("LLM_PROVIDER", _c("llm", "provider", default="default")) or
                     _env_or("LLM_CALLER", "default")).strip().lower()
LLM_MODEL_PRESET: str = _env_or("LLM_MODEL_PRESET", _c("llm", "model_preset", default="")).strip().lower()
LLM_ENABLE_THINKING: bool = _to_bool(
    os.getenv("LLM_ENABLE_THINKING"),
    default=bool(_c("llm", "enable_thinking", default=False)),
)

# ==================== 供应商档案 ====================
OPENAI_API_BASE: str = _env_or("OPENAI_API_BASE", _c("providers", "openai", "api_base", default="https://api.openai.com/v1"))
OPENAI_API_KEY: str = _env_or("OPENAI_API_KEY", _c("providers", "openai", "api_key", default=""))
OPENAI_DEFAULT_MODEL: str = _env_or("OPENAI_DEFAULT_MODEL", _c("providers", "openai", "default_model", default="gpt-4o-mini"))

DASHSCOPE_API_BASE: str = _env_or(
    "DASHSCOPE_API_BASE",
    _c("providers", "dashscope", "api_base", default="https://dashscope.aliyuncs.com/compatible-mode/v1"),
)
DASHSCOPE_API_KEY: str = _env_or("DASHSCOPE_API_KEY", _c("providers", "dashscope", "api_key", default=""))
DASHSCOPE_DEFAULT_MODEL: str = _env_or("DASHSCOPE_DEFAULT_MODEL", _c("providers", "dashscope", "default_model", default="qwen3.5-27b"))

SILICONFLOW_API_BASE: str = _env_or("SILICONFLOW_API_BASE", _c("providers", "siliconflow", "api_base", default="https://api.siliconflow.cn/v1"))
SILICONFLOW_API_KEY: str = _env_or("SILICONFLOW_API_KEY", _c("providers", "siliconflow", "api_key", default=""))
SILICONFLOW_DEFAULT_MODEL: str = _env_or(
    "SILICONFLOW_DEFAULT_MODEL",
    _c("providers", "siliconflow", "default_model", default="Qwen/Qwen3.5-27B"),
)

GLM_API_BASE: str = _env_or("GLM_API_BASE", _c("providers", "glm", "api_base", default="https://open.bigmodel.cn/api/paas/v4"))
GLM_API_KEY: str = _env_or("GLM_API_KEY", _c("providers", "glm", "api_key", default=""))
GLM_DEFAULT_MODEL: str = _env_or("GLM_DEFAULT_MODEL", _c("providers", "glm", "default_model", default="glm-4.5-flash"))

_PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    "default": ProviderProfile("default", LLM_API_BASE, LLM_API_KEY, LLM_MODEL),
    "openai": ProviderProfile("openai", OPENAI_API_BASE, OPENAI_API_KEY, OPENAI_DEFAULT_MODEL),
    "dashscope": ProviderProfile("dashscope", DASHSCOPE_API_BASE, DASHSCOPE_API_KEY, DASHSCOPE_DEFAULT_MODEL),
    "siliconflow": ProviderProfile("siliconflow", SILICONFLOW_API_BASE, SILICONFLOW_API_KEY, SILICONFLOW_DEFAULT_MODEL),
    "glm": ProviderProfile("glm", GLM_API_BASE, GLM_API_KEY, GLM_DEFAULT_MODEL),
}

_MODEL_PRESETS: dict[str, ModelPreset] = {
    "openai_default": ModelPreset("openai_default", "openai", OPENAI_DEFAULT_MODEL),
    "qwen35_27b_dashscope": ModelPreset("qwen35_27b_dashscope", "dashscope", DASHSCOPE_DEFAULT_MODEL),
    "qwen3_dashscope": ModelPreset("qwen3_dashscope", "dashscope", DASHSCOPE_DEFAULT_MODEL),
    "qwen35_27b_siliconflow": ModelPreset("qwen35_27b_siliconflow", "siliconflow", SILICONFLOW_DEFAULT_MODEL),
    "qwen3_siliconflow": ModelPreset("qwen3_siliconflow", "siliconflow", SILICONFLOW_DEFAULT_MODEL),
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
    default=bool(_c("stage1_filter", "enable_thinking", default=False)),
)
STAGE1_FILTER_MAX_TOKENS: int = int(os.getenv("STAGE1_FILTER_MAX_TOKENS") or _c("stage1_filter", "max_tokens", default=10000))
STAGE1_FILTER_TIMEOUT_SECONDS: float = float(os.getenv("STAGE1_FILTER_TIMEOUT_SECONDS") or _c("stage1_filter", "timeout_seconds", default=15))
STAGE1_FILTER_MAX_RETRIES: int = int(os.getenv("STAGE1_FILTER_MAX_RETRIES") or _c("stage1_filter", "max_retries", default=1))
FILTER_FALLBACK_KEEP_HEAD: int = int(os.getenv("FILTER_FALLBACK_KEEP_HEAD") or _c("stage1_filter", "fallback_keep_head", default=4))
FILTER_FALLBACK_MAX_RULES: int = int(os.getenv("FILTER_FALLBACK_MAX_RULES") or _c("stage1_filter", "fallback_max_rules", default=8))

STAGE2_MAX_CONCURRENT_CALLS: int = int(os.getenv("STAGE2_MAX_CONCURRENT_CALLS") or _c("stage2", "max_concurrent_calls", default=6))
STAGE2_MAX_TOKENS: int = int(os.getenv("STAGE2_MAX_TOKENS") or _c("stage2", "max_tokens", default=10000))
STAGE2_TIMEOUT_SECONDS: float = float(os.getenv("STAGE2_TIMEOUT_SECONDS") or _c("stage2", "timeout_seconds", default=90))
STAGE2_MAX_RETRIES: int = int(os.getenv("STAGE2_MAX_RETRIES") or _c("stage2", "max_retries", default=1))
STAGE2_THINKING_BUDGET: int = int(os.getenv("STAGE2_THINKING_BUDGET") or _c("stage2", "thinking_budget", default=128))

FULLDOC_MODEL_MAX_TOKENS: int = int(os.getenv("FULLDOC_MODEL_MAX_TOKENS") or _c("fulldoc_model", "max_tokens", default=STAGE2_MAX_TOKENS))
FULLDOC_MODEL_TIMEOUT_SECONDS: float = float(os.getenv("FULLDOC_MODEL_TIMEOUT_SECONDS") or _c("fulldoc_model", "timeout_seconds", default=STAGE2_TIMEOUT_SECONDS))
FULLDOC_MODEL_MAX_RETRIES: int = int(os.getenv("FULLDOC_MODEL_MAX_RETRIES") or _c("fulldoc_model", "max_retries", default=STAGE2_MAX_RETRIES))
FULLDOC_MODEL_ENABLE_THINKING: bool = _to_bool(
    os.getenv("FULLDOC_MODEL_ENABLE_THINKING"),
    default=bool(_c("fulldoc_model", "enable_thinking", default=LLM_ENABLE_THINKING)),
)
_fulldoc_budget_raw = os.getenv("FULLDOC_MODEL_THINKING_BUDGET")
FULLDOC_MODEL_THINKING_BUDGET: int | None = (
    int(_fulldoc_budget_raw) if _fulldoc_budget_raw
    else (_c("fulldoc_model", "thinking_budget") or STAGE2_THINKING_BUDGET)
)

SUGGESTION_USE_LLM_RENDERER: bool = _to_bool(
    os.getenv("SUGGESTION_USE_LLM_RENDERER"),
    default=bool(_c("suggestion_model", "use_llm_renderer", default=False)),
)
SUGGESTION_MODEL_MAX_TOKENS: int = int(os.getenv("SUGGESTION_MODEL_MAX_TOKENS") or _c("suggestion_model", "max_tokens", default=10000))
SUGGESTION_MODEL_TIMEOUT_SECONDS: float = float(os.getenv("SUGGESTION_MODEL_TIMEOUT_SECONDS") or _c("suggestion_model", "timeout_seconds", default=45))
SUGGESTION_MODEL_MAX_RETRIES: int = int(os.getenv("SUGGESTION_MODEL_MAX_RETRIES") or _c("suggestion_model", "max_retries", default=1))
SUGGESTION_MODEL_ENABLE_THINKING: bool = _to_bool(
    os.getenv("SUGGESTION_MODEL_ENABLE_THINKING"),
    default=bool(_c("suggestion_model", "enable_thinking", default=False)),
)
_suggestion_budget_raw = os.getenv("SUGGESTION_MODEL_THINKING_BUDGET")
SUGGESTION_MODEL_THINKING_BUDGET: int | None = (
    int(_suggestion_budget_raw) if _suggestion_budget_raw
    else _c("suggestion_model", "thinking_budget")  # None if yaml value is null
)


# ==================== 文本处理参数 ====================
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE") or _c("text_processing", "chunk_size", default=300))
CHUNK_MIN_SIZE: int = int(os.getenv("CHUNK_MIN_SIZE") or _c("text_processing", "chunk_min_size", default=80))

# ==================== 长文本模式参数 ====================
LONGDOC_THRESHOLD: int = int(os.getenv("LONGDOC_THRESHOLD") or _c("text_processing", "longdoc_threshold", default=1500))
LONGDOC_CHUNK_SIZE: int = int(os.getenv("LONGDOC_CHUNK_SIZE") or _c("text_processing", "longdoc_chunk_size", default=1000))
LONGDOC_CHUNK_MIN_SIZE: int = int(os.getenv("LONGDOC_CHUNK_MIN_SIZE") or _c("text_processing", "longdoc_chunk_min_size", default=200))
LONGDOC_CHUNK_OVERLAP: int = int(os.getenv("LONGDOC_CHUNK_OVERLAP") or _c("text_processing", "longdoc_chunk_overlap", default=220))
LONGDOC_CONTEXT_CHARS: int = int(os.getenv("LONGDOC_CONTEXT_CHARS") or _c("text_processing", "longdoc_context_chars", default=240))

# ==================== 全文审核（Stage 2.6）参数 ====================
FULLDOC_INLINE_TEXT_LIMIT: int = int(os.getenv("FULLDOC_INLINE_TEXT_LIMIT") or _c("fulldoc", "inline_text_limit", default=12000))
FULLDOC_CONTEXT_WINDOW: int = int(os.getenv("FULLDOC_CONTEXT_WINDOW") or _c("fulldoc", "context_window", default=220))

# ==================== 规则召回参数 ====================
TOP_K_RULES: int = int(os.getenv("TOP_K_RULES") or _c("rule_recall", "top_k_rules", default=20))
TOP_K_FILTER: int = int(os.getenv("TOP_K_FILTER") or _c("rule_recall", "top_k_filter", default=3))

# ==================== 规则引擎缓存参数 ====================
RULE_ENGINE_CACHE_MAX_SIZE: int = int(
    os.getenv("RULE_ENGINE_CACHE_MAX_SIZE")
    or _c("rule_engine", "cache_max_size", default=4096)
)

# ==================== 并发控制 ====================
MAX_CONCURRENT_CALLS: int = int(os.getenv("MAX_CONCURRENT_CALLS") or _c("concurrency", "max_concurrent_calls", default=6))

# ==================== Benchmark 稳定性运行模式 ====================
BENCHMARK_STABLE_MODE: bool = _to_bool(
    os.getenv("BENCHMARK_STABLE_MODE"),
    default=bool(_c("feature_flags", "benchmark_stable_mode", default=False)),
)

# ==================== 语义预检（Stage 1.1）Feature Flag ====================
ENABLE_SEMANTIC_PRESCREEN: bool = _to_bool(
    os.getenv("ENABLE_SEMANTIC_PRESCREEN"),
    default=bool(_c("semantic_prescreen", "enabled", default=False)),
)
SEMANTIC_PRESCREEN_MAX_DIRECTIONS: int = int(os.getenv("SEMANTIC_PRESCREEN_MAX_DIRECTIONS") or _c("semantic_prescreen", "max_directions", default=2))
SEMANTIC_PRESCREEN_MAX_EXTENDED_RULES: int = int(os.getenv("SEMANTIC_PRESCREEN_MAX_EXTENDED_RULES") or _c("semantic_prescreen", "max_extended_rules", default=4))
SEMANTIC_PRESCREEN_ENABLE_LLM: bool = _to_bool(
    os.getenv("SEMANTIC_PRESCREEN_ENABLE_LLM"),
    default=bool(_c("semantic_prescreen", "enable_llm", default=True)),
)
SEMANTIC_PRESCREEN_TIMEOUT_SECONDS: float = float(os.getenv("SEMANTIC_PRESCREEN_TIMEOUT_SECONDS") or _c("semantic_prescreen", "timeout_seconds", default=15))
SEMANTIC_PRESCREEN_MAX_RETRIES: int = int(os.getenv("SEMANTIC_PRESCREEN_MAX_RETRIES") or _c("semantic_prescreen", "max_retries", default=1))
_semantic_groups_raw: str = os.getenv("SEMANTIC_PRESCREEN_ENABLED_GROUPS", "")
if _semantic_groups_raw.strip():
    SEMANTIC_PRESCREEN_ENABLED_GROUPS: list[str] = [
        g.strip() for g in _semantic_groups_raw.split(",") if g.strip()
    ]
else:
    _yaml_groups = _c("semantic_prescreen", "enabled_groups", default=["financial_confusion", "absolute_expression"])
    SEMANTIC_PRESCREEN_ENABLED_GROUPS = list(_yaml_groups) if _yaml_groups else ["financial_confusion", "absolute_expression"]

# ==================== 数据路径 ====================
BASE_DIR: Path = _PROJECT_ROOT
RULE_CARDS_PATH: str = os.getenv("RULE_CARDS_PATH") or str(BASE_DIR / _c("paths", "rule_cards", default="data/rule_cards.json"))
AUDIT_POINT_WORKBOOK_PATH: str = os.getenv("AUDIT_POINT_WORKBOOK_PATH") or str(BASE_DIR / _c("paths", "audit_point_workbook", default="plan/smoke数据构造种子集.xlsx"))

# ==================== API 服务配置 ====================
API_HOST: str = os.getenv("API_HOST") or str(_c("api", "host", default="0.0.0.0"))
API_PORT: int = int(os.getenv("API_PORT") or _c("api", "port", default=8000))

# ==================== 审计轨迹日志 ====================
ENABLE_TRACE_LOG: bool = _to_bool(
    os.getenv("ENABLE_TRACE_LOG"),
    default=bool(_c("logging", "enable_trace_log", default=True)),
)


def _build_model_profile(
    profile_name: str,
    prefix: str,
    *,
    default_thinking_enabled: bool,
    default_thinking_budget: int | None,
    default_max_tokens: int,
    default_timeout_seconds: float,
    default_max_retries: int,
    yaml_section: str | None = None,
) -> ModelProfile:
    """环境变量优先；YAML 配置作为回退。"""
    inherited_provider = _first_env(f"{prefix}_PROVIDER", f"{prefix}_CALLER")
    inherited_preset_name = os.getenv(f"{prefix}_MODEL_PRESET", "").strip().lower()
    explicit_api_base = os.getenv(f"{prefix}_API_BASE", "").strip()
    explicit_api_key = os.getenv(f"{prefix}_API_KEY", "").strip()
    explicit_model = os.getenv(f"{prefix}_MODEL", "").strip()
    explicit_provider = (inherited_provider or "").strip().lower()

    # YAML section fallbacks for provider / preset
    yaml_provider = str(_c(yaml_section, "provider", default="") or "").strip().lower() if yaml_section else ""
    yaml_preset = str(_c(yaml_section, "model_preset", default="") or "").strip().lower() if yaml_section else ""

    preset_name = inherited_preset_name or yaml_preset or LLM_MODEL_PRESET or ""
    preset = get_model_preset(preset_name)

    provider_name = explicit_provider or yaml_provider or (preset.provider if preset else "default")
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

    max_tokens = int(os.getenv(f"{prefix}_MAX_TOKENS") or default_max_tokens)
    timeout_seconds = float(os.getenv(f"{prefix}_TIMEOUT_SECONDS") or default_timeout_seconds)
    max_retries = int(os.getenv(f"{prefix}_MAX_RETRIES") or default_max_retries)

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
        provider=provider_name,
        model_preset=preset_name or None,
    )


GLOBAL_MODEL_PROFILE = _build_model_profile(
    "global",
    "LLM",
    default_thinking_enabled=LLM_ENABLE_THINKING,
    default_thinking_budget=None,
    default_max_tokens=10000,
    default_timeout_seconds=60.0,
    default_max_retries=1,
    yaml_section="llm",
)

FILTER_MODEL_PROFILE = _build_model_profile(
    "filter",
    "FILTER_MODEL",
    default_thinking_enabled=STAGE1_FILTER_ENABLE_THINKING,
    default_thinking_budget=None,
    default_max_tokens=STAGE1_FILTER_MAX_TOKENS,
    default_timeout_seconds=STAGE1_FILTER_TIMEOUT_SECONDS,
    default_max_retries=STAGE1_FILTER_MAX_RETRIES,
    yaml_section="filter_model",
)

JUDGE_MODEL_PROFILE = _build_model_profile(
    "judge",
    "JUDGE_MODEL",
    default_thinking_enabled=LLM_ENABLE_THINKING,
    default_thinking_budget=STAGE2_THINKING_BUDGET,
    default_max_tokens=STAGE2_MAX_TOKENS,
    default_timeout_seconds=STAGE2_TIMEOUT_SECONDS,
    default_max_retries=STAGE2_MAX_RETRIES,
    yaml_section="judge_model",
)

FULLDOC_MODEL_PROFILE = _build_model_profile(
    "fulldoc",
    "FULLDOC_MODEL",
    default_thinking_enabled=FULLDOC_MODEL_ENABLE_THINKING,
    default_thinking_budget=FULLDOC_MODEL_THINKING_BUDGET,
    default_max_tokens=FULLDOC_MODEL_MAX_TOKENS,
    default_timeout_seconds=FULLDOC_MODEL_TIMEOUT_SECONDS,
    default_max_retries=FULLDOC_MODEL_MAX_RETRIES,
    yaml_section="fulldoc_model",
)

SUGGESTION_MODEL_PROFILE = _build_model_profile(
    "suggestion",
    "SUGGESTION_MODEL",
    default_thinking_enabled=SUGGESTION_MODEL_ENABLE_THINKING,
    default_thinking_budget=SUGGESTION_MODEL_THINKING_BUDGET,
    default_max_tokens=SUGGESTION_MODEL_MAX_TOKENS,
    default_timeout_seconds=SUGGESTION_MODEL_TIMEOUT_SECONDS,
    default_max_retries=SUGGESTION_MODEL_MAX_RETRIES,
    yaml_section="suggestion_model",
)



