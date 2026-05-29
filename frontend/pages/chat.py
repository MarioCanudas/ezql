from typing import Any

import streamlit as st
from components import api_client, state, ui
from dialogs.chat_dialog import create_chat_dialog
from dialogs.chat_settings_dialog import chat_settings_dialog
from dialogs.database_dialog import create_database_dialog


def _active_chat_title(chats: list[dict[str, Any]], chat_id: int | None) -> str | None:
    if chat_id is None:
        return None
    chat = next((item for item in chats if item["id"] == chat_id), None)
    if not chat:
        return None
    return chat["title"]


def render() -> None:
    state.init_state()
    if not st.session_state.logged_in:
        st.warning("Inicia sesión para usar el chat.")
        return

    try:
        users = api_client.list_users()
        models = api_client.list_models()
        engines = api_client.list_engines()
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    user = state.current_user(users)
    if user is None:
        state.logout()
        st.rerun()

    try:
        databases = api_client.list_databases(user_id=user["id"])
        chats = api_client.list_chats(user_id=user["id"])
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    chat_id = st.session_state.get("selected_chat_id")
    if chat_id not in {chat["id"] for chat in chats}:
        chat_id = chats[0]["id"] if chats else None
        st.session_state["selected_chat_id"] = chat_id

    st.title("Chat")
    active_title = _active_chat_title(chats, chat_id)
    st.caption(active_title or "Crea un chat para empezar a analizar tus datos.")

    actions = st.columns(3)
    if actions[0].button("Configurar chat", type="primary", use_container_width=True):
        chat_settings_dialog(chats=chats, databases=databases, models=models)
    if actions[1].button("Nuevo chat", use_container_width=True):
        create_chat_dialog(
            user_id=user["id"],
            databases=databases,
            models=models,
            default_db_id=st.session_state.get("selected_db_id"),
            default_model_id=st.session_state.get("selected_model_id"),
        )
    if actions[2].button("Agregar base", use_container_width=True):
        create_database_dialog(users=users, engines=engines, default_user_id=user["id"])

    st.divider()

    if not chat_id:
        ui.render_empty_state(
            "Sin chat activo",
            "Crea un chat o registra una base de datos para empezar.",
            icon=":material/chat:",
        )
        return

    try:
        messages = api_client.list_messages(chat_id)
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    st.session_state["chat_messages"] = messages
    ui.render_chat_messages(messages)

    if prompt := st.chat_input("Escribe tu pregunta sobre los datos"):
        with st.status("Analizando tu consulta...", expanded=False):
            try:
                response = api_client.create_reply(
                    chat_id=chat_id,
                    content_text=prompt,
                    user_id=user["id"],
                )
            except api_client.ApiError as exc:
                st.error(str(exc))
                return
        st.session_state["chat_messages"].extend(
            [response["user_message"], response["assistant_message"]]
        )
        st.rerun()
