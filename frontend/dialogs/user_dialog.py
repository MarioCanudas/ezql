import streamlit as st
from components import api_client, state


@st.dialog("Nuevo usuario", width="small", on_dismiss="rerun")
def create_user_dialog(*, login_after_create: bool = False) -> None:
    st.caption("Crea un perfil local para separar chats y conexiones.")

    with st.form("create_user_dialog_form"):
        name = st.text_input("Nombre", max_chars=50, placeholder="Ej. Ana Ventas")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Crear usuario", type="primary")

    if not submitted:
        return

    clean_name = name.strip()
    if not clean_name:
        st.warning("El nombre es obligatorio.")
        return
    if not password:
        st.warning("La contraseña es obligatoria.")
        return

    try:
        user = api_client.create_user(name=clean_name, password=password)
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    api_client.list_users.clear()
    st.session_state["last_created_user_id"] = user["id"]
    if login_after_create:
        state.set_current_user(user["id"])
    st.success("Usuario creado.")
    st.rerun()
