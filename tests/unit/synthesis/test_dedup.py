"""Tests for `dedup.cluster_near_duplicates` with a mocked Anthropic client.

Mock the AnthropicClient at the class level (not the SDK level) — `dedup`
calls `client.generate_json()` and we assert call counts directly. This
keeps tests fast, deterministic, and free of real Haiku spend.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmResponse, LlmResponseError
from pulse_check.storage.enums import SourceType
from pulse_check.storage.models import Mention
from pulse_check.synthesis.dedup import cluster_near_duplicates


def _make_mention(mention_id: str, raw_text: str) -> Mention:
    """Construct an unpersisted Mention. The dedup function only reads
    `mention_id` and `raw_text`, so DB insertion isn't required."""
    return Mention(
        mention_id=mention_id,
        source_type=SourceType.REDDIT_POST,
        source_url="https://example.com",
        raw_text=raw_text,
    )


def _make_client(json_response: str) -> Any:
    client = MagicMock()
    client.generate_json.return_value = LlmResponse(
        raw_output=json_response,
        parsed_output=json.loads(json_response),
    )
    return client


# ---------------------------------------------------------------------------
# Edge-case short-circuits (no LLM call)
# ---------------------------------------------------------------------------


def test_empty_list_returns_empty_dict_without_llm_call(session: Session) -> None:
    client = _make_client('{"assignments": []}')

    result = cluster_near_duplicates(session, [], client=client)

    assert result == {}
    client.generate_json.assert_not_called()


def test_single_mention_returns_c0_without_llm_call(session: Session) -> None:
    m1 = _make_mention("m1", "The fans are loud")
    client = _make_client('{"assignments": []}')

    result = cluster_near_duplicates(session, [m1], client=client)

    assert result == {"m1": "c0"}
    client.generate_json.assert_not_called()


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_three_distinct_mentions_get_three_clusters(session: Session) -> None:
    mentions = [
        _make_mention("m1", "The fans are loud"),
        _make_mention("m2", "Battery lasts 8 hours"),
        _make_mention("m3", "Display is bright"),
    ]
    client = _make_client(json.dumps({
        "assignments": [
            {"mention_id": "m1", "cluster_id": "X"},
            {"mention_id": "m2", "cluster_id": "Y"},
            {"mention_id": "m3", "cluster_id": "Z"},
        ]
    }))

    result = cluster_near_duplicates(session, mentions, client=client)

    assert result == {"m1": "c0", "m2": "c1", "m3": "c2"}
    client.generate_json.assert_called_once()


def test_paraphrases_share_cluster_distinct_stands_alone(session: Session) -> None:
    mentions = [
        _make_mention("m1", "The fans run loud"),
        _make_mention("m2", "Fans are loud"),
        _make_mention("m3", "Battery dies in 2 hours"),
    ]
    client = _make_client(json.dumps({
        "assignments": [
            {"mention_id": "m1", "cluster_id": "LOUD"},
            {"mention_id": "m2", "cluster_id": "LOUD"},
            {"mention_id": "m3", "cluster_id": "BATTERY"},
        ]
    }))

    result = cluster_near_duplicates(session, mentions, client=client)

    assert result == {"m1": "c0", "m2": "c0", "m3": "c1"}
    client.generate_json.assert_called_once()


def test_second_call_with_same_input_hits_cache(session: Session) -> None:
    mentions = [
        _make_mention("m1", "The fans are loud"),
        _make_mention("m2", "Battery lasts 8 hours"),
    ]
    client = _make_client(json.dumps({
        "assignments": [
            {"mention_id": "m1", "cluster_id": "A"},
            {"mention_id": "m2", "cluster_id": "B"},
        ]
    }))

    first = cluster_near_duplicates(session, mentions, client=client)
    second = cluster_near_duplicates(session, mentions, client=client)

    assert first == second == {"m1": "c0", "m2": "c1"}
    assert client.generate_json.call_count == 1  # cache hit on second call


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_missing_mention_id_in_response_raises(session: Session) -> None:
    mentions = [
        _make_mention("m1", "The fans are loud"),
        _make_mention("m2", "Battery lasts 8 hours"),
    ]
    client = _make_client(json.dumps({
        "assignments": [{"mention_id": "m1", "cluster_id": "A"}]
    }))

    with pytest.raises(LlmResponseError, match="missing mention_ids"):
        cluster_near_duplicates(session, mentions, client=client)


def test_extra_mention_id_in_response_raises(session: Session) -> None:
    mentions = [
        _make_mention("m1", "The fans are loud"),
        _make_mention("m2", "Battery lasts 8 hours"),
    ]
    client = _make_client(json.dumps({
        "assignments": [
            {"mention_id": "m1", "cluster_id": "A"},
            {"mention_id": "m2", "cluster_id": "A"},
            {"mention_id": "m_ghost", "cluster_id": "B"},
        ]
    }))

    with pytest.raises(LlmResponseError, match="extra mention_ids"):
        cluster_near_duplicates(session, mentions, client=client)


def test_response_not_object_raises(session: Session) -> None:
    mentions = [
        _make_mention("m1", "a"),
        _make_mention("m2", "b"),
    ]
    client = _make_client('[{"mention_id": "m1", "cluster_id": "A"}]')

    with pytest.raises(LlmResponseError, match="expected JSON object"):
        cluster_near_duplicates(session, mentions, client=client)


def test_assignments_not_list_raises(session: Session) -> None:
    mentions = [
        _make_mention("m1", "a"),
        _make_mention("m2", "b"),
    ]
    client = _make_client('{"assignments": "not a list"}')

    with pytest.raises(LlmResponseError, match="'assignments' to be a list"):
        cluster_near_duplicates(session, mentions, client=client)
