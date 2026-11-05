#!/usr/bin/python3 -I
"""Generate a HyperFrames index.html for a beat-cut film from a JSON spec.
Usage: film_build.py spec.json [out.html]
Spec keys: bpm, total_beats, music{src,media_start,duck,duck_to}, shots[{id,kind(video|img),src,start,beats,motion}],
texts[{id,lines,start,beats,cls(hook|low|top|big)}], sfx[{name,beat,vol}], flashes[beats], shakes{shot:beat},
black_beat, speed_lines[from,to], panel{src,start,beats,alt}, end{start,beats,title,sub,url,note,mark_svg}, tag,
palette{ink,paper,accent,card,accent_ink}, font{family,file}.
Assets live next to the output file. A shot src is a file name inside assets/ (for example clip.mp4). The music, panel
and font paths include the folder (for example assets/bed.mp3). Sound effects are read from assets/sfx-<name>.mp3. mark_svg must carry id="endmark".
texts[].accent_last colors the last line with the accent. A text with cls "hook" is visible on frame 0. Every key shown
above is required. Every time in the spec is in beats."""
import html, json, sys
SPEC = json.load(open(sys.argv[1])); OUT = sys.argv[2] if len(sys.argv) > 2 else "index.html"
B = 60 / SPEC["bpm"]
def t(b): return round(b*B, 3)
SHOTS = [(x["id"], x["kind"], x["src"], x["start"], x["beats"], x.get("motion")) for x in SPEC["shots"]]
TEXTS = [(x["id"], [html.escape(l) for l in x["lines"]], x["start"], x["beats"], x["cls"], x.get("accent_last", False)) for x in SPEC["texts"]]
TOTAL = SPEC["total_beats"]
SFX = [(x["name"], x["beat"], x["vol"]) for x in SPEC["sfx"]]
FLASH = SPEC["flashes"]; SHAKE = SPEC["shakes"]
P, F, E, PN, M = SPEC["palette"], SPEC["font"], SPEC["end"], SPEC["panel"], SPEC["music"]
BLK = SPEC["black_beat"]; SL = SPEC["speed_lines"]
h = []
a = h.append
a('''<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=1920, height=1080"><title>@@TITLE@@</title>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@font-face{font-family:"@@FAM@@";font-weight:700;src:url("@@FFILE@@") format("woff2")}
:root{--ink:@@INK@@;--paper:@@PAPER@@;--orange:@@ACC@@;--card:@@CARD@@;--white:#fffaf0}
html,body{margin:0;background:var(--ink)}
#root{position:relative;width:1920px;height:1080px;overflow:hidden;background:var(--ink);font-family:"@@FAM@@"}
#root>video,#root>img{position:absolute;left:0;top:0;width:1920px;height:1080px;object-fit:cover;display:block}
.clip{position:absolute;left:0;top:0;width:1920px;height:1080px}
.txt{position:absolute;left:96px;right:96px;text-transform:uppercase;font-weight:700;color:var(--white);line-height:.9;letter-spacing:.01em;
 -webkit-text-stroke:0;paint-order:stroke fill;text-shadow:6px 6px 0 var(--ink),-3px -3px 0 var(--ink),3px -3px 0 var(--ink),-3px 3px 0 var(--ink);transform-origin:0 100%}
.txt.hook{bottom:92px;font-size:178px}
.txt.low{bottom:84px;font-size:164px}
.txt.top{bottom:36px;font-size:150px;text-align:right}
.txt.big{top:50%;margin-top:-170px;left:0;right:0;text-align:center;font-size:330px;color:var(--white);transform-origin:50% 50%}
.txt.big .l{display:block}
.txt .l{display:block;transform-origin:0 100%}
.txt .l.hl{color:var(--orange)}
.flash{background:#fff;opacity:0}
.black{background:#000}
.dot{position:absolute;left:50%;top:50%;width:40px;height:40px;margin:-20px;border-radius:50%;background:var(--orange)}
.speed{background:repeating-conic-gradient(from 0deg at 50% 50%,rgba(255,250,240,0) 0 2.2deg,rgba(255,250,240,.55) 2.2deg 2.8deg);
 -webkit-mask-image:radial-gradient(circle at 50% 50%,transparent 24%,#000 78%);mask-image:radial-gradient(circle at 50% 50%,transparent 24%,#000 78%);mix-blend-mode:screen;opacity:.0}
.tag{position:absolute;right:48px;top:40px;width:auto;height:auto;padding:8px 16px 6px;background:var(--ink);color:var(--paper);font-size:34px;letter-spacing:.14em;border:3px solid var(--paper)}
.proofbg{background:var(--card)}
.panel{position:absolute;left:340px;top:56px;width:1240px;height:693px;border:10px solid var(--ink);box-shadow:18px 18px 0 var(--ink);background:var(--paper);overflow:hidden}
.panel img{width:100%;height:100%;object-fit:cover;display:block}
.endbg{background:var(--paper)}
.end{position:absolute;left:0;top:0;width:1920px;height:1080px;text-align:center;color:var(--ink)}
.end .mark{position:absolute;left:810px;top:150px;width:300px;height:300px;color:var(--ink)}
.end h1{position:absolute;left:0;right:0;top:450px;margin:0;font-size:260px;line-height:.9;text-transform:uppercase}
.end .sub{position:absolute;left:0;right:0;top:700px;font-size:74px;text-transform:uppercase;letter-spacing:.06em;color:@@ACCINK@@}
.end .url{position:absolute;left:0;right:0;top:810px;font-size:64px;letter-spacing:.04em}
.end .sim{position:absolute;left:0;right:0;top:930px;font-size:40px;letter-spacing:.1em;text-transform:uppercase;color:#4a433a}
</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-width="1920" data-height="1080" data-duration="@@DUR@@">
'''.replace('@@DUR@@', str(t(TOTAL))))
tr = 1
for n,k,src,sb,bt,_ in SHOTS:
    if k=="video":
        a(f'<video id="s-{n}" data-start="{t(sb)}" data-duration="{t(bt)}" data-track-index="1" data-media-start="0" src="assets/{src}" muted playsinline></video>')
    else:
        a(f'<img id="s-{n}" class="clip" data-start="{t(sb)}" data-duration="{t(bt)}" data-track-index="1" src="assets/{src}" alt="">')
