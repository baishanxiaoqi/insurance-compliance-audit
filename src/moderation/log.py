"""
统一日志模块
=============
集中管理全项目的日志格式、级别、输出目标（控制台 / 文件）。
所有模块统一通过 ``from log import logger`` 或 ``get_logger(__name__)`` 获取日志实例。

使用方法::

    # 方式 1: 直接使用项目根 logger
    from log import logger
    logger.info("hello")

    # 方式 2: 按模块名获取子 logger
    from log import get_logger
    logger = get_logger(__name__)

    # 在应用入口处可按需调用
    from log import setup_logging
    setup_logging(verbose=True, log_file="audit.log")
"""

import logging
import os
import sys
from pathlib import Path

# ============================================================
# 常量 & 默认值
# ============================================================

_PROJECT_NAME = "moderation"

# 从环境变量或 .env 读取（log 模块可能在 config 之前被导入，所以独立读取）

_DEFAULT_FMT = "%(asctime)s │ %(levelname)-7s │ %(name)s │ %(lineno)d │ %(message)s"
_DEFAULT_DATE_FMT = "%Y-%m-%d %H:%M:%S"

# 从环境变量读取默认级别（可在 .env 中设置 LOG_LEVEL=DEBUG）
_DEFAULT_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


# ============================================================
# 初始化 & 配置
# ============================================================

_initialized = False


def setup_logging(
    verbose: bool = False,
    log_file: str | None = None,
    level: str | None = None,
) -> None:
    """
    初始化全局日志配置（幂等，重复调用会先清除旧 handler）。

    参数:
        verbose: 为 True 时强制 DEBUG 级别
        log_file: 可选，指定日志输出文件路径（追加模式）
        level: 显式指定级别字符串（优先级最高）
    """
    global _initialized

    # 决定级别
    if level:
        log_level = getattr(logging, level.upper(), logging.INFO)
    elif verbose:
        log_level = logging.DEBUG
    else:
        log_level = getattr(logging, _DEFAULT_LEVEL, logging.INFO)

    # 获取项目根 logger
    root = logging.getLogger(_PROJECT_NAME)
    root.setLevel(log_level)

    # 清除旧 handler（幂等）
    root.handlers.clear()

    formatter = logging.Formatter(_DEFAULT_FMT, datefmt=_DEFAULT_DATE_FMT)

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # 文件 handler（可选）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # 同步标准库根 logger 级别，避免第三方库日志过于嘈杂
    logging.getLogger().setLevel(logging.WARNING)

    root.propagate = False
    _initialized = True

    root.debug(f"日志初始化完成  level={logging.getLevelName(log_level)}")


def get_logger(name: str | None = None) -> logging.Logger:
    """
    获取项目子 logger。

    如果传入模块名（通常用 __name__），返回 ``moderation.<name>`` 的 logger；
    不传参数则返回项目根 logger。
    """
    if not _initialized:
        setup_logging()

    if name is None:
        return logging.getLogger(_PROJECT_NAME)
    return logging.getLogger(f"{_PROJECT_NAME}.{name}")


# ============================================================
# 便捷导出：项目根 logger
# ============================================================

logger = get_logger()
