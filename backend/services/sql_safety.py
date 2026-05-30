import re


class UnsafeSQLError(ValueError):
    pass


_BLOCKED_KEYWORDS = {
    "alter",
    "analyze",
    "attach",
    "begin",
    "commit",
    "create",
    "delete",
    "detach",
    "drop",
    "insert",
    "pragma",
    "reindex",
    "replace",
    "rollback",
    "truncate",
    "update",
    "vacuum",
}

_BLOCKED_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(_BLOCKED_KEYWORDS)) + r")\b",
    flags=re.IGNORECASE,
)


def normalize_readonly_sql(sql: str) -> str:
    statement = sql.strip()
    if not statement:
        raise UnsafeSQLError("La consulta está vacía.")

    if ";" in statement.rstrip(";"):
        raise UnsafeSQLError("Solo se permite una consulta por mensaje.")

    statement = statement.rstrip(";").strip()
    lowered = statement.casefold()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise UnsafeSQLError("Solo puedo ejecutar consultas de lectura.")

    blocked_match = _BLOCKED_PATTERN.search(statement)
    if blocked_match:
        raise UnsafeSQLError("La solicitud intenta usar una operación no permitida.")

    return statement


def limit_readonly_sql(sql: str, *, max_rows: int) -> str:
    statement = normalize_readonly_sql(sql)
    return f"SELECT * FROM ({statement}) AS ezql_limited_result LIMIT {max_rows}"


def quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise ValueError("Identificador inválido.")
    return '"' + identifier.replace('"', '""') + '"'
