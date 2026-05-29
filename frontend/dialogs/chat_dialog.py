from typing import Any

import streamlit as st
from components import api_client, ui


@st.dialog("Nuevo chat", width="medium", on_dismiss="rerun")
def create_chat_dialog(
    *,
    user_id: int,
    databases: list[dict[str, Any]],
    models: list[dict[str, Any]],
    default_db_id: int | None = None,
    default_model_id: int | None = None,
) -> None:
    st.caption("Elige una base de datos y un modelo para iniciar el análisis.")

    if not databases:
        st.warning("Registra una base de datos antes de crear un chat.")
        return
    if not models:
        st.warning("Registra un modelo antes de crear un chat.")
        return

    db_map = {database["id"]: database["name"] for database in databases}
    model_map = {model["id"]: ui.format_model(model) for model in models}
    db_options = list(db_map.keys())
    model_options = list(model_map.keys())
    db_index = db_options.index(default_db_id) if default_db_id in db_options else 0
    model_index = (
        model_options.index(default_model_id)
        if default_model_id in model_options
        else 0
    )

    with st.form("create_chat_dialog_form"):
        title = st.text_input("Título", value="Nuevo análisis", max_chars=50)
        db_id = st.selectbox(
            "Base de datos",
            options=db_options,
            index=db_index,
            format_func=lambda value: db_map[value],
        )
        model_id = st.selectbox(
            "Modelo",
            options=model_options,
            index=model_index,
            format_func=lambda value: model_map[value],
        )
        submitted = st.form_submit_button("Crear chat", type="primary")

    if not submitted:
        return

    if db_id is None or model_id is None:
        st.warning("Selecciona base de datos y modelo.")
        return

    try:
        chat = api_client.create_chat(
            title=title.strip() or "Nuevo análisis",
            user_id=user_id,
            db_id=db_id,
            model_id=model_id,
        )
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    api_client.list_chats.clear()
    st.session_state["selected_chat_id"] = chat["id"]
    st.session_state["selected_db_id"] = db_id
    st.session_state["selected_model_id"] = model_id
    st.session_state["chat_messages"] = []
    st.success("Chat creado.")
    st.rerun()
