from typing import Any

import streamlit as st
from components import api_client, state, ui

_TEMPORARY_DB_NOTICE = (
    "Las bases SQLite que subas son temporales: no se guardan de forma permanente. "
    "Si reinicias sesión o se reinicia el servidor, tendrás que volver a cargar el archivo."
)


def _model_options(models: list[dict[str, Any]]) -> tuple[list[int], dict[int, str]]:
    model_map = {model["id"]: ui.format_model(model) for model in models}
    return list(model_map.keys()), model_map


def _finish_chat_creation(
    chat: dict[str, Any], *, runtime_db_id: str, model_id: int
) -> None:
    api_client.list_chats.clear()
    api_client.list_runtime_databases.clear()
    st.session_state["selected_chat_id"] = chat["id"]
    st.session_state["selected_runtime_db_id"] = runtime_db_id
    st.session_state["selected_model_id"] = model_id
    st.session_state["chat_messages"] = []
    st.success("Chat creado. Ya puedes preguntar por la base seleccionada.")
    st.rerun()


def _create_chat_with_runtime_db(
    *,
    user_id: int,
    title: str,
    model_id: int,
    runtime_db: dict[str, Any],
) -> None:
    chat = api_client.create_chat(
        title=title.strip() or "Nuevo análisis",
        user_id=user_id,
        model_id=model_id,
        runtime_db_id=runtime_db["id"],
    )
    _finish_chat_creation(chat, runtime_db_id=runtime_db["id"], model_id=model_id)


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
    st.caption("Crea una conversación asociada a una base SQLite y un modelo.")
    st.warning(_TEMPORARY_DB_NOTICE, icon=":material/warning:")

    try:
        models = api_client.list_models()
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    if not models:
        ui.render_empty_state(
            "Sin modelos disponibles",
            "Agrega un modelo antes de crear chats de análisis.",
            icon=":material/smart_toy:",
        )
        return

    model_options, model_map = _model_options(models)
    default_model_id = st.session_state.get("selected_model_id")
    model_index = (
        model_options.index(default_model_id)
        if default_model_id in model_options
        else 0
    )

    with st.form("runtime_chat_form"):
        title = st.text_input("Título", value="Nuevo análisis", max_chars=50)
        model_id = st.selectbox(
            "Modelo",
            options=model_options,
            index=model_index,
            format_func=lambda value: model_map[value],
        )
        source = st.radio(
            "Origen de datos",
            options=["sample", "upload"],
            format_func=lambda value: (
                "Usar base de prueba Netflix"
                if value == "sample"
                else "Subir archivo SQLite .db"
            ),
        )

        uploaded_file = None
        display_name = ""
        if source == "upload":
            uploaded_file = st.file_uploader(
                "Archivo SQLite",
                type=["db", "sqlite", "sqlite3"],
                help="El archivo se usa solo durante la sesión actual del backend.",
            )
            display_name = st.text_input(
                "Nombre visible",
                value=uploaded_file.name if uploaded_file else "Mi base SQLite",
                max_chars=50,
            )
        else:
            st.info(
                "La base de prueba incluida siempre está disponible para validar el flujo antes de subir tus datos."
            )

        submitted = st.form_submit_button("Crear chat", type="primary")

    if not submitted:
        return

    if model_id is None:
        st.warning("Selecciona un modelo.")
        return

    try:
        if source == "sample":
            runtime_db = api_client.register_sample_database(user_id=user_id)
        else:
            if uploaded_file is None:
                st.warning("Sube un archivo SQLite .db para crear el chat.")
                return
            runtime_db = api_client.upload_runtime_database(
                user_id=user_id,
                display_name=display_name.strip() or uploaded_file.name,
                filename=uploaded_file.name,
                content=uploaded_file.getvalue(),
            )

        _create_chat_with_runtime_db(
            user_id=user_id,
            title=title,
            model_id=model_id,
            runtime_db=runtime_db,
        )
    except api_client.ApiError as exc:
        st.error(str(exc))
