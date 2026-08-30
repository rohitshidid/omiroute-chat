#!/usr/bin/env python3
"""
Zero-dependency client for the OmniRoute gateway.

OmniRoute is an OpenAI-compatible proxy, so this is mostly a plain
/v1/chat/completions client. Two gateway-specific behaviours are handled here:

  1. OmniRoute streams SSE when "stream" is omitted, so every request sets the
     flag explicitly rather than relying on the OpenAI default of false.
  2. Reasoning models return their scratchpad in a separate "reasoning_content"
     field next to "content".

The "model" field on the response is the model OmniRoute actually routed to,
which is not the one you asked for when you use a combo like auto/best-coding.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, List, Optional

DEFAULT_BASE_URL = "http://localhost:20128/v1"


class OmniRouteError(RuntimeError):
    """An error returned by the gateway, or a failure to reach it."""


def load_env(path: str = ".env") -> None:
    """Load KEY=VALUE lines from a .env file into os.environ.

    Existing environment variables win, so you can override the file per-shell.
    """
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


class OmniRoute:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 300,
    ) -> None:
        self.api_key = api_key or os.environ.get("OMNIROUTE_API_KEY", "")
        self.base_url = (
            base_url or os.environ.get("OMNIROUTE_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout

    def _open(self, path: str, payload: Optional[Dict[str, Any]] = None):
        headers = {"Content-Type": "application/json"}
        # A local gateway may not enforce auth, but send the key when we have one
        # so the same code works against a remote OmniRoute.
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method="POST" if data else "GET",
        )
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            try:
                detail = json.loads(body)["error"]["message"]
            except Exception:
                detail = body[:400] or exc.reason
            raise OmniRouteError(f"HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise OmniRouteError(
                f"Cannot reach OmniRoute at {self.base_url} ({exc.reason}). "
                "Is the gateway running? Start it with: omniroute"
            ) from None

    def models(self) -> List[Dict[str, Any]]:
        """Every model and combo the gateway can route to."""
        with self._open("/models") as response:
            return json.loads(response.read()).get("data", [])

    def complete(
        self, messages: List[Dict[str, str]], model: str, **params: Any
    ) -> Dict[str, Any]:
        """One non-streaming completion. Returns the raw response object."""
        payload = {"model": model, "messages": messages, "stream": False, **params}
        with self._open("/chat/completions", payload) as response:
            return json.loads(response.read())

    def stream(
        self, messages: List[Dict[str, str]], model: str, **params: Any
    ) -> Iterator[Dict[str, Any]]:
        """Stream a completion, yielding decoded SSE chunks as dicts."""
        payload = {"model": model, "messages": messages, "stream": True, **params}
        with self._open("/chat/completions", payload) as response:
            for raw in response:
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    continue
