"""
LLM Graph → Mermaid — Streamlit 应用入口。

输入自然语言描述，调用 DeepSeek（OpenAI 兼容）模型生成结构化 GraphJSON，
并实时渲染为 Mermaid 流程图。

启动方式：
    streamlit run app.py
"""

from __future__ import annotations

import html
import json
import pathlib

import streamlit as st
import streamlit.components.v1 as components

from llm_graph.client import DeepSeekClient, LLMError
from llm_graph.config import Settings
from llm_graph.graph import GraphJSON, parse_graph
from llm_graph.mermaid import graph_to_mermaid
from llm_graph.prompt import GRAPH_TYPES, build_generation_prompt, build_optimize_prompt

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
MERMAID_THEMES = ["default", "neutral", "dark", "forest"]
MODEL_PRESETS = ["deepseek-flash", "deepseek-v4-pro", "自定义…"]

EXAMPLE_PROMPTS = [
    {"label": "➕ 简单流程", "type": "simple", "text": "用户网购下单：浏览商品、加入购物车、提交订单、支付、发货。"},
    {"label": "🧾 报销泳道", "type": "swimlane", "text": "差旅报销流程：员工提交报销单，直属上级审批，金额超过 5000 元需财务总监复核，财务打款；任一环节驳回都退回申请人修改后重新提交。"},
    {"label": "🔄 订单状态", "type": "state", "text": "电商订单的状态流转：待支付、已支付、配送中、已签收、已取消；超过 30 分钟未支付自动取消。"},
    {"label": "🔐 用户登录", "type": "workflow", "text": "用户输入账号密码和验证码登录，系统先校验验证码，再校验密码；全部通过则登录成功跳转首页，连续失败 5 次锁定账号 30 分钟。"},
    {"label": "📊 日志管道", "type": "pipeline", "text": "日志采集管道：应用日志经 Kafka 汇聚，清洗服务过滤无效数据后写入 HDFS 归档，同时 Flink 实时计算生成业务指标，异常日志进入告警队列通知值班人员。"},
]

st.set_page_config(
    page_title="LLM Graph → Mermaid",
    page_icon="🕸️",
    layout="wide",
    menu_items={
        "About": "LLM Graph → Mermaid · 自然语言一键生成 Mermaid 流程图（DeepSeek 驱动）",
    },
)


# ---------------------------------------------------------------------------
# 会话状态
# ---------------------------------------------------------------------------
def _init_session_state() -> None:
    for key, value in {
        "graph": None,             # 最近一次生成的 GraphJSON
        "raw_output": "",          # 最近一次模型原始输出
        "mermaid_override": None,  # 手动编辑过的 Mermaid 源码（优先级高于 graph）
        "user_input": "",          # 流程描述输入框
        "graph_type": "auto",      # 图表类型（默认由模型自动判断）
        "is_sample": False,        # 当前展示的是否为内置示例
    }.items():
        st.session_state.setdefault(key, value)


def _load_sample_graph() -> None:
    """首次进入时加载内置示例，给用户一个直观的初始界面。"""
    if st.session_state.graph is not None:
        return
    sample_path = pathlib.Path(__file__).parent / "examples" / "sample_graph.json"
    try:
        data = json.loads(sample_path.read_text(encoding="utf-8"))
        st.session_state.graph = GraphJSON.model_validate(data)
        st.session_state.is_sample = True
    except Exception:  # 示例缺失或非法不应阻塞应用
        pass


