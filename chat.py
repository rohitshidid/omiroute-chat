#!/usr/bin/env python3
"""
A terminal chatbot for exercising an OmniRoute gateway.

Run it with `python3 chat.py`, then type. Slash commands are listed by /help.
Every reply reports the model OmniRoute actually routed to, the token usage and
the latency, which is the point of the thing: you can watch a combo like
auto/best-coding fall through to whichever provider is alive.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

from omniroute_client import OmniRoute, OmniRouteError, load_env


class C:
    """ANSI colours, blanked out when stdout is not a terminal."""

    on = sys.stdout.isatty()
    BLUE = "\033[94m" if on else ""
    GREEN = "\033[92m" if on else ""
    YELLOW = "\033[93m" if on else ""
    RED = "\033[91m" if on else ""
    DIM = "\033[2m" if on else ""
    BOLD = "\033[1m" if on else ""
    OFF = "\033[0m" if on else ""


HELP = f"""
{C.BOLD}Commands{C.OFF}
  {C.GREEN}/help{C.OFF}              show this
  {C.GREEN}/models{C.OFF} [filter]   list routable models, optionally filtered
  {C.GREEN}/model{C.OFF} <id>        switch model, e.g. /model aug/opus4.8
  {C.GREEN}/system{C.OFF} <text>     set the system prompt (no text clears it)
  {C.GREEN}/stream{C.OFF}            toggle streaming on/off
  {C.GREEN}/think{C.OFF}             toggle showing the model's reasoning
  {C.GREEN}/temp{C.OFF} <0.0-2.0>    set temperature
  {C.GREEN}/clear{C.OFF}             wipe conversation history
  {C.GREEN}/retry{C.OFF}             re-send the last message
  {C.GREEN}/history{C.OFF}           show the conversation so far
  {C.GREEN}/save{C.OFF} [file]       write the transcript to markdown
  {C.GREEN}/exit{C.OFF}              quit

