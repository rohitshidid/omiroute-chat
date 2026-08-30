#!/usr/bin/env python3
"""
A name-translating proxy that puts the usable OmniRoute models in Claude Code's
/model picker.

Claude Code can populate the picker from a gateway's /v1/models, but it
"ignores entries whose id doesn't begin with claude or anthropic". OmniRoute
names things oc/mimo-v2.5-free and aug/opus4.8, so discovery against it returns
nothing at all.

This sits in front of OmniRoute and does three things:

  GET  /v1/models   rename  oc/mimo-v2.5-free -> claude-omni-oc__mimo-v2.5-free
                    and hand back the real name as display_name, so the picker
                    shows what you actually recognise. Models that are known
                    broken, cost money, or can't call tools are left out.
  POST /v1/messages translate the name back before OmniRoute sees it.
  background        sweep the catalogue gently and remember what works.

Everything else is passed straight through, streaming included.

    ./omnishim.py            # listens on 20129, forwards to 20128
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("OMNIROUTE_ROOT", "http://localhost:20128").rstrip("/")
PORT = int(os.environ.get("OMNISHIM_PORT", "20129"))

PREFIX = "claude-omni-"
# "/" is not safe in a model id here, so swap it for a pair of underscores.
# No OmniRoute id contains "__", which keeps the mapping reversible.
SEP = "__"

# Providers that are not a free tier. aug/* bills against an Augment
# subscription and needs the Auggie CLI. Set OMNI_INCLUDE_PAID=1 to list them.
PAID = {"aug"}
INCLUDE_PAID = os.environ.get("OMNI_INCLUDE_PAID") == "1"

HEALTH_PATH = os.path.expanduser("~/.cache/omnishim-health.json")
HEALTH_TTL = int(os.environ.get("OMNI_HEALTH_TTL", "3600"))   # re-sweep hourly
PROBE_GAP = float(os.environ.get("OMNI_PROBE_GAP", "3"))      # free tiers bite

HOP = {"host", "content-length", "connection", "transfer-encoding", "accept-encoding"}

_health_lock = threading.Lock()


def encode(model_id: str) -> str:
    return PREFIX + model_id.replace("/", SEP)


def decode(model_id: str) -> str:
    # Claude Code normally strips "[1m]" itself and sends the beta header, but
    # drop it defensively so a stray suffix can't reach OmniRoute as a name.
    if model_id.endswith("[1m]"):
        model_id = model_id[:-4]
    if model_id.startswith(PREFIX):
        return model_id[len(PREFIX):].replace(SEP, "/")
    return model_id


# ── health cache ─────────────────────────────────────────────────────────


def load_health() -> dict:
    try:
        with open(HEALTH_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def save_health(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(HEALTH_PATH), exist_ok=True)
        tmp = HEALTH_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(tmp, HEALTH_PATH)
    except Exception:
        pass


def catalogue() -> list[dict]:
    with urllib.request.urlopen(UPSTREAM + "/v1/models", timeout=10) as response:
        return json.loads(response.read()).get("data", [])


def usable(model: dict) -> bool:
    """Could Claude Code drive this model at all, and is it free?"""
    mid = model.get("id", "")
    if not mid or mid.startswith("auto/"):
        return False          # combos fall through to dead providers
    if "text" not in (model.get("output_modalities") or ["text"]):
        return False          # image/video models
    if not model.get("capabilities", {}).get("tool_calling"):
        return False          # Claude Code is entirely tool-driven
    if not INCLUDE_PAID and mid.split("/")[0] in PAID:
        return False
    return True


def probe(model_id: str) -> bool:
    """Does this model answer a request that carries a tool schema?

    A bare "hi" is not enough: several models here take plain chat happily and
    then 500 the moment a tools array appears.
    """
    body = json.dumps({
        "model": model_id,
        "stream": False,
        "max_tokens": 256,
        "tools": [{"type": "function", "function": {
            "name": "ping", "description": "Ping a host",
            "parameters": {"type": "object",
                           "properties": {"host": {"type": "string"}},
                           "required": ["host"]}}}],
        "messages": [{"role": "user", "content": "Use the ping tool on example.com"}],
    }).encode()
    request = urllib.request.Request(
        UPSTREAM + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30):
            return True
    except Exception:
        return False


def sweep() -> None:
    """Walk the catalogue slowly, remembering what answers.

    Deliberately sequential with a gap between requests: hammering these free
    providers concurrently gets the whole account blocked for a few minutes.
    """
    try:
        models = [m["id"] for m in catalogue() if usable(m)]
    except Exception:
        return
    for mid in models:
        ok = probe(mid)
        with _health_lock:
            health = load_health()
            health[mid] = {"ok": ok, "at": time.time()}
            save_health(health)
        time.sleep(PROBE_GAP)


def maybe_sweep() -> None:
    health = load_health()
    newest = max((v.get("at", 0) for v in health.values()), default=0)
    if time.time() - newest > HEALTH_TTL:
        threading.Thread(target=sweep, daemon=True).start()


# ── proxy ────────────────────────────────────────────────────────────────


class Shim(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def _relay_headers(self):
        return {k: v for k, v in self.headers.items() if k.lower() not in HOP}

    def _fail(self, code: int, message: str):
        body = json.dumps({"error": {"type": "shim_error", "message": message}}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self, body: bytes | None):
        """Relay this request upstream and stream the response straight back."""
        request = urllib.request.Request(
            UPSTREAM + self.path, data=body,
            headers=self._relay_headers(), method=self.command)
        try:
            upstream = urllib.request.urlopen(request, timeout=900)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() not in HOP:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        except Exception as exc:
            self._fail(502, f"cannot reach OmniRoute at {UPSTREAM}: {exc}")
            return

        with upstream:
            self.send_response(upstream.status)
            chunked = upstream.headers.get("Transfer-Encoding", "").lower() == "chunked"
            for key, value in upstream.headers.items():
                if key.lower() not in HOP:
                    self.send_header(key, value)
            if chunked or upstream.headers.get("Content-Length") is None:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            try:
                # Small reads and an explicit flush, so SSE tokens reach Claude
                # Code as they arrive instead of sitting in a buffer.
                while chunk := upstream.read(1024):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True   # client hung up; normal

    def do_GET(self):
        if self.path.split("?")[0] != "/v1/models":
            return self._proxy(None)

        try:
            models = catalogue()
        except Exception as exc:
            return self._fail(502, f"cannot list models: {exc}")

        maybe_sweep()
        health = load_health()
        fresh = time.time() - HEALTH_TTL

        entries, every = [], []
        for model in models:
            mid = model["id"]
            if not usable(model):
                continue
            # Hide what we know is broken. A model we haven't reached yet stays
            # listed, so the picker is useful before the first sweep finishes.
            seen = health.get(mid)
            dead = bool(seen and seen.get("at", 0) > fresh and not seen.get("ok"))

            ctx = model.get("context_length") or 0
            # Claude Code budgets 200K for a model it doesn't recognise. The
            # "[1m]" suffix raises that to 1M: the client strips the suffix and
            # sends the context-1m beta header, so OmniRoute still receives a
            # clean name. Only tag models that genuinely have the window —
            # claiming 1M on a 200K model just overflows it.
            eid, label = encode(mid), mid
            if ctx >= 1_000_000:
                eid += "[1m]"
                label = f"{mid}  (1M)"
            elif ctx > 200_000:
                label = f"{mid}  ({ctx // 1000}K)"

            entry = {"id": eid, "display_name": label, "type": "model"}
            every.append(entry)
            if not dead:
                entries.append(entry)

        # Never hand back an empty picker. When every free provider is failing
        # at once — which happens, they rate-limit in lockstep — showing the
        # full list beats showing nothing: by the time you pick one it may well
        # have recovered.
        if not entries:
            entries = every

        entries.sort(key=lambda e: e["display_name"])
        body = json.dumps({"data": entries, "has_more": False}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if body:
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("model"), str):
                payload["model"] = decode(payload["model"])
                body = json.dumps(payload).encode()
        self._proxy(body)

    do_HEAD = do_GET
    do_DELETE = lambda self: self._proxy(None)  # noqa: E731


if __name__ == "__main__":
    if "--sweep" in sys.argv:          # refresh the health cache and exit
        sweep()
        health = load_health()
        for mid, state in sorted(health.items()):
            print(f"{'ok  ' if state['ok'] else 'dead'}  {mid}")
        sys.exit(0)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Shim)
    except OSError as exc:
        sys.exit(f"cannot bind port {PORT}: {exc}")
    print(f"omnishim: 127.0.0.1:{PORT} → {UPSTREAM}", file=sys.stderr)
    maybe_sweep()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