# black beat
a(f'<div id="blk" class="clip black" data-start="{t(BLK)}" data-duration="{t(1)}" data-track-index="2"><div class="dot" id="dot"></div></div>')
# proof shot
a(f'<div id="proof" class="clip proofbg" data-start="{t(PN["start"])}" data-duration="{t(PN["beats"])}" data-track-index="1"><div class="panel" id="panel"><img src="@@PSRC@@" alt="@@PALT@@"></div></div>')
# end card
a(f'<div id="endc" class="clip endbg" data-start="{t(E["start"])}" data-duration="{t(E["beats"])}" data-track-index="1"><div class="end">'
  '@@MARK@@'
  '<h1 id="endh">@@ETITLE@@</h1><div class="sub" id="ends">@@ESUB@@</div><div class="url" id="endu">@@EURL@@</div>'
  '<div class="sim" id="endsim">@@ENOTE@@</div></div></div>')
# speed lines
a(f'<div id="speed" class="clip speed" data-start="{t(SL[0])}" data-duration="{t(SL[1]-SL[0])}" data-track-index="6"></div>')
# texts
for i,(tid,lines,sb,bt,cls,acc) in enumerate(TEXTS):
    ls="".join(f'<span class="l{" hl" if (acc and j==len(lines)-1) else ""}" id="{tid}-{j}">{x}</span>' for j,x in enumerate(lines))
    a(f'<div id="{tid}" class="clip" data-start="{t(sb)}" data-duration="{t(bt)}" data-track-index="{5 if i%2==0 else 7}"><div class="txt {cls}">{ls}</div></div>')
# flashes (0.25 s on screen, fading over 0.22 s)
for i,fb in enumerate(FLASH):
    a(f'<div id="fl{i}" class="clip flash" data-start="{t(fb)}" data-duration="0.25" data-track-index="{8+i}"></div>')
a(f'<div id="tag" class="clip tag" style="left:auto;width:auto;height:auto" data-start="0" data-duration="{t(TOTAL)}" data-track-index="20">@@TAG@@</div>')
# audio
a(f'<audio id="bgm" data-start="0" data-duration="{t(TOTAL)}" data-track-index="30" data-media-start="@@MSTART@@" src="@@MSRC@@" data-volume="1"></audio>')
for i,(n,b,v) in enumerate(SFX):
    a(f'<audio id="sx{i}" data-start="{round(max(b*B-0.05,0),3)}" data-track-index="{31+i}" src="assets/sfx-{n}.mp3" data-volume="{v}"></audio>')
a('</div><script>window.__timelines=window.__timelines||{};const tl=gsap.timeline({paused:true});const B='+str(B)+';')
js = []
j = js.append
for n,k,src,sb,bt,mo in SHOTS:
    s0=t(sb); d=t(bt)
    if mo=="punch": j(f'tl.fromTo("#s-{n}",{{scale:1.28,rotation:-1.5}},{{scale:1,rotation:0,duration:{min(d,0.4)},ease:"power4.out",immediateRender:false}},{s0});')
    if mo=="push": j(f'tl.fromTo("#s-{n}",{{scale:1}},{{scale:1.1,duration:{d},ease:"none",immediateRender:false}},{s0});')
    if mo=="pull": j(f'tl.fromTo("#s-{n}",{{scale:1.14}},{{scale:1,duration:{d},ease:"power2.out",immediateRender:false}},{s0});')
    if mo=="pan": j(f'tl.fromTo("#s-{n}",{{scale:1.15,x:60}},{{scale:1.15,x:-60,duration:{d},ease:"none",immediateRender:false}},{s0});')
