#!/usr/bin/env python3
"""E2E for ad-audio-qa: builds a good and a broken clip with ffmpeg (voice
-12 dB, sfx +150 ms late, 2 s dead gap in the broken one), runs the tool,
asserts good passes measured rules and broken fails planted ones, then
covers the failure-mode rows: nosfx, missing stems, no transcript, stem
level agreement across mono/stereo/22 kHz/time shifts, R8 grouping,
R14 onset precision, bad inputs and exit codes. Prints an evidence JSON line (exit code and rule statuses per run).
SKIPs without ffmpeg, a speech source, or AD_AUDIO_QA_EARSHOT.
"""
import atexit, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

TOOL = Path(__file__).with_name('ad-audio-qa')
DUR, FPS = 14.0, 30
CUTS = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
MID = [3.0, 5.0, 7.0, 9.0, 11.0, 13.0]
SLOTS = [0.2, 2.5, 4.5, 6.5, 8.5, 10.5, 12.5]
WORDS = ['one', 'two', 'three', 'four', 'five', 'six', 'seven']
GAP, LATE = (6.0, 8.0), 0.150
EARSHOT = os.environ.get('AD_AUDIO_QA_EARSHOT')
AUTO = ['R6_dead_audio', 'loudness', 'R14_sound_and_cuts', 'sfx_onset_80ms',
        'sfx_vs_voice', 'R7_speech_pace', 'R10_caption_sync']
SFX_RULES = ['R14_sound_and_cuts', 'sfx_onset_80ms', 'sfx_vs_voice']


def ff(*a, check=True):
    return subprocess.run(['ffmpeg', '-y', '-v', 'error', *a],
                          capture_output=True, text=True, check=check)


def dur(p):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                 'format=duration', '-of', 'csv=p=0', p],
                                capture_output=True, text=True).stdout)


def say_wav(text, out):
    """Render one word to 48 kHz mono wav; return leading silence offset."""
    if SPEECH == 'say':
        aiff = out + '.aiff'
        subprocess.run(['say', '-o', aiff, text + '.'], check=True,
                       capture_output=True)
        ff('-i', aiff, '-ar', '48000', '-ac', '1', out)
    elif SPEECH == 'flite':
        ff('-f', 'lavfi', '-i', f'flite=text={text}:voice=slt',
           '-ar', '48000', '-ac', '1', out)
    else:
        ff('-i', out, '-ar', '48000', '-ac', '1', out + '.t')
        subprocess.run([SPEECH, '-w', out + '.t', text], check=True,
                       capture_output=True)
        ff('-i', out + '.t', '-ar', '48000', '-ac', '1', out)
    r = subprocess.run(['ffmpeg', '-i', out, '-af',
                        'silencedetect=n=-45dB:d=0.05', '-f', 'null', '-'],
                       capture_output=True, text=True)
    m = re.search(r'silence_end: ([\d.]+)', r.stderr)
    return float(m.group(1)) if m else 0.0


def stem(items, out):
    """items = [(wav, start_s, volume_filter)] -> one DUR-second stem."""
    fc, labels, ins = '', [], []
    for i, (p, t, vol) in enumerate(items):
        fc += f'[{i}:a]adelay={int(t * 1000)}|{int(t * 1000)}{vol},apad=whole_dur={DUR}[a{i}];'
        labels.append(f'[a{i}]')
        ins += ['-i', p]
    fc += ''.join(labels) + f'amix=inputs={len(labels)}:normalize=0[m]'
    ff(*ins, '-filter_complex', fc, '-map', '[m]', '-t', str(DUR), out)
    return out


def peak_db(p):
    r = subprocess.run(['ffmpeg', '-i', p, '-af', 'astats=metadata=1',
                        '-f', 'null', '-'], capture_output=True, text=True)
    return float(re.search(r'Peak level dB: *(-?[\d.]+)', r.stderr).group(1))


def loudnorm(p):
    """Gain to -14 LUFS integrated, then true-peak-limit."""
    r = subprocess.run(['ffmpeg', '-i', p, '-af', 'ebur128=peak=true',
                        '-f', 'null', '-'], capture_output=True, text=True)
    lufs = float(re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)[-1])
    out = p + '.norm.wav'
    ff('-i', p, '-af', f'volume={-14.0 - lufs:.2f}dB,'
       'alimiter=limit=0.7:attack=1:release=50:level=false', out)
    return out


