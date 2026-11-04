#!/usr/bin/env python3
"""Local text-to-speech HTTP shim for voice-device servers (macOS, stdlib only).

POST /v1/audio/speech  {"input": "text", "voice": "Samantha"}  ->  16-bit mono WAV
Uses the macOS `say` and `afconvert` commands. No network, no extra packages.
Env: HOST (default 127.0.0.1), PORT (default 8880), TTS_VOICE (default Samantha).
"""
import json, os, subprocess, tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/audio/speech":
            return self.send_error(404)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except ValueError:
            return self.send_error(400, "bad json")
        text = (body.get("input") or "").strip()
        voice = body.get("voice") or os.environ.get("TTS_VOICE", "Samantha")
        if not text:
            return self.send_error(400, "empty input")
        with tempfile.TemporaryDirectory() as d:
            aiff, wav = f"{d}/o.aiff", f"{d}/o.wav"
            try:
                subprocess.run(["say", "-v", voice, "-o", aiff, "--", text], check=True, timeout=60)
                subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1", aiff, wav], check=True, timeout=30)
            except (subprocess.SubprocessError, OSError) as e:
                return self.send_error(500, f"synthesis failed: {type(e).__name__}")
            data = open(wav, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == "__main__":
    ThreadingHTTPServer((os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8880"))), Handler).serve_forever()
