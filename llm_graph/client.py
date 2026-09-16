"""DeepSeek LLM 客户端（OpenAI 兼容协议，对应旧版 client.ts）。

默认对接 DeepSeek 开放平台：
    Base URL: https://api.deepseek.com
    模型:     deepseek-flash（当前 DeepSeek-V4.1-Flash）/ deepseek-v4-pro

任何 OpenAI 协议兼容的平台（火山方舟、SiliconFlow、OpenRouter 等）
只需更换 base_url 与 model 即可复用本客户端。
"""

from __future__ import annotations

from typing import Any, Callable, Iterator, Optional

from openai import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)

from llm_graph.config import Settings
from llm_graph.graph import GraphJSON, parse_graph
from llm_graph.prompt import GraphType, build_generation_prompt, build_optimize_prompt


class LLMError(RuntimeError):
    """LLM 调用失败或输出无法解析。"""


_FRIENDLY_ERRORS: tuple[tuple[type[Exception], str], ...] = (
    (AuthenticationError, "API Key 无效或未授权（401），请检查侧边栏 / 环境变量中的 API Key"),
    (NotFoundError, "接口或模型不存在（404），请检查 Base URL 与模型名是否匹配"),
    (RateLimitError, "触发限流或额度不足（429），请稍后重试，或检查账户余额"),
    (APIConnectionError, "网络连接失败，请检查网络、代理或 Base URL 是否可达"),
)


def _friendly_message(exc: Exception) -> str:
    for exc_type, message in _FRIENDLY_ERRORS:
        if isinstance(exc, exc_type):
            return message
    return f"调用模型接口失败：{exc}"


class DeepSeekClient:
    """对 OpenAI 兼容 Chat Completions 接口的轻量流式封装。"""

    def __init__(self, settings: Settings):
        if not settings.has_key:
            raise LLMError("未配置 API Key：请在侧边栏「连接配置」中填写，或设置环境变量 DEEPSEEK_API_KEY")
        self.settings = settings
        self._client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout,
        )

    def chat_stream(self, system: str, user: str) -> Iterator[str]:
        """流式对话，逐段 yield 文本增量；失败时抛出带可读原因的 LLMError。"""
        # DeepSeek V4 系列支持思考模式开关（deepseek-flash 默认开启思考）；
        # 通过 extra_body 传递非标准字段，thinking_mode 为 None 时不发送以兼容其他平台。
        extra_kwargs: dict[str, Any] = {}
        if self.settings.thinking_mode is not None:
            extra_kwargs["extra_body"] = {
                "thinking": {"type": "enabled" if self.settings.thinking_mode else "disabled"}
            }
        try:
            stream = self._client.chat.completions.create(
                model=self.settings.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.settings.temperature,
                max_tokens=self.settings.max_tokens,
                stream=True,
                **extra_kwargs,
            )
            for event in stream:
                if not event.choices:
                    continue
                delta = event.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except (AuthenticationError, NotFoundError, RateLimitError, APIConnectionError) as exc:
            raise LLMError(_friendly_message(exc)) from exc
        except APIError as exc:
            raise LLMError(_friendly_message(exc)) from exc


def _collect(client: DeepSeekClient, system: str, user: str, on_chunk: Optional[Callable[[str], None]] = None) -> str:
    """消费流式输出并拼接为完整文本，可选逐块回调。"""
    parts: list[str] = []
    for chunk in client.chat_stream(system, user):
        parts.append(chunk)
        if on_chunk:
            on_chunk(chunk)
    return "".join(parts)


def generate_graph_json(
    client: DeepSeekClient,
    user_input: str,
    graph_type: GraphType = "general",
    on_chunk: Optional[Callable[[str], None]] = None,
) -> tuple[GraphJSON, str]:
    """自然语言 → (GraphJSON, 模型原始输出)。

    :raises LLMError: 调用失败或输出无法解析为合法 GraphJSON
    """
    system, user = build_generation_prompt(user_input, graph_type)
    raw = _collect(client, system, user, on_chunk)
    try:
        return parse_graph(raw), raw
    except ValueError as exc:
        raise LLMError(f"模型输出解析失败：{exc}") from exc


def optimize_graph_json(
    client: DeepSeekClient,
    graph: GraphJSON,
    improvements: str,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> tuple[GraphJSON, str]:
    """根据改进要求优化现有 GraphJSON，返回 (新 GraphJSON, 模型原始输出)。"""
    system, user = build_optimize_prompt(graph, improvements)
    raw = _collect(client, system, user, on_chunk)
    try:
        return parse_graph(raw), raw
    except ValueError as exc:
        raise LLMError(f"模型输出解析失败：{exc}") from exc
