"""冒烟测试：不调用 LLM，仅验证本地逻辑（模型校验 / JSON 提取 / Mermaid 渲染 / 提示词）。

运行：python scripts/smoke_test.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from llm_graph.config import Settings
from llm_graph.graph import GraphJSON, extract_json_object, parse_graph
from llm_graph.mermaid import graph_to_mermaid
from llm_graph.prompt import GRAPH_TYPES, build_generation_prompt, build_optimize_prompt

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    # 1. 加载内置示例并通过 pydantic 校验
    sample = json.loads((ROOT / "examples" / "sample_graph.json").read_text(encoding="utf-8"))
    graph = GraphJSON.model_validate(sample)
    assert graph.title == "用户登录流程"
    assert len(graph.nodes) == 8 and len(graph.edges) == 10

    # 2. 容错解析：带 markdown 代码块与前后杂讯的模型输出
    raw = f"好的，以下是生成的流程图：\n```json\n{json.dumps(sample, ensure_ascii=False)}\n```\n希望对你有帮助！"
    parsed = parse_graph(raw)
    assert parsed.title == graph.title

    # 3. 结构校验：边引用不存在的节点应报错
    bad = dict(sample, edges=[{"from": "n1", "to": "ghost"}])
    try:
        GraphJSON.model_validate(bad)
        raise AssertionError("应当校验失败")
    except Exception as exc:
        assert "不存在的节点" in str(exc)

    # 4. 类型归一化：未知类型回落到 process（同时清空边，避免引用校验干扰本用例）
    assert GraphJSON.model_validate(
        dict(sample, nodes=[{"id": "a", "label": "x", "type": "Whatever"}], edges=[])
    ).nodes[0].type == "process"

    # 5. Mermaid 渲染
    code = graph_to_mermaid(graph)
    assert code.startswith("flowchart TB")
    assert 'n3{"验证码是否正确"}' in code
    assert '-->|"通过"|' in code
    assert "classDef startEnd" in code
    assert graph_to_mermaid(graph, direction="LR").startswith("flowchart LR")

    # 6. 括号配对提取：字符串内的花括号不应干扰
    tricky = '前言 {"a": "包含 } 与 { 的字符串", "b": {"c": 1}} 后记'
    assert extract_json_object(tricky)["b"] == {"c": 1}

    # 7. 提示词构建
    system, user = build_generation_prompt("测试流程", "workflow")
    assert "GraphJSON" in system and "测试流程" in user
    system2, user2 = build_optimize_prompt(graph, "增加重试节点")
    assert "改进" in system2 and "增加重试节点" in user2

    # 8. 配置默认值
    settings = Settings()
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-flash"
    assert settings.thinking_mode is None

    # 9. 图表类型清单：auto + 7 种，auto 排第一（默认）
    assert list(GRAPH_TYPES)[0] == "auto" and len(GRAPH_TYPES) == 8

    # 9.1 auto 提示词模板可用，且包含类型判断指引
    auto_system, auto_user = build_generation_prompt("测试流程", "auto")
    assert "自动判断" in auto_system and "simple" in auto_user

    # 10. 泳道图渲染：lane → subgraph 分组
    lane_graph = GraphJSON.model_validate(
        dict(
            sample,
            nodes=[
                {"id": "a", "label": "提交申请", "type": "process", "lane": "员工"},
                {"id": "b", "label": "是否通过", "type": "decision", "lane": "主管"},
                {"id": "c", "label": "打款", "type": "end", "lane": "财务"},
            ],
            edges=[
                {"from": "a", "to": "b"},
                {"from": "b", "to": "c", "label": "通过"},
            ],
        )
    )
    lane_code = graph_to_mermaid(lane_graph)
    assert 'subgraph L0["员工"]' in lane_code
    assert 'subgraph L1["主管"]' in lane_code
    assert "    end" in lane_code
    assert '-->|"通过"|' in lane_code

    # 11. 状态机图渲染：stateDiagram-v2 + 起止伪状态
    state_graph = GraphJSON.model_validate(
        dict(
            sample,
            diagram="state",
            nodes=[
                {"id": "s0", "label": "初始", "type": "start"},
                {"id": "s1", "label": "待支付", "type": "process"},
                {"id": "s2", "label": "已签收", "type": "end"},
            ],
            edges=[
                {"from": "s0", "to": "s1"},
                {"from": "s1", "to": "s2", "label": "确认收货"},
            ],
        )
    )
    state_code = graph_to_mermaid(state_graph)
    assert state_code.startswith("stateDiagram-v2")
    assert 'state "待支付" as s1' in state_code
    assert "[*] --> s1" in state_code
    assert "s1 --> [*]: 确认收货" in state_code

    # 12. diagram 字段归一化：未知值回落为 flowchart
    assert GraphJSON.model_validate(dict(sample, diagram="whatever")).diagram == "flowchart"

    # 13. 模型自选类型字段：合法值保留、非法值置空、缺省为 None
    assert GraphJSON.model_validate(dict(sample, type="swimlane")).type == "swimlane"
    assert GraphJSON.model_validate(dict(sample, type=" nonsense ")).type is None
    assert GraphJSON.model_validate(sample).type is None

    print("SMOKE OK")
    print("-" * 60)
    print(code)


if __name__ == "__main__":
    main()
