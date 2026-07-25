"""Tests for the LangGraph agent graph structure and routing."""

from langchain_core.messages import AIMessage, HumanMessage

from backend.services.agent.graph import create_agent_graph, route_after_orchestrator, route_tool_calls
from backend.services.agent.nodes.orchestrator import OrchestratorNode
from backend.services.agent.nodes.sql import SqlNode
from backend.services.agent.nodes.statistics import StatisticsNode
from backend.services.agent.nodes.visualization import VisualizationNode
from backend.services.agent.state import AgentState, PlanStep


# ---------------------------------------------------------------------------
# route_tool_calls
# ---------------------------------------------------------------------------


class TestRouteToolCalls:
    def test_empty_messages_returns_next(self):
        state = AgentState(messages=[])
        assert route_tool_calls(state) == "next"

    def test_no_tool_calls_returns_next(self):
        state = AgentState(messages=[AIMessage(content="Hello")])
        assert route_tool_calls(state) == "next"

    def test_with_tool_calls_returns_tools(self):
        msg = AIMessage(
            content="",
            tool_calls=[{"name": "test", "args": {}, "id": "1"}],
        )
        state = AgentState(messages=[msg])
        assert route_tool_calls(state) == "tools"

    def test_human_message_returns_next(self):
        state = AgentState(messages=[HumanMessage(content="hi")])
        assert route_tool_calls(state) == "next"


class TestPlanRouting:
    def test_routes_to_first_pending_specialist(self):
        state = AgentState(pending_steps=[PlanStep(specialist="sql", objective="Descubrir datos")])
        assert route_after_orchestrator(state) == "sql"

    def test_routes_to_second_specialist_after_sql(self):
        state = AgentState(
            pending_steps=[PlanStep(specialist="statistics", objective="Analizar datos")],
        )
        assert route_after_orchestrator(state) == "statistics"

    def test_routes_sql_statistics_then_visualization(self):
        state = AgentState(
            pending_steps=[PlanStep(specialist="visualization", objective="Visualizar datos")],
        )
        assert route_after_orchestrator(state) == "visualization"

    def test_routes_sql_then_visualization(self):
        state = AgentState(
            pending_steps=[PlanStep(specialist="visualization", objective="Visualizar datos")],
        )
        assert route_after_orchestrator(state) == "visualization"

    def test_returns_to_orchestrator_for_final_formatting(self):
        state = AgentState(planning_started=True)
        assert route_after_orchestrator(state) == "orchestrator"


class TestSanitizeToolCallsInMessages:
    def test_injects_missing_tool_messages(self):
        from langchain_core.messages import ToolMessage
        from backend.services.agent.nodes.base import sanitize_tool_calls_in_messages

        messages = [
            HumanMessage(content="hi"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "tool1", "args": {}, "id": "call_1"},
                    {"name": "tool2", "args": {}, "id": "call_2"},
                ],
            ),
            ToolMessage(content="res1", tool_call_id="call_1"),
        ]

        sanitized = sanitize_tool_calls_in_messages(messages)
        assert len(sanitized) == 4
        assert isinstance(sanitized[3], ToolMessage)
        assert sanitized[3].tool_call_id == "call_2"


# ---------------------------------------------------------------------------
# Graph compilation and structure
# ---------------------------------------------------------------------------


class TestAgentGraph:
    def test_graph_compiles(self):
        """Graph should compile without errors."""
        graph = create_agent_graph(
            OrchestratorNode(),
            SqlNode(),
            StatisticsNode(),
            VisualizationNode(),
        )
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        graph = create_agent_graph(
            OrchestratorNode(),
            SqlNode(),
            StatisticsNode(),
            VisualizationNode(),
        )
        node_names = set(graph.nodes.keys())

        expected = {
            "__start__",
            "orchestrator",
            "sql",
            "statistics",
            "visualization",
            "tools_sql",
            "tools_statistics",
            "tools_visualization",
            "collect_sql",
            "collect_statistics",
            "collect_visualization",
        }
        # All expected nodes must be present
        assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"
