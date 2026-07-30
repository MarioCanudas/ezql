from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


class ApiError(RuntimeError):
    pass


def _secret(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except StreamlitSecretNotFoundError:
        return None
    if isinstance(value, str):
        return value
    return None


def _base_url() -> str:
    return (
        _secret("API_BASE_URL")
        or os.getenv("EZQL_API_BASE_URL")
        or "http://localhost:8000/api/v1"
    ).rstrip("/")


@st.cache_resource
def get_client(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=300.0)


def _handle_response(response: httpx.Response) -> Any:
    if response.status_code >= 400:
        detail = f"Request failed ({response.status_code})."
        try:
            payload = response.json()
            detail = payload.get("detail") or payload.get("message") or detail
        except ValueError:
            pass
        raise ApiError(detail)
    if response.status_code == 204:
        return None
    return response.json()


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    client = get_client(_base_url())
    try:
        response = client.request(method, path, params=params, json=json)
    except httpx.ConnectError as exc:
        raise ApiError(
            "No se pudo conectar con el backend. Verifica que FastAPI este "
            "ejecutandose y que API_BASE_URL en secrets.toml sea correcto."
        ) from exc
    except httpx.ReadTimeout as exc:
        raise ApiError(
            "El agente está tardando más de lo esperado en responder. "
            "Tu consulta sigue procesándose en el servidor. "
            "Sal del chat y vuelve a entrar en unos segundos para ver la respuesta."
        ) from exc
    except httpx.RequestError as exc:
        raise ApiError(
            "Error de red al llamar al backend. Verifica la URL configurada."
        ) from exc
    return _handle_response(response)


def _request_multipart(
    method: str,
    path: str,
    *,
    data: dict[str, Any],
    files: dict[str, Any] | None = None,
) -> Any:
    client = get_client(_base_url())
    try:
        response = client.request(method, path, data=data, files=files)
    except httpx.ConnectError as exc:
        raise ApiError(
            "No se pudo conectar con el backend. Verifica que FastAPI este "
            "ejecutandose y que API_BASE_URL en secrets.toml sea correcto."
        ) from exc
    except httpx.ReadTimeout as exc:
        raise ApiError(
            "El agente está tardando más de lo esperado en responder. "
            "Tu consulta sigue procesándose en el servidor. "
            "Sal del chat y vuelve a entrar en unos segundos para ver la respuesta."
        ) from exc
    except httpx.RequestError as exc:
        raise ApiError(
            "Error de red al llamar al backend. Verifica la URL configurada."
        ) from exc
    return _handle_response(response)


@st.cache_data(ttl=5)
def list_users() -> list[dict[str, Any]]:
    return _request("GET", "/users")


def create_user(name: str, password: str) -> dict[str, Any]:
    return _request("POST", "/users", json={"name": name, "password": password})


def login_user(name: str, password: str) -> dict[str, Any]:
    return _request("POST", "/users/login", json={"name": name, "password": password})


@st.cache_data(ttl=5)
def get_user_api_key_status(user_id: int) -> dict[str, Any]:
    return _request("GET", f"/users/{user_id}/api-keys")


def update_user_api_keys(
    *,
    user_id: int,
    openai_api_key: str | None,
    deepseek_api_key: str | None,
) -> dict[str, Any]:
    return _request(
        "PUT",
        f"/users/{user_id}/api-keys",
        json={
            "openai_api_key": openai_api_key,
            "deepseek_api_key": deepseek_api_key,
        },
    )


@st.cache_data(ttl=10)
def list_engines() -> list[dict[str, Any]]:
    engines = _request("GET", "/engines")
    return [
        engine
        for engine in engines
        if engine.get("is_supported") and engine.get("name", "").casefold() == "sqlite3"
    ]


@st.cache_data(ttl=10)
def list_models() -> list[dict[str, Any]]:
    models = _request("GET", "/models")
    supported_providers = {"openai", "deepseek"}
    return [
        model
        for model in models
        if model.get("company", "").casefold() in supported_providers
    ]


@st.cache_data(ttl=5)
def list_databases(
    *,
    user_id: int | None = None,
    engine_id: int | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    if user_id is not None:
        params["user_id"] = user_id
    if engine_id is not None:
        params["engine_id"] = engine_id
    return _request("GET", "/databases", params=params)


def create_database(
    *,
    name: str,
    user_id: int,
    engine_id: int,
    db_link: str,
    auth_token: str | None,
) -> dict[str, Any]:
    return _request(
        "POST",
        "/databases",
        json={
            "name": name,
            "user_id": user_id,
            "engine_id": engine_id,
            "db_link": db_link,
            "auth_token": auth_token,
        },
    )


def _chat_filters(
    *,
    user_id: int | None = None,
    db_id: int | None = None,
    model_id: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if user_id is not None:
        params["user_id"] = user_id
    if db_id is not None:
        params["db_id"] = db_id
    if model_id is not None:
        params["model_id"] = model_id
    return params


@st.cache_data(ttl=3)
def list_chats(
    *,
    user_id: int | None = None,
    db_id: int | None = None,
    model_id: int | None = None,
) -> list[dict[str, Any]]:
    return _request(
        "GET",
        "/chats",
        params=_chat_filters(user_id=user_id, db_id=db_id, model_id=model_id),
    )


def list_chat_summaries(
    *,
    user_id: int | None = None,
    db_id: int | None = None,
    model_id: int | None = None,
) -> list[dict[str, Any]]:
    return _request(
        "GET",
        "/chats",
        params=_chat_filters(user_id=user_id, db_id=db_id, model_id=model_id),
    )


def create_chat(
    *,
    title: str,
    user_id: int,
    model_id: int,
    db_id: int | None = None,
    runtime_db_id: str | None = None,
) -> dict[str, Any]:
    return _request(
        "POST",
        "/chats",
        json={
            "title": title,
            "user_id": user_id,
            "db_id": db_id,
            "runtime_db_id": runtime_db_id,
            "model_id": model_id,
        },
    )


@st.cache_data(ttl=5)
def list_runtime_databases(user_id: int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    if user_id is not None:
        params["user_id"] = user_id
    return _request("GET", "/runtime-databases", params=params)


def register_sample_database(
    *,
    user_id: int,
    runtime_id: str | None = None,
    sample_name: str = "netflix",
) -> dict[str, Any]:
    data = {"user_id": str(user_id), "sample_name": sample_name}
    if runtime_id is not None:
        data["runtime_id"] = runtime_id
    return _request_multipart(
        "POST",
        "/runtime-databases/sample",
        data=data,
    )


def upload_runtime_database(
    *,
    user_id: int,
    display_name: str,
    filename: str,
    content: bytes,
    runtime_id: str | None = None,
) -> dict[str, Any]:
    data = {"user_id": str(user_id), "display_name": display_name}
    if runtime_id is not None:
        data["runtime_id"] = runtime_id
    return _request_multipart(
        "POST",
        "/runtime-databases/upload",
        data=data,
        files={"file": (filename, content, "application/octet-stream")},
    )


def list_messages(chat_id: int) -> list[dict[str, Any]]:
    return _request("GET", f"/chats/{chat_id}/messages")


def create_reply(
    *,
    chat_id: int,
    content_text: str,
    user_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": {"text": content_text, "data": None},
        "user_id": user_id,
    }
    return _request("POST", f"/chats/{chat_id}/reply", json=payload)


def delete_chat(chat_id: int) -> None:
    _request("DELETE", f"/chats/{chat_id}")
    list_chats.clear()


def update_chat(
    chat_id: int,
    *,
    title: str | None = None,
    summary: str | None = None,
    runtime_db_id: str | None = None,
    db_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if summary is not None:
        payload["summary"] = summary
    if runtime_db_id is not None:
        payload["runtime_db_id"] = runtime_db_id
    if db_id is not None:
        payload["db_id"] = db_id
    res = _request("PATCH", f"/chats/{chat_id}", json=payload)
    list_chats.clear()
    return res
