"""Topic authorization decisions — pure functions."""

from __future__ import annotations

from domain.topics import Grant, TopicSpec, authorize_subscription, default_spec


def g(**kw):
    kw.setdefault("environment", "production")
    return Grant(**kw)


def test_public_topic_open_to_same_environment():
    assert authorize_subscription("payments", g())


def test_cross_environment_denied():
    spec = TopicSpec("payments", "public", "staging")
    d = authorize_subscription("payments", g(environment="production"), spec)
    assert not d and d.code == "forbidden"


def test_user_topic_requires_matching_claim():
    assert authorize_subscription("user:5", g(user_id="5"))
    assert not authorize_subscription("user:5", g(user_id="6"))
    assert not authorize_subscription("user:5", g())


def test_org_and_project_topics():
    assert authorize_subscription("organization:9", g(organization_id="9"))
    assert not authorize_subscription("organization:9", g(organization_id="8"))
    assert authorize_subscription("project:7", g(project_ids=frozenset({"7"})))
    assert not authorize_subscription("project:7", g(project_ids=frozenset({"1"})))


def test_system_topics_need_scope():
    assert not authorize_subscription("system", g())
    assert authorize_subscription("system", g(scopes=frozenset({"system:read"})))
    assert authorize_subscription("audit", g(operator=True))


def test_private_row_needs_explicit_grant_or_pattern():
    spec = TopicSpec("secret-topic", "private", "production")
    assert not authorize_subscription("secret-topic", g(), spec)
    assert authorize_subscription("secret-topic", g(topic_patterns=("secret-*",)), spec)


def test_operator_sees_everything_in_env():
    spec = TopicSpec("anything", "private", "production")
    assert authorize_subscription("anything", g(operator=True), spec)


def test_default_spec_classification():
    assert default_spec("payments", "e").visibility == "public"
    assert default_spec("user:1", "e").visibility == "private"
    assert default_spec("system", "e").visibility == "internal"
