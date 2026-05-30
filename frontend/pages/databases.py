from typing import Any

import streamlit as st
from components import api_client, state, ui


def _related_chats(
    chats: list[dict[str, Any]], database_id: int
) -> list[dict[str, Any]]:
    return [chat for chat in chats if chat.get("db_id") == database_id]


def render() -> None:
    state.init_state()
    if not st.session_state.logged_in:
        st.warning("Inicia sesión para ver tus bases de datos.")
        return

    user_id = state.get_current_user_id()
    if user_id is None:
        state.logout()
        st.rerun()

    st.title("Bases de datos")
    st.caption("Consulta tus conexiones y los chats relacionados a cada una.")

    try:
        databases = api_client.list_databases(user_id=user_id)
        chats = api_client.list_chat_summaries(user_id=user_id)
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    if not databases:
        ui.render_empty_state(
            "Sin bases registradas",
            "Agrega una base de datos para empezar a crear chats de análisis.",
            icon=":material/database:",
        )
        return

    for database in databases:
        related_chats = _related_chats(chats, database["id"])
        with st.expander(
            f"{database['name']} · {len(related_chats)} chats",
            expanded=False,
        ):
            st.caption(f"ID de base: {database['id']}")
            if not related_chats:
                st.info("Esta base todavía no tiene chats relacionados.")
                continue

            chat_rows = [
                {
                    "título": chat.get("title") or f"Chat {chat['id']}",
                    "mensajes": chat.get("message_count", 0),
                }
                for chat in related_chats
            ]
            ui.display_table(
                chat_rows,
                empty_message="No hay chats relacionados.",
                column_order=["título", "mensajes"],
            )
