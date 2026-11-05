#!/usr/bin/python3 -I
"""Image-to-video with Veo 3.1 on Vertex (set VERTEX_PROJECT; optional CLOUDSDK_CONFIG).
Usage: veo.py clips.json stilldir outdir [--only id,id]
clips.json: {"model":..., "secs":4, "style":"...", "clips":[{"id","still","motion"}]}
Logs an estimate per clip to spend.jsonl next to clips.json. Never prints tokens."""
import base64, json, os, subprocess, sys, tempfile, time, urllib.request, concurrent.futures as cf
if len(sys.argv) < 4 or "VERTEX_PROJECT" not in os.environ:
    sys.exit("usage: VERTEX_PROJECT=<id> veo.py clips.json stilldir outdir [--only a,b]")
PROJECT = os.environ["VERTEX_PROJECT"]  # the cloud project that bills Veo
def token():
    env = dict(os.environ, CLOUDSDK_CONFIG=os.environ.get("CLOUDSDK_CONFIG", os.path.expanduser("~/.config/gcloud")))
    return subprocess.check_output(["gcloud","auth","print-access-token"], env=env, text=True).strip()
def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Authorization": f"Bearer {token()}", "x-goog-user-project": PROJECT, "Content-Type": "application/json"})
    try: return json.load(urllib.request.urlopen(req, timeout=300))
    except urllib.error.HTTPError as e: raise RuntimeError(f"{e.code}: {e.read().decode()[:400]}")
spec = json.load(open(sys.argv[1])); stills, out = sys.argv[2], sys.argv[3]; os.makedirs(out, exist_ok=True)
only = sys.argv[sys.argv.index("--only")+1].split(",") if "--only" in sys.argv else None
model = spec["model"]; secs = spec.get("secs", 4)
BASE = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/us-central1/publishers/google/models/{model}"
log = os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), "spend.jsonl")
def run(c):
    jpg = os.path.join(tempfile.mkdtemp(), f"{c['id']}.jpg")
    subprocess.run(["ffmpeg","-loglevel","error","-y","-i",f"{stills}/{c['still']}.png","-q:v","3",jpg], check=True)
    prompt = (f"Start from the supplied frame. Keep the character, outfit and art style unchanged. {c['motion']} "
              f"{spec['style']} Ends on a held pose.")
    try:
        op = post(f"{BASE}:predictLongRunning", {"instances":[{"prompt":prompt,"image":{"bytesBase64Encoded":base64.b64encode(open(jpg,"rb").read()).decode(),"mimeType":"image/jpeg"}}],
            "parameters":{"aspectRatio":"16:9","durationSeconds":secs,"generateAudio":False,"sampleCount":1,"resolution":"720p","negativePrompt":spec.get("negative","")}})
        for _ in range(60):
            time.sleep(10)
            r = post(f"{BASE}:fetchPredictOperation", {"operationName": op["name"]})
            if r.get("done"):
                if "error" in r: return f"{c['id']} FAILED {r['error']}"
                v = (r["response"].get("videos") or [])
                if not v: return f"{c['id']} FILTERED {json.dumps(r['response'])[:200]}"
                open(f"{out}/{c['id']}.mp4","wb").write(base64.b64decode(v[0]["bytesBase64Encoded"]))
                open(log,"a").write(json.dumps({"veo":c["id"],"model":model,"secs":secs,"usd_est":round(secs*spec.get("usd_per_s",0.15),2),"t":time.time()})+"\n")
                return f"{c['id']} ok"
        return f"{c['id']} TIMEOUT"
    except Exception as e: return f"{c['id']} FAILED {e}"
with cf.ThreadPoolExecutor(4) as ex:
    for m in ex.map(run, [c for c in spec["clips"] if not only or c["id"] in only]): print(m, flush=True)
