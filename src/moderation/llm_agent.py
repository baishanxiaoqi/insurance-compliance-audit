"""
LLM Agent 集成层（基于 Agno 2.5）
==================================
将 Agno Agent + OpenAIChat 适配到 OpenAI 兼容 API：
  - create_model()  : 生成兼容 OpenAI 协议的 OpenAIChat
  - create_agent()  : 构建带结构化输出的 Agno Agent
  - safe_arun()     : 异步调用 + 429 指数退避 + 超时保护
  - safe_run()      : 同步版本
"""

import asyncio
import json
import random
import re
from typing import Any, List, Optional, Type, TypeVar

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from pydantic import BaseModel

from . import config
from .log import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# ============================================================
# OpenAI 兼容配置
# ============================================================

# Agno 默认将 system 映射为 developer（OpenAI 新规范），
# 部分兼容接口仅支持 system / user / assistant，需要显式覆盖
_OPENAI_COMPAT_ROLE_MAP = {
    "system": "system",
    "user": "user",
    "assistant": "assistant",
    "tool": "tool",
    "model": "assistant",
}


def _build_json_contract_instructions(output_schema: Type[T]) -> List[str]:
    if not isinstance(output_schema, type) or not issubclass(output_schema, BaseModel):
        return []

    properties = output_schema.model_json_schema().get("properties", {})
    fields = ", ".join(properties.keys())
    return [
        "最终答案必须只输出一个合法 JSON 对象，不要输出 markdown、代码块、解释或额外前后缀。",
        f"JSON 字段必须严格遵循当前 schema，可用字段为：{fields}。",
        "如果开启了思考，思考内容只能出现在 reasoning，不得污染最终 JSON 正文。",
    ]


def _normalize_text_candidate(text: str) -> str:
    return (text or "").strip()


def _extract_json_substring(text: str) -> str | None:
    normalized = _normalize_text_candidate(text)
    if not normalized:
        return None

    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", normalized, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        normalized = fenced_match.group(1).strip()

    for opener, closer in (("{", "}"), ("[", "]")):
        start = normalized.find(opener)
        if start < 0:
            continue
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(normalized)):
            char = normalized[index]
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    return normalized[start : index + 1]
    return None


def _validate_against_schema(output_schema: Type[T], text: str) -> T | None:
    raw = _normalize_text_candidate(text)
    if not raw:
        return None

    candidates = [raw]
    extracted = _extract_json_substring(raw)
    if extracted and extracted not in candidates:
        candidates.append(extracted)

    for candidate in candidates:
        try:
            return output_schema.model_validate_json(candidate)
        except Exception:
            pass
        try:
            return output_schema.model_validate(json.loads(candidate))
        except Exception:
            continue
    return None


def _message_text(message: Any) -> str:
    if message is None:
        return ""
    if hasattr(message, "get_content_string"):
        try:
            return _normalize_text_candidate(message.get_content_string())
        except Exception:
            return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return _normalize_text_candidate(content)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return _normalize_text_candidate("\n".join(parts))
    return ""


