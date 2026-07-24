from .sql import (
    get_schema,
    preview_table,
    count_rows,
    summarize_column,
    execute_advanced_sql,
    search_similar_values,
    get_column_distinct_values,
    validate_sql_syntax,
    query_planner,
)

from .statistics import (
    analyze_trend,
    detect_outliers,
)

from .orchestrator import (
    delegate_to_sql,
    delegate_to_statistics,
    delegate_to_visualization,
)

from .visualization import (
    create_bar_chart,
    create_line_chart,
)

sql_tools = [
    get_schema,
    preview_table,
    count_rows,
    summarize_column,
    execute_advanced_sql,
    search_similar_values,
    get_column_distinct_values,
    validate_sql_syntax,
    query_planner,
]

statistics_tools = [
    analyze_trend,
    detect_outliers,
]

orchestrator_tools = [
    delegate_to_sql,
    delegate_to_statistics,
    delegate_to_visualization,
]

visualization_tools = [
    create_bar_chart,
    create_line_chart,
]

__all__ = [
    "sql_tools",
    "statistics_tools",
    "orchestrator_tools",
    "visualization_tools",
]
