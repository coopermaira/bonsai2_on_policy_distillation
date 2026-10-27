"""Experiment-local Harbor 0.23.0 adapter: never replay failed HTTP calls.

The parent retains context recovery, output-length recovery, prompts, parsing,
and all terminal behavior. Only transport retry decorators are bypassed.
"""
from types import MethodType
import json
import time

from harbor.agents.terminus_2.terminus_2 import Terminus2
from harbor.llms.lite_llm import LiteLLM


class ReliableTerminus(Terminus2):
    def __init__(self, *args, **kwargs):
        llm_kwargs = dict(kwargs.pop("llm_kwargs", {}) or {})
        # Harbor's 8h task deadline remains authoritative. A long nonstreaming
        # generation must not be abandoned by the SDK's default 600s read limit.
        llm_kwargs.update(timeout=86400, max_retries=0, num_retries=0)
        kwargs["llm_kwargs"] = llm_kwargs
        super().__init__(*args, **kwargs)
        if not isinstance(self._llm, LiteLLM):
            raise TypeError("This experiment adapter requires Harbor LiteLLM")
        self._llm.call = MethodType(LiteLLM.call.__wrapped__, self._llm)
        self._parse_failures = 0
        self._activity("initialized")

    def _activity(self, stage, **details):
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        event = dict(ts=time.time(), stage=stage, **details)
        with (self.logs_dir / "reliability-events.jsonl").open("a") as f:
            f.write(json.dumps(event)+"\n")
        path = self.logs_dir / "reliability-status.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(event))
        temp.replace(path)

    async def _query_llm(self, chat, prompt, original_instruction="", session=None):
        self._activity("waiting_for_llm", messages=len(chat.messages))
        try:
            response = await Terminus2._query_llm.__wrapped__(
                self, chat, prompt, original_instruction, session
            )
            self._activity("llm_returned", messages=len(chat.messages))
            return response
        except Exception as exc:
            self._activity("llm_error", error=repr(exc))
            raise

    async def _handle_llm_interaction(self, *args, **kwargs):
        result = await super()._handle_llm_interaction(*args, **kwargs)
        self._parse_failures = self._parse_failures + 1 if "ERROR:" in result[2] else 0
        self._activity("parsed", consecutive_parse_failures=self._parse_failures,
                       command_count=len(result[0]))
        if self._parse_failures >= 10:
            raise ModelNonProgressError("10 consecutive unparseable responses; review trace before rerunning")
        return result

    async def _execute_commands(self, commands, session):
        self._activity("executing_commands", command_count=len(commands),
                       deadline=time.time()+180*len(commands)+120)
        result = await super()._execute_commands(commands, session)
        self._activity("commands_finished", timed_out=result[0])
        return result

    async def run(self, *args, **kwargs):
        try:
            return await super().run(*args, **kwargs)
        finally:
            self._activity("agent_finished")


class ModelNonProgressError(RuntimeError):
    """Censored diagnostic outcome, never automatically converted to reward zero."""
