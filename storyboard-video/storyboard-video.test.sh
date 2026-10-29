#!/usr/bin/env bash
# Offline end-to-end test for storyboard-video. No network, no cloud project, no keys.
# Each case is a way the tool has failed, or could fail, on a real film.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
sv="$here/storyboard-video"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
expect_exit() { local want="$1"; shift; set +e; "$@" >"$tmp/out" 2>"$tmp/err"; local got=$?; set -e; [ "$got" = "$want" ] || fail "$* exited $got, want $want: $(cat "$tmp/err")"; }

# 1. Bad usage exits 2.
expect_exit 2 "$sv"
expect_exit 2 "$sv" nonsense "$tmp"

# 2. The schema rejects a bad board before any spend, and names the failing path.
mkdir -p "$tmp/bad"
python3 - "$here/examples/board.json" "$tmp/bad" <<'PY'
import json, os, sys
good = json.load(open(sys.argv[1]))
def write(name, mutate):
    b = json.loads(json.dumps(good)); mutate(b)
    os.makedirs(os.path.join(sys.argv[2], name), exist_ok=True)
    json.dump(b, open(os.path.join(sys.argv[2], name, "board.json"), "w"))
write("nocast", lambda b: b.pop("cast"))
write("dupe", lambda b: b["shots"].append(dict(b["shots"][0])))
write("typo", lambda b: b.update({"shotz": []}))
write("stage", lambda b: b["shots"][0].update({"stage": "MIDDLE"}))
write("nostill", lambda b: b["shots"][1]["prompts"].pop("still"))
PY
expect_exit 0 "$sv" check "$here/examples"
for c in nocast:cast dupe:duplicate typo:shotz stage:stage nostill:still; do
  expect_exit 1 "$sv" check "$tmp/bad/${c%%:*}"; grep -q "${c##*:}" "$tmp/err" || fail "${c%%:*}: message lacks '${c##*:}': $(cat "$tmp/err")"
done

# 3. Generation needs the project from the environment and never guesses one.
mkdir -p "$tmp/film"
python3 - "$here/examples/board.json" "$tmp/film/board.json" <<'PY'
import json, sys
b = json.load(open(sys.argv[1]))
b["shots"][0]["title"] = "<script>alert(1)</script>"
json.dump(b, open(sys.argv[2], "w"))
PY
expect_exit 1 env -u VERTEX_PROJECT "$sv" stills "$tmp/film"; grep -q VERTEX_PROJECT "$tmp/err" || fail "project message"

# 4. Veo bills at submit, so it refuses without --confirm-spend and prints an estimate first.
expect_exit 1 env VERTEX_PROJECT=dummy "$sv" veo "$tmp/film"
grep -q 'confirm-spend' "$tmp/err" || fail "veo spend gate"; grep -q 'USD' "$tmp/err" || fail "veo estimate"

# Synthetic stills, clips and voice-over so board and cut run offline.
mkdir -p "$tmp/film/img" "$tmp/film/vid" "$tmp/film/out/work"
ids=$(python3 -c "import json,sys;print(' '.join(str(s['id']) for s in json.load(open(sys.argv[1]))['shots']))" "$tmp/film/board.json")
for id in $ids; do
  n=$(printf %02d "$id")
  ffmpeg -loglevel error -f lavfi -i "testsrc2=size=1376x768:rate=1" -frames:v 1 "$tmp/film/img/shot-$n.png"
  ffmpeg -loglevel error -f lavfi -i "testsrc2=size=1280x720:rate=24" -f lavfi -i "sine=frequency=$((200 + id * 50)):sample_rate=48000" \
    -t 8 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$tmp/film/vid/shot-$n.mp4"
  ffmpeg -loglevel error -f lavfi -i "sine=frequency=600:sample_rate=24000" -t 1.5 "$tmp/film/out/work/vo-$n.wav"
done

# 5. The board renders every shot and escapes HTML in titles.
"$sv" board "$tmp/film" "$tmp/film/board.html" >/dev/null
for id in $ids; do grep -q "shot-$(printf %02d "$id")" "$tmp/film/board.html" || fail "board misses shot $id"; done
grep -q '<script>' "$tmp/film/board.html" && fail "board did not escape HTML"

# 6. The cut starts video and audio at 0 (a shifted first frame shows as black), hits the planned length,
#    and queues voice-over lines without overlap warnings.
"$sv" cut "$tmp/film" >"$tmp/out" 2>"$tmp/err" || fail "cut: $(tail -5 "$tmp/err")"
film="$tmp/film/out/film.mp4"
starts=$(ffprobe -v error -show_entries stream=start_time -of csv=p=0 "$film" | sort -u)
[ "$starts" = "0.000000" ] || fail "streams start at '$starts', want 0"
want=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['length_s'])" "$tmp/film/out/timeline.json")
got=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$film")
python3 -c "import sys;sys.exit(abs(float(sys.argv[1])-float(sys.argv[2]))>0.15)" "$got" "$want" || fail "length $got, planned $want"
grep -q 'past its slot' "$tmp/err" && fail "unexpected overlap warning"
# The narrator keys the duck; when the last line ends early the scene sound must still run to the end.
a_len=$(ffprobe -v error -select_streams a -show_entries stream=duration -of csv=p=0 "$film")
python3 -c "import sys;sys.exit(abs(float(sys.argv[1])-float(sys.argv[2]))>0.15)" "$a_len" "$want" || fail "audio is $a_len s, film is $want s"
# A board saved in another folder, for a project whose path has '#' and a space, still finds every still and clip.
mkdir -p "$tmp/else #where" && touch "$tmp/film/img/cast.png" && ln -s "$tmp/film" "$tmp/film #2"
"$sv" board "$tmp/film #2" "$tmp/else #where/b.html" >/dev/null
python3 - "$tmp/else #where" "$tmp/else #where/b.html" <<'PY' || fail "board media paths do not resolve from another folder"
import html, os, re, sys, urllib.parse
raw = re.findall(r'(?:src|poster)="([^"]+)"', open(sys.argv[2]).read())
srcs = [urllib.parse.unquote(html.unescape(s)) for s in raw]
missing = [s for s in srcs if not os.path.exists(os.path.join(sys.argv[1], s))]
sys.exit(1 if missing or len(srcs) < 7 or any("#" in s for s in raw) else 0)  # a raw '#' starts a URL fragment
PY

# 7. A voice-over line too long for its slot is reported, not silently overlapped.
ffmpeg -loglevel error -y -f lavfi -i "sine=frequency=600:sample_rate=24000" -t 9 "$tmp/film/out/work/vo-01.wav"
"$sv" cut "$tmp/film" >"$tmp/out" 2>"$tmp/err" || fail "cut with long line"
grep -q 'past its slot' "$tmp/err" || fail "missing overlap warning"

echo "storyboard-video: all tests passed"
