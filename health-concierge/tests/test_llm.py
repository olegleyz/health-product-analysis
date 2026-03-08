"""Tests for the LLM integration layer."""

import logging
from unittest.mock import Mock, patch

import anthropic
import pytest

from src.llm import call_llm, call_llm_json


def _mock_response(text: str = "Hello", input_tokens: int = 10, output_tokens: int = 5):
    """Create a mock Anthropic message response."""
    resp = Mock()
    resp.content = [Mock(text=text)]
    resp.usage = Mock(input_tokens=input_tokens, output_tokens=output_tokens)
    return resp


@patch("src.llm._get_client")
def test_call_llm_returns_string(mock_get_client):
    client = mock_get_client.return_value
    client.messages.create.return_value = _mock_response("Hello world")

    result = call_llm("You are helpful.", "Say hello")

    assert isinstance(result, str)
    assert result == "Hello world"
    client.messages.create.assert_called_once()


@patch("src.llm._get_client")
def test_call_llm_json_returns_dict(mock_get_client):
    client = mock_get_client.return_value
    client.messages.create.return_value = _mock_response('{"key": "value"}')

    result = call_llm_json("You are helpful.", "Return JSON")

    assert isinstance(result, dict)
    assert result == {"key": "value"}


@patch("src.llm._get_client")
def test_call_llm_json_raises_on_invalid_json(mock_get_client):
    client = mock_get_client.return_value
    client.messages.create.return_value = _mock_response("not json at all")

    with pytest.raises(ValueError, match="not valid JSON"):
        call_llm_json("You are helpful.", "Return JSON")


@patch("src.llm.time.sleep")
@patch("src.llm._get_client")
def test_retry_on_rate_limit(mock_get_client, mock_sleep):
    client = mock_get_client.return_value
    rate_limit_error = anthropic.RateLimitError(
        message="rate limited",
        response=Mock(status_code=429, headers={}),
        body=None,
    )
    client.messages.create.side_effect = [
        rate_limit_error,
        _mock_response("Success after retry"),
    ]

    result = call_llm("system", "user")

    assert result == "Success after retry"
    assert client.messages.create.call_count == 2
    mock_sleep.assert_called_once()


@patch("src.llm._get_client")
def test_no_retry_on_client_error(mock_get_client):
    client = mock_get_client.return_value
    client_error = anthropic.BadRequestError(
        message="bad request",
        response=Mock(status_code=400, headers={}),
        body=None,
    )
    client.messages.create.side_effect = client_error

    with pytest.raises(anthropic.BadRequestError):
        call_llm("system", "user")

    assert client.messages.create.call_count == 1


@patch("src.llm._get_client")
def test_timeout_raises_error(mock_get_client):
    client = mock_get_client.return_value
    client.messages.create.side_effect = anthropic.APITimeoutError(
        request=Mock(),
    )

    with pytest.raises(anthropic.APITimeoutError):
        call_llm("system", "user")


@patch("src.llm._get_client")
def test_token_usage_logged(mock_get_client, caplog):
    client = mock_get_client.return_value
    client.messages.create.return_value = _mock_response(
        "Hi", input_tokens=42, output_tokens=17
    )

    with caplog.at_level(logging.INFO, logger="llm"):
        call_llm("system", "user")

    assert "input_tokens=42" in caplog.text
    assert "output_tokens=17" in caplog.text
