"""
LLM Agent 集成层（基于 Agno 2.5）
==================================
将 Agno Agent + OpenAIChat 适配到 Moonshot API：
  - create_model()  : 生成 Moonshot 兼容的 OpenAIChat
  - create_agent()  : 构建带结构化输出的 Agno Agent
  - safe_arun()     : 异步调用 + 429 指数退避 + 超时保护
  - safe_run()      : 同步版本
"""

import asyncio
from typing import List, Optional, Type, TypeVar

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from pydantic import BaseModel

from . import config
from .log import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# ============================================================
# Moonshot 兼容配置
# ============================================================

# Agno 默认将 system 映射为 developer（OpenAI 新规范），
# 但 Moonshot 仅支持 system / user / assistant，需要显式覆盖
_MOONSHOT_ROLE_MAP = {
    "system": "system",
    "user": "user",
    "assistant": "assistant",
    "tool": "tool",
    "model": "assistant",
}


# ============================================================
# 工厂函数
# ============================================================

def create_model(
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> OpenAIChat:
    """
    创建 Moonshot 兼容的 OpenAIChat 模型实例。

    关键适配：
      - supports_native_structured_outputs=False  → Moonshot 不支持 OpenAI Structured Outputs
      - role_map                                   → 避免 developer role 报错
      - retries + exponential_backoff              → Agno 内建重试
    """
    return OpenAIChat(
        id=config.LLM_MODEL,
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_API_BASE,
        temperature=temperature,
        max_tokens=max_tokens,
        # Moonshot 兼容
        supports_native_structured_outputs=False,
        supports_json_schema_outputs=False,
        role_map=_MOONSHOT_ROLE_MAP,
        # Agno 内建重试（处理偶发网络错误）
        retries=2,
        delay_between_retries=1,
        exponential_backoff=True,
    )


def create_agent(
    output_schema: Type[T],
    instructions: List[str],
    name: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> Agent:
    """
    创建配置好的 Agno Agent 实例。

    参数:
      output_schema : Pydantic 模型类，Agno 将使用 json_mode 解析 LLM 返回
      instructions  : 系统提示列表（Agent 会拼接为 system message）
      name          : Agent 名称（用于日志标识）
      temperature   : 采样温度
    """
    model = create_model(temperature=temperature, max_tokens=max_tokens)

    agent = Agent(
        model=model,
        name=name or f"agent_{output_schema.__name__}",
        output_schema=output_schema,
        structured_outputs=False,   # 使用 json_mode，非 native structured outputs
        instructions=instructions,
        markdown=False,
        parse_response=True,
    )

    logger.debug(f"创建 Agno Agent: {agent.name} (schema={output_schema.__name__})")
    return agent


# ============================================================
# 安全调用封装（429 退避 + 超时保护）
# ============================================================

async def safe_arun(
    agent: Agent,
    prompt: str,
    max_retries: int = 4,
    timeout_seconds: float = 60.0,
) -> T:
    """
    安全的异步 Agent 调用。

    在 Agno 内建重试之外，额外处理：
      - Moonshot 429 限流 → 指数退避（1.5s / 3s / 6s / 12s）
      - 超时保护 → asyncio.wait_for
      - 返回值提取 → RunOutput.content → Pydantic 模型

    返回: 解析后的 Pydantic 模型实例（output_schema 类型 T）
    """
    for attempt in range(max_retries + 1):
        try:
            run_output = await asyncio.wait_for(
                agent.arun(prompt),
                timeout=timeout_seconds,
            )

            # Agno 成功解析时，content 是 Pydantic 模型实例
            if isinstance(run_output.content, BaseModel):
                return run_output.content

            # 如果返回的是字符串（通常是错误信息）
            if isinstance(run_output.content, str):
                raise ValueError(
                    f"Agent [{agent.name}] 返回非结构化内容: "
                    f"{str(run_output.content)[:200]}"
                )

            raise ValueError(
                f"Agent [{agent.name}] 返回意外类型: {type(run_output.content)}"
            )

        except asyncio.TimeoutError:
            logger.warning(
                f"Agent [{agent.name}] 超时 ({timeout_seconds}s, "
                f"尝试 {attempt + 1}/{max_retries + 1})"
            )
            if attempt >= max_retries:
                raise TimeoutError(
                    f"LLM 调用超时 (>{timeout_seconds}s)，已重试 {max_retries} 次"
                )

        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "rate_limit" in error_str.lower()

            if attempt < max_retries:
                if is_rate_limit:
                    wait_time = (2 ** attempt) * 1.5  # 1.5s, 3s, 6s, 12s
                    logger.info(
                        f"API 限流 429，等待 {wait_time:.1f}s 后重试 "
                        f"(尝试 {attempt + 1}/{max_retries + 1})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(
                        f"Agent [{agent.name}] 调用失败 "
                        f"(尝试 {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    await asyncio.sleep(0.5)
                continue
            raise


def safe_run(
    agent: Agent,
    prompt: str,
    max_retries: int = 4,
) -> T:
    """同步版本：安全的 Agent 调用（带重试）"""
    for attempt in range(max_retries + 1):
        try:
            run_output = agent.run(prompt)

            if isinstance(run_output.content, BaseModel):
                return run_output.content

            raise ValueError(
                f"Agent [{agent.name}] 返回非结构化内容: "
                f"{str(run_output.content)[:200]}"
            )

        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"Agent [{agent.name}] 同步调用失败 "
                    f"(尝试 {attempt + 1}/{max_retries + 1}): {e}"
                )
                continue
            raise
