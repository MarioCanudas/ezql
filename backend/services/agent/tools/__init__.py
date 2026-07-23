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
    transfer_to_statistics,
)

from .statistics import (
    analyze_trend,
    detect_outliers,
    transfer_to_sql,
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
    transfer_to_statistics,
]

statistics_tools = [
    analyze_trend,
    detect_outliers,
    transfer_to_sql,
]

__all__ = ["sql_tools", "statistics_tools"]
