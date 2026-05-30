from typing import Any

import streamlit as st

_CURRENT_USER_KEYS = ("current_user_id", "selected_user_id")


def init_state() -> None:
    st.session_state.setdefault("logged_in", False)
    st.session_state.setdefault("current_user_id", None)
    st.session_state.setdefault("selected_user_id", None)
    st.session_state.setdefault("selected_db_id", None)
    st.session_state.setdefault("selected_runtime_db_id", None)
    st.session_state.setdefault("selected_model_id", None)
    st.session_state.setdefault("selected_chat_id", None)
    st.session_state.setdefault("chat_messages", [])


def set_current_user(user_id: int | None) -> None:
    for key in _CURRENT_USER_KEYS:
        st.session_state[key] = user_id
    st.session_state["logged_in"] = user_id is not None
    st.session_state["selected_db_id"] = None
    st.session_state["selected_runtime_db_id"] = None
    st.session_state["selected_chat_id"] = None
    st.session_state["chat_messages"] = []


def get_current_user_id() -> int | None:
    if not st.session_state.get("logged_in"):
        return None
    return st.session_state.get("current_user_id") or st.session_state.get(
        "selected_user_id"
    )


def current_user(users: list[dict[str, Any]]) -> dict[str, Any] | None:
    user_id = get_current_user_id()
    if user_id is None:
        return None
    return next((user for user in users if user["id"] == user_id), None)


def logout() -> None:
    st.session_state["logged_in"] = False
    for key in _CURRENT_USER_KEYS:
        st.session_state[key] = None
    st.session_state["selected_db_id"] = None
    st.session_state["selected_runtime_db_id"] = None
    st.session_state["selected_model_id"] = None
    st.session_state["selected_chat_id"] = None
    st.session_state["chat_messages"] = []
