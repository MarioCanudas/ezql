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
    compare_segments,
    describe_metric,
    detect_outliers,
    profile_data,
    run_statistics_python,
)

from .visualization import (
    create_bar_chart,
    create_line_chart,
    create_scatter_chart,
)
from .quality import quality_tools

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
    profile_data,
    describe_metric,
    compare_segments,
    analyze_trend,
    detect_outliers,
    run_statistics_python,
]

visualization_tools = [
    create_bar_chart,
    create_line_chart,
    create_scatter_chart,
]

__all__ = [
    "sql_tools",
    "statistics_tools",
    "visualization_tools",
    "quality_tools",
]
