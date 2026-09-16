"""LLM 提示词模板（对应旧版 prompt.ts）。

约定：系统提示词负责定义 GraphJSON 规范与硬性规则，
用户提示词按场景提供描述与建模侧重。

支持的图表类型（GraphType）：
    simple       简单流程图（少量节点、线性主干）
    general      通用流程图
    workflow     工作流程图
    swimlane     泳道图（跨职能流程图，按角色 / 部门 / 系统分泳道）
    state        状态机图（stateDiagram-v2 渲染）
    architecture 系统架构图
    pipeline     数据管道图
"""

from __future__ import annotations

import json
from typing import Literal

from llm_graph.graph import GraphJSON

GraphType = Literal["auto", "simple", "general", "workflow", "swimlane", "state", "architecture", "pipeline"]

# 图表类型的中文展示名（app 主界面使用；dict 顺序即下拉框顺序，auto 排第一作为默认）
GRAPH_TYPES: dict[GraphType, str] = {
    "auto": "自动判断（推荐）",
    "simple": "简单流程图",
    "general": "通用流程图",
    "workflow": "工作流程图",
    "swimlane": "泳道图（跨职能）",
    "state": "状态机图",
    "architecture": "系统架构图",
    "pipeline": "数据管道图",
}

GRAPH_SYSTEM_PROMPT = """你是一个专业的流程图和系统架构设计师。
用户会用自然语言描述一个业务流程、系统架构、工作流程或状态机。
你需要生成一个标准的 GraphJSON 结构来表示这个图。

重要规则：
1. 每个节点必须有唯一的 ID（如 n1, n2, n3...）
2. 节点类型 type 只能是：start（开始）、process（处理）、decision（决策）、end（结束）、subprocess（子流程）
3. 边 edges 连接节点，from / to 必须引用已存在的节点 ID，可以包含 label 标签和 condition 条件
4. 决策节点的出边必须有清晰的条件标签（如"是"、"否"、"成功"、"失败"）
5. 确保图有合理的开始（start）与结束（end）节点，节点规模符合用户场景的要求
6. 只返回一个有效的 JSON 对象，不要包含 markdown 代码块标记、注释或任何其他文本
7. 泳道图：为每个节点添加 "lane" 字段标注所属角色/部门/系统，同一泳道的节点 lane 值必须完全一致
8. 状态机图：将顶层 "diagram" 字段设为 "state"，节点表示状态（type 用 process），start/end 表示初始/终止状态，边 label 表示触发迁移的事件
9. 自动判断模式：如果用户提示要求自动判断，先根据描述特征选择最合适的图表类型（简单线性步骤选 simple，多角色协作选 swimlane，状态迁移选 state，系统组成选 architecture，数据加工选 pipeline，其余选 general 或 workflow），并在 JSON 顶层添加 "type" 字段标注选择（取值：simple / general / workflow / swimlane / state / architecture / pipeline）

生成的 JSON 结构必须严格符合以下格式：
{
  "version": "1.0",
  "title": "流程名称",
  "description": "简要描述",
  "direction": "TB",
  "diagram": "flowchart",
  "type": "workflow",
  "nodes": [
    {"id": "n1", "label": "节点标签", "type": "start", "description": "详细描述（可选）", "lane": "泳道归属（仅泳道图需要，其他图省略）"}
  ],
  "edges": [
    {"from": "n1", "to": "n2", "label": "边的标签（可选）", "condition": "条件表达式（决策分支时使用，可选）"}
  ]
}

其中 direction 为布局方向（"TB" 从上到下 / "LR" 从左到右）；
diagram 为渲染种类（"flowchart" 流程图 / "state" 状态机图），普通流程图保持 "flowchart" 即可；
type 为图表类型标识，自动判断模式下必填，其他模式可省略。"""

_AUTO_USER_PROMPT = """请根据以下描述生成 GraphJSON，并由你判断最合适的图表类型。流程描述如下：

{user_input}

请先按下表判断类型，再按对应类型的建模要求生成：
- 少量步骤的线性流程 → simple（极简，3~7 个节点）
- 常规业务流程 / 带审批环节 → workflow
- 多角色 / 多部门 / 多系统协作 → swimlane（为节点添加 lane 字段）
- 对象状态随事件迁移 → state（diagram 设为 "state"）
- 系统组成与组件交互 → architecture
- 数据采集 / 加工 / 消费 → pipeline

生成时：
1. 在 JSON 顶层添加 "type" 字段，标注你选择的类型（上述英文标识之一）
2. 严格遵循该类型的建模要求与节点规模
3. 只返回 JSON，不要有其他文本"""

_SIMPLE_USER_PROMPT = """生成一个简单流程图。流程描述如下：

{user_input}

请创建一个极简、一目了然的流程图：
- 只保留主干步骤，节点总数控制在 3~7 个
- 最多 1~2 个关键决策分支，没有把握的细节一律省略
- 标签简短精炼（建议不超过 10 个字）
- 有明确的开始（start）和结束（end）"""

