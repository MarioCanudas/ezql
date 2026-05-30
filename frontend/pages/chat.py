from typing import Any

import streamlit as st
from components import api_client, state, ui
from dialogs.chat_settings_dialog import chat_settings_dialog


def _active_chat_title(chats: list[dict[str, Any]], chat_id: int | None) -> str | None:
    if chat_id is None:
        return None
    chat = next((item for item in chats if item["id"] == chat_id), None)
    if not chat:
        return None
    return chat["title"]


def render(chat_id: int | None = None) -> None:
    state.init_state()
    if chat_id is not None:
        st.session_state["selected_chat_id"] = chat_id
    if not st.session_state.logged_in:
        st.warning("Inicia sesión para usar el chat.")
        return

    try:
        users = api_client.list_users()
        models = api_client.list_models()
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
        runtime_databases = api_client.list_runtime_databases(user_id=user["id"])
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
    st.info(
        "Las bases SQLite cargadas son temporales. Si el servidor o la sesión se reinicia, tendrás que volver a crear el chat subiendo la base otra vez.",
        icon=":material/info:",
    )
    st.caption(
        "Nota: por ahora las respuestas se entregan en texto o tablas. Las gráficas todavía no están disponibles."
    )

    active_chat = next((chat for chat in chats if chat["id"] == chat_id), None)
    runtime_db_ids = {db["id"] for db in runtime_databases}
    runtime_db_missing = False
    if active_chat and active_chat.get("runtime_db_id"):
        runtime_db_missing = active_chat["runtime_db_id"] not in runtime_db_ids
        if runtime_db_missing:
            st.warning(
                "Este chat usa una base temporal que ya no está cargada. "
                "Vuelve a crear el chat y sube la base SQLite nuevamente para continuar.",
                icon=":material/warning:",
            )

    if st.button("Configurar chat", type="primary"):
        chat_settings_dialog(chats=chats, databases=databases, models=models)

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

    if prompt := st.chat_input(
        "Escribe tu pregunta sobre los datos", disabled=runtime_db_missing
    ):
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
