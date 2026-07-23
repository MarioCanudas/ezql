from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from backend.services.agent.state import AgentState
from backend.services.agent.nodes.base import NodeBase
from backend.services.agent.tools import sql_tools, statistics_tools


def route_node(state: AgentState):
    if not state.messages:
        return END

    last_message = state.messages[-1]

    # Maneja tanto si last_message es un objeto (AIMessage) como si es un diccionario
    if isinstance(last_message, dict):
        tool_calls = last_message.get("tool_calls", [])
    else:
        tool_calls = getattr(last_message, "tool_calls", [])

    if tool_calls:
        return "tools"

    return END


def create_agent_graph(
    sql_node: NodeBase, statistics_node: NodeBase, visualization_node: NodeBase
):
    """
    Creates and compiles the main agent graph using injected node instances.
    """
    workflow = StateGraph(AgentState)

    tool_node_sql = ToolNode(sql_tools)
    tool_node_statistics = ToolNode(statistics_tools)

    # Add nodes
    workflow.add_node("sql", sql_node)
    workflow.add_node("statistics", statistics_node)
    workflow.add_node("tools_sql", tool_node_sql)
    workflow.add_node("tools_statistics", tool_node_statistics)
    workflow.add_node("visualization", visualization_node)

    # Add edges
    workflow.add_edge(START, "sql")

    # Enrutamiento condicional para SQL
    workflow.add_conditional_edges(
        "sql",
        route_node,
        {"tools": "tools_sql", END: END},
    )

    # Enrutamiento condicional para Statistics
    workflow.add_conditional_edges(
        "statistics",
        route_node,
        {"tools": "tools_statistics", END: END},
    )

    # Enrutamiento estático de vuelta. 
    # NOTA: Si una herramienta devuelve Command(goto="..."), LangGraph 1.2+ sobrescribirá estas aristas
    # y enrutará automáticamente al nodo deseado.
    workflow.add_edge("tools_sql", "sql")
    workflow.add_edge("tools_statistics", "statistics")

    return workflow.compile()
