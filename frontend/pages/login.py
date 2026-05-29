import streamlit as st
from components import api_client, state, ui
from dialogs.user_dialog import create_user_dialog


def render() -> None:
    state.init_state()

    if st.session_state.logged_in:
        st.title("EzQL")
        st.success("Ya iniciaste sesión.")
        if st.button("Continuar", type="primary"):
            st.rerun()
        return

    st.title("Iniciar sesión")
    st.caption("Ingresa con tu usuario y contraseña para acceder a EzQL.")

    try:
        users = api_client.list_users()
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    st.subheader("Entrar")
    if not users:
        ui.render_empty_state(
            "Aún no hay usuarios",
            "Crea el primer usuario para empezar.",
            icon=":material/person:",
        )
    else:
        user_names = [user["name"] for user in users]
        with st.form("login_form"):
            name = st.selectbox("Usuario", options=user_names)
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button(
                "Entrar",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            if not name or not password:
                st.warning("Escribe tu usuario y contraseña.")
                return
            try:
                user = api_client.login_user(name=name, password=password)
            except api_client.ApiError:
                st.error("Usuario o contraseña incorrectos.")
                return
            state.set_current_user(user["id"])
            st.rerun()

    st.divider()
    st.caption("¿No tienes usuario?")
    if st.button("Crear usuario", use_container_width=True):
        create_user_dialog(login_after_create=True)
