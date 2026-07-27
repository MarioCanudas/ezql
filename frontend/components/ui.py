from collections.abc import Callable
from typing import Any

import pandas as pd
import streamlit as st


MISSING_VALUE = "Dato no disponible"


def resolve_metadata_template(value: Any, metadata: dict[str, Any] | None) -> Any:
    """Resolve references without modifying the persisted message payload."""
    if not isinstance(value, str) or "{{meta." not in value:
        return value
    import re

    metadata = metadata or {}

    def replace(match: re.Match[str]) -> str:
        entry = metadata.get(match.group(1))
        if not isinstance(entry, dict) or entry.get("display") is None:
            return MISSING_VALUE
        return str(entry["display"])

    return re.sub(r"\{\{meta\.([A-Za-z0-9_.-]+)\}\}", replace, value)


def role_to_streamlit(role: str) -> str:
    if role == "agent":
        return "assistant"
    return role


def render_agent_response(response_json: dict[str, Any]) -> None:
    """Itera sobre la lista de bloques e invoca el componente de Streamlit adecuado."""
    blocks = response_json.get("blocks", [])
    metadata = response_json.get("metadata")
    if not blocks:
        text = response_json.get("summary") or response_json.get("text")
        if text:
            st.markdown(resolve_metadata_template(text, metadata))
        return

    i = 0
    while i < len(blocks):
        block = blocks[i]
        if not isinstance(block, dict):
            i += 1
            continue

        block_type = block.get("type")

        # Agrupación dinámica de métricas consecutivas en columnas
        if block_type == "metric":
            metric_group = []
            while i < len(blocks) and isinstance(blocks[i], dict) and blocks[i].get("type") == "metric":
                metric_group.append(blocks[i])
                i += 1

            cols = st.columns(len(metric_group))
            for idx, m in enumerate(metric_group):
                cols[idx].metric(
                    label=m.get("label", ""),
                    value=resolve_metadata_template(m.get("value", ""), metadata),
                    delta=resolve_metadata_template(m.get("delta"), metadata),
                )
            continue  # Continuar sin incrementar i nuevamente

        elif block_type == "markdown":
            st.markdown(resolve_metadata_template(block.get("content", ""), metadata))

        elif block_type == "table":
            if block.get("title"):
                st.caption(f"**{block['title']}**")
            data = block.get("data", [])
            df = pd.DataFrame(data)
            columns = block.get("columns")
            if columns and not df.empty:
                valid_cols = [col for col in columns if col in df.columns]
                if valid_cols:
                    df = df[valid_cols]
            st.dataframe(df, hide_index=True, width="stretch")

        elif block_type == "chart":
            if block.get("title"):
                st.subheader(block["title"])

            df = pd.DataFrame(block.get("data", []))
            chart_type = block.get("chart_type", "bar")
            x_axis = block.get("x_axis")
            y_axis = block.get("y_axis")

            if not df.empty and x_axis and y_axis:
                if chart_type == "bar":
                    st.bar_chart(df, x=x_axis, y=y_axis)
                elif chart_type == "line":
                    st.line_chart(df, x=x_axis, y=y_axis)
                elif chart_type == "area":
                    st.area_chart(df, x=x_axis, y=y_axis)
                elif chart_type == "scatter":
                    st.scatter_chart(df, x=x_axis, y=y_axis)

        elif block_type in {"trend", "outliers"}:
            _render_legacy_block(block)

        i += 1


def _render_legacy_block(block: dict[str, Any]) -> None:
    """Render historical block types without making them part of the new contract."""
    if block.get("type") == "trend":
        st.info(
            f"**Tendencia temporal**: {block.get('metric', '')} - "
            f"Dirección: {block.get('direction', '')}"
        )
        if (pct := block.get("pct_change")) is not None:
            st.caption(f"Cambio: {pct}%")
    elif block.get("type") == "outliers":
        st.info(f"**Anomalías**: {block.get('message', '')}")


def render_chat_messages(messages: list[dict[str, Any]]) -> None:
    for message in messages:
        role = role_to_streamlit(message["role"])
        content = message["content"]
        with st.chat_message(role):
            blocks = content.get("blocks")
            if blocks:
                render_agent_response({"blocks": blocks, "summary": content.get("text"), "metadata": content.get("metadata")})
            else:
                text = content.get("text", "")
                if text:
                    st.markdown(resolve_metadata_template(text, content.get("metadata")))
                data = content.get("data") or []
                if data:
                    render_agent_response({"blocks": data, "summary": text, "metadata": content.get("metadata")})


def select_from_options(
    label: str,
    options: list[int],
    format_func: Callable[[int], str],
    key: str,
    default_id: int | None,
):
    if not options:
        st.selectbox(label, options=[], key=key, disabled=True)
        return None
    if default_id not in options:
        default_id = options[0]
    index = options.index(default_id)
    return st.selectbox(
        label,
        options=options,
        index=index,
        format_func=format_func,
        key=key,
    )


def render_empty_state(
    title: str,
    body: str,
    icon: str = ":material/info:",
) -> None:
    st.info(f"**{title}**\n\n{body}", icon=icon)


def render_stat_cards(stats: list[tuple[str, str | int, str | None]]) -> None:
    columns = st.columns(len(stats) or 1)
    for column, (label, value, help_text) in zip(columns, stats, strict=False):
        column.metric(label=label, value=value, help=help_text)


def display_table(
    rows: list[dict[str, Any]],
    *,
    empty_message: str,
    column_order: list[str] | None = None,
) -> None:
    if not rows:
        st.info(empty_message)
        return

    if column_order:
        rows = [
            {column: row.get(column) for column in column_order if column in row}
            for row in rows
        ]
    st.dataframe(rows, hide_index=True, width="stretch")


def format_model(model: dict[str, Any]) -> str:
    company = model.get("company") or "Proveedor"
    return f"{model['name']} · {company}"
