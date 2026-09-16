"""GraphJSON 数据模型、解析与结构校验（对应旧版 zod 的 types/graph）。"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

NodeType = Literal["start", "process", "decision", "end", "subprocess"]

Direction = Literal["TB", "BT", "LR", "RL"]

# 图的渲染种类：flowchart = 流程图；state = 状态机图（stateDiagram-v2 渲染）
DiagramKind = Literal["flowchart", "state"]

# 合法的图表类型标识（与 prompt.GRAPH_TYPES 的键保持一致；此处独立定义避免循环导入）
_GRAPH_TYPE_IDS: set[str] = {"simple", "general", "workflow", "swimlane", "state", "architecture", "pipeline"}

# 允许模型输出同义节点类型，统一归一化为标准五类
_NODE_TYPE_MAP: dict[str, str] = {
    "start": "start",
    "begin": "start",
    "init": "start",
    "process": "process",
    "task": "process",
    "step": "process",
    "action": "process",
    "decision": "decision",
    "condition": "decision",
    "branch": "decision",
    "end": "end",
    "finish": "end",
    "stop": "end",
    "terminal": "end",
    "subprocess": "subprocess",
    "sub_process": "subprocess",
    "subprocess ": "subprocess",
    "subroutine": "subprocess",
}


def _clean(value: Any) -> Optional[str]:
    """去除首尾空白；空字符串归一化为 None。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class GraphNode(BaseModel):
    """流程图节点。"""

    id: str
    label: str
    type: NodeType = "process"
    description: Optional[str] = None
    # 泳道图专用：节点所属的角色 / 部门 / 系统（非泳道图为空）
    lane: Optional[str] = None

    @field_validator("id", "label")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        text = _clean(value)
        if not text:
            raise ValueError("节点 id / label 不能为空")
        return text

    @field_validator("description", "lane")
    @classmethod
    def _clean_optional(cls, value: Optional[str]) -> Optional[str]:
        return _clean(value)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: Any) -> str:
        return _NODE_TYPE_MAP.get(str(value or "").strip().lower(), "process")


class GraphEdge(BaseModel):
    """流程图边（from -> to），决策分支建议携带 label 或 condition。"""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(
        validation_alias=AliasChoices("from", "source", "src"),
        serialization_alias="from",
        description="起始节点 ID",
    )
    to: str = Field(
        validation_alias=AliasChoices("to", "target", "dst"),
        description="目标节点 ID",
    )
    label: Optional[str] = None
    condition: Optional[str] = None

    @field_validator("from_", "to")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        text = _clean(value)
        if not text:
            raise ValueError("边的 from / to 不能为空")
        return text

    @field_validator("label", "condition")
    @classmethod
    def _clean_optional(cls, value: Optional[str]) -> Optional[str]:
        return _clean(value)


class GraphJSON(BaseModel):
    """标准图结构：节点 + 边，可往返序列化为 GraphJSON 1.0 格式。"""

    model_config = ConfigDict(populate_by_name=True)

    version: str = "1.0"
    title: str = "未命名流程"
    description: Optional[str] = None
    direction: Direction = "TB"
    diagram: DiagramKind = "flowchart"
    # 图表类型标识：auto 模式下由模型自行判断并填写；无法识别或未提供时为空
    type: Optional[str] = None
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    @field_validator("title", mode="before")
    @classmethod
    def _default_title(cls, value: Any) -> str:
        return _clean(value) or "未命名流程"

    @field_validator("description")
    @classmethod
    def _clean_optional(cls, value: Optional[str]) -> Optional[str]:
        return _clean(value)

    @field_validator("direction", mode="before")
    @classmethod
    def _normalize_direction(cls, value: Any) -> str:
        text = str(value or "TB").strip().upper()
        if text in ("TD", "TOPDOWN", "TOP_DOWN", "VERTICAL"):
            return "TB"
        if text in ("HORIZONTAL", "HORIZ"):
            return "LR"
        return text if text in ("TB", "BT", "LR", "RL") else "TB"

    @field_validator("diagram", mode="before")
    @classmethod
    def _normalize_diagram(cls, value: Any) -> str:
        text = str(value or "flowchart").strip().lower().replace("-", "").replace("_", "")
        return "state" if text in ("state", "statediagram") else "flowchart"

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_graph_type(cls, value: Any) -> Optional[str]:
        """归一化模型自选的图表类型；无法识别时置空（不影响渲染）。"""
        text = str(value or "").strip().lower()
        return text if text in _GRAPH_TYPE_IDS else None

    @model_validator(mode="after")
    def _validate_structure(self) -> "GraphJSON":
        if not self.nodes:
            raise ValueError("图至少需要一个节点（nodes 不能为空）")

        ids = [node.id for node in self.nodes]
        duplicated = sorted({node_id for node_id in ids if ids.count(node_id) > 1})
        if duplicated:
            raise ValueError(f"节点 ID 重复：{duplicated}")

        known = set(ids)
        referenced = {edge.from_ for edge in self.edges} | {edge.to for edge in self.edges}
        missing = sorted(referenced - known)
        if missing:
            raise ValueError(f"边引用了不存在的节点：{missing}")
        return self

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """导出为标准 GraphJSON 字典（from 别名、剔除 None 字段）。"""
        return self.model_dump(by_alias=True, exclude_none=True)

    def to_json_str(self, indent: int = 2) -> str:
        """导出为格式化的 GraphJSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @property
    def node_ids(self) -> list[str]:
        return [node.id for node in self.nodes]


# ----------------------------------------------------------------------
# 解析：从 LLM 原始输出中提取并校验 GraphJSON
# ----------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json[c5]?|javascript|js)?", re.IGNORECASE)


def extract_json_object(text: str) -> dict[str, Any]:
    """从模型输出中提取第一个完整的 JSON 对象。

    容忍 markdown 代码块、前后闲聊文本等杂讯；按括号配对扫描，
    并正确跳过字符串字面量内的花括号。
    """
    if not text or not text.strip():
        raise ValueError("模型输出为空")

    cleaned = _FENCE_RE.sub("", text)
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("输出中未找到 JSON 对象（缺少 '{'）")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                snippet = cleaned[start : index + 1]
                try:
                    data = json.loads(snippet)
                except json.JSONDecodeError as exc:
                    preview = snippet[:200] + ("…" if len(snippet) > 200 else "")
                    raise ValueError(f"JSON 解析失败：{exc.msg}（片段预览：{preview}）") from exc
                if not isinstance(data, dict):
                    raise ValueError("输出中的 JSON 不是对象（应为 {\"nodes\": [...], ...}）")
                return data

    raise ValueError("JSON 对象不完整（括号未闭合），输出可能被 max_tokens 截断，可尝试调大 Max Tokens 后重试")


def parse_graph(text: str) -> GraphJSON:
    """解析模型原始输出为 GraphJSON，结构非法时抛出带原因的 ValueError。"""
    data = extract_json_object(text)
    try:
        return GraphJSON.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"GraphJSON 结构校验失败：{exc}") from exc
