from unittest.mock import MagicMock, patch

from frontend.components import ui


@patch.object(ui, "st")
def test_renderer_handles_only_base_blocks(mock_st):
    metric_column = MagicMock()
    mock_st.columns.return_value = [metric_column]

    ui.render_agent_response(
        {
            "summary": "Resumen",
            "blocks": [
                {"type": "markdown", "content": "Hallazgo"},
                {"type": "metric", "label": "Total", "value": "10"},
                {"type": "table", "columns": ["x"], "data": [{"x": 1}]},
                {
                    "type": "chart",
                    "chart_type": "bar",
                    "x_axis": "x",
                    "y_axis": ["y"],
                    "data": [{"x": "A", "y": 1}],
                },
            ],
        }
    )

    mock_st.markdown.assert_called_once_with("Hallazgo")
    metric_column.metric.assert_called_once_with(label="Total", value="10", delta=None)
    mock_st.dataframe.assert_called_once()
    mock_st.bar_chart.assert_called_once()


@patch.object(ui, "st")
def test_renderer_keeps_historical_specialized_blocks(mock_st):
    ui.render_agent_response(
        {
            "blocks": [
                {"type": "trend", "metric": "ventas", "direction": "up", "pct_change": 12},
                {"type": "outliers", "message": "Dos valores inusuales."},
            ]
        }
    )

    assert mock_st.info.call_count == 2
    mock_st.caption.assert_called_once_with("Cambio: 12%")


@patch.object(ui, "st")
def test_renderer_resolves_metadata_without_mutating_the_block(mock_st):
    metric_column = MagicMock()
    mock_st.columns.return_value = [metric_column]
    payload = {
        "metadata": {"sales.total": {"value": 8808, "display": "8,808", "artifact_id": "call-1", "path": "data.total"}},
        "blocks": [
            {"type": "markdown", "content": "Total: {{meta.sales.total}}"},
            {"type": "metric", "label": "Total", "value": "{{meta.sales.total}}"},
        ],
    }

    ui.render_agent_response(payload)

    mock_st.markdown.assert_called_once_with("Total: 8,808")
    metric_column.metric.assert_called_once_with(label="Total", value="8,808", delta=None)
    assert payload["blocks"][1]["value"] == "{{meta.sales.total}}"


@patch.object(ui, "st")
def test_renderer_marks_missing_metadata_as_unavailable(mock_st):
    ui.render_agent_response(
        {"blocks": [{"type": "markdown", "content": "Total: {{meta.missing}}"}], "metadata": {}}
    )

    mock_st.markdown.assert_called_once_with("Total: Dato no disponible")