def _try_recover_structured_content(agent: Agent, run_output: Any) -> T | None:
    output_schema = getattr(agent, "output_schema", None)
    if not isinstance(output_schema, type) or not issubclass(output_schema, BaseModel):
        return None

    seen: set[str] = set()
    candidate_texts: list[str] = []

    raw_content = getattr(run_output, "content", None)
    if isinstance(raw_content, str) and _normalize_text_candidate(raw_content):
        candidate_texts.append(raw_content)

    for message in reversed(getattr(run_output, "messages", []) or []):
        if getattr(message, "role", None) != "assistant":
            continue
        text = _message_text(message)
        if text:
            candidate_texts.append(text)

    for text in candidate_texts:
        normalized = _normalize_text_candidate(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        parsed = _validate_against_schema(output_schema, normalized)
        if parsed is not None:
            return parsed
    return None


def _is_output_budget_exhausted(agent: Agent, run_output: Any) -> bool:
    content_text = _normalize_text_candidate(getattr(run_output, "content", "") or "")
    if content_text:
        return False

    reasoning_text = _normalize_text_candidate(getattr(run_output, "reasoning_content", "") or "")
    if not reasoning_text:
        messages = getattr(run_output, "messages", []) or []
        reasoning_text = next(
            (
                _normalize_text_candidate(getattr(message, "reasoning_content", "") or "")
                for message in reversed(messages)
                if _normalize_text_candidate(getattr(message, "reasoning_content", "") or "")
            ),
            "",
        )
    if not reasoning_text:
        return False

    max_tokens = getattr(getattr(agent, "model", None), "max_tokens", None)
    output_tokens = getattr(getattr(run_output, "metrics", None), "output_tokens", None)
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        return False
    if not isinstance(output_tokens, int) or output_tokens <= 0:
        return False
    return output_tokens >= max_tokens


def _is_thinking_enabled(agent: Agent) -> bool:
    extra_body = getattr(getattr(agent, "model", None), "extra_body", None)
    return isinstance(extra_body, dict) and bool(extra_body.get("enable_thinking"))


def _set_thinking_enabled(agent: Agent, enabled: bool) -> None:
    model = getattr(agent, "model", None)
    if model is None:
        return
    extra_body = dict(getattr(model, "extra_body", {}) or {})
    extra_body["enable_thinking"] = enabled
    if not enabled:
        extra_body.pop("thinking_budget", None)
    model.extra_body = extra_body


# ============================================================
# 工厂函数
# ============================================================

def create_model(
    temperature: float = 0.1,
    max_tokens: int | None = None,
    thinking_enabled: Optional[bool] = None,
    thinking_budget: Optional[int] = None,
    profile: config.ModelProfile | None = None,
) -> OpenAIChat:
    """
    创建兼容 OpenAI 协议的 OpenAIChat 模型实例。

    关键适配：
      - supports_native_structured_outputs=False  → 兼容接口通常不支持 OpenAI Structured Outputs
      - role_map                                   → 避免 developer role 报错
      - retries + exponential_backoff              → Agno 内建重试
    """
    selected_profile = profile

    if thinking_enabled is None:
        thinking_enabled = (
            selected_profile.thinking_enabled
            if selected_profile is not None
            else config.LLM_ENABLE_THINKING
        )
    if thinking_budget is None and selected_profile is not None:
        thinking_budget = selected_profile.thinking_budget
    if max_tokens is None:
        max_tokens = selected_profile.max_tokens if selected_profile is not None else 10000

    extra_body = {"enable_thinking": bool(thinking_enabled)}
    if thinking_enabled and thinking_budget is not None:
        extra_body["thinking_budget"] = thinking_budget

    model_id = selected_profile.model if selected_profile is not None else config.LLM_MODEL
    api_key = selected_profile.api_key if selected_profile is not None else config.LLM_API_KEY
    base_url = selected_profile.api_base if selected_profile is not None else config.LLM_API_BASE

    return OpenAIChat(
        id=model_id,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        # OpenAI 兼容模式
        supports_native_structured_outputs=False,
        supports_json_schema_outputs=False,
        role_map=_OPENAI_COMPAT_ROLE_MAP,
        extra_body=extra_body,
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
    max_tokens: int | None = None,
    thinking_enabled: Optional[bool] = None,
    thinking_budget: Optional[int] = None,
    profile: config.ModelProfile | None = None,
) -> Agent:
    """
    创建配置好的 Agno Agent 实例。

    参数:
      output_schema : Pydantic 模型类，Agno 将使用 json_mode 解析 LLM 返回
      instructions  : 系统提示列表（Agent 会拼接为 system message）
      name          : Agent 名称（用于日志标识）
      temperature   : 采样温度
    """
    model = create_model(
        temperature=temperature,
        max_tokens=max_tokens,
        thinking_enabled=thinking_enabled,
        thinking_budget=thinking_budget,
        profile=profile,
    )

    json_contract = _build_json_contract_instructions(output_schema)

    agent = Agent(
        model=model,
        name=name or f"agent_{output_schema.__name__}",
        output_schema=output_schema,
        structured_outputs=False,   # 使用 json_mode，非 native structured outputs
        instructions=[*json_contract, *instructions],
        markdown=False,
        parse_response=True,
        use_json_mode=True,
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
    base_max_tokens = getattr(getattr(agent, "model", None), "max_tokens", None)

    for attempt in range(max_retries + 1):
        try:
            run_output = await asyncio.wait_for(
                agent.arun(prompt),
                timeout=timeout_seconds,
            )

            # Agno 成功解析时，content 是 Pydantic 模型实例
            if isinstance(run_output.content, BaseModel):
                return run_output.content

            recovered = _try_recover_structured_content(agent, run_output)
            if recovered is not None:
                logger.info(
                    "Agent [%s] 原始输出未直接解析成功，已通过恢复逻辑提取结构化 JSON。",
                    agent.name,
                )
                return recovered

            if (
                attempt < max_retries
                and _is_output_budget_exhausted(agent, run_output)
                and isinstance(base_max_tokens, int)
                and base_max_tokens > 0
            ):
                current_max_tokens = getattr(agent.model, "max_tokens", base_max_tokens)
                if isinstance(current_max_tokens, int) and current_max_tokens > 0:
                    if current_max_tokens < 512:
                        next_max_tokens = min(
                            max(current_max_tokens * 2, current_max_tokens + 256),
                            10000,
                        )
                    else:
                        next_max_tokens = min(
                            max(current_max_tokens * 3, current_max_tokens + 1024),
                            10000,
                        )
                    if next_max_tokens > current_max_tokens:
                        agent.model.max_tokens = next_max_tokens
                        logger.warning(
                            "Agent [%s] 输出预算疑似被 reasoning 吃满，"
                            "max_tokens 从 %s 提升到 %s 后重试。",
                            agent.name,
                            current_max_tokens,
                            next_max_tokens,
                        )
                        await asyncio.sleep(0.2)
                        continue

            if (
                attempt < max_retries
                and _is_output_budget_exhausted(agent, run_output)
                and _is_thinking_enabled(agent)
            ):
                current_max_tokens = getattr(agent.model, "max_tokens", base_max_tokens)
                if isinstance(current_max_tokens, int) and current_max_tokens >= 3072:
                    _set_thinking_enabled(agent, False)
                    logger.warning(
                        "Agent [%s] 在 think 模式下仍未产出最终 JSON，"
                        "切换为 no-think 结构化救援重试。",
                        agent.name,
                    )
                    await asyncio.sleep(0.2)
                    continue

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
            wait_time = min((2 ** attempt) * 1.0, 8.0) + random.uniform(0, 0.25)
            logger.info(
                f"Agent [{agent.name}] 超时后退避 {wait_time:.2f}s，"
                f"准备重试"
            )
            await asyncio.sleep(wait_time)
            continue

        except Exception as e:
            error_str = str(e)
            error_lower = error_str.lower()
            is_rate_limit = "429" in error_str or "rate_limit" in error_lower
            is_transient_network = any(
                keyword in error_lower
                for keyword in (
                    "timeout",
                    "timed out",
                    "connection error",
                    "connecterror",
                    "readtimeout",
                    "apiconnectionerror",
                    "temporarily unavailable",
                    "service unavailable",
                )
            )

            if attempt < max_retries:
                if is_rate_limit:
                    wait_time = (2 ** attempt) * 1.5  # 1.5s, 3s, 6s, 12s
                    logger.info(
                        f"API 限流 429，等待 {wait_time:.1f}s 后重试 "
                        f"(尝试 {attempt + 1}/{max_retries + 1})"
                    )
                    await asyncio.sleep(wait_time)
                elif is_transient_network:
                    wait_time = min((2 ** attempt) * 1.0, 8.0) + random.uniform(0, 0.25)
                    logger.warning(
                        f"Agent [{agent.name}] 网络抖动/服务瞬时异常，"
                        f"等待 {wait_time:.2f}s 后重试 "
                        f"(尝试 {attempt + 1}/{max_retries + 1}): {e}"
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

            recovered = _try_recover_structured_content(agent, run_output)
            if recovered is not None:
                logger.info(
                    "Agent [%s] 同步输出未直接解析成功，已通过恢复逻辑提取结构化 JSON。",
                    agent.name,
                )
                return recovered

            raise ValueError(
                f"Agent [{agent.name}] 返回非结构化内容: "
                f"{str(run_output.content)[:200]}"
            )

        except Exception as e:
            if attempt < max_retries:
                import random
                import time
                wait = min(2 ** attempt + random.uniform(0, 1), 30.0)
                logger.warning(
                    f"Agent [{agent.name}] 同步调用失败 "
                    f"(尝试 {attempt + 1}/{max_retries + 1}): {e}，"
                    f"等待 {wait:.1f}s 后重试"
                )
                time.sleep(wait)
                continue
            raise
