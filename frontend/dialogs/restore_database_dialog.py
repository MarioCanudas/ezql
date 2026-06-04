import streamlit as st
from components import api_client


@st.dialog("Restaurar base de datos temporal", width="medium")
def restore_database_dialog(*, runtime_db_id: str, user_id: int) -> None:
    st.write(
        "Esta conversación utiliza una base SQLite temporal que ya no está cargada. "
        "Selecciona el origen original para reactivar el chat."
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

    if source == "sample":
        st.info("Se cargará la base de prueba original y se asociará con esta sesión del chat.")
        if st.button("Restaurar con base de prueba", type="primary"):
            try:
                with st.spinner("Cargando base de prueba..."):
                    api_client.register_sample_database(
                        user_id=user_id,
                        runtime_id=runtime_db_id,
                    )
                    
                    # Try to permanently associate db_id with Netflix Titles database in the chat model
                    try:
                        db_list = api_client.list_databases(user_id=user_id)
                        associated_db = next(
                            (d for d in db_list if d.get("name", "").strip().casefold() in (
                                "netflix titles",
                                "netflix_titles",
                                "base de prueba netflix",
                            )),
                            None
                        )
                        if associated_db and "selected_chat_id" in st.session_state:
                            chat_id = st.session_state["selected_chat_id"]
                            api_client.update_chat(chat_id, db_id=associated_db["id"])
                    except Exception:
                        pass
                    
                    api_client.list_runtime_databases.clear()
                    api_client.list_chats.clear()
                st.success("Base de datos de prueba restaurada correctamente.")
                st.rerun()
            except api_client.ApiError as exc:
                st.error(f"Error al restaurar: {exc}")
    else:
        uploaded_file = st.file_uploader(
            "Archivo SQLite",
            type=["db", "sqlite", "sqlite3"],
            help="El archivo se restaurará con el mismo identificador de sesión para continuar el chat.",
        )
        if uploaded_file is not None:
            if st.button("Subir y restaurar", type="primary"):
                try:
                    with st.spinner("Subiendo y validando archivo..."):
                        api_client.upload_runtime_database(
                            user_id=user_id,
                            display_name=uploaded_file.name,
                            filename=uploaded_file.name,
                            content=uploaded_file.getvalue(),
                            runtime_id=runtime_db_id,
                        )
                        api_client.list_runtime_databases.clear()
                    st.success("Base de datos restaurada correctamente.")
                    st.rerun()
                except api_client.ApiError as exc:
                    st.error(f"Error al subir: {exc}")
