#!/usr/bin/env python3
"""E2E test for the ad-video-tools: builds clips with ffmpeg (dead
gap, jumbled caption, silent, tail-only, hot mastering inputs), runs
every tool, writes an evidence JSON. macOS only (swiftc, Pillow).

    python3 ad-video-tools.test.py [EVIDENCE.json]
"""
import atexit, json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = "540", "960", "30"
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
CAPS = [{"start": 1.0, "end": 2.0, "text": "HELLO WORLD"},
        {"start": 8.0, "end": 9.0, "text": "BUY NOW"}]
JUMBLED = {"HELLO WORLD": "XELLO WORLE", "BUY NOW": "B0Y NUW"}
HOT = "0.13*sin(2*PI*440*t)+1.3*sin(2*PI*880*t)*lt(mod(t\\,2)\\,0.053)"
PEAKY = "0.05*sin(2*PI*440*t)+1.4*sin(2*PI*880*t)*lt(mod(t\\,2)\\,0.053)"
TPH = "0.4*sin(2*PI*440*t)+0.9*sin(2*PI*19000*t)*lt(mod(t\\,2)\\,0.05)"


def ff(args):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
                       + args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-400:])


def caption_png(path, text):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (540, 960), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 72)
    b = d.textbbox((0, 0), text, font=f)
    d.text(((540 - b[2] + b[0]) // 2 - b[0], 780 - b[1]), text, font=f,
           fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))
    img.save(path)


def avclip(d, name, aeval, dur=12, vsrc=None):
    vsrc = vsrc or f"testsrc2=size={W}x{H}:rate={FPS}:duration={dur}"
    out = os.path.join(d, name + ".mp4")
    ff(["-f", "lavfi", "-i", vsrc, "-f", "lavfi", "-i",
        f"aevalsrc={aeval}:s=48000:d={dur}", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out])
    return out


def build(d, broken):
    caps = []
    for i, c in enumerate(CAPS):
        png = os.path.join(d, f"cap{i}.png")
        caption_png(png, JUMBLED[c["text"]] if broken else c["text"])
        caps += ["-loop", "1", "-framerate", str(FPS), "-t", "10", "-i", png]
    # broken: dead gap 4-6 s (black + silence), sound ends ~9.4 s
    # good: quiet sine, hard cuts, captions on two windows
    segs = ([("red", 4), ("black", 2), ("blue", 2), ("navy", 2)] if broken else
            [("red", 2.5), ("blue", 2.5), ("green", 2.5), ("navy", 2.5)])
    v = [f"color={k}:size={W}x{H}:duration={du}:rate={FPS}" for k, du in segs]
    if broken:
        a = ["aevalsrc=0.4*sin(2*PI*440*t):s=48000:d=4",
             "anullsrc=r=48000:cl=stereo:d=2",
             "aevalsrc=0.4*sin(2*PI*440*t):s=48000:d=3.4"]
        afc = "[6:a][7:a][8:a]concat=n=3:v=0:a=1[a]"
    else:
        a = ["aevalsrc=0.05*sin(2*PI*440*t):s=48000:d=10.5"]
        afc = "[6:a]anull[a]"
    vfc = "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v0]"
    for j, c in enumerate(CAPS):
        vfc += (f";[v{j}][{4 + j}:v]overlay=0:0:enable='between(t,{c['start']}"
                f",{c['end']})'[v{j + 1}]")
    vfc += ";[v2]format=yuv420p[v]"
    inputs = (sum([["-f", "lavfi", "-i", s] for s in v], []) + caps +
              sum([["-f", "lavfi", "-i", s] for s in a], []))
    out = os.path.join(d, "broken.mp4" if broken else "good.mp4")
    ff(inputs + ["-filter_complex", vfc + ";" + afc, "-map", "[v]", "-map", "[a]",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                 "-b:a", "192k", out])
    return out


