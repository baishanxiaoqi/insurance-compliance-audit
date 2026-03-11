"""审计决策轨迹日志工具。

用于输出结构化 TRACE 日志，便于质检看板与复盘。
"""

from __future__ import annotations

import json
from typing import Any

from .config import ENABLE_TRACE_LOG
from .log import get_logger

logger = get_logger(__name__)


def trace_event(event: str, payload: dict[str, Any]) -> None:
    """输出结构化轨迹日志。"""
    if not ENABLE_TRACE_LOG:
        return
    logger.info(f"TRACE::{event}::{json.dumps(payload, ensure_ascii=False, default=str)}")
