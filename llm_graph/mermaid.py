"""GraphJSON → Mermaid 渲染。

支持两种渲染目标：
    flowchart       普通流程图；节点带 lane 字段时自动分组为泳道（subgraph）
    stateDiagram-v2 状态机图（graph.diagram == "state"）
"""

from __future__ import annotations

from llm_graph.graph import GraphJSON, GraphNode

# 节点类型 → Mermaid 形状（左右包裹符）
_SHAPES: dict[str, tuple[str, str]] = {
    "start": ("([", "])"),      # 体育场形：开始
    "end": ("([", "])"),        # 体育场形：结束
    "process": ("[", "]"),      # 矩形：处理
    "decision": ("{", "}"),     # 菱形：决策
    "subprocess": ("[[", "]]"), # 双竖线矩形：子流程
}

# 节点类型分组 → classDef 样式（start / end 共用一套配色）
_CLASS_GROUPS: dict[str, tuple[str, ...]] = {
    "startEnd": ("start", "end"),
    "decision": ("decision",),
    "subprocess": ("subprocess",),
}

_CLASS_STYLES: dict[str, str] = {
    "startEnd": "fill:#2e7d32,stroke:#1b5e20,color:#ffffff",
    "decision": "fill:#f9a825,stroke:#f57f17,color:#ffffff",
    "subprocess": "fill:#1565c0,stroke:#0d47a1,color:#ffffff",
}


def _escape_label(text: str) -> str:
    """转义会破坏 Mermaid 语法的字符（引号用 Mermaid 实体表示，换行折叠为空格）。"""
    return (
        (text or "")
        .replace('"', "#quot;")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _escape_state_label(text: str) -> str:
    """stateDiagram 迁移标签转义（双引号替换为单引号，换行折叠为空格）。"""
    return (
        (text or "")
        .replace('"', "'")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _normalize_direction(direction: str | None) -> str:
    chosen = (direction or "TB").strip().upper()
    if chosen == "TD":
        chosen = "TB"
    return chosen if chosen in ("TB", "BT", "LR", "RL") else "TB"


def graph_to_mermaid(graph: GraphJSON, direction: str | None = None) -> str:
    """将 GraphJSON 渲染为 Mermaid 源码（自动按 diagram 字段选择渲染器）。

    :param direction: 覆盖布局方向（TB / LR / BT / RL）；缺省用 graph.direction
    """
    chosen = _normalize_direction(direction or graph.direction)
    if graph.diagram == "state":
        return _render_state_diagram(graph, chosen)
    return _render_flowchart(graph, chosen)


# ----------------------------------------------------------------------
# 流程图（含泳道）
# ----------------------------------------------------------------------
def _node_line(node: GraphNode, indent: str = "    ") -> str:
    left, right = _SHAPES.get(node.type, _SHAPES["process"])
    return f"{indent}{node.id}{left}\"{_escape_label(node.label)}\"{right}"


def _render_flowchart(graph: GraphJSON, direction: str) -> str:
    lines = [f"flowchart {direction}"]

    # 泳道分组：任一节点带 lane 字段时，按 lane 归入 subgraph
    lanes: list[str] = []
    lane_members: dict[str, list[GraphNode]] = {}
    for node in graph.nodes:
        if node.lane:
            if node.lane not in lane_members:
                lane_members[node.lane] = []
                lanes.append(node.lane)
            lane_members[node.lane].append(node)

    if lanes:
        for index, lane in enumerate(lanes):
            lines.append(f"    subgraph L{index}[\"{_escape_label(lane)}\"]")
            for node in lane_members[lane]:
                lines.append(_node_line(node, indent="        "))
            lines.append("    end")
        # 未标注泳道的节点保留在顶层，避免丢失
        for node in graph.nodes:
            if not node.lane:
                lines.append(_node_line(node))
    else:
        for node in graph.nodes:
            lines.append(_node_line(node))

    for edge in graph.edges:
        text = _escape_label(edge.label or edge.condition or "")
        if text:
            lines.append(f'    {edge.from_} -->|"{text}"| {edge.to}')
        else:
            lines.append(f"    {edge.from_} --> {edge.to}")

    # 按节点类型上色（只输出实际用到的 classDef）
    for class_name, types in _CLASS_GROUPS.items():
        member_ids = [node.id for node in graph.nodes if node.type in types]
        if member_ids:
            lines.append(f"    classDef {class_name} {_CLASS_STYLES[class_name]}")
            lines.append(f"    class {','.join(member_ids)} {class_name}")

    return "\n".join(lines)


# ----------------------------------------------------------------------
# 状态机图
# ----------------------------------------------------------------------
def _render_state_diagram(graph: GraphJSON, direction: str) -> str:
    # stateDiagram 的 direction 常用 TB / LR，其余方向回落为 TB
    state_direction = direction if direction in ("TB", "LR") else "TB"
    lines = ["stateDiagram-v2", f"    direction {state_direction}"]

    node_types = {node.id: node.type for node in graph.nodes}

    # 非起止状态显式声明标签别名（stateDiagram 节点名不便带中文/空格）
    for node in graph.nodes:
        if node.type in ("start", "end"):
            continue
        label = _escape_state_label(node.label)
        if label and label != node.id:
            lines.append(f'    state "{label}" as {node.id}')

    for edge in graph.edges:
        src, dst = edge.from_, edge.to
        if node_types.get(src) == "end":
            continue  # 终止状态不应有出边，忽略脏数据
        text = _escape_state_label(edge.label or edge.condition or "")
        suffix = f": {text}" if text else ""

        src_is_start = node_types.get(src) == "start"
        dst_is_end = node_types.get(dst) == "end"
        if src_is_start and dst_is_end:
            lines.append(f"    [*] --> [*]{suffix}")
        elif dst_is_end:
            lines.append(f"    {src} --> [*]{suffix}")
        elif src_is_start:
            lines.append(f"    [*] --> {dst}{suffix}")
        else:
            lines.append(f"    {src} --> {dst}{suffix}")

    return "\n".join(lines)
