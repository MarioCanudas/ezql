import streamlit as st
from components import api_client, state, ui
from dialogs.chat_dialog import create_chat_dialog


def render() -> None:
    state.init_state()
    if not st.session_state.logged_in:
        st.warning("Inicia sesión para crear chats.")
        return

    user_id = state.get_current_user_id()
    if user_id is None:
        state.logout()
        st.rerun()

    st.title("Nuevo chat")
    st.caption("Crea una conversación asociada a una base de datos y un modelo.")

    try:
        databases = api_client.list_databases(user_id=user_id)
        models = api_client.list_models()
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    if not databases:
        ui.render_empty_state(
            "Sin bases de datos",
            "Agrega una base de datos antes de crear un chat.",
            icon=":material/database:",
        )
        return

    if st.button("Abrir formulario de nuevo chat", type="primary"):
        create_chat_dialog(
            user_id=user_id,
            databases=databases,
            models=models,
            default_db_id=st.session_state.get("selected_db_id"),
            default_model_id=st.session_state.get("selected_model_id"),
        )
