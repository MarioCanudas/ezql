from typing import Any

import streamlit as st
from components import ui


@st.dialog("Configurar chat", width="medium", on_dismiss="rerun")
def chat_settings_dialog(
    *,
    chats: list[dict[str, Any]],
    databases: list[dict[str, Any]],
    models: list[dict[str, Any]],
) -> None:
    st.caption("Cambia la conversación activa y el contexto para crear nuevos chats.")

    with st.form("chat_settings_form"):
        selected_chat_id = None
        selected_db_id = None
        selected_model_id = None

        if chats:
            chat_map = {
                chat["id"]: f"{chat['title']} · {chat.get('message_count', 0)} mensajes"
                for chat in chats
            }
            selected_chat_id = st.selectbox(
                "Chat activo",
                options=list(chat_map.keys()),
                index=0,
                format_func=lambda value: chat_map[value],
            )
        else:
            st.info("Todavía no tienes chats.")

        if databases:
            db_map = {database["id"]: database["name"] for database in databases}
            selected_db_id = st.selectbox(
                "Base por defecto",
                options=list(db_map.keys()),
                index=0,
                format_func=lambda value: db_map[value],
            )
        else:
            st.info("Agrega una base de datos para crear chats.")

        if models:
            model_map = {model["id"]: ui.format_model(model) for model in models}
            selected_model_id = st.selectbox(
                "Modelo por defecto",
                options=list(model_map.keys()),
                index=0,
                format_func=lambda value: model_map[value],
            )
        else:
            st.info("Agrega un modelo para crear chats.")

        submitted = st.form_submit_button("Guardar", type="primary")

    if not submitted:
        return

    if selected_chat_id is not None:
        st.session_state["selected_chat_id"] = selected_chat_id
    if selected_db_id is not None:
        st.session_state["selected_db_id"] = selected_db_id
    if selected_model_id is not None:
        st.session_state["selected_model_id"] = selected_model_id
    st.rerun()
