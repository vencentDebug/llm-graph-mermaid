"""
llm-graph-mermaid 核心包。

将自然语言描述转换为结构化 GraphJSON，并渲染为 Mermaid 流程图。

模块一览：
    config  —— 运行配置（环境变量默认值 + 界面覆盖）
    graph   —— GraphJSON 数据模型与解析校验（pydantic v2）
    prompt  —— 提示词模板（生成 / 按场景 / 优化）
    client  —— DeepSeek（OpenAI 兼容）流式客户端
    mermaid —— GraphJSON → Mermaid flowchart 渲染
"""

from llm_graph.client import DeepSeekClient, LLMError, generate_graph_json, optimize_graph_json
from llm_graph.config import DEFAULT_BASE_URL, DEFAULT_MODEL, Settings
from llm_graph.graph import GraphEdge, GraphJSON, GraphNode, parse_graph
from llm_graph.mermaid import graph_to_mermaid

__version__ = "2.0.0"

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DeepSeekClient",
    "GraphEdge",
    "GraphJSON",
    "GraphNode",
    "LLMError",
    "Settings",
    "generate_graph_json",
    "graph_to_mermaid",
    "optimize_graph_json",
    "parse_graph",
]
