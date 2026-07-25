from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from backend.services.agent.nodes.artifacts import ArtifactCollectorNode
from backend.services.agent.nodes.base import NodeBase
from backend.services.agent.state import AgentState
from backend.services.agent.tools import sql_tools, statistics_tools, visualization_tools


def route_tool_calls(state: AgentState) -> str:
    if not state.messages:
        return "next"
    return "tools" if getattr(state.messages[-1], "tool_calls", []) else "next"


def route_after_orchestrator(state: AgentState) -> str:
    if state.response:
        return "end"
    if state.pending_steps:
        return state.pending_steps[0].specialist
    return "orchestrator"


def create_agent_graph(
    orchestrator_node: NodeBase,
    sql_node: NodeBase,
    statistics_node: NodeBase,
    visualization_node: NodeBase,
):
    workflow = StateGraph(AgentState)
    collector = ArtifactCollectorNode()

    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("sql", sql_node)
    workflow.add_node("statistics", statistics_node)
    workflow.add_node("visualization", visualization_node)
    workflow.add_node("tools_sql", ToolNode(sql_tools))
    workflow.add_node("tools_statistics", ToolNode(statistics_tools))
    workflow.add_node("tools_visualization", ToolNode(visualization_tools))
    workflow.add_node("collect_sql", collector)
    workflow.add_node("collect_statistics", collector)
    workflow.add_node("collect_visualization", collector)

    workflow.add_edge(START, "orchestrator")
    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "sql": "sql",
            "statistics": "statistics",
            "visualization": "visualization",
            "orchestrator": "orchestrator",
            "end": END,
        },
    )
    for specialist, tools, collector_name in (
        ("sql", "tools_sql", "collect_sql"),
        ("statistics", "tools_statistics", "collect_statistics"),
        ("visualization", "tools_visualization", "collect_visualization"),
    ):
        workflow.add_conditional_edges(
            specialist, route_tool_calls, {"tools": tools, "next": "orchestrator"}
        )
        workflow.add_edge(tools, collector_name)
        workflow.add_edge(collector_name, specialist)

    return workflow.compile()
