"""
全局配置模块
从环境变量 / .env 文件中读取配置项
"""

import os
from pathlib import Path
from dotenv import load_dotenv


def _to_bool(value: str | None, default: bool = False) -> bool:
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "y", "on"}

# 加载 .env 文件（向上查找到项目根目录）
_PKG_DIR = Path(__file__).parent
_PROJECT_ROOT = _PKG_DIR.parent.parent
_env_path = _PROJECT_ROOT / ".env"
load_dotenv(_env_path)

# ==================== LLM 配置 ====================
LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "sk-xxx")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

# ==================== 文本处理参数 ====================
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "300"))
CHUNK_MIN_SIZE: int = int(os.getenv("CHUNK_MIN_SIZE", "80"))
# 注意：CHUNK_OVERLAP 已弃用，自适应切分使用句级回溯重叠策略

# ==================== 规则召回参数 ====================
TOP_K_RULES: int = int(os.getenv("TOP_K_RULES", "20"))
TOP_K_FILTER: int = int(os.getenv("TOP_K_FILTER", "3"))

# ==================== 并发控制 ====================
MAX_CONCURRENT_CALLS: int = int(os.getenv("MAX_CONCURRENT_CALLS", "3"))

# ==================== 数据路径 ====================
BASE_DIR: Path = _PROJECT_ROOT
RULE_CARDS_PATH: str = os.getenv("RULE_CARDS_PATH", str(BASE_DIR / "data" / "rule_cards.json"))

# ==================== API 服务配置 ====================
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# ==================== 审计轨迹日志 ====================
ENABLE_TRACE_LOG: bool = _to_bool(os.getenv("ENABLE_TRACE_LOG"), default=True)
