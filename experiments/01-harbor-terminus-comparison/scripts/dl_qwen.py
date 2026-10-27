import os, sys, time, urllib.request, json
REPO = "Qwen/Qwen3.8-27B"
out = "/work/qwen38-27b-src"
os.makedirs(out, exist_ok=True)
FILES = ["config.json","generation_config.json","model.safetensors.index.json","tokenizer.json","tokenizer_config.json","merges.txt","vocab.json","chat_template.jinja"] + \
        [f"model-{i:05d}-of-00018.safetensors" for i in range(1,19)]
for name in FILES:
    path = os.path.join(out, name)
    url = f"https://huggingface.co/{REPO}/resolve/main/{name}"
    have = os.path.getsize(path) if os.path.exists(path) else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            total = have + int(r.headers.get('Content-Length', 0))
            if have and r.status != 206:
                have = 0  # server ignored range; restart
            t0 = time.time(); done = have; last=t0
            with open(path, "ab" if have and r.status==206 else "wb") as f:
                while True:
                    b = r.read(8 << 20)
                    if not b: break
                    f.write(b); done += len(b)
                    if time.time()-last > 20:
                        print(f"{name} {done/1e9:.2f}/{total/1e9:.2f} GB {(done-have)/1e6/(time.time()-t0+1e-9):.0f} MB/s", flush=True); last=time.time()
        got = os.path.getsize(path)
        ok = (got == total) if total else True
        print(name, "done", got, "OK" if ok else f"MISMATCH expected {total}", flush=True)
    except Exception as e:
        print(name, "ERROR", e, flush=True); sys.exit(1)
print("ALLDONE", flush=True)