for n,fb in SHAKE.items():
    s0=t(fb)
    for q,(x,y) in enumerate([(26,-14),(-22,18),(16,-10),(-10,8),(5,-4),(0,0)]):
        j(f'tl.to("#s-{n}",{{x:{x},y:{y},duration:0.045,ease:"none"}},{round(s0+0.05+q*0.045,3)});')
for i,fb in enumerate(FLASH):
    j(f'tl.fromTo("#fl{i}",{{opacity:1}},{{opacity:0,duration:0.22,ease:"power2.out",immediateRender:false}},{t(fb)});')
j(f'tl.fromTo("#dot",{{scale:0.3}},{{scale:5,duration:{t(1)},ease:"power3.in",immediateRender:false}},{t(BLK)});')
j(f'tl.fromTo("#speed",{{opacity:0}},{{opacity:.5,duration:0.2,immediateRender:false}},{t(SL[0])});')
j(f'tl.fromTo("#speed",{{rotation:0}},{{rotation:20,duration:{t(SL[1]-SL[0])},ease:"none",immediateRender:false}},{t(SL[0])});')
j(f'tl.to("#speed",{{opacity:0,duration:0.15}},{round(t(SL[1])-0.15,3)});')
# texts: slam in line by line, hook visible at frame 0
for tid,lines,sb,bt,cls,acc in TEXTS:
    s0=t(sb)
    for jx in range(len(lines)):
        if cls=="hook": j(f'tl.fromTo("#{tid}-{jx}",{{scale:1.12,x:-30}},{{scale:1,x:0,duration:0.25,ease:"power4.out",immediateRender:false}},{s0+jx*0.18});')
        else: j(f'tl.fromTo("#{tid}-{jx}",{{scale:1.7,opacity:0,x:-70,skewX:-10}},{{scale:1,opacity:1,x:0,skewX:-6,duration:0.2,ease:"power4.out",immediateRender:false}},{round(s0+jx*B*0.6,3)});')
j(f'tl.fromTo("#panel",{{scale:0.7,rotation:-6,y:120}},{{scale:1,rotation:-1.5,y:0,duration:0.3,ease:"power4.out",immediateRender:false}},{t(PN["start"])});')
e0=t(E["start"])
j(f'tl.fromTo("#endmark",{{scale:2.2,opacity:0,rotation:-12}},{{scale:1,opacity:1,rotation:0,duration:0.3,ease:"power4.out",immediateRender:false}},{e0});')
for idn,dl in (("endh",.1),("ends",.22),("endu",.34),("endsim",.46)):
    j(f'tl.fromTo("#{idn}",{{y:50,opacity:0}},{{y:0,opacity:1,duration:0.28,ease:"power3.out",immediateRender:false}},{round(e0+dl,3)});')
# music lane: fade in, riser duck before black beat, slam back, outro fade
j(f'tl.fromTo("#bgm",{{volume:0}},{{volume:1,duration:0.3}},0);')
j(f'tl.to("#bgm",{{volume:{M["duck_to"]},duration:0.25}},{round(t(M["duck"][0]),3)});tl.to("#bgm",{{volume:1,duration:0.05}},{t(M["duck"][1])});')
j(f'tl.to("#bgm",{{volume:0,duration:1.5}},{round(t(TOTAL)-1.5,3)});')
a("\n".join(js))
a('window.__timelines["main"]=tl;</script></body></html>')
HTML = "\n".join(h)
for k, v in {"@@INK@@": P["ink"], "@@PAPER@@": P["paper"], "@@ACC@@": P["accent"], "@@CARD@@": P["card"], "@@ACCINK@@": P["accent_ink"],
  "@@TITLE@@": E["title"] + " film", "@@FAM@@": F["family"], "@@FFILE@@": F["file"], "@@PALT@@": PN["alt"], "@@PSRC@@": PN["src"],
  "@@TAG@@": SPEC["tag"], "@@MSRC@@": M["src"], "@@MSTART@@": str(M["media_start"]), "@@MARK@@": E["mark_svg"], "@@ETITLE@@": E["title"],
  "@@ESUB@@": E["sub"], "@@EURL@@": E["url"], "@@ENOTE@@": E["note"]}.items():
    HTML = HTML.replace(k, v if k == "@@MARK@@" else html.escape(v, quote=True))
open(OUT, "w").write(HTML); print("beats", TOTAL, "dur", t(TOTAL))
