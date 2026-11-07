"""Dossier: cream paper with a dot grid, ink, Newsreader serif beats, red-ink underlines and redaction.

Spec: demo-video/examples/dossier.json. Style guide: itsryanarmani/skills ship-demo-video/styles/dossier.md.
Scene starts are beat numbers; the exhibits scene should start on the music's drop.
"""
import shutil
from pathlib import Path

from dvkit import SpecError, beat_grid, comp, guard_clips, host, index_html, music_lane, sfx_tags, write_project

PAPER, INK, MUTED, RED = "#f0eee6", "#262624", "#6f6e66", "#b83a1b"
FONT_FILES = ["newsreader-normal-500.woff2", "newsreader-italic-500.woff2"]


def fonts_css(prefix):
    return (f'  @font-face {{ font-family: "Newsreader"; src: url("{prefix}newsreader-normal-500.woff2") format("woff2"); font-weight: 500 700; font-style: normal; }}\n'
            f'  @font-face {{ font-family: "Newsreader"; src: url("{prefix}newsreader-italic-500.woff2") format("woff2"); font-weight: 500; font-style: italic; }}\n')


def build(spec, project):
    project = Path(project)
    src = project / "assets" / "fonts"
    missing = [f for f in FONT_FILES if not (src / f).exists()]
    if missing:
        raise SpecError(f"Dossier needs {', '.join(missing)} in {src} (Newsreader from Google Fonts, latin woff2)")
    (project / "compositions" / "fonts").mkdir(parents=True, exist_ok=True)
    for f in FONT_FILES:  # sub-compositions may not reach ../, so the fonts sit next to them
        shutil.copy(src / f, project / "compositions" / "fonts" / f)

    B, sc = beat_grid(spec), spec["scenes"]
    root_css = f'font-family: "Newsreader", serif; color: {INK};'
    base = f"""  .mono {{ font-family: "IBM Plex Mono", monospace; }}
  .red {{ color: {RED}; }}
  .m {{ display: inline-block; overflow: hidden; vertical-align: bottom; padding-bottom: 0.1em; }}
  .m > span {{ display: inline-block; }}
"""
    c = lambda cid, css, body, js: comp(cid, base + css, body, js, root_css, fonts_css("fonts/"))
    composer = f"""  .card {{ position: absolute; left: 260px; top: 360px; width: 1400px; background: #fffdf8; border: 3px solid {INK}; border-radius: 20px; padding: 46px 52px; }}
  .lbl {{ font-size: 22px; letter-spacing: 0.16em; text-transform: uppercase; color: {MUTED}; margin-bottom: 18px; }}
  .txt {{ font-size: 46px; line-height: 1.35; }}
"""
    order = ["type", "wait", "about", "exhibits", "redact", "end"]
    starts = {k: sc[k]["at_beat"] for k in order}
    span = lambda k, nxt: (B(starts[k]), round((B(starts[nxt]) if nxt else spec["duration"]) - B(starts[k]), 2))
    comps, hosts, cues = {}, [], []
    rel = lambda k, beat: round(B(beat) - B(starts[k]), 2)

    # Setup: typed message; red-ink underlines and tags on the risky parts.
    t = sc["type"]
    chars, js, n = [], [], 0
    for seg in t["segments"]:
        text, kind = seg["text"], seg.get("pii")
        body = "".join(f'<span class="c" id="ch{n + i}">{ch}</span>' for i, ch in enumerate(text))
        n += len(text)
        chars.append(f'<span class="pii">{body}<span class="ul" id="ul-{kind}"></span><span class="tag mono" id="tag-{kind}">{kind}</span></span>' if kind else body)
    js += [f'  tl.set("#ch{i}", {{ opacity: 1 }}, {0.25 + i * 0.024:.3f});' for i in range(n)]
    for seg in t["segments"]:
        if seg.get("pii"):
            at = rel("type", seg["underline_beat"])
            js += [f'  tl.fromTo("#ul-{seg["pii"]}", {{ clipPath: "inset(0 100% 0 0)" }}, {{ clipPath: "inset(0 0% 0 0)", duration: 0.35, ease: P3 }}, {at});',
                   f'  tl.fromTo("#tag-{seg["pii"]}", {{ opacity: 0, y: 12 }}, {{ opacity: 1, y: 0, duration: 0.3, ease: EO }}, {at + 0.15:.2f});']
            cues.append(("scribble", B(seg["underline_beat"])))
    s0, d0 = span("type", "wait")
    js += ['  tl.fromTo(".card", { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.4, ease: EO }, 0.02);',
           f'  tl.to(".card", {{ scale: 0.82, opacity: 0, filter: "blur(14px)", duration: 0.32, ease: "power3.in" }}, {d0 - 0.32:.2f});']
    comps["type"] = c("type", composer + f"""  .c {{ opacity: 0; }}
  .pii {{ position: relative; }}
  .ul {{ position: absolute; left: 0; right: 0; bottom: -2px; height: 6px; background: {RED}; display: block; }}
  .tag {{ position: absolute; left: 0; top: -30px; font-size: 18px; letter-spacing: 0.14em; text-transform: uppercase; color: {RED}; white-space: nowrap; }}
""", f'  <div class="card"><div class="lbl mono">{t["label"]}</div><div class="txt">{"".join(chars)}</div></div>', "\n".join(js))
    cues += [("type", 0.25), ("type", 1.0)]

    comps["wait"] = c("wait", """  .w { position: absolute; left: 0; right: 0; top: 250px; text-align: center; font-size: 420px; font-style: italic; font-weight: 500; letter-spacing: -0.03em; line-height: 1; }
""", f'  <div class="w" id="w">{sc["wait"]["word"]}</div>', '  tl.fromTo("#w", { opacity: 0, scale: 1.08 }, { opacity: 1, scale: 1, duration: 0.18, ease: P3 }, 0.02);')
    cues.append(("stamp", B(starts["wait"])))

    a = sc["about"]
    rows = "".join(f'<div class="row"><div id="r{i}">{r}</div></div>' for i, r in enumerate(a["rows"]))
    _, da = span("about", "exhibits")
    comps["about"] = c("about", """  .rows { position: absolute; left: 180px; top: 300px; }
  .row { overflow: hidden; font-size: 150px; font-weight: 500; letter-spacing: -0.03em; line-height: 1.12; }
  .row > div { display: block; }
""", f'  <div class="rows" id="rows">{rows}</div>',
        "\n".join(f'  tl.fromTo("#r{i}", {{ y: 190 }}, {{ y: 0, duration: 0.55, ease: EO }}, {0.05 + 0.5 * i:.2f});' for i in range(len(a["rows"]))) +
        f'\n  tl.to("#rows", {{ scale: 1.55, opacity: 0, filter: "blur(18px)", duration: 0.34, ease: "power2.in", transformOrigin: "40% 50%" }}, {da - 0.34:.2f});')
    cues += [("riser", B(starts["exhibits"] - 2)), ("hit", B(starts["exhibits"]))]

    # Exhibits: tilted footage cards on the drop, hard cuts on beats; labels in the scene's own comp.
    e = sc["exhibits"]
    clips, cam_html, cam_js = [], [], []
    labels, ljs = [], []
    beats = [x["at_beat"] for x in e["clips"]] + [starts["redact"]]
    for i, cl in enumerate(e["clips"]):
        st, du = B(cl["at_beat"]), round(B(beats[i + 1]) - B(cl["at_beat"]), 2)
        cid = f"ex{i}"
        clips.append({"id": cid, "footage": cl["footage"], "media": cl["media"], "dur": du, "rate": cl.get("rate", 1.3)})
        s, x, y = cl["zoom"]
        cam_html.append(f'''    <div class="cam" id="c-{cid}"><div class="photo"><div class="inner" id="i-{cid}" data-layout-allow-overflow>
      <video id="v-{cid}" class="clip" src="{spec["footage"][cl["footage"]]["src"]}" muted playsinline data-start="{st}" data-duration="{du}" data-media-start="{cl["media"]}" data-playback-rate="{cl.get("rate", 1.3)}" data-track-index="2"></video>
    </div></div></div>''')
        cam_js += [f'  tl.set("#c-{cid}", {{ opacity: 1, rotation: {cl.get("tilt", -1.0)} }}, {st});',
                   f'  tl.fromTo("#c-{cid}", {{ scale: 1.06 }}, {{ scale: 1, duration: 0.25, ease: EO, immediateRender: false }}, {st});',
                   f'  tl.fromTo("#i-{cid}", {{ scale: {s}, xPercent: {x}, yPercent: {y} }}, {{ scale: {round(s - 0.08, 2)}, xPercent: {x}, yPercent: {y}, duration: {du}, ease: "power1.out", immediateRender: false }}, {st});',
                   f'  tl.set("#c-{cid}", {{ opacity: 0 }}, {round(st + du, 2)});']
        if i:
            cues.append(("whoosh", st))
        labels.append(f'<div class="ex" id="lb{i}"><span class="mono red">{cl["exhibit"]}</span> <span class="mono">· {cl["site"]}</span></div>')
        at = rel("exhibits", cl["at_beat"])
        ljs.append(f'  tl.fromTo("#lb{i}", {{ opacity: 0, x: -20 }}, {{ opacity: 1, x: 0, duration: 0.25, ease: EO }}, {at + 0.02:.2f});')
        if i + 1 < len(e["clips"]):
            ljs.append(f'  tl.set("#lb{i}", {{ opacity: 0 }}, {rel("exhibits", beats[i + 1]):.2f});')
    ljs.append('  tl.fromTo("#hd", { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.4, ease: EO }, 0.1);')
    comps["exhibits"] = c("exhibits", """  .ex { position: absolute; left: 300px; top: 70px; font-size: 26px; letter-spacing: 0.14em; text-transform: uppercase; }
  .hd { position: absolute; right: 300px; top: 58px; font-size: 52px; font-style: italic; }
""", "".join(labels) + f'<div class="hd" id="hd">{e["headline"]}</div>', "\n".join(ljs))
    guard_clips(spec, clips)

    # Payoff: the same message, values swapping to tags, then a stamp.
    r = sc["redact"]
    txt, js = "", []
    for i, seg in enumerate(r["segments"]):
        if "tag" in seg:
            txt += f'<span class="slot" id="s{i}"><span class="old" id="o{i}">{seg["text"]}</span><span class="new" id="n{i}">{seg["tag"]}</span></span>'
            at = rel("redact", seg["swap_beat"])
            js += [f'  tl.to("#o{i}", {{ yPercent: -115, duration: 0.22, ease: "power2.in" }}, {at});',
                   f'  tl.fromTo("#n{i}", {{ yPercent: 115 }}, {{ yPercent: 0, duration: 0.3, ease: EO }}, {at + 0.08:.2f});',
                   f'  tl.to("#s{i}", {{ width: {24 * len(seg["tag"]) + 4}, duration: 0.3, ease: EO }}, {at + 0.08:.2f});']
            cues.append(("pop", B(seg["swap_beat"])))
        else:
            txt += seg["text"]
    js.insert(0, '  tl.fromTo("#card", { opacity: 0, scale: 1.25, filter: "blur(10px)" }, { opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.45, ease: EO }, 0.02);')
    js.append(f'  tl.fromTo("#stamp", {{ opacity: 0, scale: 1.6 }}, {{ opacity: 1, scale: 1, duration: 0.18, ease: P3 }}, {rel("redact", r["stamp_beat"])});')
    cues.append(("stamp", B(r["stamp_beat"])))
    comps["redact"] = c("redact", composer + f"""  .slot {{ display: inline-block; position: relative; overflow: hidden; vertical-align: bottom; white-space: nowrap; }}
  .slot .old, .slot .new {{ display: inline-block; }}
  .slot .new {{ position: absolute; left: 0; top: 0; color: {RED}; font-family: "IBM Plex Mono", monospace; font-size: 40px; white-space: nowrap; }}
  .stamp {{ position: absolute; right: 300px; top: 220px; font-size: 30px; letter-spacing: 0.2em; text-transform: uppercase; color: {RED}; border: 4px solid {RED}; padding: 10px 18px; transform: rotate(-6deg); }}
""", f'  <div class="stamp mono" id="stamp">{r["stamp"]}</div>\n  <div class="card" id="card"><div class="lbl mono">{r["label"]}</div><div class="txt">{txt}</div></div>', "\n".join(js))

    en = sc["end"]
    lines = "\n".join(f'  <div class="l mono" style="top: {610 + 60 * i}px"><div id="l{i}">{l}</div></div>' for i, l in enumerate(en["lines"]))
    comps["end"] = c("end", f"""  .wm {{ position: absolute; left: 180px; top: 300px; font-size: 230px; font-weight: 700; letter-spacing: -0.035em; line-height: 1; }}
  .bar {{ position: absolute; left: 180px; top: 560px; width: 1200px; height: 8px; background: {INK}; transform-origin: left center; display: block; }}
  .l {{ position: absolute; left: 180px; font-size: 36px; overflow: hidden; }}
""", f'  <div class="wm" id="wm">{en["word"]}<span class="red">.</span></div>\n  <span class="bar" id="bar"></span>\n{lines}',
        '  tl.fromTo("#wm", { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.18, ease: P3 }, 0.02);\n'
        '  tl.fromTo("#bar", { scaleX: 0 }, { scaleX: 1, duration: 0.6, ease: EO }, 0.3);\n' +
        "\n".join(f'  tl.fromTo("#l{i}", {{ y: 60 }}, {{ y: 0, duration: 0.45, ease: EO }}, {0.55 + 0.25 * i:.2f});' for i in range(len(en["lines"]))))
    cues.append(("hit", B(starts["end"])))

    for i, k in enumerate(order):
        s, d = span(k, order[i + 1] if i + 1 < len(order) else None)
        hosts.append(host(k, s, d))
    m = spec["music"]
    lane = music_lane(spec["duration"], fade_in=m.get("fade_in", 0), fade_out=m.get("fade_out", 1.3))
    head_css = f"""    #dots {{ position: absolute; inset: 0; background: radial-gradient(circle, rgba(38,36,30,0.09) 1.6px, transparent 1.6px) 0 0 / 34px 34px; }}
    .cam {{ position: absolute; left: 290px; top: 150px; width: 1340px; height: 870px; opacity: 0; background: #fffdf8; padding: 18px;
      border: 3px solid {INK}; box-shadow: 0 26px 60px rgba(38,36,30,0.22); }}
    .photo {{ position: relative; width: 100%; height: 100%; overflow: hidden; }}
    .inner {{ position: absolute; inset: 0; transform-origin: 50% 50%; }}
    .cam video {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
"""
    body = '    <div id="dots"></div>\n' + "\n".join(cam_html + hosts) + \
        f'\n    <audio id="music" src="{m["src"]}" data-start="0" data-duration="{spec["duration"]}" data-track-index="9" data-volume="{m.get("volume", 0.9)}" data-automation=\'{lane}\'></audio>\n' + \
        sfx_tags(project, sorted(cues, key=lambda q: q[1]), volumes={"type": 0.3, "whoosh": 0.55, "hit": 0.55, "stamp": 0.55, "scribble": 0.55, "riser": 0.55, "pop": 0.55})
    return write_project(project, index_html(spec["duration"], PAPER, head_css, body, "\n".join(cam_js), fonts_css("assets/fonts/")), comps)
