#!/usr/bin/python3 -I
"""Generate stills on WaveSpeed from shots.json. Logs every call to spend.jsonl.
Usage: ws_image.py shots.json outdir [--only id,id] [--cap 1.5]
Key: WAVESPEED_API_KEY, or WAVESPEED_ENV_FILE pointing at a file that holds it. Never printed."""
import json, os, sys, time, urllib.request, concurrent.futures as cf
KEY = os.environ.get("WAVESPEED_API_KEY") or [l.split("=",1)[1].strip().strip('"') for l in open(os.path.expanduser(os.environ["WAVESPEED_ENV_FILE"])) if l.startswith("WAVESPEED_API_KEY")][0]
API = "https://api.wavespeed.ai/api/v3"
def call(path, body=None):
    req = urllib.request.Request(f"{API}/{path}", data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))
def gen(model, body):
    r = call(model, body)["data"]; rid = r["id"]
    for _ in range(90):
        d = call(f"predictions/{rid}/result")["data"]
        if d["status"] == "completed": return d["outputs"][0]
        if d["status"] == "failed": raise RuntimeError(d.get("error"))
        time.sleep(2)
    raise TimeoutError(rid)
def upload(path):
    import subprocess
    # The key goes in on stdin so it never shows in the process list.
    out = subprocess.run(["curl","-s","-X","POST",f"{API}/media/upload/binary","-K","-","-F",f"file=@{path}"],
                         input=f'header = "Authorization: Bearer {KEY}"\n',capture_output=True,text=True).stdout
    return json.loads(out)["data"]["download_url"]
if __name__ == "__main__":
    spec = json.load(open(sys.argv[1])); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    only = sys.argv[sys.argv.index("--only")+1].split(",") if "--only" in sys.argv else None
    cap = float(sys.argv[sys.argv.index("--cap")+1]) if "--cap" in sys.argv else 1.5
    anchor = spec["anchor"]; size = spec.get("size","1920*1080")
    hero_url = None
    if os.path.exists(f"{out}/hero.png"): hero_url = upload(f"{out}/hero.png")
    shots = [s for s in spec["shots"] if not only or s["id"] in only]
    spent = 0.0; log = open(os.path.join(os.path.dirname(sys.argv[1]),"spend.jsonl"),"a")
    def run(s):
        use_ref = s.get("ref") and hero_url
        model = "bytedance/seedream-v4/edit" if use_ref else "bytedance/seedream-v4"
        body = {"prompt": f'{s["prompt"]}. {anchor}', "size": size}
        if use_ref: body["images"] = [hero_url]
        url = gen(model, body)
        data = urllib.request.urlopen(url, timeout=120).read()
        open(f'{out}/{s["id"]}.png',"wb").write(data)
        return s["id"], 0.027
    # hero first (reference for the rest)
    order = sorted(shots, key=lambda s: s["id"] != "hero")
    if order and order[0]["id"] == "hero" and not hero_url:
        if cap <= 0: sys.exit("cap hit, stopped before hero")
        i,c = run(order[0]); spent += c; log.write(json.dumps({"id":i,"usd":c,"t":time.time()})+"\n"); log.flush()
        hero_url = upload(f"{out}/hero.png"); order = order[1:]
    if any(s.get("ref") for s in order) and not hero_url: print("warning: no hero.png, so shots marked ref run without the reference")
    # Submit in batches of 4 and stop between batches, so the cap really stops the spend.
    for k in range(0, len(order), 4):
        if spent >= cap: print("cap hit, stopped before", order[k]["id"]); break
        with cf.ThreadPoolExecutor(4) as ex:
            for f in cf.as_completed([ex.submit(run,s) for s in order[k:k+4]]):
                try:
                    i,c = f.result(); spent += c; log.write(json.dumps({"id":i,"usd":c,"t":time.time()})+"\n"); log.flush(); print("ok",i)
                except Exception as e: print("fail", e)
    print("spent ~", round(spent,3))
