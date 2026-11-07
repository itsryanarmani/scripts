"""Pop flats: flat colour grounds cut on the beat, giant League Gothic, Space Mono labels, pop-art cards.

Spec: demo-video/examples/pop-flats.json. Style guide: itsryanarmani/skills ship-demo-video/styles/pop-flats.md.
Scene starts are beat numbers. Montage images must be in the project's assets/montage/.
"""
import shutil
from pathlib import Path

from dvkit import SpecError, beat_grid, comp, guard_clips, host, index_html, music_lane, sfx_tags, write_project

INK, WHITE = "#121212", "#ffffff"
SLAM = '{ scale: 1.25, opacity: 0.15, filter: "blur(20px)" }, { scale: 1, opacity: 1, filter: "blur(0px)", duration: 0.4, ease: EO }'
ORDER = ["hook", "montage", "words", "name", "demo", "attitude", "headline", "proof", "end"]


def build(spec, project):
    project = Path(project)
    B, sc = beat_grid(spec), spec["scenes"]
    starts = {k: sc[k]["at_beat"] for k in ORDER}
    nxt = {k: (ORDER[i + 1] if i + 1 < len(ORDER) else None) for i, k in enumerate(ORDER)}
    span = lambda k: (B(starts[k]), round((B(starts[nxt[k]]) if nxt[k] else spec["duration"]) - B(starts[k]), 2))
    rel = lambda k, beat: round(B(beat) - B(starts[k]), 2)
    root_css = f'font-family: "League Gothic", sans-serif; color: {INK};'
    c = lambda cid, css, body, js: comp(cid, '  .mono { font-family: "Space Mono", monospace; }\n' + css, body, js, root_css)
    fg = lambda k: WHITE if sc[k]["ground"].lower() in ("#ff4050", "#6d3cf5", "#121212") or sc[k].get("light_text") else INK
    comps, cues = {}, [("glitch", 0.02)]

    h = sc["hook"]
    comps["hook"] = c("hook", f'  .g {{ position: absolute; left: 0; right: 0; top: 150px; text-align: center; font-size: {h.get("size", 640)}px; line-height: 0.9; color: {fg("hook")}; letter-spacing: 0.01em; }}\n',
                      f'  <div class="g" id="g">{h["word"]}</div>', f'  tl.fromTo("#g", {SLAM}, 0.02);')

    # Montage: real screenshots pile up at shrinking gaps. Images sit next to the scene file.
    mo = sc["montage"]
    (project / "compositions" / "montage").mkdir(parents=True, exist_ok=True)
    pos = [(-40, -20, -3), (60, 30, 2), (-90, 50, -1.5), (120, -40, 3), (0, 70, -2.5), (-130, -60, 1.5), (90, 90, -3.5)]
    imgs, js, t = [], [], 0.0
    for i, (img, gap) in enumerate(zip(mo["images"], mo["gaps"])):
        src = project / "assets" / "montage" / img
        if not src.exists():
            raise SpecError(f"montage image missing: {src}")
        shutil.copy(src, project / "compositions" / "montage" / img)
        t += gap
        x, y, r = pos[i % len(pos)]
        imgs.append(f'  <img class="bn" id="bn{i}" src="montage/{img}" alt="" />')
        js.append(f'  tl.fromTo("#bn{i}", {{ opacity: 0, scale: 0.86, x: {x}, y: {y}, rotation: {r} }}, {{ opacity: 1, scale: 1, x: {x}, y: {y}, rotation: {r}, duration: 0.16, ease: EO }}, {t:.2f});')
        cues.append(("pop", round(B(starts["montage"]) + t, 2)))
    comps["montage"] = c("montage", f"""  .bn {{ position: absolute; left: 400px; top: 196px; width: 1120px; height: 700px; object-fit: cover; border: 10px solid {WHITE}; border-radius: 14px; box-shadow: 16px 16px 0 rgba(0,0,0,0.55); }}
  .cap {{ position: absolute; left: 70px; bottom: 50px; font-size: 30px; color: {fg("montage")}; letter-spacing: 0.08em; }}
""", "\n".join(imgs) + f'\n  <div class="cap mono" id="cap">{mo["caption"]}</div>', "\n".join(js) + '\n  tl.fromTo("#cap", { opacity: 0 }, { opacity: 1, duration: 0.3, ease: EO }, 0.4);')

    w = sc["words"]
    ws = w["words"]
    step = float(spec["beat"]["period"])
    comps["words"] = c("words", f'  .w {{ position: absolute; left: 0; right: 0; top: 120px; text-align: center; font-size: {w.get("size", 780)}px; line-height: 0.9; opacity: 0; color: {fg("words")}; }}\n',
                       "\n".join(f'  <div class="w" id="w{i}">{x}</div>' for i, x in enumerate(ws)),
                       "\n".join(f'  tl.set("#w{i}", {{ opacity: 1 }}, {i * step:.2f});' + (f'\n  tl.set("#w{i}", {{ opacity: 0 }}, {(i + 1) * step:.2f});' if i < len(ws) - 1 else "") for i in range(len(ws))))
    cues += [("stamp", B(starts["words"] + i)) for i in range(len(ws))]

    n = sc["name"]
    glyphs = "".join(f'<span class="gl" id="gl{i}">{ch if ch != " " else "&nbsp;"}</span>' for i, ch in enumerate(n["name"]))
    mid = (len(n["name"]) - 1) / 2
    comps["name"] = c("name", f"""  .nm {{ position: absolute; left: 0; right: 0; top: 260px; text-align: center; font-size: {n.get("size", 330)}px; line-height: 1; color: {fg("name")}; white-space: nowrap; }}
  .gl {{ display: inline-block; }}
  .p {{ position: absolute; left: 0; right: 0; top: 640px; text-align: center; font-size: 44px; color: {fg("name")}; overflow: hidden; }}
  .p > div {{ display: block; }}
""", f'  <div class="nm">{glyphs}</div>\n  <div class="p mono"><div id="p1">{n["promise"]}</div></div>',
        "\n".join(f'  tl.fromTo("#gl{i}", {{ x: {round((i - mid) * 34)}, opacity: 0 }}, {{ x: 0, opacity: 1, duration: 0.45, ease: "power2.out" }}, 0.03);' for i in range(len(n["name"]))) +
        '\n  tl.fromTo("#p1", { y: 70 }, { y: 0, duration: 0.45, ease: EO }, 1.0);')
    cues.append(("whoosh", B(starts["name"])))

    d = sc["demo"]
    rows = "\n".join(f'  <div class="r" id="sr{i}" style="top: {250 + i * 120}px">{r}<span class="off">{d.get("chip", "OFF")}</span></div>' for i, r in enumerate(d["rows"]))
    js = ['  tl.fromTo("#sk", { opacity: 0 }, { opacity: 1, duration: 0.3, ease: EO }, 0.05);']
    js += [f'  tl.fromTo("#sr{i}", {{ opacity: 0, x: 40 }}, {{ opacity: 1, x: 0, duration: 0.25, ease: EO }}, {rel("demo", d["row_beats"][i])});' for i in range(len(d["rows"]))]
    js.append(f'  tl.fromTo("#sr9", {SLAM}, {rel("demo", d["verdict_beat"])});')
    comps["demo"] = c("demo", f"""  .k {{ position: absolute; left: 1430px; top: 150px; font-size: 26px; letter-spacing: 0.12em; color: {fg("demo")}; }}
  .r {{ position: absolute; left: 1430px; font-size: 92px; line-height: 1; white-space: nowrap; color: {fg("demo")}; }}
  .off {{ color: {WHITE}; background: {INK}; padding: 0 12px; margin-left: 12px; }}
""", f'  <div class="k mono" id="sk">{d["kicker"]}</div>\n{rows}\n  <div class="r" id="sr9" style="top: 640px">{d["verdict"]}</div>', "\n".join(js))
    cues += [("pop", B(b)) for b in d["row_beats"]] + [("hit", B(d["verdict_beat"]))]

    a = sc["attitude"]
    comps["attitude"] = c("attitude", f"""  .bg {{ position: absolute; left: -30px; top: 110px; font-size: {a.get("size", 820)}px; line-height: 0.9; color: rgba(18,18,18,0.92); white-space: nowrap; opacity: 0; }}
  .k {{ position: absolute; left: 70px; bottom: 50px; font-size: 28px; letter-spacing: 0.1em; }}
""", "\n".join(f'  <div class="bg" id="n{i}">{x}</div>' for i, x in enumerate(a["words"])) + f'\n  <div class="k mono" id="nk">{a["caption"]}</div>',
        "\n".join((f'  tl.set("#n{i - 1}", {{ opacity: 0 }}, {rel("attitude", b)});\n' if i else "") + f'  tl.fromTo("#n{i}", {SLAM}, {max(0.02, rel("attitude", b))});' for i, b in enumerate(a["word_beats"])) +
        '\n  tl.fromTo("#nk", { opacity: 0 }, { opacity: 1, duration: 0.3, ease: EO }, 0.3);')
    cues += [("hit", B(b)) for b in a["word_beats"]]

    hl = sc["headline"]
    comps["headline"] = c("headline", f"""  .t {{ position: absolute; left: 70px; top: 50px; font-size: 170px; line-height: 0.9; color: {fg("headline")}; }}
  .k {{ position: absolute; left: 70px; bottom: 50px; font-size: 28px; letter-spacing: 0.1em; color: {fg("headline")}; }}
""", f'  <div class="t" id="t">{hl["text"]}</div>\n  <div class="k mono" id="tk">{hl["caption"]}</div>', f'  tl.fromTo("#t", {SLAM}, 0.02);\n  tl.fromTo("#tk", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.3, ease: EO }}, 0.3);')
    cues.append(("whoosh", B(starts["headline"])))

    pr = sc["proof"]
    lefts = [140, 1250, 1900]
    comps["proof"] = c("proof", f"""  .s {{ position: absolute; top: 230px; color: {fg("proof")}; }}
  .n {{ font-size: 470px; line-height: 0.85; }}
  .l {{ font-size: 34px; margin-top: 20px; }}
""", "\n".join(f'  <div class="s" id="p{i}" style="left: {lefts[i]}px"><div class="n">{v}</div><div class="l mono">{l}</div></div>' for i, (v, l) in enumerate(pr["stats"])),
        "\n".join(f'  tl.fromTo("#p{i}", {SLAM}, {0.02 + i * 2 * step:.2f});' for i in range(len(pr["stats"]))))
    cues += [("stamp", round(B(starts["proof"]) + i * 2 * step, 2)) for i in range(len(pr["stats"]))]

    en = sc["end"]
    lines = "\n".join(f'  <div class="l mono" style="top: {560 + 70 * i}px"><div id="e{i}">{l}</div></div>' for i, l in enumerate(en["lines"]))
    comps["end"] = c("end", f"""  .nm {{ position: absolute; left: 140px; top: 250px; font-size: 300px; line-height: 0.9; color: {fg("end")}; }}
  .l {{ position: absolute; left: 140px; font-size: 40px; color: {fg("end")}; overflow: hidden; }}
  .l > div {{ display: block; }}
""", f'  <div class="nm" id="nm">{en["name"]}</div>\n{lines}', f'  tl.fromTo("#nm", {SLAM}, 0.02);\n' +
        "\n".join(f'  tl.fromTo("#e{i}", {{ y: 70 }}, {{ y: 0, duration: 0.45, ease: EO }}, {0.5 + 0.25 * i:.2f});' for i in range(len(en["lines"]))))
    cues.append(("chime", B(starts["end"])))

    # Footage cards: pop-art frames, each clip a hard cut at its beat, held at a fixed push-in.
    clips, cam_html, cam_js = [], [], []
    for i, cl in enumerate(spec["clips"]):
        cid = f"cl{i}"
        st = B(cl["at_beat"])
        du = round(B(cl["at_beat"] + cl["beats"]) - st, 2)
        clips.append({"id": cid, "footage": cl["footage"], "media": cl["media"], "dur": du, "rate": cl.get("rate", 1.5)})
        l, tp, cw, ch = cl["box"]
        s, x, y = cl.get("zoom", [1.0, 0, 0])
        cam_html.append(f'''    <div class="cam" id="c-{cid}" style="left: {l}px; top: {tp}px; width: {cw}px; height: {ch}px"><div class="inner" id="i-{cid}" data-layout-allow-overflow>
      <video id="v-{cid}" class="clip" src="{spec["footage"][cl["footage"]]["src"]}" muted playsinline data-start="{st}" data-duration="{du}" data-media-start="{cl["media"]}" data-playback-rate="{cl.get("rate", 1.5)}" data-track-index="2"></video>
    </div></div>''')
        cam_js += [f'  tl.set("#c-{cid}", {{ opacity: 1 }}, {st});',
                   f'  tl.fromTo("#c-{cid}", {{ scale: 1.08, rotation: -2 }}, {{ scale: 1, rotation: 0, duration: 0.3, ease: EO, immediateRender: false }}, {st});',
                   f'  tl.fromTo("#i-{cid}", {{ scale: {s}, xPercent: {x}, yPercent: {y} }}, {{ scale: {s}, xPercent: {x}, yPercent: {y}, duration: {du}, ease: "none", immediateRender: false }}, {st});',
                   f'  tl.set("#c-{cid}", {{ opacity: 0 }}, {round(st + du, 2)});']
        if cl.get("click_beat") is not None:
            cues.append(("click", B(cl["click_beat"])))
    guard_clips(spec, clips)

    grounds = "\n".join(f'    tl.set("#ground", {{ backgroundColor: "{sc[k]["ground"]}" }}, {B(starts[k])});' for k in ORDER)
    hosts = [host(k, *span(k), style="z-index: 1" if k == "attitude" else "z-index: 3") for k in ORDER]
    m = spec["music"]
    lane = music_lane(spec["duration"], fade_in=m.get("fade_in", 0), fade_out=m.get("fade_out", 1.0))
    head_css = f"""    #ground {{ position: absolute; inset: 0; background: {sc["hook"]["ground"]}; }}
    .cam {{ position: absolute; opacity: 0; border: 12px solid {WHITE}; border-radius: 16px; overflow: hidden; z-index: 2; box-shadow: 18px 18px 0 {INK}; background: {WHITE}; }}
    .inner {{ position: absolute; inset: 0; transform-origin: 50% 50%; }}
    .cam video {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
"""
    body = '    <div id="ground"></div>\n' + "\n".join(cam_html + hosts) + \
        f'\n    <audio id="music" src="{m["src"]}" data-start="0" data-duration="{spec["duration"]}" data-track-index="9" data-volume="{m.get("volume", 0.9)}" data-automation=\'{lane}\'></audio>\n' + \
        sfx_tags(project, sorted(cues, key=lambda q: q[1]), volumes={"pop": 0.4})
    return write_project(project, index_html(spec["duration"], sc["hook"]["ground"], head_css, body, grounds + "\n" + "\n".join(cam_js)), comps)
