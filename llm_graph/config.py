"""应用配置：环境变量提供默认值，Streamlit 侧边栏可在运行时覆盖。"""

from __future__ import annotations

import os
from dataclasses import dataclass

# DeepSeek 开放平台（OpenAI 兼容协议）默认接入点
DEFAULT_BASE_URL = "https://api.deepseek.com"
# deepseek-flash 当前指向 DeepSeek-V4.1-Flash（思考/非思考双模式，1M 上下文）
DEFAULT_MODEL = "deepseek-flash"


def _load_dotenv() -> None:
    """尽力加载项目根目录的 .env 文件；未安装 python-dotenv 时静默跳过。"""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # pragma: no cover - 环境变量仍然可用
        pass


_load_dotenv()


def _parse_thinking(value: str) -> bool | None:
    """解析 DEEPSEEK_THINKING：true/false 显式开关，空值跟随模型默认。"""
    text = value.strip().lower()
    if not text:
        return None
    return text in ("1", "true", "yes", "on")


@dataclass
class Settings:
    """一次 LLM 调用所需的全部连接与采样参数。"""

    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    temperature: float = 0.7
    max_tokens: int = 2048
    # DeepSeek V4 系列思考模式：True 强制开启 / False 强制关闭 / None 不发送（跟随模型默认）
    thinking_mode: bool | None = None
    timeout: float = 120.0

    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量（含 .env）读取默认配置。"""
        return cls(
            api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            base_url=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
            model=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "2048")),
            thinking_mode=_parse_thinking(os.getenv("DEEPSEEK_THINKING", "")),
        )

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)
