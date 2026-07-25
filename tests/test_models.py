"""Tests for Pydantic model validation and schema contracts."""

from datetime import datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.models import (
    AgentReply,
    AgentResponse,
    ChatReplyRequest,
    ChatReplyResponse,
    Content,
    MessageRead,
    Role,
)
from backend.models.blocks import (
    ChartBlock,
    DataBlock,
    MarkdownBlock,
    MetricBlock,
    OutlierBlock,
    TableBlock,
    TrendBlock,
    UIBlock,
)


# ---------------------------------------------------------------------------
# Content model
# ---------------------------------------------------------------------------


class TestContent:
    def test_valid_text(self):
        c = Content(text="hello", data=None)
        assert c.text == "hello"
        assert c.data is None
        assert c.blocks is None

    def test_empty_text_is_allowed(self):
        c = Content(text="", data=None)
        assert c.text == ""

    def test_with_typed_blocks(self):
        block = MetricBlock(label="Sales", value="$100")
        c = Content(text="results", blocks=[block])
        assert len(c.blocks) == 1  # type: ignore[arg-type]

    def test_with_none_data(self):
        c = Content(text="hello", data=None, blocks=None)
        assert c.data is None
        assert c.blocks is None


# ---------------------------------------------------------------------------
# AgentReply model
# ---------------------------------------------------------------------------


class TestAgentReply:
    def test_basic(self):
        reply = AgentReply(text="answer")
        assert reply.text == "answer"
        assert reply.data is None
        assert reply.blocks is None

    def test_with_blocks(self):
        block = MetricBlock(label="Total", value="42")
        reply = AgentReply(text="answer", blocks=[block])
        assert len(reply.blocks) == 1  # type: ignore[arg-type]

    def test_immutability(self):
        reply = AgentReply(text="test")
        with pytest.raises(ValidationError):
            reply.text = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DataBlock discriminated union
# ---------------------------------------------------------------------------


class TestDataBlock:
    adapter = TypeAdapter(UIBlock)

    def test_markdown_block(self):
        block = self.adapter.validate_python({"type": "markdown", "content": "Hello"})
        assert isinstance(block, MarkdownBlock)

    def test_table_block(self):
        block = self.adapter.validate_python(
            {"type": "table", "columns": ["a"], "data": [{"a": 1}]}
        )
        assert isinstance(block, TableBlock)

    def test_metric_block(self):
        block = self.adapter.validate_python(
            {"type": "metric", "label": "Sales", "value": "$100"}
        )
        assert isinstance(block, MetricBlock)

    def test_trend_block(self):
        block = self.adapter.validate_python(
            {"type": "trend", "metric": "Revenue", "pct_change": 5.2, "direction": "up"}
        )
        assert isinstance(block, TrendBlock)

    def test_outlier_block(self):
        block = self.adapter.validate_python(
            {"type": "outliers", "message": "2 outliers found"}
        )
        assert isinstance(block, OutlierBlock)

    def test_chart_block(self):
        block = self.adapter.validate_python(
            {
                "type": "chart",
                "chart_type": "bar",
                "x_axis": "month",
                "y_axis": ["sales"],
                "data": [{"month": "Jan", "sales": 10}],
            }
        )
        assert isinstance(block, ChartBlock)

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            self.adapter.validate_python({"type": "unknown", "data": []})


# ---------------------------------------------------------------------------
# AgentResponse model
# ---------------------------------------------------------------------------


class TestAgentResponse:
    def test_valid_agent_response(self):
        resp = AgentResponse(
            summary="Ventas crecieron 15%",
            blocks=[
                MarkdownBlock(content="### Análisis"),
                MetricBlock(label="Total", value="$150,000", delta="+15%"),
                ChartBlock(
                    chart_type="bar",
                    title="Ventas por Mes",
                    x_axis="mes",
                    y_axis=["ventas"],
                    data=[{"mes": "Ene", "ventas": 150000}],
                ),
            ],
        )
        assert resp.summary == "Ventas crecieron 15%"
        assert len(resp.blocks) == 3
        assert resp.blocks[0].type == "markdown"
        assert resp.blocks[1].type == "metric"
        assert resp.blocks[2].type == "chart"


# ---------------------------------------------------------------------------
# Individual block validation
# ---------------------------------------------------------------------------


class TestBlockValidation:
    def test_metric_requires_label_and_value(self):
        with pytest.raises(ValidationError):
            MetricBlock(type="metric")  # type: ignore[call-arg]

    def test_trend_requires_direction(self):
        with pytest.raises(ValidationError):
            TrendBlock(type="trend", metric="X")  # type: ignore[call-arg]

    def test_outlier_requires_message(self):
        with pytest.raises(ValidationError):
            OutlierBlock(type="outliers")  # type: ignore[call-arg]

    def test_chart_requires_fields(self):
        with pytest.raises(ValidationError):
            ChartBlock(type="chart")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class TestChatReplySchemas:
    def test_request_schema(self):
        req = ChatReplyRequest(content=Content(text="Hello", data=None))
        assert req.content.text == "Hello"
        assert req.user_id is None

    def test_request_with_user_id(self):
        req = ChatReplyRequest(content=Content(text="Hi", data=None), user_id=1)
        assert req.user_id == 1

    def test_response_schema(self):
        msg = MessageRead(
            id=1,
            chat_id=1,
            role=Role.user,
            content=Content(text="Hello", data=None),
            sent_at=datetime.now(),
        )
        resp = ChatReplyResponse(user_message=msg, assistant_message=msg)
        assert resp.user_message.id == 1
        assert resp.assistant_message.role == Role.user
