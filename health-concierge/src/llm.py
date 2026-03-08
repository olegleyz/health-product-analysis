"""LLM integration layer.

Wraps the Anthropic Claude API for message generation.
Handles prompt construction, token management, and response parsing.
"""

import json
import logging
import time

import anthropic

from config import settings

logger = logging.getLogger("llm")

_client: anthropic.Anthropic | None = None

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0  # seconds
_TIMEOUT = 30.0  # seconds


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.claude_api_key)
    return _client


def call_llm(
    system_prompt: str, user_message: str, max_tokens: int = 1024
) -> str:
    """Send a message to Claude and return the response text.

    Retries up to 3 times with exponential backoff on transient errors
    (rate limit / 5xx). No retry on client errors (4xx except 429).
    """
    last_error: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        start = time.monotonic()
        try:
            response = _get_client().messages.create(
                model=settings.claude_model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                timeout=_TIMEOUT,
            )
            latency = time.monotonic() - start

            logger.info(
                "LLM call model=%s input_tokens=%d output_tokens=%d latency=%.2fs",
                settings.claude_model,
                response.usage.input_tokens,
                response.usage.output_tokens,
                latency,
            )

            return response.content[0].text

        except anthropic.RateLimitError as exc:
            last_error = exc
            if attempt < _MAX_RETRIES:
                backoff = _INITIAL_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "Rate limited (attempt %d/%d), retrying in %.1fs",
                    attempt,
                    _MAX_RETRIES,
                    backoff,
                )
                time.sleep(backoff)
            else:
                logger.error("Rate limited, exhausted all %d retries", _MAX_RETRIES)

        except anthropic.APIStatusError as exc:
            last_error = exc
            if exc.status_code >= 500 and attempt < _MAX_RETRIES:
                backoff = _INITIAL_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "Server error %d (attempt %d/%d), retrying in %.1fs",
                    exc.status_code,
                    attempt,
                    _MAX_RETRIES,
                    backoff,
                )
                time.sleep(backoff)
            else:
                raise

        except anthropic.APITimeoutError:
            raise

    # All retries exhausted for rate-limit / 5xx errors
    raise last_error  # type: ignore[misc]


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from LLM responses.

    LLMs frequently wrap JSON in ```json ... ``` blocks. This strips
    those fences so json.loads() can parse the content.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1:]
        # Remove closing fence
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()
    return stripped


def call_llm_json(
    system_prompt: str, user_message: str, max_tokens: int = 1024
) -> dict:
    """Send a message to Claude and parse the response as JSON.

    Strips markdown code fences if present before parsing.
    Raises ValueError if the response is not valid JSON.
    """
    text = call_llm(system_prompt, user_message, max_tokens)
    cleaned = _strip_markdown_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {text!r}") from exc
