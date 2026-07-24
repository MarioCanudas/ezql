from typing import Annotated
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import ToolMessage
from langgraph.types import Command


@tool
def delegate_to_sql(
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Delega al Especialista SQL para consultar la base de datos, inspeccionar
    esquemas, contar registros, ejecutar consultas complejas o resumir columnas."""
    return Command(
        goto="sql",
        update={
            "messages": [
                ToolMessage(
                    content="Delegado al Especialista SQL.",
                    tool_call_id=tool_call_id,
                )
            ]
        },
    )


@tool
def delegate_to_statistics(
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Delega al Especialista en Estadística para analizar tendencias temporales,
    detectar anomalías (outliers) o realizar análisis estadístico avanzado."""
    return Command(
        goto="statistics",
        update={
            "messages": [
                ToolMessage(
                    content="Delegado al Especialista en Estadística.",
                    tool_call_id=tool_call_id,
                )
            ]
        },
    )


@tool
def delegate_to_visualization(
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Delega al Especialista en Visualización para crear gráficas de barras,
    líneas, dispersión u otras representaciones visuales de los datos."""
    return Command(
        goto="visualization",
        update={
            "messages": [
                ToolMessage(
                    content="Delegado al Especialista en Visualización.",
                    tool_call_id=tool_call_id,
                )
            ]
        },
    )
