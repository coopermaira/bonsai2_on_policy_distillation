"""Cancellation-aware, byte-preserving nonstreaming experiment proxy.

Usage: python reliable_proxy.py PORT BACKEND LOGFILE LABEL
Raw bodies are saved separately; JSONL records request start, backend completion,
delivery, cancellation and errors, with trial/session IDs and SHA256 hashes.
"""
import asyncio
import hashlib
import json
import pathlib
import sys
import time
import uuid

from aiohttp import ClientSession, ClientTimeout, web

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailer", "transfer-encoding", "upgrade", "content-length", "host"}


def create_app(backend, logfile, label):
    logfile = pathlib.Path(logfile)
    logfile.parent.mkdir(parents=True, exist_ok=True)
    raw = logfile.parent / (logfile.stem + "-raw")
    raw.mkdir(exist_ok=True)
    active = set()

    def record(event, **fields):
        with logfile.open("a") as f:
            f.write(json.dumps(dict(ts=time.time(), label=label, event=event, **fields)) + "\n")

    async def lifecycle(app):
        async with ClientSession(timeout=ClientTimeout(total=None, sock_connect=30,
                                                        sock_read=86400),
                                 auto_decompress=False) as client:
            app["client"] = client
            yield

    async def forward(request):
        if request.path == "/proxy-health":
            return web.json_response({"status": "ok", "active": len(active), "label": label})
        body = await request.read()
        chat = request.path.rstrip("/").endswith("/chat/completions")
        rid = uuid.uuid4().hex
        info = dict(request_id=rid, request_sha256=hashlib.sha256(body).hexdigest())
        if chat:
            obj = json.loads(body)
            info.update(session_id=obj.get("session_id") or request.headers.get("X-Session-ID"),
                        n_messages_in=len(obj.get("messages", [])))
            (raw / (rid + ".request.json")).write_bytes(body)
            if active:
                record("rejected_overlap", **info)
                return web.json_response({"error": {"message": "Endpoint already has an active generation",
                                                    "type": "endpoint_busy"}}, status=409)
            active.add(rid)
            record("request_started", **info)
        started = time.monotonic()
        try:
            excluded = HOP | {h.strip().lower() for h in request.headers.get("Connection", "").split(",")}
            headers = {k: v for k, v in request.headers.items() if k.lower() not in excluded}
            async with request.app["client"].request(
                request.method, backend.rstrip("/") + request.path_qs,
                data=body or None, headers=headers, allow_redirects=False
            ) as upstream:
                response_body = await upstream.read()
                if chat:
                    (raw / (rid + ".response.json")).write_bytes(response_body)
                    details = {}
                    try:
                        result = json.loads(response_body)
                        choice = result.get("choices", [{}])[0]
                        details = dict(usage=result.get("usage"), finish_reason=choice.get("finish_reason"))
                    except (ValueError, IndexError, AttributeError):
                        details = {"response_parse_failed": True}
                    record("backend_completed", **info, **details, status=upstream.status,
                           latency_s=time.monotonic()-started,
                           response_sha256=hashlib.sha256(response_body).hexdigest())
                excluded = HOP | {h.strip().lower() for h in upstream.headers.get("Connection", "").split(",")}
                response = web.StreamResponse(status=upstream.status,
                    headers={k:v for k,v in upstream.headers.items() if k.lower() not in excluded})
                response.content_length = len(response_body)
                await response.prepare(request)
                await response.write(response_body)
                await response.write_eof()
                if chat:
                    record("response_sent", **info, latency_s=time.monotonic()-started)
                return response
        except asyncio.CancelledError:
            if chat:
                record("client_cancelled", **info, latency_s=time.monotonic()-started)
            raise
        except Exception as exc:
            if chat:
                record("proxy_error", **info, error=repr(exc), latency_s=time.monotonic()-started)
            raise
        finally:
            active.discard(rid)

    app = web.Application(client_max_size=128*1024*1024)
    app.cleanup_ctx.append(lifecycle)
    app.router.add_route("*", "/{path:.*}", forward)
    return app


if __name__ == "__main__":
    port, backend, logfile, label = sys.argv[1:]
    web.run_app(create_app(backend, logfile, label), host="127.0.0.1", port=int(port),
                handler_cancellation=True, access_log=None)
