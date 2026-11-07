"""Keynote whip: light gray stage, white cards, Montserrat + JetBrains Mono, exponential whips with blur.

Spec: demo-video/examples/keynote-whip.json. Style guide: itsryanarmani/skills ship-demo-video/styles/keynote-whip.md.
Scene lengths are in beats; times inside a scene are seconds from the scene's start.
"""
from dvkit import beat_grid, comp, guard_clips, host, index_html, music_lane, sfx_tags, write_project, words

INK, BG, MUTED = "#0f1115", "#f2f4f7", "#5b6170"
ORDER = ["hook", "promise", "demos", "stat", "values", "finale", "end"]


def build(spec, project):
    B, acc, sc = beat_grid(spec), spec["accent"], spec["scenes"]
    root_css = f'font-family: "Montserrat", sans-serif; color: {INK};'
    base = f"""  .mono {{ font-family: "JetBrains Mono", monospace; }}
  .acc {{ color: {acc}; }}
  .m {{ display: inline-block; overflow: hidden; vertical-align: bottom; padding-bottom: 0.08em; }}
  .m > span {{ display: inline-block; }}
"""
    c = lambda cid, css, body, js: comp(cid, base + css, body, js, root_css)

    # Lay scenes end to end on the beat grid: [(name, start, dur)].
    k, slots = 0, []
    for name in ORDER:
        items = sc[name] if name == "demos" else [sc[name]]
        for i, item in enumerate(items):
            beats = item.get("beats")
            start = B(k)
            end = spec["duration"] if beats is None else B(k + beats)
            slots.append((name if name != "demos" else f"demo{i}", start, round(end - start, 2), item))
            k += beats or 0
    comps, hosts, clips, cam_html, cam_js, cues = {}, [], [], [], [], []

    for cid, start, dur, item in slots:
        out = round(dur - 0.3, 2)  # whip out so it lands on the next scene's first beat
        if cid == "hook":
            comps[cid] = c(cid, "  .big { position: absolute; left: 150px; top: 330px; font-size: 230px; font-weight: 800; letter-spacing: -0.05em; line-height: 1; }\n",
                           f'  <div class="big" id="hk">{words(item["text"])}</div>',
                           f'  tl.fromTo("#hk .m > span", {{ yPercent: 115 }}, {{ yPercent: 0, duration: 0.55, ease: P4, stagger: 0.12 }}, 0.1);\n'
                           f'  tl.to("#hk", {{ x: -1745, filter: "blur(8px)", duration: 0.3, ease: EI }}, {out});')
            cues.append(("whoosh", round(start + out - 0.02, 2)))
        elif cid == "promise":
            ws = item["words"]
            spans = "".join(f'<span class="w{" acc" if i == item["accent"] else ""}" id="wf{i}">{w}</span>' for i, w in enumerate(ws))
            gaps = [360, 180, 120, 60] + [30] * max(0, len(ws) - 4)
            js = [f'  tl.fromTo("#wf{i}", {{ x: {g + 230}, opacity: 0 }}, {{ x: 0, opacity: 1, duration: 0.32, ease: P4 }}, {0.02 + i * 0.07:.2f});' for i, g in enumerate(gaps[:len(ws)])]
            js += [f'  tl.fromTo("#rg", {{ scale: 0.2, opacity: 1 }}, {{ scale: 3.2, opacity: 0, duration: 0.6, ease: EO }}, {item["click_at"]});',
                   f'  tl.to("#wf{item["accent"]}", {{ scale: 0.94, duration: 0.08, ease: "power2.in", yoyo: true, repeat: 1, transformOrigin: "50% 60%" }}, {item["click_at"]});',
                   f'  tl.to(".line", {{ y: -900, filter: "blur(8px)", duration: 0.3, ease: EI }}, {out});']
            comps[cid] = c(cid, f"""  .line {{ position: absolute; left: 150px; top: 390px; font-size: {item.get("size", 128)}px; font-weight: 800; letter-spacing: -0.045em; white-space: nowrap; }}
  .w {{ display: inline-block; margin-right: 0.24em; }}
  .ring {{ position: absolute; width: 60px; height: 60px; border-radius: 50%; border: 6px solid {acc}; left: {item.get("ring_x", 1600)}px; top: 470px; }}
""", f'  <div class="line">{spans}</div>\n  <div class="ring" id="rg"></div>', "\n".join(js))
            cues += [("click", round(start + item["click_at"] + 0.04, 2))]
        elif cid.startswith("demo"):
            goal = item["goal"]
            chars = "".join(f'<span class="ch" id="{cid}-c{i}">{ch}</span>' for i, ch in enumerate(goal))
            js = [f'  tl.fromTo("#{cid}-lab", {{ opacity: 0, x: 40 }}, {{ opacity: 1, x: 0, duration: 0.45, ease: EO }}, 0.1);',
                  f'  tl.fromTo("#{cid}-box", {{ opacity: 0, y: 30, filter: "blur(10px)" }}, {{ opacity: 1, y: 0, filter: "blur(0px)", duration: 0.5, ease: EO }}, 0.15);']
            js += [f'  tl.set("#{cid}-c{i}", {{ opacity: 1 }}, {0.35 + i * 0.033:.3f});' for i in range(len(goal))]
            js.append(f'  tl.fromTo("#{cid}-done", {{ opacity: 0, y: 30, filter: "blur(10px)" }}, {{ opacity: 1, y: 0, filter: "blur(0px)", duration: 0.5, ease: EO }}, {item["done_at"]});')
            comps[cid] = c(cid, f"""  .col {{ position: absolute; left: 1370px; top: 120px; width: 470px; }}
  .lab {{ font-size: 22px; letter-spacing: 0.18em; text-transform: uppercase; color: {MUTED}; }}
  .box {{ margin-top: 22px; background: #fff; border-radius: 22px; padding: 26px 28px; font-size: 34px; line-height: 1.3; font-weight: 700;
    box-shadow: 0 20px 60px rgba(15,17,21,0.12), 0 2px 6px rgba(15,17,21,0.06); }}
  .ch {{ opacity: 0; }}
  .done {{ margin-top: 22px; font-size: 30px; font-weight: 700; color: {acc}; }}
""", f"""  <div class="col">
    <div class="lab mono" id="{cid}-lab">{item.get("label", "Goal")}</div>
    <div class="box" id="{cid}-box">{chars}</div>
    <div class="done mono" id="{cid}-done">{item["done"]}</div>
  </div>""", "\n".join(js))
            cues += [("type", round(start + 0.35, 2)), ("chime", round(start + item["done_at"], 2))]
            for j, cl in enumerate(item["clips"]):
                cl = dict(cl, id=f"{cid}-{j}")
                at = round(start + cl.get("at", 0), 2)
                clips.append(dict(cl, dur=cl["dur"]))
                s, x, y = cl["zoom"]
                cam_html.append(f'''    <div class="cam" id="c-{cl["id"]}"><div class="inner" id="i-{cl["id"]}" data-layout-allow-overflow>
      <video id="v-{cl["id"]}" class="clip" src="{spec["footage"][cl["footage"]]["src"]}" muted playsinline data-start="{at}" data-duration="{cl["dur"]}" data-media-start="{cl["media"]}" data-playback-rate="{cl.get("rate", 1.0)}" data-track-index="2"></video>
    </div></div>''')
                cam_js.append(f'  tl.fromTo("#i-{cl["id"]}", {{ scale: 1.02, xPercent: 0, yPercent: 0 }}, {{ scale: {s}, xPercent: {x}, yPercent: {y}, duration: 0.8, ease: EO, immediateRender: false }}, {round(at + 0.35, 2)});')
                if j == 0 and item.get("enter", "grow") == "grow":
                    cam_js.append(f'  tl.fromTo("#c-{cl["id"]}", {{ opacity: 0, scale: 1.3, filter: "blur(12px)" }}, {{ opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.6, ease: EO }}, {at});')
                else:
                    sx = 1745 if j == 0 else 300
                    cam_js.append(f'  tl.fromTo("#c-{cl["id"]}", {{ opacity: 1, x: {sx}, filter: "blur(8px)" }}, {{ opacity: 1, x: 0, filter: "blur(0px)", duration: {0.45 if j == 0 else 0.35}, ease: EO, immediateRender: false }}, {at});')
                    cues.append(("whoosh", round(at - 0.03, 2)))
                last = j == len(item["clips"]) - 1
                if last:
                    exit_to = {"up": "y: -1300", "left": "x: -1745"}[item.get("exit", "up")]
                    cam_js.append(f'  tl.to("#c-{cl["id"]}", {{ {exit_to}, filter: "blur(8px)", duration: 0.3, ease: EI }}, {round(start + dur - 0.3, 2)});')
                    cues.append(("whoosh", round(start + dur - 0.32, 2)))
                else:
                    cam_js.append(f'  tl.set("#c-{cl["id"]}", {{ opacity: 0 }}, {round(at + cl["dur"], 2)});')
        elif cid == "stat":
            comps[cid] = c(cid, f"""  .wrap {{ position: absolute; left: 150px; top: 300px; }}
  .n {{ font-size: 330px; font-weight: 800; letter-spacing: -0.06em; line-height: 0.9; }}
  .n small {{ font-size: 140px; letter-spacing: -0.03em; }}
  .l {{ font-size: 36px; margin-top: 30px; color: {MUTED}; }}
""", f'  <div class="wrap"><div class="n" id="st">{item["value"]}<small>{item.get("unit", "")}</small></div><div class="l mono" id="sl">{item["label"]}</div></div>',
                f"""  tl.fromTo("#st", {{ scale: 1.25, opacity: 0.15, filter: "blur(20px)" }}, {{ scale: 1, opacity: 1, filter: "blur(0px)", duration: 0.5, ease: EO, transformOrigin: "0% 50%" }}, 0.05);
  tl.fromTo("#sl", {{ opacity: 0, x: -30 }}, {{ opacity: 1, x: 0, duration: 0.45, ease: EO }}, 0.5);
  tl.to(".wrap", {{ x: -1745, filter: "blur(8px)", duration: 0.3, ease: EI }}, {out});""")
            cues.append(("hit", round(start + 0.02, 2)))
        elif cid == "values":
            rows = item["rows"]
            per = item.get("every_beats", 2) * float(spec["beat"]["period"])
            body = '  <div class="rows">' + "".join(f'<div class="row"><div id="pr{i}"{" class=\"acc\"" if i == len(rows) - 1 else ""}>{r}</div></div>' for i, r in enumerate(rows)) + "</div>"
            js = [f'  tl.fromTo("#pr{i}", {{ y: 140 }}, {{ y: 0, duration: 0.5, ease: EO }}, {round(0.01 + i * per, 2)});' for i in range(len(rows))]
            js.append(f'  tl.to(".rows", {{ y: -900, filter: "blur(8px)", duration: 0.3, ease: EI }}, {out});')
            comps[cid] = c(cid, """  .rows { position: absolute; left: 150px; top: 250px; }
  .row { overflow: hidden; font-size: 120px; font-weight: 800; letter-spacing: -0.045em; line-height: 1.12; }
  .row > div { display: block; }
""", body, "\n".join(js))
            cues += [("pop", round(start + 0.01 + i * per, 2)) for i in range(len(rows))]
        elif cid == "finale":
            comps[cid] = c(cid, f"""  .wm {{ position: absolute; left: 0; right: 0; top: 330px; text-align: center; font-size: 300px; font-weight: 800; letter-spacing: -0.06em; line-height: 1; }}
  .dot {{ color: {acc}; }}
  .tag {{ position: absolute; left: 0; right: 0; top: 690px; text-align: center; font-size: 64px; font-weight: 700; letter-spacing: -0.02em; }}
""", f'  <div class="wm" id="wm">{item["word"]}<span class="dot">.</span></div>\n  <div class="tag" id="tg">{words(item["tagline"])}</div>',
                f"""  tl.fromTo("#wm", {{ scale: 1.25, opacity: 0.15, filter: "blur(20px)" }}, {{ scale: 1, opacity: 1, filter: "blur(0px)", duration: 0.55, ease: EO }}, {item.get("slam_at", 0.15)});
  tl.fromTo("#tg .m > span", {{ yPercent: 115 }}, {{ yPercent: 0, duration: 0.5, ease: P4, stagger: 0.1 }}, {item.get("tag_at", 1.14)});""")
            cues.append(("hit", round(start + item.get("slam_at", 0.15), 2)))
        elif cid == "end":
            lines = "\n".join(f'  <div class="rowx mono" style="top: {560 + 70 * i}px"><div id="e{i}">{l}</div></div>' for i, l in enumerate(item["lines"]))
            comps[cid] = c(cid, f"""  .wm {{ position: absolute; left: 150px; top: 330px; font-size: 180px; font-weight: 800; letter-spacing: -0.055em; }}
  .dot {{ color: {acc}; }}
  .rowx {{ position: absolute; left: 150px; overflow: hidden; font-size: 40px; }}
""", f'  <div class="wm" id="ew">{item["word"]}<span class="dot">.</span></div>\n{lines}',
                '  tl.fromTo("#ew", { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.5, ease: EO }, 0.05);\n' +
                "\n".join(f'  tl.fromTo("#e{i}", {{ y: 60 }}, {{ y: 0, duration: 0.45, ease: EO }}, {0.35 + 0.2 * i:.2f});' for i in range(len(item["lines"]))))
            cues.append(("chime", round(start + 0.2, 2)))
        hosts.append(host(cid, start, dur))

    guard_clips(spec, clips)
    duck = []
    pip_html, pip_js = "", ""
    p = spec.get("presenter")
    if p:
        end = round(p["start"] + p["duration"], 2)
        duck = [(round(p["start"] + 0.3, 2), round(end - 0.24, 2), p.get("duck", 0.26))]
        pip_html = (f'    <div id="pip"><video id="v-pip" class="clip" src="{p["src"]}" playsinline data-has-audio="true" data-volume="1" data-start="{p["start"]}" data-duration="{p["duration"]}" data-track-index="5"></video></div>\n'
                    f'    <div id="pip-tag">{p["tag"]}</div>')
        pip_js = f"""    tl.fromTo("#pip", {{ opacity: 0, scale: 0.6, y: 40 }}, {{ opacity: 1, scale: 1, y: 0, duration: 0.6, ease: EO, transformOrigin: "100% 100%" }}, {p["start"]});
    tl.fromTo("#pip-tag", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.4, ease: EO }}, {round(p["start"] + 0.4, 2)});
    tl.to(["#pip", "#pip-tag"], {{ opacity: 0, scale: 0.85, duration: 0.35, ease: EI, transformOrigin: "100% 100%" }}, {round(end - 0.14, 2)});"""
    m = spec["music"]
    lane = music_lane(spec["duration"], fade_in=m.get("fade_in", 0), fade_out=m.get("fade_out", 1.6), duck=duck)
    head_css = f"""    .cam {{ position: absolute; left: 120px; top: 110px; width: 1180px; height: 920px; border-radius: 28px; overflow: hidden; opacity: 0; background: #fff;
      box-shadow: 0 30px 80px rgba(15,17,21,0.18), 0 2px 6px rgba(15,17,21,0.08); }}
    .inner {{ position: absolute; inset: 0; transform-origin: 50% 50%; }}
    .cam video {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
    #pip {{ position: absolute; right: 70px; bottom: 96px; width: 330px; height: 330px; border-radius: 30px; overflow: hidden; opacity: 0;
      box-shadow: 0 24px 70px rgba(15,17,21,0.25); border: 6px solid #fff; background: #fff; }}
    #pip video {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
    #pip-tag {{ position: absolute; right: 70px; bottom: 44px; width: 330px; text-align: center; font-family: "JetBrains Mono", monospace; font-size: 22px; color: {MUTED}; opacity: 0; }}
"""
    body = "\n".join(cam_html + hosts) + "\n" + pip_html + \
        f'\n    <audio id="music" src="{m["src"]}" data-start="0" data-duration="{spec["duration"]}" data-track-index="9" data-volume="{m.get("volume", 0.9)}" data-automation=\'{lane}\'></audio>\n' + \
        sfx_tags(project, sorted(cues, key=lambda q: q[1]), volumes={"whoosh": 0.35, "type": 0.35})
    return write_project(project, index_html(spec["duration"], BG, head_css, body, "\n".join(cam_js) + "\n" + pip_js), comps)
