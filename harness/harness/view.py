"""View client: SSE chat with channel separation and an optional exchange archive.

The view is an HTTP service, reached by default at HARNESS_VIEW_URL (or the
neutral local default below). On a private network it may present a self-signed
certificate; TLS verification can be turned off for that case and is never the
default. /api/chat streams SSE events: `content` chunks are the seat's answer,
`reasoning` chunks are its deliberation where the stack splits them, `done`
carries finish_reason and token usage. Every exchange can be archived to the
directory named by HARNESS_ARCHIVE_DIR (pass archive=False to disable).
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

DEFAULT_VIEW = os.environ.get("HARNESS_VIEW_URL", "http://localhost:8080")
DEFAULT_ARCHIVE_DIR = Path.home() / ".harness" / "seat-work"
ARCHIVE_DIR = Path(os.environ.get("HARNESS_ARCHIVE_DIR", str(DEFAULT_ARCHIVE_DIR)))


@dataclass
class ChatReply:
    content: str = ""
    reasoning: str = ""
    finish_reason: str = ""
    usage: dict = field(default_factory=dict)
    seat: str = ""
    elapsed_s: float = 0.0


class ViewClient:
    def __init__(self, base_url: str = DEFAULT_VIEW, timeout: float = 900.0,
                 archive: bool = True, verify: bool = True):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.archive = archive
        self._client = httpx.Client(verify=verify, timeout=httpx.Timeout(timeout, connect=20.0))
        self._roster = None

    def seats(self) -> dict:
        r = self._client.get(f"{self.base_url}/api/seats")
        r.raise_for_status()
        return r.json().get("seats", {})

    def seat_provenance(self, seat_key: str) -> dict:
        if self._roster is None:
            try:
                self._roster = self.seats()
            except Exception:
                self._roster = {}
        s = self._roster.get(seat_key, {})
        return {"seat": seat_key, "seat_name": s.get("name", ""),
                "stack": s.get("stack", ""), "node": s.get("node", "")}

    def chat(self, seat: str, messages: list, label: str = "",
             max_tokens: int | None = None,
             temperature: float | None = 0.0,
             tools: bool | None = False) -> ChatReply:
        t0 = time.time()
        reply = ChatReply(seat=seat)
        event = ""
        body = {"seat": seat, "messages": messages}
        if tools is not None:
            # Toolless by default, same reasoning as the temperature pin above:
            # every request through here is a scored stage, and the view's
            # `tools` field defaults to True, so an omitted flag arms the seat's
            # whole kit for a job that only needs it to read the prompt it was
            # handed.
            #
            # Seats that carry a tool kit are the ones most likely to be handed
            # a scored stage, so this is not a rare path. It costs three ways.
            # Context: the tool schemas take roughly 800 tokens off an already
            # tight window. Latency: measured on a large extraction backlog the
            # same day, median time per record went 559s to 293s with tools off,
            # a 1.91x speedup for no quality change. And correctness: a seat
            # handed an extraction job used the kit to go read another archive
            # directory, reasoned about OTHER records' ids it found there, and
            # never answered. That is a contamination path into a judgment
            # surface, which is exactly what this harness exists to keep clean.
            #
            # Pass None for a judgment that genuinely needs the seat to go look
            # something up. That should be a deliberate act, not a default.
            body["tools"] = tools
        if temperature is not None:
            # Greedy by default. Both callers of this method are inside
            # judge(), so every request that has ever gone through here was a
            # scored stage, and an omitted temperature inherits the vessel's
            # conversational 0.6. Pass None only for a task that wants variety;
            # the decision belongs to TaskContract.temperature.
            body["temperature"] = temperature
        if max_tokens is not None:
            # the view's default completion budget (4096 observed 2026-07-09)
            # starves reasoning seats mid-deliberation; judgment calls raise it
            body["max_tokens"] = max_tokens
        with self._client.stream(
            "POST", f"{self.base_url}/api/chat", json=body,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                try:
                    data = json.loads(line.split(":", 1)[1].strip())
                except json.JSONDecodeError:
                    continue
                if event == "content":
                    reply.content += data.get("text", "")
                elif event == "reasoning":
                    reply.reasoning += data.get("text", "")
                elif event == "done":
                    reply.finish_reason = data.get("finish_reason", "")
                    reply.usage = data.get("usage", {})
        reply.elapsed_s = round(time.time() - t0, 2)
        if self.archive:
            self._archive(seat, messages, reply, label)
        return reply

    def _archive(self, seat: str, messages: list, reply: ChatReply, label: str):
        try:
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            path = ARCHIVE_DIR / f"harness-{time.strftime('%Y%m%d')}.jsonl"
            rec = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "label": label, "seat": seat, "messages": messages,
                "content": reply.content, "reasoning_chars": len(reply.reasoning),
                "finish_reason": reply.finish_reason, "usage": reply.usage,
                "elapsed_s": reply.elapsed_s, "pid": os.getpid(),
            }
            with open(path, "a") as fh:
                fh.write(json.dumps(rec) + "\n")
        except OSError:
            pass
