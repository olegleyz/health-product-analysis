"""Tests for Claude Vision API integration."""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from src.llm import call_llm_vision, call_llm_vision_json


# A tiny 1x1 JPEG for testing (valid image bytes)
_TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkS"
    "Ew8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJ"
    "CQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEA"
    "AAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIh"
    "MUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6"
    "Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZ"
    "mqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx"
    "8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA"
    "AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAV"
    "YnLRChYkNOEl8RcYI4Q/RFhHRUYnJCk2NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNk"
    "ZWZnaGlqc3R1dnd4eXqCg4SFhoeIiYqSk5SVlpeYmZqio6SlpqeoqaqyxLW2t7i5"
    "usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6ery8/T19vf4+fr/xAAfAAABBQEB"
    "AQEBAQAAAAAAAAAAAQIDBAUGBwgJCgv/2gAMAwEAAhEDEQA/AP0poA//2Q=="
)


def _mock_response(text: str):
    """Create a mock Anthropic API response."""
    content_block = MagicMock()
    content_block.text = text
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    response = MagicMock()
    response.content = [content_block]
    response.usage = usage
    return response


class TestCallLlmVision:
    @patch("src.llm._get_client")
    def test_call_llm_vision_sends_image_content_block(self, mock_get_client):
        """Vision call sends an image content block with base64 data."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_response("result")
        mock_get_client.return_value = mock_client

        call_llm_vision("system", _TINY_JPEG, "image/jpeg")

        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs["messages"]
        content = messages[0]["content"]

        # Should have at least one image block
        image_blocks = [b for b in content if b["type"] == "image"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["source"]["type"] == "base64"
        assert image_blocks[0]["source"]["media_type"] == "image/jpeg"
        assert image_blocks[0]["source"]["data"] == base64.b64encode(_TINY_JPEG).decode()

    @patch("src.llm._get_client")
    def test_call_llm_vision_includes_text_hint(self, mock_get_client):
        """When text_hint is provided, a text block is included."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_response("result")
        mock_get_client.return_value = mock_client

        call_llm_vision("system", _TINY_JPEG, "image/jpeg", text_hint="this is lunch")

        call_args = mock_client.messages.create.call_args
        content = call_args.kwargs["messages"][0]["content"]

        text_blocks = [b for b in content if b["type"] == "text"]
        assert len(text_blocks) == 1
        assert "this is lunch" in text_blocks[0]["text"]

    @patch("src.llm._get_client")
    def test_call_llm_vision_empty_text_hint(self, mock_get_client):
        """When text_hint is empty, no text block is included."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_response("result")
        mock_get_client.return_value = mock_client

        call_llm_vision("system", _TINY_JPEG, "image/jpeg", text_hint="")

        call_args = mock_client.messages.create.call_args
        content = call_args.kwargs["messages"][0]["content"]

        text_blocks = [b for b in content if b["type"] == "text"]
        assert len(text_blocks) == 0

    @patch("src.llm._get_client")
    def test_call_llm_vision_retries_on_rate_limit(self, mock_get_client):
        """Retries with backoff on 429 rate limit errors."""
        import anthropic

        mock_client = MagicMock()
        rate_limit_error = anthropic.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429),
            body={"error": {"message": "rate limited"}},
        )
        mock_client.messages.create.side_effect = [
            rate_limit_error,
            _mock_response("ok"),
        ]
        mock_get_client.return_value = mock_client

        with patch("src.llm.time.sleep"):
            result = call_llm_vision("system", _TINY_JPEG, "image/jpeg")

        assert result == "ok"
        assert mock_client.messages.create.call_count == 2

    @patch("src.llm._get_client")
    def test_call_llm_vision_retries_on_server_error(self, mock_get_client):
        """Retries on 5xx server errors."""
        import anthropic

        mock_client = MagicMock()
        server_error = anthropic.APIStatusError(
            message="server error",
            response=MagicMock(status_code=500),
            body={"error": {"message": "server error"}},
        )
        mock_client.messages.create.side_effect = [
            server_error,
            _mock_response("recovered"),
        ]
        mock_get_client.return_value = mock_client

        with patch("src.llm.time.sleep"):
            result = call_llm_vision("system", _TINY_JPEG, "image/jpeg")

        assert result == "recovered"

    @patch("src.llm._get_client")
    def test_call_llm_vision_no_retry_on_client_error(self, mock_get_client):
        """Does not retry on 4xx client errors (except 429)."""
        import anthropic

        mock_client = MagicMock()
        client_error = anthropic.APIStatusError(
            message="bad request",
            response=MagicMock(status_code=400),
            body={"error": {"message": "bad request"}},
        )
        mock_client.messages.create.side_effect = client_error
        mock_get_client.return_value = mock_client

        with pytest.raises(anthropic.APIStatusError):
            call_llm_vision("system", _TINY_JPEG, "image/jpeg")

        assert mock_client.messages.create.call_count == 1


class TestCallLlmVisionJson:
    @patch("src.llm._get_client")
    def test_call_llm_vision_json_parses_response(self, mock_get_client):
        """Parses a JSON response from the vision model."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_response(
            '{"meal_name": "pasta", "calories": 500}'
        )
        mock_get_client.return_value = mock_client

        result = call_llm_vision_json("system", _TINY_JPEG, "image/jpeg")

        assert result == {"meal_name": "pasta", "calories": 500}

    @patch("src.llm._get_client")
    def test_call_llm_vision_json_strips_markdown_fences(self, mock_get_client):
        """Strips ```json ... ``` fences before parsing."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_response(
            '```json\n{"meal_name": "salad"}\n```'
        )
        mock_get_client.return_value = mock_client

        result = call_llm_vision_json("system", _TINY_JPEG, "image/jpeg")

        assert result == {"meal_name": "salad"}

    @patch("src.llm._get_client")
    def test_call_llm_vision_json_raises_on_invalid_json(self, mock_get_client):
        """Raises ValueError on non-JSON response."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_response("not json at all")
        mock_get_client.return_value = mock_client

        with pytest.raises(ValueError, match="not valid JSON"):
            call_llm_vision_json("system", _TINY_JPEG, "image/jpeg")