# ---------------------------------------------------------------------------
# 侧边栏
# ---------------------------------------------------------------------------
def _render_sidebar() -> tuple[Settings, str, str]:
    """渲染侧边栏，返回 (运行配置, Mermaid 主题, 布局方向)。"""
    st.sidebar.header("⚙️ 模型设置")
    defaults = Settings.from_env()

    with st.sidebar.expander("🔗 连接配置", expanded=not defaults.has_key):
        st.caption("默认对接 DeepSeek 开放平台，兼容任意 OpenAI 协议接口")
        api_key = st.text_input(
            "API Key",
            value=defaults.api_key,
            type="password",
            help="DeepSeek 平台的 sk-… 密钥；也可通过环境变量 DEEPSEEK_API_KEY 配置",
        )
        base_url = st.text_input(
            "Base URL",
            value=defaults.base_url,
            help="DeepSeek 官方：https://api.deepseek.com\n火山方舟：https://ark.cn-beijing.volces.com/api/v3",
        )
        default_preset = defaults.model if defaults.model in MODEL_PRESETS else "自定义…"
        preset = st.selectbox(
            "模型预设",
            MODEL_PRESETS,
            index=MODEL_PRESETS.index(default_preset),
            help="deepseek-flash = DeepSeek-V4.1-Flash（当前主力，1M 上下文）；deepseek-v4-pro = DeepSeek-V4-Pro",
        )
        custom_model = st.text_input(
            "自定义模型名（填写后优先）",
            value=defaults.model if preset == "自定义…" else "",
            help="例如火山方舟的 ep-xxxx 接入点，或 SiliconFlow 的 deepseek-ai/DeepSeek-V3",
        )

    temperature = st.sidebar.slider(
        "Temperature（创造性）", 0.0, 1.5, defaults.temperature, 0.1,
        help="越低越严谨，越高越发散；生成结构化 JSON 建议 ≤ 1.0",
    )
    max_tokens = st.sidebar.slider(
        "Max Tokens（输出上限）", 512, 8192, defaults.max_tokens, 256,
        help="输出被截断会导致 JSON 不完整，失败时可调大后重试",
    )
    thinking_label = st.sidebar.selectbox(
        "思考模式（DeepSeek V4 专属）",
        ["关闭（更快更省，推荐）", "开启（深度推理）", "跟随模型默认"],
        index={False: 0, True: 1, None: 2}[defaults.thinking_mode],
        help="deepseek-flash 默认开启思考模式，本应用生成结构化 JSON 通常无需思考；"
        "非 DeepSeek 平台建议选「跟随模型默认」以避免参数不兼容",
    )
    thinking_map = {
        "关闭（更快更省，推荐）": False,
        "开启（深度推理）": True,
        "跟随模型默认": None,
    }

    st.sidebar.divider()
    st.sidebar.subheader("🎨 渲染设置")
    theme = st.sidebar.selectbox("Mermaid 主题", MERMAID_THEMES)
    direction_label = st.sidebar.radio("布局方向", ["上下（TB）", "左右（LR）"])
    direction = "LR" if direction_label.startswith("左右") else "TB"

    st.sidebar.divider()
    st.sidebar.markdown(
        "[🔑 获取 DeepSeek API Key](https://platform.deepseek.com/api_keys)  \n"
        "[📖 DeepSeek API 文档](https://api-docs.deepseek.com/)"
    )

    custom_model_name = custom_model.strip() or (defaults.model if preset == "自定义…" else preset)
    settings = Settings(
        api_key=api_key.strip(),
        base_url=base_url.strip() or defaults.base_url,
        model=custom_model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        thinking_mode=thinking_map[thinking_label],
    )
    return settings, theme, direction


# ---------------------------------------------------------------------------
# 生成 / 优化
# ---------------------------------------------------------------------------
def _handle_parse_failure(raw: str, exc: ValueError) -> None:
    st.error(f"❌ 模型输出解析失败：{exc}")
    with st.expander("查看模型原始输出", expanded=True):
        st.code(raw or "（空输出）", language="text")


