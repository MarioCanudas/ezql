"""Tests for Pydantic model validation and schema contracts."""

from datetime import datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.models import AgentReply, ChatReplyRequest, ChatReplyResponse, Content, MessageRead, Role
from backend.models.blocks import (
    ChartBlock,
    DataBlock,
    MetricBlock,
    OutlierBlock,
    TableBlock,
    TrendBlock,
)


# ---------------------------------------------------------------------------
# Content model
# ---------------------------------------------------------------------------


class TestContent:
    def test_valid_text(self):
        c = Content(text="hello", data=None)
        assert c.text == "hello"
        assert c.data is None

    def test_empty_text_is_allowed(self):
        c = Content(text="", data=None)
        assert c.text == ""

    def test_with_typed_data_blocks(self):
        block = MetricBlock(label="Sales", value=100)
        c = Content(text="results", data=[block])
        assert len(c.data) == 1  # type: ignore[arg-type]

    def test_with_none_data(self):
        c = Content(text="hello", data=None)
        assert c.data is None

    def test_with_raw_dict_backward_compat(self):
        """FlexibleDataBlock accepts raw dicts for legacy chats."""
        c = Content.model_validate({"text": "test", "data": [{"key": "value"}]})
        assert isinstance(c.data[0], dict)  # type: ignore[index]

    def test_with_raw_list_backward_compat(self):
        """FlexibleDataBlock accepts raw lists for legacy chats."""
        c = Content.model_validate({"text": "test", "data": [["a", "b"]]})
        assert isinstance(c.data[0], list)  # type: ignore[index]


# ---------------------------------------------------------------------------
# AgentReply model
# ---------------------------------------------------------------------------


class TestAgentReply:
    def test_basic(self):
        reply = AgentReply(text="answer")
        assert reply.text == "answer"
        assert reply.data is None

    def test_with_data(self):
        block = MetricBlock(label="Total", value=42)
        reply = AgentReply(text="answer", data=[block.model_dump()])
        assert len(reply.data) == 1  # type: ignore[arg-type]

    def test_immutability(self):
        reply = AgentReply(text="test")
        with pytest.raises(ValidationError):
            reply.text = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DataBlock discriminated union
# ---------------------------------------------------------------------------


class TestDataBlock:
    adapter = TypeAdapter(DataBlock)

    def test_table_block(self):
        block = self.adapter.validate_python({"type": "table", "rows": [{"a": 1}]})
        assert isinstance(block, TableBlock)

    def test_metric_block(self):
        block = self.adapter.validate_python({"type": "metric", "label": "Sales", "value": 100})
        assert isinstance(block, MetricBlock)

    def test_trend_block(self):
        block = self.adapter.validate_python(
            {"type": "trend", "metric": "Revenue", "pct_change": 5.2, "direction": "up"}
        )
        assert isinstance(block, TrendBlock)

    def test_outlier_block(self):
        block = self.adapter.validate_python({"type": "outliers", "message": "2 outliers found"})
        assert isinstance(block, OutlierBlock)

    def test_chart_block(self):
        block = self.adapter.validate_python({"type": "chart", "spec": {"mark": "bar"}})
        assert isinstance(block, ChartBlock)

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            self.adapter.validate_python({"type": "unknown", "data": []})


# ---------------------------------------------------------------------------
# Individual block validation
# ---------------------------------------------------------------------------


class TestBlockValidation:
    def test_metric_requires_label_and_value(self):
        with pytest.raises(ValidationError):
            MetricBlock(type="metric")  # type: ignore[call-arg]

    def test_trend_requires_all_fields(self):
        with pytest.raises(ValidationError):
            TrendBlock(type="trend", metric="X")  # type: ignore[call-arg]

    def test_outlier_requires_message(self):
        with pytest.raises(ValidationError):
            OutlierBlock(type="outliers")  # type: ignore[call-arg]

    def test_chart_requires_spec(self):
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
