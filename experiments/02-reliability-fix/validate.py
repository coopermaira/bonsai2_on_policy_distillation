"""Run on the actual remote Harbor installation; --long crosses the old 600s limit."""
import asyncio
import json
import pathlib
import sys
import tempfile
import time
from unittest.mock import patch

import aiohttp
import litellm
from aiohttp import web
from tenacity import wait_none
from harbor.agents.terminus_2.terminus_2 import Terminus2
from harbor.llms.chat import Chat
from harbor.llms.lite_llm import LiteLLM
from reliable_terminus import ReliableTerminus, ModelNonProgressError
from reliable_proxy import create_app


async def serve(app):
    runner = web.AppRunner(app, handler_cancellation=True, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, "http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1])


async def main():
    output = []
    long = "--long" in sys.argv
    root = pathlib.Path(__file__).parent
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        def agent(cls, name, base):
            p = td/name
            p.mkdir(exist_ok=True)
            return cls(logs_dir=p, model_name="openai/qwen-a", api_base=base+"/v1",
                       llm_kwargs={"api_key":"not-needed-local-server"},
                       interleaved_thinking=False)

        baseline = agent(Terminus2, "baseline", "http://127.0.0.1:1")
        fixed = agent(ReliableTerminus, "fixed", "http://127.0.0.1:1")
        LiteLLM.call.retry.wait = wait_none()
        async def failed(**kwargs):
            raise litellm.Timeout(message="injected transport timeout", model="qwen-a", llm_provider="openai")
        for a, expected in [(baseline, 9), (fixed, 1)]:
            with patch("litellm.acompletion", side_effect=failed) as call:
                try:
                    await a._query_llm(Chat(a._llm), "test")
                    raise AssertionError("timeout was swallowed")
                except litellm.Timeout:
                    assert call.call_count == expected, (call.call_count, expected)
            output.append({"test":type(a).__name__+"_transport_failure", "calls":expected})

        bad = ([], False, "ERROR: invalid JSON", "", "", None)
        good = ([], False, "", "", "", None)
        with patch.object(Terminus2, "_handle_llm_interaction", return_value=bad):
            for _ in range(9):
                await fixed._handle_llm_interaction()
        with patch.object(Terminus2, "_handle_llm_interaction", return_value=good):
            await fixed._handle_llm_interaction()
            assert fixed._parse_failures == 0
        with patch.object(Terminus2, "_handle_llm_interaction", return_value=bad):
            for _ in range(9):
                await fixed._handle_llm_interaction()
            try:
                await fixed._handle_llm_interaction()
                raise AssertionError("parse failure bound not enforced")
            except ModelNonProgressError:
                pass
        output.append({"test":"parse_failure_bound_and_reset", "passed":True})

        # Use the exact archived >600s response from the incident, including reasoning.
        fixture = json.loads((root/"qwen-a-long-response.json").read_text())
        requests = []
        entered = asyncio.Event()
        cancelled = asyncio.Event()
        async def backend(request):
            body = await request.json()
            requests.append(body)
            if body.get("cancel_test"):
                entered.set()
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
            if body.get("delay_test"):
                await asyncio.sleep(605 if long else 1)
            return web.json_response(fixture)
        upstream = web.Application()
        upstream.router.add_post("/v1/chat/completions", backend)
        ur, ub = await serve(upstream)
        pr, pb = await serve(create_app(ub, td/"proxy.jsonl", "test"))
        try:
            a = agent(ReliableTerminus, "replay", pb)
            chat = Chat(a._llm)
            a._llm_call_kwargs["extra_body"] = {"delay_test": True}
            start = time.monotonic()
            response = await a._query_llm(chat, "Replay regression fixture")
            elapsed = time.monotonic()-start
            assert len(requests) == 1
            assert response.content == fixture["choices"][0]["message"]["content"]
            assert response.reasoning_content == fixture["choices"][0]["message"].get("reasoning_content")
            parsed = a._parser.parse_response(response.content)
            assert not parsed.error, parsed.error
            a._llm_call_kwargs.clear()
            await a._query_llm(chat, "Next turn")
            assert len(requests) == 2
            assert len(requests[1]["messages"]) == len(requests[0]["messages"])+2
            output.append({"test":"archived_long_response", "elapsed":elapsed,
                           "completion_tokens":fixture["usage"]["completion_tokens"],
                           "http_calls":2,"commands":len(parsed.commands),"next_turn_advanced":True})

            async with aiohttp.ClientSession() as client:
                pending = asyncio.create_task(client.post(pb+"/v1/chat/completions",json={"cancel_test":True}))
                await entered.wait()
                async with client.post(pb+"/v1/chat/completions",json={"messages":[]}) as r:
                    assert r.status == 409
                pending.cancel()
                try:
                    await pending
                except asyncio.CancelledError:
                    pass
                await asyncio.wait_for(cancelled.wait(), 5)
                async with client.post(pb+"/v1/chat/completions",json={"messages":[]}) as r:
                    assert r.status == 200
                    assert len(r.headers.getall("Content-Length")) == 1
                    assert await r.json() == fixture
            events=[json.loads(l)["event"] for l in (td/"proxy.jsonl").read_text().splitlines()]
            assert "client_cancelled" in events and "rejected_overlap" in events
            output.append({"test":"disconnect_cancels_backend_and_releases_endpoint", "passed":True})
            output.append({"test":"single_content_length_and_exact_response", "passed":True})
        finally:
            await pr.cleanup()
            await ur.cleanup()
    (root/("validation-long.json" if long else "validation.json")).write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2),flush=True)


if __name__ == "__main__":
    asyncio.run(main())
