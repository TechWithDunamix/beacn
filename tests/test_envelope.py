"""Unit tests for the event envelope — no database, no framework."""

from __future__ import annotations

import pytest

from domain.errors import PayloadTooLargeError, ValidationError
from domain.events import MAX_DATA_BYTES, Envelope, ProducerContext, parse_batch

CTX = ProducerContext(producer="payments-api", producer_id="prd_1", environment="production")


def test_minimal_event_gets_server_fields():
    e = Envelope.ingest({"event": "payment.completed", "topic": "payments"}, CTX)
    assert e.id.startswith("evt_")
    assert e.producer == "payments-api"
    assert e.environment == "production"  # from context, not body
    assert e.severity == "info"
    assert e.kind == "event"
    assert e.timestamp.tzinfo is not None


def test_body_cannot_spoof_environment_or_producer():
    e = Envelope.ingest(
        {"event": "x.y", "topic": "t", "environment": "development", "producer": "evil"}, CTX
    )
    assert e.environment == "production"
    assert e.producer == "payments-api"


def test_topic_defaults_to_event_head():
    e = Envelope.ingest({"event": "deployment.completed"}, CTX)
    assert e.topic == "deployment"


@pytest.mark.parametrize("name", ["", "Bad Name", "a..b", "a.b.c.d.e.f.g.h.i.j"])
def test_bad_event_names_rejected(name):
    with pytest.raises(ValidationError):
        Envelope.ingest({"event": name, "topic": "t"}, CTX)


def test_bad_severity_rejected():
    with pytest.raises(ValidationError):
        Envelope.ingest({"event": "a.b", "topic": "t", "severity": "loud"}, CTX)


def test_oversized_payload_rejected():
    big = {"blob": "x" * (MAX_DATA_BYTES + 10)}
    with pytest.raises(PayloadTooLargeError):
        Envelope.ingest({"event": "a.b", "topic": "t", "data": big}, CTX)


def test_non_serialisable_payload_rejected():
    with pytest.raises(ValidationError):
        Envelope.ingest({"event": "a.b", "topic": "t", "data": {"x": object()}}, CTX)


def test_task_kind_and_fields_derived():
    e = Envelope.ingest(
        {"event": "task.completed", "data": {"task_id": "c-9", "name": "orders.process", "status": "success"}},
        CTX,
    )
    assert e.kind == "task"
    assert e.task_id == "c-9"
    assert e.task_name == "orders.process"
    assert e.task_status == "completed"


def test_notification_and_message_kinds():
    n = Envelope.ingest({"event": "notification.created", "topic": "notifications"}, CTX)
    assert n.kind == "notification"
    m = Envelope.ingest({"event": "chat.message.created", "topic": "chat:42"}, CTX)
    assert m.kind == "message"


def test_wire_shape_round_trips_ids():
    e = Envelope.ingest(
        {"event": "a.b", "topic": "t", "correlation_id": "cor_1", "data": {"n": 1}}, CTX
    )
    wire = e.to_wire()
    assert wire["id"] == e.id
    assert wire["correlation_id"] == "cor_1"
    assert wire["timestamp"].endswith("Z")
    assert wire["data"] == {"n": 1}


def test_parse_batch_forms():
    assert len(parse_batch({"event": "a.b"})) == 1
    assert len(parse_batch({"events": [{"event": "a.b"}, {"event": "c.d"}]})) == 2
    assert len(parse_batch([{"event": "a.b"}])) == 1
    with pytest.raises(ValidationError):
        parse_batch({"events": []})
    with pytest.raises(ValidationError):
        parse_batch("nope")


def test_ids_are_monotonic():
    from domain.ids import new_ulid

    ids = [new_ulid() for _ in range(2000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
