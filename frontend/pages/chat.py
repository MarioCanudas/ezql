from typing import Any

import streamlit as st
from components import api_client, state, ui
from dialogs.chat_settings_dialog import chat_settings_dialog
from dialogs.restore_database_dialog import restore_database_dialog


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

    # Check if the associated database is Netflix Titles
    is_netflix_db = False
    netflix_db_id = None
    
    # Try to find the persistent Netflix database ID
    associated_netflix_db = next(
        (d for d in databases if d.get("name", "").strip().casefold() in (
            "netflix titles",
            "netflix_titles",
            "base de prueba netflix",
        )),
        None
    )
    if associated_netflix_db:
        netflix_db_id = associated_netflix_db["id"]

    if active_chat:
        # Check persistent db association
        db_id = active_chat.get("db_id")
        if db_id and str(db_id) == str(netflix_db_id):
            is_netflix_db = True

        # Check runtime db association
        runtime_db_id = active_chat.get("runtime_db_id")
        if runtime_db_id and (runtime_db_id.startswith("sample-") or runtime_db_id == "sample"):
            is_netflix_db = True

        # Cheap fallback: Check in-memory chat title or summary
        if not is_netflix_db:
            title = active_chat.get("title", "").strip().casefold()
            summary = active_chat.get("summary", "").strip().casefold() if active_chat.get("summary") else ""
            netflix_keywords = {
                "netflix", "película", "pelicula", "series", "título", "titulo",
                "director", "duración", "duracion", "lanzamiento", "catálogo", "catalogo"
            }
            if any(kw in title for kw in netflix_keywords) or any(kw in summary for kw in netflix_keywords):
                is_netflix_db = True

        # Diagnostic logs for debugging
        print(
            f"[DEBUG - chat.py] chat_id={active_chat.get('id')} title={active_chat.get('title')} "
            f"db_id={db_id} netflix_db_id={netflix_db_id} is_netflix_db={is_netflix_db} "
            f"runtime_db_id={active_chat.get('runtime_db_id')}"
        )

    if active_chat:
        db_id_to_check = active_chat.get("runtime_db_id")
        db_is_missing = not db_id_to_check or db_id_to_check not in runtime_db_ids

        if db_is_missing:
            if is_netflix_db:
                # AUTOMATIC REACTIVATION
                try:
                    target_runtime_id = db_id_to_check or f"sample-{active_chat['id']}"
                    api_client.register_sample_database(
                        user_id=user["id"],
                        runtime_id=target_runtime_id,
                    )
                    
                    # Update chat in the backend database to link it persistent and runtime-wise
                    updates: dict[str, Any] = {}
                    if not db_id_to_check:
                        updates["runtime_db_id"] = target_runtime_id
                    if not active_chat.get("db_id") and netflix_db_id is not None:
                        updates["db_id"] = netflix_db_id
                    
                    if updates:
                        api_client.update_chat(active_chat["id"], **updates)

                    api_client.list_runtime_databases.clear()
                    st.rerun()
                except api_client.ApiError as exc:
                    st.error(f"Error cargando base de prueba de Netflix: {exc}")
            else:
                # Custom uploaded database is missing
                if db_id_to_check:
                    runtime_db_missing = True
                    st.warning(
                        "Este chat usa una base temporal personalizada que ya no está cargada en el servidor. "
                        "Restaura la base de datos subiendo el archivo SQLite original para continuar la conversación.",
                        icon=":material/warning:",
                    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Configurar chat", type="secondary" if runtime_db_missing else "primary"):
            chat_settings_dialog(
                chats=chats, databases=databases, models=models, active_chat_id=chat_id
            )
    if runtime_db_missing and active_chat:
        with col2:
            if st.button("Restaurar base de datos ⚡", type="primary"):
                restore_database_dialog(
                    runtime_db_id=active_chat["runtime_db_id"],
                    user_id=user["id"]
                )

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
