from typing import Annotated, Literal, Any
from pydantic import BaseModel, Field

# 1. Bloque de Texto / Markdown
class MarkdownBlock(BaseModel):
    type: Literal["markdown"] = "markdown"
    content: str = Field(description="Explicación, hallazgos o texto formativo en Markdown.")

# 2. Bloque de Métrica / KPI
class MetricBlock(BaseModel):
    type: Literal["metric"] = "metric"
    label: str = Field(description="Etiqueta del KPI (ej. 'Ventas Totales')")
    value: str = Field(description="Valor principal formateado (ej. '$125,400')")
    delta: str | None = Field(default=None, description="Variación porcentual o absoluta (ej. '+12.5%')")

# 3. Bloque de Tablas de Datos
class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    title: str | None = Field(default=None, description="Título descriptivo opcional para la tabla")
    columns: list[str] = Field(description="Lista de nombres de columnas")
    data: list[dict[str, Any]] = Field(description="Registros en formato JSON [{col: val}]")

# 4. Bloque de Gráficas
class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    chart_type: Literal["bar", "line", "area", "scatter"] = Field(description="Tipo de gráfica")
    title: str | None = Field(default=None, description="Título de la gráfica")
    x_axis: str = Field(description="Nombre de la columna para el eje X")
    y_axis: list[str] = Field(description="Lista de nombres de columnas para el eje Y")
    data: list[dict[str, Any]] = Field(description="Conjunto de datos a graficar")

# Discriminador de tipos de bloque
UIBlock = Annotated[
    MarkdownBlock | MetricBlock | TableBlock | ChartBlock,
    Field(discriminator="type")
]

# Alias por compatibilidad interna de modelos
DataBlock = UIBlock
FlexibleDataBlock = UIBlock | dict[str, Any] | list[Any]

# Respuesta Global del Agente
class AgentResponse(BaseModel):
    summary: str = Field(description="Resumen corto o respuesta principal en una oración.")
    blocks: list[UIBlock] = Field(default_factory=list, description="Lista secuencial ordenada de elementos visuales a renderizar.")
