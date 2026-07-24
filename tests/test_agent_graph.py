"""Tests for the LangGraph agent graph structure and routing."""

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END

from backend.services.agent.graph import create_agent_graph, route_tool_calls
from backend.services.agent.nodes.orchestrator import OrchestratorNode
from backend.services.agent.nodes.sql import SqlNode
from backend.services.agent.nodes.statistics import StatisticsNode
from backend.services.agent.nodes.visualization import VisualizationNode
from backend.services.agent.state import AgentState


# ---------------------------------------------------------------------------
# route_tool_calls
# ---------------------------------------------------------------------------


class TestRouteToolCalls:
    def test_empty_messages_returns_end(self):
        state = AgentState(messages=[])
        assert route_tool_calls(state) == END

    def test_no_tool_calls_returns_end(self):
        state = AgentState(messages=[AIMessage(content="Hello")])
        assert route_tool_calls(state) == END

    def test_with_tool_calls_returns_tools(self):
        msg = AIMessage(
            content="",
            tool_calls=[{"name": "test", "args": {}, "id": "1"}],
        )
        state = AgentState(messages=[msg])
        assert route_tool_calls(state) == "tools"

    def test_human_message_returns_end(self):
        state = AgentState(messages=[HumanMessage(content="hi")])
        assert route_tool_calls(state) == END


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
            "tools_orchestrator",
            "tools_sql",
            "tools_statistics",
            "tools_visualization",
        }
        # All expected nodes must be present
        assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"
