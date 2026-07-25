"""Tests for the new Block-Based UI architecture and AgentResponse contracts."""

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.models.blocks import (
    AgentResponse,
    ChartBlock,
    MarkdownBlock,
    MetricBlock,
    TableBlock,
    UIBlock,
)


def test_agent_response_json_contract():
    """Verifica que el JSON de ejemplo provisto en la especificación técnica deserialice correctamente."""
    sample_json = {
        "summary": "Análisis de ventas del último trimestre",
        "blocks": [
            {
                "type": "markdown",
                "content": "### Resumen Ejecutivo\nLas ventas mostraron un incremento sostenido.",
            },
            {
                "type": "metric",
                "label": "Ingresos Totales",
                "value": "$452,000",
                "delta": "+15.4%",
            },
            {
                "type": "chart",
                "chart_type": "bar",
                "title": "Ventas Mensuales",
                "x_axis": "mes",
                "y_axis": ["ventas"],
                "data": [
                    {"mes": "Enero", "ventas": 120000},
                    {"mes": "Febrero", "ventas": 150000},
                    {"mes": "Marzo", "ventas": 182000},
                ],
            },
            {
                "type": "table",
                "title": "Detalle de Transacciones",
                "columns": ["mes", "ventas", "ordenes"],
                "data": [
                    {"mes": "Enero", "ventas": 120000, "ordenes": 450},
                    {"mes": "Febrero", "ventas": 150000, "ordenes": 520},
                    {"mes": "Marzo", "ventas": 182000, "ordenes": 610},
                ],
            },
        ],
    }

    response = AgentResponse.model_validate(sample_json)
    assert response.summary == "Análisis de ventas del último trimestre"
    assert len(response.blocks) == 4

    b0, b1, b2, b3 = response.blocks
    assert isinstance(b0, MarkdownBlock)
    assert b0.content.startswith("### Resumen")

    assert isinstance(b1, MetricBlock)
    assert b1.label == "Ingresos Totales"
    assert b1.value == "$452,000"
    assert b1.delta == "+15.4%"

    assert isinstance(b2, ChartBlock)
    assert b2.chart_type == "bar"
    assert b2.x_axis == "mes"
    assert b2.y_axis == ["ventas"]
    assert len(b2.data) == 3

    assert isinstance(b3, TableBlock)
    assert b3.title == "Detalle de Transacciones"
    assert b3.columns == ["mes", "ventas", "ordenes"]
    assert len(b3.data) == 3


def test_sql_block_is_excluded():
    """Garantiza que SqlBlock no forme parte de UIBlock para cumplir con la filosofía EzQL."""
    adapter = TypeAdapter(UIBlock)
    with pytest.raises(ValidationError):
        adapter.validate_python({
            "type": "sql",
            "query": "SELECT * FROM users;"
        })


def test_chart_block_types():
    """Valida los tipos de chart_type permitidos."""
    for chart_type in ["bar", "line", "area", "scatter"]:
        cb = ChartBlock(
            chart_type=chart_type,
            x_axis="x",
            y_axis=["y"],
            data=[{"x": 1, "y": 2}]
        )
        assert cb.chart_type == chart_type

    with pytest.raises(ValidationError):
        ChartBlock(
            chart_type="pie",  # Not in allowed literal
            x_axis="x",
            y_axis=["y"],
            data=[]
        )
