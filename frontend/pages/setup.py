from typing import Any

import streamlit as st
from components import api_client, state
from dialogs.database_dialog import create_database_dialog
from dialogs.profile_dialog import profile_dialog


def _names(rows: list[dict[str, Any]], key: str = "name") -> str:
    values = [row[key] for row in rows[:4]]
    if not values:
        return "Sin elementos todavía."
    suffix = "" if len(rows) <= 4 else f" y {len(rows) - 4} más"
    return ", ".join(values) + suffix


def _section_card(
    *,
    title: str,
    description: str,
    count: int,
    preview: str,
    button_label: str | None = None,
    on_click=None,
) -> None:
    with st.container(border=True):
        st.subheader(title)
        st.metric("Total", count)
        st.caption(description)
        st.write(preview)
        if button_label and on_click:
            if st.button(button_label, width="stretch", key=f"action_{title}"):
                on_click()


def render() -> None:
    state.init_state()
    if not st.session_state.logged_in:
        st.warning("Inicia sesión para configurar EzQL.")
        return

    st.title("Configuración")
    st.caption("Configura tus API keys y tus conexiones de datos.")

    try:
        users = api_client.list_users()
        models = api_client.list_models()
        engines = api_client.list_engines()
        databases = api_client.list_databases(user_id=state.get_current_user_id())
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    current_user_id = state.get_current_user_id()
    if current_user_id is None:
        state.logout()
        st.rerun()

    try:
        key_status = api_client.get_user_api_key_status(current_user_id)
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    configured_keys = sum(
        [
            bool(key_status.get("has_openai_api_key")),
            bool(key_status.get("has_deepseek_api_key")),
        ]
    )

    first_row = st.columns(2)
    with first_row[0]:
        _section_card(
            title="Perfil",
            description="API keys privadas para ejecutar los modelos disponibles.",
            count=configured_keys,
            preview="OpenAI y DeepSeek disponibles para configurar.",
            button_label="Configurar API keys",
            on_click=lambda: profile_dialog(user_id=current_user_id),
        )
    with first_row[1]:
        _section_card(
            title="Bases de datos",
            description="Conexiones que puede analizar EzQL.",
            count=len(databases),
            preview=_names(databases),
            button_label="Agregar base de datos",
            on_click=lambda: create_database_dialog(
                users=users,
                engines=engines,
                default_user_id=current_user_id,
            ),
        )

    second_row = st.columns(2)
    with second_row[0]:
        model_preview = (
            ", ".join(f"{model['name']} ({model['company']})" for model in models[:4])
            or "Sin modelos disponibles."
        )
        _section_card(
            title="Modelos disponibles",
            description="Administrados por la aplicación.",
            count=len(models),
            preview=model_preview,
        )
    with second_row[1]:
        _section_card(
            title="Motores SQL disponibles",
            description="Administrados por la aplicación.",
            count=len(engines),
            preview=_names(engines),
        )