_GENERAL_USER_PROMPT = """请根据以下描述生成 GraphJSON：

{user_input}

要求：
1. 识别主要的流程步骤和决策点
2. 合理使用节点类型（开始、处理、决策、结束）
3. 确保流程的逻辑完整性
4. 使用清晰的标签和条件说明
5. 只返回 JSON，不要有其他文本"""

_WORKFLOW_USER_PROMPT = """生成一个工作流程图。流程描述如下：

{user_input}

请创建一个清晰的流程图，包含：
- 触发事件（start 节点）
- 主要的处理步骤（process 节点）
- 条件分支和决策点（decision 节点）
- 流程结束（end 节点）"""

_SWIMLANE_USER_PROMPT = """生成一个泳道图（跨职能流程图）。流程描述如下：

{user_input}

请创建一个泳道图：
- 识别流程中涉及的角色 / 部门 / 系统，划分 2~5 个泳道
- 每个节点必须携带 "lane" 字段，标注其所属泳道；同一泳道的 lane 值完全一致
- 跨泳道的边表示职责交接，并用 label 说明交接条件或产物
- 保持流程开始（start）与结束（end）清晰"""

_STATE_USER_PROMPT = """生成一个状态机图。对象描述如下：

{user_input}

请创建一个状态机图：
- 将顶层 "diagram" 字段设为 "state"
- 节点表示对象可能处于的状态（type 使用 process），"start" 表示初始状态，"end" 表示终止状态
- 边的 label 表示触发状态迁移的事件或条件
- 每个状态都应可达，且不出现无法离开的孤立状态"""

_ARCHITECTURE_USER_PROMPT = """生成一个系统架构图。系统描述如下：

{user_input}

请创建一个架构图，展示：
- 主要组件或服务（process / subprocess 节点）
- 组件间的交互和数据流（edges）
- 系统的输入输出（start / end 节点）
- 关键的架构决策或路由（decision 节点）"""

_PIPELINE_USER_PROMPT = """生成一个数据处理管道图。管道描述如下：

{user_input}

请创建一个数据流图，展示：
- 数据源（start 节点）
- 数据处理步骤（process 节点）
- 数据验证和条件检查（decision 节点）
- 数据输出（end 节点）
- 数据在各步骤间的流向（edges）"""

_TYPE_PROMPTS: dict[GraphType, str] = {
    "auto": _AUTO_USER_PROMPT,
    "simple": _SIMPLE_USER_PROMPT,
    "general": _GENERAL_USER_PROMPT,
    "workflow": _WORKFLOW_USER_PROMPT,
    "swimlane": _SWIMLANE_USER_PROMPT,
    "state": _STATE_USER_PROMPT,
    "architecture": _ARCHITECTURE_USER_PROMPT,
    "pipeline": _PIPELINE_USER_PROMPT,
}

_OPTIMIZE_SYSTEM_PROMPT = """你是流程图建模专家。用户会提供一个现有的 GraphJSON 和改进要求。
你需要返回改进后的 GraphJSON。

重要规则：
1. 保持 GraphJSON 结构与字段名完全一致（version / title / description / direction / diagram / nodes / edges）
2. 节点 ID 保持唯一，调整结构时同步修正所有受影响的边；泳道图的节点保留 / 修正 lane 字段
3. 决策节点的出边必须带条件标签
4. 只返回一个有效的 JSON 对象，不要包含 markdown 代码块标记或任何其他文本"""


def build_generation_prompt(user_input: str, graph_type: GraphType = "auto") -> tuple[str, str]:
    """构建「描述 → GraphJSON」的系统提示词与用户提示词。

    graph_type 为 "auto" 时，由模型自行判断类型并在结果 JSON 的 type 字段标注。
    """
    template = _TYPE_PROMPTS.get(graph_type, _GENERAL_USER_PROMPT)
    return GRAPH_SYSTEM_PROMPT, template.format(user_input=user_input.strip())


def build_optimize_prompt(graph: GraphJSON, improvements: str) -> tuple[str, str]:
    """构建「现有 GraphJSON + 改进要求 → 新 GraphJSON」的提示词。"""
    user_prompt = (
        "以下是现有的 GraphJSON：\n\n"
        f"{graph.to_json_str(indent=2)}\n\n"
        "请根据以下要求进行改进：\n"
        f"{improvements.strip()}\n\n"
        "返回改进后的 GraphJSON（只返回 JSON，不要其他文本）："
    )
    return _OPTIMIZE_SYSTEM_PROMPT, user_prompt


def build_optimize_prompt_from_dict(graph_dict: dict, improvements: str) -> tuple[str, str]:
    """同 build_optimize_prompt，但接受原始字典（便于外部调用）。"""
    user_prompt = (
        "以下是现有的 GraphJSON：\n\n"
        f"{json.dumps(graph_dict, ensure_ascii=False, indent=2)}\n\n"
        "请根据以下要求进行改进：\n"
        f"{improvements.strip()}\n\n"
        "返回改进后的 GraphJSON（只返回 JSON，不要其他文本）："
    )
    return _OPTIMIZE_SYSTEM_PROMPT, user_prompt
