"""Model-provider boundary for the query-to-page workflow."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """Raised when the configured model cannot return usable JSON."""


class JsonModel(Protocol):
    def complete_json(self, *, system: str, user: str, max_tokens: int = 16_000) -> dict[str, Any]:
        """Return one JSON object."""


@dataclass
class DeepSeekClient:
    """Small dependency-free client for DeepSeek's OpenAI-compatible API."""

    api_key: str
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    timeout_seconds: int = 180
    retries: int = 2

    @classmethod
    def from_env(cls) -> "DeepSeekClient":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise ProviderError(
                "DEEPSEEK_API_KEY is not set. Add it to your shell or an ignored local env file."
            )
        return cls(
            api_key=api_key,
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip()
            or "deepseek-flash",
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
            or "https://api.deepseek.com",
        )

    def complete_json(
        self, *, system: str, user: str, max_tokens: int = 16_000
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ojo-query-to-page-agent/0.2",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    body = json.loads(response.read().decode("utf-8"))
                content = body["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ProviderError("DeepSeek returned empty content.")
                value = json.loads(content)
                if not isinstance(value, dict):
                    raise ProviderError("DeepSeek returned JSON that is not an object.")
                return value
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:800]
                last_error = ProviderError(f"DeepSeek HTTP {exc.code}: {detail}")
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(2**attempt)
        raise ProviderError(f"DeepSeek request failed: {last_error}") from last_error


@dataclass
class FixtureClient:
    """Offline model used by the public demo and unit tests."""

    fixture_path: Path

    def complete_json(
        self, *, system: str, user: str, max_tokens: int = 16_000
    ) -> dict[str, Any]:
        del system, user, max_tokens
        try:
            value = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Cannot load fixture JSON: {self.fixture_path}: {exc}") from exc
        if not isinstance(value, dict):
            raise ProviderError(f"Fixture must contain a JSON object: {self.fixture_path}")
        return value
