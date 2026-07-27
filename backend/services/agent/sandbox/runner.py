"""Entrypoint for the prebuilt statistics sandbox image.

This file runs only inside Docker. It receives one JSON object on stdin and emits
one validated JSON object on stdout; it never reads or writes application files.
"""
from __future__ import annotations

import ast
import json
import math
import sys
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

ALLOWED_IMPORTS = {"pandas": "pd", "numpy": "np", "scipy.stats": "stats"}
ALLOWED_BUILTINS = {
    "abs": abs, "len": len, "min": min, "max": max, "sum": sum,
    "round": round, "range": range, "str": str, "int": int, "float": float,
    "list": list, "dict": dict, "zip": zip, "enumerate": enumerate,
}
FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "globals", "locals", "vars", "getattr", "setattr", "delattr", "help", "input", "__import__"}


class UnsafeCode(ValueError):
    pass


def validate_code(code: str) -> ast.Module:
    tree = ast.parse(code, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name not in {"pandas", "numpy"}:
                        raise UnsafeCode("import not allowed")
            elif node.module != "scipy" or any(alias.name != "stats" for alias in node.names):
                raise UnsafeCode("import not allowed")
        if isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAMES or "__" in node.id):
            raise UnsafeCode("name not allowed")
        if isinstance(node, ast.Attribute) and "__" in node.attr:
            raise UnsafeCode("attribute not allowed")
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith(("to_", "read_")) or node.attr in {"save", "load"}
        ):
            raise UnsafeCode("file access not allowed")
        if isinstance(node, (ast.Lambda, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.With, ast.AsyncWith, ast.Try, ast.Raise, ast.Delete, ast.Global, ast.Nonlocal)):
            raise UnsafeCode("syntax not allowed")
    return tree


def json_value(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError("unsupported result value")


def normalize(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("result must be a dictionary")
    findings = [str(value)[:500] for value in result.get("findings", [])[:10]]
    metrics = {str(key)[:80]: json_value(value) for key, value in result.get("metrics", {}).items()}
    if len(metrics) > 12:
        raise ValueError("too many metrics")
    tables = []
    for table in result.get("tables", [])[:3]:
        if not isinstance(table, dict):
            raise ValueError("invalid table")
        rows = table.get("data", [])[:100]
        if not isinstance(rows, list):
            raise ValueError("invalid table rows")
        tables.append({
            "title": str(table.get("title", "Resultados"))[:120],
            "columns": [str(column)[:80] for column in table.get("columns", [])[:12]],
            "data": [{str(key)[:80]: json_value(value) for key, value in row.items()} for row in rows if isinstance(row, dict)],
        })
    return {"findings": findings, "metrics": metrics, "tables": tables, "warnings": [str(value)[:300] for value in result.get("warnings", [])[:10]]}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        code = payload["code"]
        records = payload["records"]
        if not isinstance(code, str) or len(code) > 12_000 or not isinstance(records, list):
            raise ValueError("invalid input")
        tree = validate_code(code)
        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "pandas":
                return pd
            if name == "numpy":
                return np
            if name == "scipy" and "stats" in fromlist:
                return __import__("scipy", fromlist=("stats",))
            raise ImportError("import not allowed")

        namespace = {
            "__builtins__": {**ALLOWED_BUILTINS, "__import__": safe_import},
            "pd": pd, "np": np, "stats": stats, "data": pd.DataFrame(records),
        }
        exec(compile(tree, "<statistics-sandbox>", "exec"), namespace, namespace)
        print(json.dumps(normalize(namespace.get("result")), ensure_ascii=False))
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