def build_video(path, tmp):
    colors = ['red', 'lime', 'blue', 'yellow', 'fuchsia', 'aqua', 'gray']
    for i, c in enumerate(colors):
        ff('-f', 'lavfi', '-i', f'color=c={c}:s=640x360:r={FPS}:d=2', '-t', '2',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', tmp / f'seg{i}.mp4')
    lst = tmp / 'segs.txt'
    lst.write_text(''.join(f"file '{tmp}/seg{i}.mp4'\n" for i in range(7)))
    ff('-f', 'concat', '-safe', '0', '-i', str(lst), '-c', 'copy', path)


def build_clip(kind, tmp, video, bed, hit):
    """Return (mp4, transcript, voice_stem, sfx_stem) for kind in
    {'good','broken'}."""
    vw, words = [], []
    for i, (w, t) in enumerate(zip(WORDS, SLOTS)):
        p = tmp / f'{kind}_w{i}.wav'
        off = say_wav(w, str(p))
        vw.append((str(p), t + off, f',volume={2.0 if kind == "good" else 2.0 * 10 ** (-12.0 / 20):.3f}'))
        words.append({'word': w, 'start': round(t + off, 3),
                      'end': round(t + off + dur(p) - 0.15, 3)})
    vstem = stem(vw, tmp / f'{kind}_voice.wav')
    # sfx peak ~18 dB under the good-clip voice peak; broken voice is -12 dB,
    # so the margin collapses under the 6 dB rule
    vpk = peak_db(vstem) + (12.0 if kind == 'broken' else 0.0)
    sfx_gain = 10 ** ((vpk - 18.0 - peak_db(hit)) / 20)
    late = LATE if kind == 'broken' else 0.0
    sstem = stem([(hit, c + late, f',volume={sfx_gain:.4f}') for c in CUTS],
                 tmp / f'{kind}_sfx.wav')
    mix = tmp / f'{kind}_mix.wav'
    filt = '[0:a][1:a][2:a]amix=inputs=3:normalize=0[m]'
    label = '[m]'
    if kind == 'broken':
        filt += f";[m]volume=0:enable='between(t,{GAP[0]},{GAP[1]})'[g]"
        label = '[g]'
    ff('-i', str(vstem), '-i', str(sstem), '-i', bed,
       '-filter_complex', filt, '-map', label, '-t', str(DUR), str(mix))
    vid = tmp / f'{kind}.mp4'
    ff('-i', video, '-i', loudnorm(str(mix)), '-c:v', 'copy',
       '-c:a', 'aac', '-shortest', str(vid))
    tr = tmp / f'{kind}_transcript.json'
    tr.write_text(json.dumps({'words': words}))
    return str(vid), str(tr), str(vstem), str(sstem)


def run(vid, tmp, name, extra=()):
    """Run the tool; return (exit, stdout, report-dict-or-None)."""
    out = tmp / f'{name}_qa.json'
    r = subprocess.run([str(TOOL), vid, '--earshot', EARSHOT,
                        '--out', str(out), *extra],
                       capture_output=True, text=True)
    rep = json.loads(out.read_text()) if out.exists() else None
    return r.returncode, r.stdout + r.stderr, rep


def status(rep, key):
    return ((rep or {}).get('rules') or {}).get(key, {})


def main():
    global SPEECH
    if not all(shutil.which(b) for b in ('ffmpeg', 'ffprobe')):
        print('SKIP ad-audio-qa e2e: no ffmpeg/ffprobe')
        return 0
    SPEECH = next((b for b in ('say', 'espeak', 'espeak-ng', 'flite')
                   if shutil.which(b)), None)
    if not SPEECH:
        print('SKIP ad-audio-qa e2e: no speech source (say/espeak/flite)')
        return 0
    if not EARSHOT:
        print('SKIP ad-audio-qa e2e: set AD_AUDIO_QA_EARSHOT')
        return 0
    tmp = Path(tempfile.mkdtemp(prefix='ad-audio-qa-e2e-'))
    atexit.register(shutil.rmtree, tmp, True)  # kept on failure or AD_AUDIO_QA_KEEP
    video = tmp / 'video.mp4'
    build_video(str(video), tmp)
    bed = tmp / 'bed.wav'
    ff('-f', 'lavfi', '-i', f'sine=frequency=100:duration={DUR}',
       '-af', 'volume=0.008', str(bed))
    hit = tmp / 'hit.wav'
    ff('-f', 'lavfi', '-i', 'sine=frequency=1568:duration=0.09', '-af',
       'afade=t=out:st=0.02:d=0.07,volume=0.4', str(hit))
    results = {}
    for kind in ('good', 'broken'):
        vid, tr, vstem, sstem = build_clip(kind, tmp, video, bed, hit)
        results[kind] = run(vid, tmp, kind,
                            ('--transcript', tr, '--sfx-stem', sstem,
                             '--voice-stem', vstem))
    extra = {}

    def add(name, *a):
        extra[name] = (a[0], a[1:])

    gvid = tmp / 'good.mp4'
    gtr = tmp / 'good_transcript.json'
    gv = tmp / 'good_voice.wav'
    gs = tmp / 'good_sfx.wav'
    # nosfx: silent sfx stem on the good video
    silent = tmp / 'silent.wav'
    ff('-f', 'lavfi', '-i', f'anullsrc=r=48000:cl=stereo:d={DUR}', silent)
    add('nosfx', str(gvid), '--transcript', str(gtr), '--sfx-stem',
        str(silent), '--voice-stem', str(gv))
    # no stems at all
    add('nostems', str(gvid), '--transcript', str(gtr))
    # no transcript
    add('notx', str(gvid), '--sfx-stem', str(gs), '--voice-stem', str(gv))
    # stem level agreement: mono / stereo / 22 kHz / +60 ms shift
    def variant_sfx(name, filt, src=gs):
        p = tmp / f'{name}.wav'
        ff('-i', src, '-af', filt, p)
        return str(p)
    stereo = variant_sfx('sfx_stereo', 'asplit[x][y];[x][y]amerge=inputs=2')
    v22050 = variant_sfx('sfx_22k', 'aresample=22050,aresample=48000')
    shifted = variant_sfx('sfx_sh60', 'adelay=60|60')
    vstereo = variant_sfx('voice_stereo', 'asplit[x][y];[x][y]amerge=inputs=2',
                          gv)
    # panned-to-one-side stems read the same as centred (louder channel)
    span = variant_sfx('sfx_pan', 'pan=stereo|c0=c0|c1=0*c0')
    vpan = variant_sfx('voice_pan', 'pan=stereo|c0=c0|c1=0*c0', gv)
    for nm, ss, vv in (('lvl_mono', gs, gv), ('lvl_stereo', stereo, vstereo),
                       ('lvl_22k', v22050, gv), ('lvl_sh60', shifted, gv),
                       ('lvl_pan', span, vpan)):
        add(nm, str(gvid), '--sfx-stem', ss, '--voice-stem', vv)
    # R14 precision: sfx on 3 of 6 cuts PASS; floating between cuts FAIL
    gain = ',volume=1.0'
    s3 = stem([(hit, c, gain) for c in CUTS[:3]], tmp / 'sfx_3cuts.wav')
    sfloat = stem([(hit, m, gain) for m in MID], tmp / 'sfx_float.wav')
    add('r14_3cuts', str(gvid), '--sfx-stem', s3)
    add('r14_float', str(gvid), '--sfx-stem', sfloat)
    # R14: riser with a linear ramp ending on each cut PASSes; the onset
    # syncs at its peak (the hit), not at the ramp start
    def riser(path, R):
        ff('-f', 'lavfi', '-i',
           f"aevalsrc='0.25*sin(6.2831853*220*t)*min(1\\,t/{R})'"
           f":s=48000:d={R + 0.15}",
           '-af', f'afade=t=out:st={R + 0.08}:d=0.07', str(path))
    for R, tag in ((0.30, 'riser300'), (0.10, 'riser100')):
        riser(tmp / f'{tag}.wav', R)
        p = stem([(str(tmp / f'{tag}.wav'), c - R, gain) for c in CUTS],
                 tmp / f'sfx_{tag}.wav')
        add(f'r14_{tag}', str(gvid), '--sfx-stem', p)
    # R14: a flat sustained hit and a soft hit followed 200 ms later by a
    # louder boom both sync at their attack and PASS
    for nm, amp, d in (('sustain', 0.3, 0.6), ('hit_small', 0.15, 0.15),
                       ('boom', 0.6, 0.15)):
        ff('-f', 'lavfi', '-i',
           f"aevalsrc='{amp}*sin(6.2831853*220*t)':s=48000:d={d}",
           str(tmp / f'{nm}.wav'))
    p = stem([(str(tmp / 'sustain.wav'), c, gain) for c in CUTS],
             tmp / 'sfx_sustain.wav')
    add('r14_sustain', str(gvid), '--sfx-stem', p)
    p = stem([(str(tmp / 'hit_small.wav'), c, gain) for c in CUTS] +
             [(str(tmp / 'boom.wav'), c + 0.2, gain) for c in CUTS],
             tmp / 'sfx_double.wav')
    add('r14_double', str(gvid), '--sfx-stem', p)
    # R14: a soft pre-hit 200 ms BEFORE a boom on the cut is one cue (true
    # merge keeps the boom); a swell that starts on the cut and peaks 500 ms
    # later syncs at its start
    ff('-f', 'lavfi', '-i', "aevalsrc='0.6*sin(6.2831853*110*t)*min(1\\,t/0.5)':s=48000:d=0.5",
       str(tmp / 'swell.wav'))
    p = stem([(str(tmp / 'hit_small.wav'), c - 0.2, gain) for c in CUTS] +
             [(str(tmp / 'boom.wav'), c, gain) for c in CUTS],
             tmp / 'sfx_prehit.wav')
    add('r14_prehit', str(gvid), '--sfx-stem', p)
    p = stem([(str(tmp / 'swell.wav'), c, gain) for c in CUTS],
             tmp / 'sfx_swell.wav')
    add('r14_swell', str(gvid), '--sfx-stem', p)
    # R14: a steady bed of ticks (a sound every 0.2 s) must not chain into one
    # cue that always counts: it FAILs, because most ticks are off the cuts
    ff('-f', 'lavfi', '-i', "aevalsrc='0.4*sin(6.2831853*1000*t)':s=48000:d=0.03",
       str(tmp / 'tick.wav'))
    p = stem([(str(tmp / 'tick.wav'), 0.2 * k, gain) for k in range(70)],
             tmp / 'sfx_tickbed.wav')
    add('r14_tickbed', str(gvid), '--sfx-stem', p)
    # --cuts overrides scene detection: right times PASS, shifted FAIL
    add('cuts_override', str(gvid), '--sfx-stem', str(gs), '--cuts',
        ','.join(str(c) for c in CUTS))
    add('cuts_wrong', str(gvid), '--sfx-stem', str(gs), '--cuts',
        ','.join(str(c + 0.5) for c in CUTS))
    # unreadable sfx stem prints its error in the table, not null
    fake_stem = tmp / 'fake_sfx.wav'
    fake_stem.write_text('this is not audio')
    add('fakestem', str(gvid), '--sfx-stem', str(fake_stem))
    # R8: single-line-per-character -> NOT CHECKED; pitch spread -> OWNER CHECK
    wsrc = sorted(tmp.glob('good_w*.wav'))
    ldir = tmp / 'lines'
    ldir.mkdir()
    for i, nm in enumerate(('ann_l1', 'bob_l1', 'cat_l1')):
        shutil.copy(wsrc[i], ldir / f'{nm}.wav')
    ldir2 = tmp / 'lines2'
    ldir2.mkdir()
    shutil.copy(wsrc[0], ldir2 / 'ann_l1.wav')
    chip = tmp / 'chip.wav'
    ff('-i', str(wsrc[1]), '-af', 'asetrate=24000,aresample=48000', chip)
    shutil.copy(chip, ldir2 / 'ann_l2.wav')
    add('r8_single', str(gvid), '--lines', str(ldir))
    add('r8_spread', str(gvid), '--lines', str(ldir2))
    # R8: two voices on one character, F0 ratio ~1.4 -> OWNER CHECK band
    ldir3 = tmp / 'lines3'
    ldir3.mkdir()
    shutil.copy(wsrc[0], ldir3 / 'ann_l1.wav')
    chip14 = tmp / 'chip14.wav'
    ff('-i', str(wsrc[1]), '-af', 'asetrate=33600,aresample=48000', chip14)
    shutil.copy(chip14, ldir3 / 'ann_l2.wav')
    add('r8_swap', str(gvid), '--lines', str(ldir3))
    # bad voice-map prints its error in the table
    badvm = tmp / 'badvm.json'
    badvm.write_text('{not json')
    add('badvm', str(gvid), '--lines', str(ldir2), '--voice-map',
        str(badvm))
    # bad transcript prints its reason in the table
    badtx = tmp / 'badtx.json'
    badtx.write_text('{oops')
    add('badtx', str(gvid), '--transcript', str(badtx))
    # undecodable video: a text file named .mp4
    fake = tmp / 'fake.mp4'
    fake.write_text('this is not a video')
    add('fakevid', str(fake))
    # missing video exits 2
    add('missingvid', str(tmp / 'nope.mp4'))
    # --require-stems exit 3 when every sfx rule is NOT CHECKED
    add('reqstems', str(gvid), '--transcript', str(gtr),
        '--require-stems')
    # R7 FAIL branch: transcript squeezed to ~10% of real time -> high WPS
    fast = tmp / 'fasttx.json'
    words = json.loads(gtr.read_text())['words']
    t0 = words[0]['start']
    fast.write_text(json.dumps({'words': [
        {'word': w['word'], 'start': round(t0 + (w['start'] - t0) * 0.1, 3),
         'end': round(t0 + (w['end'] - t0) * 0.1, 3)} for w in words]}))
    add('fasttx', str(gvid), '--transcript', str(fast))
    # stem much longer than the video -> WARN about the t=0 assumption
    longstem = tmp / 'long_sfx.wav'
    ff('-i', str(gs), '-af', 'apad=whole_dur=18', longstem)
    add('longstem', str(gvid), '--sfx-stem', str(longstem))

    for name, (vid, args) in extra.items():
        results[name] = run(vid, tmp, name, args)

    allres = results
    print('evidence:', json.dumps({k: {'exit': c, 'rules': {r: v.get('status') for r, v in (rp or {}).get('rules', {}).items()}} for k, (c, o, rp) in allres.items()}))
    for k, (code, out, rep) in allres.items():
        print(f'--- {k} (exit {code}) ---')
        print(out)
    ok = True

    def chk(name, cond):
        nonlocal ok
        ok = ok and cond
        print(('ok  - ' if cond else 'FAIL- ') + name)

    grules = (results['good'][2] or {}).get('rules', {})
    brules = (results['broken'][2] or {}).get('rules', {})
    for k in AUTO:
        chk(f'good {k} not FAIL (got {grules.get(k, {}).get("status")})',
            grules.get(k, {}).get('status') != 'FAIL')
    for k in ('R6_dead_audio', 'R14_sound_and_cuts', 'sfx_onset_80ms',
              'sfx_vs_voice'):
        chk(f'broken {k} FAIL (got {brules.get(k, {}).get("status")})',
            brules.get(k, {}).get('status') == 'FAIL')
    chk('good exit 0', results['good'][0] == 0)
    chk('broken exit 1', results['broken'][0] == 1)
    chk('evidence has measured values',
        isinstance(grules.get('loudness', {}).get('value'), dict))

    def rep(n):
        return results[n][2] or {}

    def st(n, k):
        return (rep(n).get('rules') or {}).get(k, {}).get('status')

    # failure-mode rows
    chk('nosfx R14 FAIL "Sound is required"',
        st('nosfx', 'R14_sound_and_cuts') == 'FAIL' and
        'Sound is required' in str(rep('nosfx').get('rules', {})
                                   .get('R14_sound_and_cuts', {})
                                   .get('detail', '')))
    chk('nostems all sfx rules NOT CHECKED',
        all(st('nostems', k) == 'NOT CHECKED' for k in SFX_RULES))
    chk('notx R7 NOT CHECKED', st('notx', 'R7_speech_pace') == 'NOT CHECKED')
    chk('reqstems exit 3', results['reqstems'][0] == 3)
    chk('reqstems without flag exit != 3',
        results['nostems'][0] != 3)
    margins = {n: (rep(n).get('rules') or {}).get('sfx_vs_voice', {})
               .get('value') for n in
               ('lvl_mono', 'lvl_stereo', 'lvl_22k', 'lvl_sh60', 'lvl_pan')}
    vals = [margins[n] for n in margins if isinstance(margins[n], (int, float))]
    chk(f'stem level agreement within 0.5 dB (margins {margins})',
        len(vals) == len(margins) and max(vals) - min(vals) <= 0.5)
    chk('r14_3cuts PASS (sfx on 3 of 6 cuts)',
        st('r14_3cuts', 'R14_sound_and_cuts') == 'PASS')
    chk('r14_float FAIL (sfx between cuts)',
        st('r14_float', 'R14_sound_and_cuts') == 'FAIL')
    chk('r14_riser300 PASS (ramp ends on cut)',
        st('r14_riser300', 'R14_sound_and_cuts') == 'PASS')
    chk('r14_riser100 PASS (ramp ends on cut)',
        st('r14_riser100', 'R14_sound_and_cuts') == 'PASS')
    chk('r14_sustain PASS (flat hit syncs at its attack)',
        st('r14_sustain', 'R14_sound_and_cuts') == 'PASS')
    chk('r14_double PASS (hit then louder boom is one cue)',
        st('r14_double', 'R14_sound_and_cuts') == 'PASS')
    chk('r14_prehit PASS (soft pre-hit then boom on the cut)',
        st('r14_prehit', 'R14_sound_and_cuts') == 'PASS')
    chk('r14_swell PASS (swell starts on the cut)',
        st('r14_swell', 'R14_sound_and_cuts') == 'PASS')
    chk('r14_tickbed FAIL (a tick bed is not one cue)',
        st('r14_tickbed', 'R14_sound_and_cuts') == 'FAIL')
    chk('cuts_override PASS and detail lists cuts',
        st('cuts_override', 'R14_sound_and_cuts') == 'PASS' and
        'cuts at' in str(rep('cuts_override').get('rules', {})
                         .get('R14_sound_and_cuts', {}).get('detail', '')))
    chk('cuts_wrong FAIL (shifted --cuts)',
        st('cuts_wrong', 'R14_sound_and_cuts') == 'FAIL')
    chk('fakestem error in table, not null',
        st('fakestem', 'R14_sound_and_cuts') == 'NOT CHECKED' and
        bool((rep('fakestem').get('rules') or {})
             .get('R14_sound_and_cuts', {}).get('value')))
    chk('r8_single NOT CHECKED (no 2+ line character)',
        st('r8_single', 'R8_voice_consistency') == 'NOT CHECKED')
    chk('r8_spread OWNER CHECK, never FAIL (pitch is a weak proxy)',
        st('r8_spread', 'R8_voice_consistency') == 'OWNER CHECK')
    chk('r8_swap OWNER CHECK (spread over 1.25)',
        st('r8_swap', 'R8_voice_consistency') == 'OWNER CHECK' and
        'listen to these lines' in str(rep('r8_swap').get('rules', {})
                                     .get('R8_voice_consistency', {})
                                     .get('detail', '')) and
        'ratio' in str(rep('r8_swap').get('rules', {})
                       .get('R8_voice_consistency', {}).get('value', '')))
    chk('badvm error in table',
        st('badvm', 'voice_map_input') == 'NOT CHECKED' and
        st('badvm', 'R8_voice_consistency') == 'NOT CHECKED' and
        'bad voice-map JSON' in results['badvm'][1])
    chk('badtx error in table',
        st('badtx', 'transcript_input') == 'NOT CHECKED' and
        'bad transcript JSON' in results['badtx'][1])
    chk('fakevid exit 2 with real error',
        results['fakevid'][0] == 2 and
        'cannot decode' in results['fakevid'][1])
    chk('missingvid exit 2', results['missingvid'][0] == 2)
    chk('fasttx R7 FAIL (WPS over limit)',
        st('fasttx', 'R7_speech_pace') == 'FAIL')
    chk('longstem WARN on length mismatch',
        'WARN' in results['longstem'][1] and 't=0' in results['longstem'][1])
    chk('good R8 NOT CHECKED without --lines',
        grules.get('R8_voice_consistency', {}).get('status') == 'NOT CHECKED')
    chk('broken R10 FAIL (caption sync)',
        brules.get('R10_caption_sync', {}).get('status') == 'FAIL')
    chk('badtx R10 NOT CHECKED (no usable transcript)',
        st('badtx', 'R10_caption_sync') == 'NOT CHECKED')
    chk('owner rows always OWNER CHECK',
        all(grules.get(k, {}).get('status') == 'OWNER CHECK' for k in
            ('R8_voice_face_fit', 'R11_mouth_vs_voice', 'owner_judgment')))
    if not ok or os.environ.get('AD_AUDIO_QA_KEEP'):
        atexit.unregister(shutil.rmtree)
        print('kept scratch folder:', tmp)
    print(f'{"PASS" if ok else "FAIL"}: ad-audio-qa e2e')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
