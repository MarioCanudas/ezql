import streamlit as st
from components import state
from pages import chat, home, login, setup

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
                chat.render,
                title="Chat",
                icon=":material/chat:",
                url_path="chat",
            ),
            st.Page(
                setup.render,
                title="Configuración",
                icon=":material/settings:",
                url_path="configuracion",
            ),
        ],
        "Cuenta": [
            st.Page(
                logout_page,
                title="Cerrar sesión",
                icon=":material/logout:",
                url_path="logout",
            ),
        ],
    }

page = st.navigation(
    pages,
    position="sidebar" if st.session_state.logged_in else "hidden",
)
page.run()
