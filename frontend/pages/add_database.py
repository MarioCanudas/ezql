import streamlit as st
from components import api_client, state
from dialogs.database_dialog import create_database_dialog


def render() -> None:
    state.init_state()
    if not st.session_state.logged_in:
        st.warning("Inicia sesión para agregar bases de datos.")
        return

    user_id = state.get_current_user_id()
    if user_id is None:
        state.logout()
        st.rerun()

    st.title("Agregar base")
    st.caption("Registra una conexión para que EzQL pueda analizar tus datos.")

    try:
        users = api_client.list_users()
        engines = api_client.list_engines()
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    if st.button("Abrir formulario de nueva base", type="primary"):
        create_database_dialog(users=users, engines=engines, default_user_id=user_id)
