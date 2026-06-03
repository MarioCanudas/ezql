from typing import Any

import streamlit as st
from components import ui


@st.dialog("Configurar chat", width="medium", on_dismiss="rerun")
def chat_settings_dialog(
    *,
    chats: list[dict[str, Any]],
    databases: list[dict[str, Any]],
    models: list[dict[str, Any]],
    active_chat_id: int | None = None,
) -> None:
    st.caption("Cambia el nombre del chat activo y las opciones por defecto.")

    with st.form("chat_settings_form"):
        selected_db_id = None
        selected_model_id = None
        new_title = None

        active_chat = None
        if active_chat_id and chats:
            active_chat = next((chat for chat in chats if chat["id"] == active_chat_id), None)
            if active_chat:
                new_title = st.text_input("Nombre del chat", value=active_chat.get("title", ""))
        elif not chats:
            st.info("Todavía no tienes chats.")


        if databases:
            db_map = {database["id"]: database["name"] for database in databases}
            db_options = list(db_map.keys())
            db_index = 0
            if "selected_db_id" in st.session_state and st.session_state["selected_db_id"] in db_options:
                db_index = db_options.index(st.session_state["selected_db_id"])

            selected_db_id = st.selectbox(
                "Base por defecto",
                options=db_options,
                index=db_index,
                format_func=lambda value: db_map[value],
            )
        else:
            st.info("Agrega una base de datos para crear chats.")

        if models:
            model_map = {model["id"]: ui.format_model(model) for model in models}
            model_options = list(model_map.keys())
            model_index = 0
            if "selected_model_id" in st.session_state and st.session_state["selected_model_id"] in model_options:
                model_index = model_options.index(st.session_state["selected_model_id"])

            selected_model_id = st.selectbox(
                "Modelo por defecto",
                options=model_options,
                index=model_index,
                format_func=lambda value: model_map[value],
            )
        else:
            st.info("Agrega un modelo para crear chats.")

        submitted = st.form_submit_button("Guardar", type="primary")

    if active_chat_id:
        st.divider()
        st.write("### Opciones del chat")
        if st.button("Eliminar chat actual", type="secondary", icon=":material/delete:"):
            from components import api_client
            api_client.delete_chat(active_chat_id)
            st.session_state.pop("selected_chat_id", None)
            st.rerun()

    if not submitted:
        return

    from components import api_client

    if active_chat and new_title and new_title != active_chat.get("title"):
        try:
            api_client.update_chat(active_chat_id, title=new_title)
        except api_client.ApiError as exc:
            st.error(str(exc))
            return

    if selected_db_id is not None:
        st.session_state["selected_db_id"] = selected_db_id
    if selected_model_id is not None:
        st.session_state["selected_model_id"] = selected_model_id
    st.rerun()
