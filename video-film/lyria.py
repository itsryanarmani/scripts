#!/usr/bin/python3 -I
"""Instrumental bed with Lyria 2 on Vertex. Usage: VERTEX_PROJECT=<id> lyria.py out.wav "<prompt>" "<negative>" """
import base64, json, os, subprocess, sys, urllib.request
if len(sys.argv) < 4 or "VERTEX_PROJECT" not in os.environ:
    sys.exit("usage: VERTEX_PROJECT=<id> lyria.py out.wav \"<prompt>\" \"<negative>\"")
env = dict(os.environ, CLOUDSDK_CONFIG=os.environ.get("CLOUDSDK_CONFIG", os.path.expanduser("~/.config/gcloud")))
tok = subprocess.check_output(["gcloud","auth","print-access-token"], env=env, text=True).strip()
url = "https://us-central1-aiplatform.googleapis.com/v1/projects/"+os.environ["VERTEX_PROJECT"]+"/locations/us-central1/publishers/google/models/lyria-002:predict"
body = {"instances":[{"prompt":sys.argv[2],"negative_prompt":sys.argv[3]}],"parameters":{"sample_count":1}}
req = urllib.request.Request(url, json.dumps(body).encode(), {"Authorization":f"Bearer {tok}","x-goog-user-project":os.environ["VERTEX_PROJECT"],"Content-Type":"application/json"})
r = json.load(urllib.request.urlopen(req, timeout=900))
open(sys.argv[1],"wb").write(base64.b64decode(r["predictions"][0]["bytesBase64Encoded"])); print("ok", sys.argv[1])