def _run_generation(settings: Settings, user_input: str, graph_type: str) -> None:
    """执行「描述 → GraphJSON」生成流程。"""
    try:
        client = DeepSeekClient(settings)
    except LLMError as exc:
        st.error(f"❌ {exc}")
        return

    system, user = build_generation_prompt(user_input, graph_type)
    raw = ""
    try:
        with st.status("🤖 正在生成流程图…", expanded=True) as status:
            st.caption(f"模型 `{settings.model}` · `{settings.base_url}`")
            if st.session_state.get("stream_output", True):
                raw = st.write_stream(client.chat_stream(system, user))
            else:
                with st.spinner("等待模型返回…"):
                    raw = "".join(client.chat_stream(system, user))
            status.update(label="✅ 生成完成", state="complete", expanded=False)
    except LLMError as exc:
        st.error(f"❌ 调用失败：{exc}")
        return

    try:
        graph = parse_graph(raw)
    except ValueError as exc:
        _handle_parse_failure(raw, exc)
        return

    st.session_state.graph = graph
    st.session_state.raw_output = raw
    st.session_state.mermaid_override = None
    st.session_state.is_sample = False
    auto_note = ""
    if graph_type == "auto" and graph.type:
        auto_note = f"（自动判断：{GRAPH_TYPES.get(graph.type, graph.type)}）"
    st.toast(f"「{graph.title}」生成成功{auto_note}：{len(graph.nodes)} 节点 / {len(graph.edges)} 边", icon="✅")


def _run_optimize(settings: Settings, graph: GraphJSON, improvements: str) -> None:
    """执行「改进要求 → 新 GraphJSON」优化流程。"""
    try:
        client = DeepSeekClient(settings)
    except LLMError as exc:
        st.error(f"❌ {exc}")
        return

    system, user = build_optimize_prompt(graph, improvements)
    raw = ""
    try:
        with st.status("🔧 正在优化图表…", expanded=True) as status:
            st.caption(f"模型 `{settings.model}` · `{settings.base_url}`")
            if st.session_state.get("stream_output", True):
                raw = st.write_stream(client.chat_stream(system, user))
            else:
                with st.spinner("等待模型返回…"):
                    raw = "".join(client.chat_stream(system, user))
            status.update(label="✅ 优化完成", state="complete", expanded=False)
    except LLMError as exc:
        st.error(f"❌ 调用失败：{exc}")
        return

    try:
        new_graph = parse_graph(raw)
    except ValueError as exc:
        _handle_parse_failure(raw, exc)
        return

    st.session_state.graph = new_graph
    st.session_state.raw_output = raw
    st.session_state.mermaid_override = None
    st.session_state.is_sample = False
    st.toast("图表优化完成", icon="🔧")


# ---------------------------------------------------------------------------
# 结果渲染
# ---------------------------------------------------------------------------
def render_mermaid(code: str, theme: str, height: int = 560) -> None:
    """通过 iframe + Mermaid.js CDN 渲染流程图；CDN 不可达时给出降级提示。"""
    page = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 12px; background: transparent; }}
  .mermaid {{ display: flex; justify-content: center; }}
  #fallback {{ display: none; font-family: sans-serif; color: #b91c1c; padding: 8px; line-height: 1.6; }}
</style>
</head>
<body>
<div class="mermaid" id="diagram">
{html.escape(code)}
</div>
<div id="fallback">⚠️ Mermaid.js 渲染脚本加载失败（可能无法访问 CDN）。<br>图表源码请切换到「Mermaid 代码」标签页查看。</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
  if (window.mermaid) {{
    mermaid.initialize({{
      startOnLoad: true,
      theme: "{theme}",
      securityLevel: "loose",
      flowchart: {{ useMaxWidth: true, htmlLabels: true }}
    }});
  }} else {{
    document.getElementById("diagram").style.display = "none";
    document.getElementById("fallback").style.display = "block";
  }}
