from collections.abc import Callable
from datetime import datetime
from typing import Any

import streamlit as st
from components import api_client, state
from pages import add_database, chat, databases, home, login, new_chat, setup

st.set_page_config(
    page_title="EzQL",
    page_icon=":material/query_stats:",
    layout="centered",
)
state.init_state()


def logout_page() -> None:
    state.logout()
    st.success("Sesión cerrada.")
    st.rerun()


def _chat_title(chat_summary: dict[str, Any]) -> str:
    return chat_summary.get("title") or f"Chat {chat_summary['id']}"


def _render_chat(chat_id: int) -> Callable[[], None]:
    def render_selected_chat() -> None:
        chat.render(chat_id=chat_id)

    return render_selected_chat


def _last_message_at(chat_summary: dict[str, Any]) -> datetime | None:
    value = chat_summary.get("last_message_at")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _sort_chat_summaries(
    chat_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    active_chats = [chat for chat in chat_summaries if _last_message_at(chat)]
    empty_chats = [chat for chat in chat_summaries if not _last_message_at(chat)]

    active_chats.sort(
        key=lambda chat_summary: _last_message_at(chat_summary) or datetime.min,
        reverse=True,
    )
    empty_chats.sort(key=lambda chat_summary: _chat_title(chat_summary).casefold())
    return [*active_chats, *empty_chats]


def _dynamic_chat_pages() -> list[Any]:
    user_id = state.get_current_user_id()
    if user_id is None:
        return []

    try:
        chat_summaries = api_client.list_chat_summaries(user_id=user_id)
    except api_client.ApiError as exc:
        st.sidebar.error(str(exc))
        return []

    return [
        st.Page(
            _render_chat(chat_summary["id"]),
            title=_chat_title(chat_summary),
            icon=":material/chat:",
            url_path=f"chat-{chat_summary['id']}",
        )
        for chat_summary in _sort_chat_summaries(chat_summaries)
    ]


pages = {
    "Usuario": [
        st.Page(
            login.render,
            title="Login",
            icon=":material/lock:",
            url_path="login",
            default=not st.session_state.logged_in,
        ),
    ]
}

if st.session_state.logged_in:
    pages = {
        "EzQL": [
            st.Page(
                home.render,
                title="Inicio",
                icon=":material/home:",
                url_path="inicio",
                default=True,
            ),
            st.Page(
                setup.render,
                title="Configuración",
                icon=":material/settings:",
                url_path="configuracion",
            ),
            st.Page(
                logout_page,
                title="Cerrar sesión",
                icon=":material/logout:",
                url_path="logout",
            ),
        ],
        "Bases de datos": [
            st.Page(
                databases.render,
                title="Mis bases",
                icon=":material/database:",
                url_path="bases-de-datos",
            ),
            st.Page(
                add_database.render,
                title="Agregar base",
                icon=":material/add:",
                url_path="agregar-base",
            ),
        ],
        "Chats": [
            st.Page(
                new_chat.render,
                title="Nuevo chat",
                icon=":material/add_comment:",
                url_path="nuevo-chat",
            ),
            *_dynamic_chat_pages(),
        ],
    }

page = st.navigation(
    pages,
    position="sidebar" if st.session_state.logged_in else "hidden",
)

if "nav_to_chat_id" in st.session_state:
    st.session_state["nav_to_path"] = f"chat-{st.session_state.pop('nav_to_chat_id')}"

if "nav_to_path" in st.session_state:
    target_path = st.session_state.pop("nav_to_path")
    for section_pages in pages.values():
        for p in section_pages:
            if getattr(p, "url_path", "") == target_path:
                st.switch_page(p)

page.run()
