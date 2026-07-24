from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from backend.services.agent.state import AgentState
from backend.services.agent.nodes.base import NodeBase
from backend.services.agent.tools import (
    orchestrator_tools,
    sql_tools,
    statistics_tools,
    visualization_tools,
)


def route_tool_calls(state: AgentState):
    """Routes to tools if the last message has tool_calls, otherwise continues."""
    if not state.messages:
        return END

    last_message = state.messages[-1]

    if isinstance(last_message, dict):
        tool_calls = last_message.get("tool_calls", [])
    else:
        tool_calls = getattr(last_message, "tool_calls", [])

    if tool_calls:
        return "tools"

    return END


def create_agent_graph(
    orchestrator_node: NodeBase,
    sql_node: NodeBase,
    statistics_node: NodeBase,
    visualization_node: NodeBase,
):
    """
    Creates and compiles the Hub-and-Spoke agent graph.
    The Orchestrator is the central hub that delegates to specialist nodes.
    """
    workflow = StateGraph(AgentState)

    # Tool nodes
    tool_node_orchestrator = ToolNode(orchestrator_tools)
    tool_node_sql = ToolNode(sql_tools)
    tool_node_statistics = ToolNode(statistics_tools)
    tool_node_visualization = ToolNode(visualization_tools)

    # Add all nodes
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("sql", sql_node)
    workflow.add_node("statistics", statistics_node)
    workflow.add_node("visualization", visualization_node)
    workflow.add_node("tools_orchestrator", tool_node_orchestrator)
    workflow.add_node("tools_sql", tool_node_sql)
    workflow.add_node("tools_statistics", tool_node_statistics)
    workflow.add_node("tools_visualization", tool_node_visualization)

    # Entry point: START -> orchestrator
    workflow.add_edge(START, "orchestrator")

    # Orchestrator routing: tool_calls -> tools_orchestrator, else -> END
    workflow.add_conditional_edges(
        "orchestrator",
        route_tool_calls,
        {"tools": "tools_orchestrator", END: END},
    )

    # Specialist routing: tool_calls -> their tools, else -> END (task completed)
    workflow.add_conditional_edges(
        "sql",
        route_tool_calls,
        {"tools": "tools_sql", END: END},
    )
    workflow.add_conditional_edges(
        "statistics",
        route_tool_calls,
        {"tools": "tools_statistics", END: END},
    )
    workflow.add_conditional_edges(
        "visualization",
        route_tool_calls,
        {"tools": "tools_visualization", END: END},
    )

    # Tool nodes loop back to their respective specialist
    workflow.add_edge("tools_sql", "sql")
    workflow.add_edge("tools_statistics", "statistics")
    workflow.add_edge("tools_visualization", "visualization")

    return workflow.compile()