</script>
</body>
</html>"""
    components.html(page, height=height, scrolling=True)


def _render_result(theme: str, direction: str) -> None:
    """右栏：可视化、代码编辑与导出。"""
    st.subheader("📊 可视化结果")
    graph: GraphJSON | None = st.session_state.graph
    override: str | None = st.session_state.mermaid_override

    if graph is None and not override:
        st.info("👈 在左侧输入自然语言描述，点击「🚀 生成图表」开始")
        return

    if override:
        code = override
    elif graph is not None:
        code = graph_to_mermaid(graph, direction=direction)
    else:
        return

    if st.session_state.is_sample and graph is not None:
        st.caption("📌 当前展示的是内置示例，在左侧生成后自动替换")
    elif graph is not None:
        type_label = GRAPH_TYPES.get(graph.type, "") if graph.type else ""
        type_part = f" · 类型：{type_label}（{graph.type}）" if type_label else ""
        st.caption(f"**{graph.title}**{type_part} · {len(graph.nodes)} 个节点 · {len(graph.edges)} 条边")

    tab_view, tab_mermaid, tab_json, tab_raw = st.tabs(["🖼️ 可视化", "📝 Mermaid 代码", "🧩 GraphJSON", "🗂️ 原始输出"])

    with tab_view:
        render_mermaid(code, theme)

    with tab_mermaid:
        edited = st.text_area("Mermaid 源码（可直接编辑）", value=code, height=320)
        col_apply, col_reset = st.columns(2)
        if col_apply.button("✅ 应用编辑", use_container_width=True, disabled=(edited == code)):
            st.session_state.mermaid_override = edited
            st.rerun()
        if col_reset.button("↩️ 还原为生成结果", use_container_width=True, disabled=(override is None)):
            st.session_state.mermaid_override = None
            st.rerun()

    with tab_json:
        if graph is not None:
            st.json(graph.to_dict())
        else:
            st.caption("当前展示手动编辑的 Mermaid 源码，暂无 GraphJSON")

    with tab_raw:
        if st.session_state.raw_output:
            st.code(st.session_state.raw_output, language="json")
        else:
            st.caption("暂无模型原始输出（当前内容为示例或手动编辑）")

    col_mmd, col_json = st.columns(2)
    col_mmd.download_button("⬇️ 下载 Mermaid（.mmd）", data=code, file_name="graph.mmd", mime="text/plain")
    if graph is not None:
        col_json.download_button(
            "⬇️ 下载 GraphJSON（.json）",
            data=graph.to_json_str(),
            file_name="graph.json",
            mime="application/json",
        )


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
def main() -> None:
    _init_session_state()
    _load_sample_graph()

    settings, theme, direction = _render_sidebar()

    st.title("🕸️ LLM Graph → Mermaid")
    st.caption("输入自然语言描述，调用 DeepSeek 生成结构化 GraphJSON，并实时渲染为 Mermaid 流程图")

    left, right = st.columns([2, 3], gap="large")

    with left:
        st.subheader("① 描述你的流程")
        st.caption("试试示例（自动带上图表类型）：")
        example_cols = st.columns(len(EXAMPLE_PROMPTS))
        for example, col in zip(EXAMPLE_PROMPTS, example_cols):
            if col.button(example["label"], use_container_width=True):
                st.session_state.user_input = example["text"]
                st.session_state.graph_type = example["type"]
                st.rerun()

        graph_type = st.selectbox(
            "图表类型",
            options=list(GRAPH_TYPES),
            format_func=lambda key: f"{GRAPH_TYPES[key]}（{key}）",
            key="graph_type",
        )

        user_input = st.text_area(
            "流程描述",
            height=180,
            key="user_input",
            placeholder="例：用户注册后需要邮箱验证，验证通过则注册成功并登录，"
            "验证失败可重新发送邮件，最多重试 3 次后锁定账号…",
        )
        st.toggle("流式输出", value=True, key="stream_output", help="开启后逐字显示模型生成过程")

        generate_clicked = st.button(
            "🚀 生成图表",
            type="primary",
            use_container_width=True,
            disabled=not user_input.strip(),
        )

        with st.expander("🔧 优化当前图表"):
            improvements = st.text_area(
                "改进要求",
                height=90,
                placeholder="例：在发货前增加库存检查节点；把决策标签改成「通过 / 驳回」…",
            )
            optimize_clicked = st.button(
                "应用优化",
                use_container_width=True,
                disabled=(st.session_state.graph is None or not improvements.strip()),
                help="基于当前图表和改进要求，让模型重新生成",
            )

    # ---- 生成 / 优化（状态与流式输出显示在左栏按钮下方） ----
    if generate_clicked:
        _run_generation(settings, user_input.strip(), graph_type)
    if optimize_clicked:
        current_graph: GraphJSON | None = st.session_state.graph
        if current_graph is not None:
            _run_optimize(settings, current_graph, improvements.strip())

    with right:
        st.subheader("② 查看与导出")
        _render_result(theme, direction)


if __name__ == "__main__":
    main()
