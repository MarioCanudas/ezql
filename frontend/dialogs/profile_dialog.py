import streamlit as st
from components import api_client


@st.dialog("Perfil", width="medium", on_dismiss="rerun")
def profile_dialog(*, user_id: int) -> None:
    st.caption("Configura las API keys que EzQL usará para tus chats.")

    try:
        status = api_client.get_user_api_key_status(user_id)
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    openai_status = "Configurada" if status.get("has_openai_api_key") else "Pendiente"
    deepseek_status = (
        "Configurada" if status.get("has_deepseek_api_key") else "Pendiente"
    )
    st.write(f"OpenAI: {openai_status}")
    st.write(f"DeepSeek: {deepseek_status}")

    with st.form("profile_api_keys_form"):
        openai_api_key = st.text_input(
            "OpenAI API key",
            type="password",
            placeholder="Deja vacío para conservar la key actual",
        )
        deepseek_api_key = st.text_input(
            "DeepSeek API key",
            type="password",
            placeholder="Deja vacío para conservar la key actual",
        )
        submitted = st.form_submit_button("Guardar", type="primary")

    if not submitted:
        return

    try:
        api_client.update_user_api_keys(
            user_id=user_id,
            openai_api_key=openai_api_key.strip() or None,
            deepseek_api_key=deepseek_api_key.strip() or None,
        )
    except api_client.ApiError as exc:
        st.error(str(exc))
        return

    api_client.get_user_api_key_status.clear()
    st.success("Configuración guardada.")
    st.rerun()
