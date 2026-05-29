from typing import Any

import streamlit as st
from components import api_client


@st.dialog("Nueva base de datos", width="medium", on_dismiss="rerun")
def create_database_dialog(
    *,
    users: list[dict[str, Any]],
    engines: list[dict[str, Any]],
    default_user_id: int | None = None,
) -> None:
    st.caption(
        "Guarda una conexión para que EzQL pueda responder preguntas en lenguaje "
        "natural. Los secretos se envían al backend para almacenarse protegidos."
    )

    if default_user_id is None or not users:
        st.warning("Inicia sesión antes de registrar una base de datos.")
        return
    if not engines:
        st.warning("No hay motores SQL disponibles.")
        return

    engine_map = {engine["id"]: engine["name"] for engine in engines}

    with st.form("create_database_dialog_form"):
        name = st.text_input("Nombre visible", value="Nueva base", max_chars=50)
        user_id = default_user_id
        engine_id = st.selectbox(
            "Motor",
            options=list(engine_map.keys()),
            format_func=lambda value: engine_map[value],
        )
        db_link = st.text_input(
            "Enlace o cadena de conexión",
            placeholder="sqlite:///backend/ezql.db",
        )
        auth_token = st.text_input("Token o contraseña (opcional)", type="password")
        submitted = st.form_submit_button("Registrar base", type="primary")

    if not submitted:
        return

    clean_name = name.strip() or "Nueva base"
    clean_link = db_link.strip()
    if not clean_link:
        st.warning("El enlace o cadena de conexión es obligatorio.")
        return

    if user_id is None or engine_id is None:
        st.warning("Selecciona usuario y motor.")
        return

    try:
        database = api_client.create_database(
            name=clean_name,
            user_id=user_id,
            engine_id=engine_id,
            db_link=clean_link,
            auth_token=auth_token.strip() or None,
        )
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    api_client.list_databases.clear()
    st.session_state["selected_db_id"] = database["id"]
    st.success("Base de datos registrada.")
    st.rerun()
