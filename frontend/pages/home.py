from typing import Any

import streamlit as st
from components import api_client, state, ui
from dialogs.chat_dialog import create_chat_dialog
from dialogs.database_dialog import create_database_dialog
from dialogs.profile_dialog import profile_dialog


def _find_by_id(
    rows: list[dict[str, Any]], row_id: int | None
) -> dict[str, Any] | None:
    if row_id is None:
        return None
    return next((row for row in rows if row["id"] == row_id), None)


def _api_key_summary(status: dict[str, Any]) -> str:
    configured = sum(
        [
            bool(status.get("has_openai_api_key")),
            bool(status.get("has_deepseek_api_key")),
        ]
    )
    if configured == 0:
        return "Sin API keys configuradas"
    if configured == 1:
        return "1 proveedor configurado"
    return "2 proveedores configurados"


def render() -> None:
    state.init_state()
    if not st.session_state.logged_in:
        st.warning("Inicia sesión para ver tu panel.")
        return

    try:
        users = api_client.list_users()
        current_user = state.current_user(users)
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    if current_user is None:
        state.logout()
        st.rerun()

    user_id = current_user["id"]
    try:
        databases = api_client.list_databases(user_id=user_id)
        chats = api_client.list_chats(user_id=user_id)
        key_status = api_client.get_user_api_key_status(user_id)
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    st.title(f"Hola, {current_user['name']}")
    st.caption("Este es el resumen de tu espacio de trabajo en EzQL.")

    ui.render_stat_cards(
        [
            ("Chats", len(chats), "Conversaciones creadas por tu usuario"),
            ("Bases de datos", len(databases), "Conexiones disponibles para analizar"),
            ("API keys", _api_key_summary(key_status), "Configuración de proveedores"),
        ]
    )

    st.divider()

    actions = st.columns(3)
    if actions[0].button("Nuevo chat", type="primary", use_container_width=True):
        try:
            models = api_client.list_models()
        except api_client.ApiError as exc:
            st.error(str(exc))
            return
        create_chat_dialog(
            user_id=user_id,
            databases=databases,
            models=models,
            default_db_id=st.session_state.get("selected_db_id"),
            default_model_id=st.session_state.get("selected_model_id"),
        )
    if actions[1].button("Agregar base de datos", use_container_width=True):
        try:
            engines = api_client.list_engines()
        except api_client.ApiError as exc:
            st.error(str(exc))
            return
        create_database_dialog(users=users, engines=engines, default_user_id=user_id)
    if actions[2].button("Configurar API keys", use_container_width=True):
        profile_dialog(user_id=user_id)

    st.divider()

    st.subheader("Chats recientes")
    if not chats:
        ui.render_empty_state(
            "Sin chats todavía",
            "Crea un chat para empezar a hacer preguntas sobre tus datos.",
            icon=":material/chat:",
        )
    else:
        chat_rows = []
        for chat in chats[:8]:
            database = _find_by_id(databases, chat.get("db_id"))
            chat_rows.append(
                {
                    "título": chat["title"],
                    "base": database["name"] if database else "-",
                    "mensajes": chat.get("message_count", 0),
                }
            )
        ui.display_table(
            chat_rows,
            empty_message="No hay chats.",
            column_order=["título", "base", "mensajes"],
        )

    st.divider()

    st.subheader("Tus bases de datos")
    if not databases:
        ui.render_empty_state(
            "Sin bases registradas",
            "Agrega una base de datos para que EzQL pueda analizarla.",
            icon=":material/database:",
        )
    else:
        database_rows = [{"nombre": database["name"]} for database in databases]
        ui.display_table(
            database_rows,
            empty_message="No hay bases de datos.",
            column_order=["nombre"],
        )
