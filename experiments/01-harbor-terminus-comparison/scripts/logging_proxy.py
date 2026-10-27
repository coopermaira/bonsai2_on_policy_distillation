#!/usr/bin/env python3
"""Transparent logging reverse-proxy for llama-server, for Terminal-Bench runs.

Forwards every request byte-for-byte to the real backend and returns the exact
response untouched -- Terminus-2 and the model server see a normal, unmodified
setup. On the side, for chat-completions calls, it writes a JSONL record with
the full response (incl. reasoning_content) and flags Terminus-2's own
handoff/proactive-summarization prompts by their known text signatures, so we
can analyze reasoning and count handoffs without changing agent behavior.
"""
import http.server, urllib.request, json, sys, time, threading, os

LISTEN_PORT = int(sys.argv[1])
BACKEND = sys.argv[2].rstrip('/')          # e.g. http://127.0.0.1:8091
LOGFILE = sys.argv[3]                      # jsonl output path
LABEL = sys.argv[4] if len(sys.argv) > 4 else LISTEN_PORT

HANDOFF_SIGNATURES = {
    'proactive_summary_request': 'You are about to hand off your work to another AI agent',
    'handoff_questions_prompt':  'You are picking up work from a previous',
    'handoff_continue_prompt':   'Continue working on this task from where the previous agent left off',
}

_lock = threading.Lock()

def detect_signatures(body_obj):
    hits = []
    try:
        for m in body_obj.get('messages', []):
            c = m.get('content')
            if not isinstance(c, str):
                continue
            for name, sig in HANDOFF_SIGNATURES.items():
                if sig in c:
                    hits.append(name)
    except Exception:
        pass
    return hits

def log_line(rec):
    rec['ts'] = time.time()
    rec['label'] = LABEL
    with _lock:
        with open(LOGFILE, 'a') as f:
            f.write(json.dumps(rec) + '\n')

class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def _forward(self):
        length = int(self.headers.get('Content-Length', 0) or 0)
        body = self.rfile.read(length) if length else b''
        url = BACKEND + self.path
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'content-length')}
        req = urllib.request.Request(url, data=body if body else None, headers=headers, method=self.command)

        is_chat = self.path.rstrip('/').endswith('/chat/completions')
        req_obj = None
        if is_chat and body:
            try:
                req_obj = json.loads(body)
            except Exception:
                req_obj = None

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=None) as resp:
                resp_body = resp.read()
                status = resp.status
                resp_headers = list(resp.getheaders())
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            status = e.code
            resp_headers = list(e.headers.items())
        dt = time.time() - t0

        if is_chat and req_obj is not None:
            sigs = detect_signatures(req_obj)
            resp_obj = None
            try:
                resp_obj = json.loads(resp_body)
            except Exception:
                pass
            rec = {
                'kind': 'chat_completion',
                'latency_s': round(dt, 3),
                'n_messages_in': len(req_obj.get('messages', [])),
                'handoff_signatures_in_request': sigs,
                'status': status,
            }
            if resp_obj and 'choices' in resp_obj:
                msg = resp_obj['choices'][0].get('message', {})
                rec['finish_reason'] = resp_obj['choices'][0].get('finish_reason')
                rec['reasoning_content'] = msg.get('reasoning_content')
                rec['content'] = msg.get('content')
                rec['usage'] = resp_obj.get('usage')
            else:
                rec['response_parse_failed'] = True
                rec['raw_response_head'] = resp_body[:500].decode('utf-8', 'replace')
            log_line(rec)

        self.send_response(status)
        for k, v in resp_headers:
            if k.lower() not in ('transfer-encoding', 'connection', 'content-length'):
                self.send_header(k, v)
        self.send_header('Content-Length', str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def do_GET(self): self._forward()
    def do_POST(self): self._forward()
    def do_PUT(self): self._forward()
    def do_DELETE(self): self._forward()
    def log_message(self, fmt, *args): pass  # quiet; we log our own structured records

if __name__ == '__main__':
    os.makedirs(os.path.dirname(os.path.abspath(LOGFILE)) or '.', exist_ok=True)
    srv = http.server.ThreadingHTTPServer(('0.0.0.0', LISTEN_PORT), Proxy)
    print(f'proxy listening on :{LISTEN_PORT} -> {BACKEND}, logging to {LOGFILE}', flush=True)
    srv.serve_forever()
