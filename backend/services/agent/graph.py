from langgraph.graph import StateGraph, START, END
from backend.services.agent.state import AgentState
from backend.services.agent.nodes.base import NodeBase


def route_node(state: AgentState):
    """
    Router node that determines which sub-agent should handle the request.
    Currently routes everything to the SQL node, but will be expanded
    to route to statistics or visualization based on the user's query.
    """
    # Placeholder logic for routing
    return "sql"


def create_agent_graph(
    sql_node: NodeBase, statistics_node: NodeBase, visualization_node: NodeBase
):
    """
    Creates and compiles the main agent graph using injected node instances.
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("sql", sql_node)
    workflow.add_node("statistics", statistics_node)
    workflow.add_node("visualization", visualization_node)

    # Add edges
    workflow.add_conditional_edges(
        START,
        route_node,
        {"sql": "sql", "statistics": "statistics", "visualization": "visualization"},
    )

    workflow.add_edge("sql", END)
    workflow.add_edge("statistics", END)
    workflow.add_edge("visualization", END)

    return workflow.compile()
