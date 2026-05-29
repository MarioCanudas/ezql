from collections.abc import Callable
from typing import Any

import streamlit as st


def role_to_streamlit(role: str) -> str:
    if role == "agent":
        return "assistant"
    return role


def render_chat_messages(messages: list[dict[str, Any]]) -> None:
    for message in messages:
        role = role_to_streamlit(message["role"])
        content = message["content"]
        with st.chat_message(role):
            st.markdown(content.get("text", ""))
            data = content.get("data")
            if isinstance(data, list) and data:
                st.dataframe(data, hide_index=True, use_container_width=True)


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
    st.dataframe(rows, hide_index=True, use_container_width=True)


def format_model(model: dict[str, Any]) -> str:
    company = model.get("company") or "Proveedor"
    return f"{model['name']} · {company}"
