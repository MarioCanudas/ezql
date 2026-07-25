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