End a line with {C.GREEN}\\{C.OFF} to continue it on the next line.
"""


class Chat:
    def __init__(self) -> None:
        load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
        self.client = OmniRoute()
        self.model = os.environ.get("OMNIROUTE_MODEL", "auto/best-chat")
        self.system = os.environ.get("OMNIROUTE_SYSTEM", "")
        self.temperature = 0.7
        self.streaming = True
        self.show_reasoning = False
        self.history: List[Dict[str, str]] = []

    # ---------- helpers ----------

    def payload(self) -> List[Dict[str, str]]:
        messages = [{"role": "system", "content": self.system}] if self.system else []
        return messages + self.history

    def banner(self) -> None:
        print(f"\n{C.BOLD}OmniRoute chat{C.OFF}")
        print(f"{C.DIM}gateway {self.client.base_url}{C.OFF}")
        try:
            models = self.client.models()
            key = "set" if self.client.api_key else "none (gateway is open)"
            print(f"{C.DIM}{len(models)} models routable · api key {key}{C.OFF}")
        except OmniRouteError as exc:
            print(f"{C.RED}{exc}{C.OFF}")
            sys.exit(1)
        print(f"{C.DIM}model {self.model} · /help for commands{C.OFF}\n")

    def stats(self, model: str, usage: Dict[str, Any], elapsed: float) -> None:
        bits = [f"{model}", f"{elapsed:.1f}s"]
        if usage:
            prompt = usage.get("prompt_tokens", 0)
            done = usage.get("completion_tokens", 0)
            bits.append(f"{prompt}+{done} tok")
            reasoning = usage.get("completion_tokens_details", {}).get(
                "reasoning_tokens", 0
            )
            if reasoning:
                bits.append(f"{reasoning} thinking")
            if done and elapsed > 0:
                bits.append(f"{done / elapsed:.0f} tok/s")
        print(f"\n{C.DIM}[{' · '.join(bits)}]{C.OFF}\n")

    # ---------- commands ----------

    def cmd_models(self, arg: str) -> None:
        try:
            models = self.client.models()
        except OmniRouteError as exc:
            print(f"{C.RED}{exc}{C.OFF}")
            return
        ids = sorted(m.get("id", "") for m in models)
        if arg:
            ids = [i for i in ids if arg.lower() in i.lower()]
            if not ids:
                print(f"{C.YELLOW}nothing matches {arg!r}{C.OFF}")
                return
        groups: Dict[str, List[str]] = {}
        for i in ids:
            groups.setdefault(i.split("/")[0] if "/" in i else "other", []).append(i)
        for provider, items in groups.items():
            print(f"\n{C.BOLD}{provider}{C.OFF} {C.DIM}({len(items)}){C.OFF}")
            for i in items:
                mark = f"{C.GREEN} ←{C.OFF}" if i == self.model else ""
                print(f"  {i}{mark}")
        print(f"\n{C.DIM}{len(ids)} shown · /model <id> to switch{C.OFF}")

    def cmd_save(self, arg: str) -> None:
        if not self.history:
            print(f"{C.YELLOW}nothing to save{C.OFF}")
            return
        name = arg or f"chat-{datetime.now():%Y%m%d-%H%M%S}.md"
        with open(name, "w", encoding="utf-8") as handle:
            handle.write(f"# OmniRoute chat · {self.model}\n\n")
            if self.system:
                handle.write(f"> system: {self.system}\n\n")
            for message in self.history:
                who = "You" if message["role"] == "user" else "Assistant"
                handle.write(f"**{who}**\n\n{message['content']}\n\n---\n\n")
        print(f"{C.GREEN}saved {name}{C.OFF}")

    def command(self, line: str) -> bool:
        """Handle a /command. Returns False to exit the REPL."""
        verb, _, arg = line[1:].partition(" ")
        verb, arg = verb.lower(), arg.strip()

        if verb in ("exit", "quit", "q"):
            return False
        if verb == "help":
            print(HELP)
        elif verb == "models":
            self.cmd_models(arg)
        elif verb == "model":
            if arg:
                self.model = arg
                print(f"{C.GREEN}model → {arg}{C.OFF}")
            else:
                print(f"current model: {self.model}")
        elif verb == "system":
            self.system = arg
            print(f"{C.GREEN}system {'set' if arg else 'cleared'}{C.OFF}")
        elif verb == "stream":
            self.streaming = not self.streaming
            print(f"{C.GREEN}streaming {'on' if self.streaming else 'off'}{C.OFF}")
        elif verb == "think":
            self.show_reasoning = not self.show_reasoning
            print(f"{C.GREEN}reasoning {'shown' if self.show_reasoning else 'hidden'}{C.OFF}")
        elif verb == "temp":
            try:
                self.temperature = max(0.0, min(2.0, float(arg)))
                print(f"{C.GREEN}temperature → {self.temperature}{C.OFF}")
            except ValueError:
                print(f"{C.YELLOW}usage: /temp 0.7{C.OFF}")
        elif verb == "clear":
            self.history.clear()
            print(f"{C.GREEN}history cleared{C.OFF}")
        elif verb == "history":
            for message in self.history:
                who = "you" if message["role"] == "user" else "bot"
                print(f"{C.DIM}{who}:{C.OFF} {message['content'][:200]}")
        elif verb == "retry":
            while self.history and self.history[-1]["role"] == "assistant":
                self.history.pop()
            if self.history:
                last = self.history.pop()["content"]
                self.send(last)
            else:
                print(f"{C.YELLOW}nothing to retry{C.OFF}")
        elif verb == "save":
            self.cmd_save(arg)
        else:
            print(f"{C.YELLOW}unknown command {verb!r} — /help{C.OFF}")
        return True

    # ---------- the actual chat ----------

    def send(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})
        print(f"\n{C.BLUE}{C.BOLD}assistant{C.OFF}")
        started = time.time()
        params = {"temperature": self.temperature}

        try:
            if self.streaming:
                reply, model, usage = self.stream_reply(params)
            else:
                reply, model, usage = self.block_reply(params)
        except OmniRouteError as exc:
            self.history.pop()
            print(f"{C.RED}{exc}{C.OFF}\n")
            return
        except KeyboardInterrupt:
            self.history.pop()
            print(f"\n{C.YELLOW}interrupted{C.OFF}\n")
            return

        if reply.strip():
            self.history.append({"role": "assistant", "content": reply})
        self.stats(model, usage, time.time() - started)

    def stream_reply(self, params: Dict[str, Any]):
        reply, model, usage = "", self.model, {}
        in_reasoning = False
        for chunk in self.client.stream(self.payload(), self.model, **params):
            model = chunk.get("model") or model
            usage = chunk.get("usage") or usage
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}

            thought = delta.get("reasoning_content")
            if thought and self.show_reasoning:
                if not in_reasoning:
                    print(f"{C.DIM}", end="")
                    in_reasoning = True
                print(thought, end="", flush=True)

            piece = delta.get("content")
            if piece:
                if in_reasoning:
                    print(f"{C.OFF}\n", end="")
                    in_reasoning = False
                print(piece, end="", flush=True)
                reply += piece
        if in_reasoning:
            print(C.OFF, end="")
        return reply, model, usage

    def block_reply(self, params: Dict[str, Any]):
        response = self.client.complete(self.payload(), self.model, **params)
        message = (response.get("choices") or [{}])[0].get("message", {})
        if self.show_reasoning and message.get("reasoning_content"):
            print(f"{C.DIM}{message['reasoning_content']}{C.OFF}\n")
        reply = message.get("content") or ""
        print(reply, end="")
        return reply, response.get("model", self.model), response.get("usage", {})

    def run(self) -> None:
        self.banner()
        while True:
            try:
                line = input(f"{C.GREEN}{C.BOLD}you ›{C.OFF} ").rstrip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            while line.endswith("\\"):  # backslash continues onto the next line
                try:
                    line = line[:-1] + "\n" + input(f"{C.DIM}···{C.OFF} ").rstrip()
                except (EOFError, KeyboardInterrupt):
                    break

            if not line.strip():
                continue
            if line.startswith("/"):
                if not self.command(line):
                    break
                continue
            self.send(line)
        print(f"{C.DIM}bye{C.OFF}")


if __name__ == "__main__":
    Chat().run()