def main():
    for t in ("ffmpeg", "ffprobe", "swiftc"):
        if subprocess.run(["which", t], capture_output=True).returncode:
            print(f"missing {t}", file=sys.stderr)
            return 2
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("missing Pillow (test-only dep)", file=sys.stderr)
        return 2
    tmp = tempfile.mkdtemp(prefix="ad-video-tools-test-")
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    capjson = tmp + "/captions.json"; json.dump(CAPS, open(capjson, "w"))
    good, bad = build(tmp, False), build(tmp, True)
    silent = tmp + "/silent.mp4"
    ff(["-f", "lavfi", "-i",
        f"color=gray:size={W}x{H}:duration=10:rate={FPS}",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=10",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", silent])
    ev = {"clips": {"good": good, "broken": bad, "silent": silent}, "runs": {}}

    tail5, tail2, hot, peaky, tpclip, lim = (
        avclip(tmp, n, a, d) for n, a, d in
        (("tail05", "0.3*sin(2*PI*440*t)*lt(t\\,3.5)", 4),
         ("tail02", "0.3*sin(2*PI*440*t)*lt(t\\,3.8)", 4),
         ("hot", HOT, 12), ("peaky", PEAKY, 12), ("tpclip", TPH, 12),
         ("lim", "0.08*sin(2*PI*440*t)+0.688*sin(2*PI*990*t)"
          "*lt(mod(t\\,2)\\,0.115)", 8)))
    def rec(name, want, tool, *a):
        r = subprocess.run([os.path.join(ROOT, tool)] + list(a),
                           capture_output=True, text=True)
        ev["runs"][name] = {"rc": r.returncode, "want_rc": want,
                            "output": (r.stdout + r.stderr).strip()[-600:]}
        ok = r.returncode == want and (want != 1 or "FAIL" in r.stdout + r.stderr)
        print(f"{name}: rc={r.returncode} want={want} {'OK' if ok else 'MISMATCH'}")
        return ok

    results = [
        rec("master.good", 0, "ad-video-master", good, tmp + "/gm.mp4"),
        rec("master.silent", 1, "ad-video-master", silent, tmp + "/sm.mp4"),
        rec("master.peaky", 1, "ad-video-master", peaky, tmp + "/pm.mp4"),
        rec("master.tpclip", 1, "ad-video-master", tpclip, tmp + "/xm.mp4"),
        rec("master.lim", 0, "ad-video-master", lim, tmp + "/lm.mp4"),
        rec("ocr.good", 0, "ad-caption-ocr", good, capjson),
        rec("ocr.broken", 1, "ad-caption-ocr", bad, capjson),
        rec("ocr.blank", 1, "ad-caption-ocr", silent, capjson),
        rec("sync.tail05", 1, "ad-video-sync", tail5),
        rec("sync.tail02", 0, "ad-video-sync", tail2),
    ]
    r = subprocess.run([os.path.join(ROOT, "ad-video-master"), hot,
                        tmp + "/hm.mp4"], capture_output=True, text=True)
    m = re.search(r"before: (-?[\d.]+) LUFS, (-?[\d.]+) dBTP \| "
                  r"after: (-?[\d.]+) LUFS, (-?[\d.]+) dBTP", r.stdout)
    ok = (r.returncode == 0 and m and -15 <= float(m[3]) <= -13
          and float(m[4]) <= -1.0 and m[1] != m[3])
    ev["runs"]["master.hot"] = {"rc": r.returncode, "want_rc": 0,
                                "output": r.stdout.strip()[-300:]}
    print(f"master.hot: rc={r.returncode} {'OK' if ok else 'MISMATCH'}")
    results.append(ok)
    sg, sb = tmp + "/g.json", tmp + "/b.json"
    results.append(rec("sync.good", 0, "ad-video-sync", good, "--out", sg)
                   and json.load(open(sg)).get("pass") is True)
    results.append(rec("sync.broken", 1, "ad-video-sync", bad, "--out", sb)
                   and bool(json.load(open(sb)).get("dead_gaps"))
                   and json.load(open(sb)).get("tail_after_sound", 9) >= 0.3)
    ev["pass"] = all(results)
    out = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.getcwd(), "ad-video-tools.evidence.json")
    json.dump(ev, open(out, "w"), indent=2)
    print(f"evidence: {out} pass={ev['pass']}")
    return 0 if ev["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
