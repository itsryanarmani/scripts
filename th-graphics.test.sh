#!/usr/bin/env bash
# E2E for th-graphics with stub skill scripts. Proves order, stop on failure, timing file, dry run and closed stdin.
# Writes a JSON verdict to $1 or stdout.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
res="$tmp/res"; : > "$res"; ok() { printf '%s\t%s\n' "$1" "$([ "$2" = 0 ] && echo true || echo false)" >> "$res"; }
S="$tmp/skill"; mkdir "$S"; export LOG="$tmp/log"
cat > "$S/prep.sh" <<'X'
#!/usr/bin/env bash
echo prep >> "$LOG"; echo noise-on-stdout; wc -c < /dev/stdin | tr -d ' ' >> "$LOG.stdin"; mkdir -p "$2/assets"; : > "$2/assets/base.mp4"; [ "${STUB_FAIL:-}" = prep ] && exit 1; exit 0
X
cat > "$S/build.py" <<'X'
import sys, os; open(os.environ["LOG"], "a").write("build\n"); open(os.environ["LOG"] + ".stdin", "a").write(str(len(sys.stdin.read())) + "\n")
X
cat > "$S/cutouts.sh" <<'X'
#!/usr/bin/env bash
echo cutouts >> "$LOG"; wc -c < /dev/stdin | tr -d ' ' >> "$LOG.stdin"; [ "${STUB_FAIL:-}" = cutouts ] && exit 1; exit 0
X
cat > "$S/render.sh" <<'X'
#!/usr/bin/env bash
echo render "${@:3}" >> "$LOG"; wc -c < /dev/stdin | tr -d ' ' >> "$LOG.stdin"; [ -n "${STUB_NO_OUT:-}" ] || echo video > "$2"; exit 0
X
chmod +x "$S"/*.sh; echo x > "$tmp/in.mp4"
run() { : > "$LOG"; : > "$LOG.stdin"; echo data | TH_SKILL_DIR="$S" "$here/th-graphics" "$@" >"$tmp/o" 2>"$tmp/e"; echo $?; }   # real stdin on purpose: the stages must still get EOF
order() { tr '\n' ' ' < "$LOG"; }

# 1 a prepared project runs build, cutouts, render in order and writes the timing file
mkdir -p "$tmp/p1/assets"; : > "$tmp/p1/assets/base.mp4"; cp "$S/build.py" "$tmp/p1/build.py"
rc=$(run "$tmp/in.mp4" "$tmp/p1" "$tmp/o1.mp4")
python3 - "$tmp/p1/timing.json" > "$tmp/t" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); print("ok" if d["pass"] is True and list(d["seconds"]) == ["build", "cutouts", "render"] and d["total_seconds"] >= 0 else "bad")
PY
[ "$rc" = 0 ] && [ "$(order)" = "build cutouts render " ] && [ "$(cat "$tmp/t")" = ok ] && [ -f "$tmp/o1.mp4" ]; ok runs_in_order_and_writes_timing $?
# 2 --force adds prep first
rc=$(run "$tmp/in.mp4" "$tmp/p1" "$tmp/o1.mp4" --force); [ "$rc" = 0 ] && [ "$(order)" = "prep build cutouts render " ]; ok force_runs_prep $?
# 3 stdin is closed for every stage (prep, build, cutouts, render), so a tool in a loop cannot eat input
mkdir -p "$tmp/p4"; rc=$(run "$tmp/in.mp4" "$tmp/p4" "$tmp/o7.mp4" --build "$tmp/p1/build.py")
[ "$rc" = 0 ] && [ "$(sort -u "$LOG.stdin" | tr -d '\n')" = 0 ] && [ "$(wc -l < "$LOG.stdin" | tr -d ' ')" = 4 ]; ok stages_get_closed_stdin $?
# 3b stdout is exactly one JSON line even when a stage prints to stdout
python3 -c "import json,sys; l=open(sys.argv[1]).read().strip().split('\n'); assert len(l)==1; json.loads(l[0])" "$tmp/o" 2>/dev/null; ok stdout_is_one_json_line $?
# 4 CONTROL: a failing stage stops the run, names the stage, and render never runs
rc=$(STUB_FAIL=cutouts run "$tmp/in.mp4" "$tmp/p1" "$tmp/o2.mp4")
python3 - "$tmp/p1/timing.json" > "$tmp/t" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); print("ok" if d["pass"] is False and d["failed_stage"] == "cutouts" else "bad")
PY
[ "$rc" = 1 ] && [ "$(order)" = "build cutouts " ] && [ "$(cat "$tmp/t")" = ok ] && [ ! -e "$tmp/o2.mp4" ]; ok control_failure_stops_and_names_stage $?
# 5 a dry run runs nothing
rc=$(run "$tmp/in.mp4" "$tmp/p1" "$tmp/o3.mp4" --dry-run); [ "$rc" = 0 ] && [ ! -s "$LOG" ] && grep -q 'would run render' "$tmp/o"; ok dry_run_runs_nothing $?
# 6 a prepared project with no build file is refused (2)
mkdir -p "$tmp/p2/assets"; : > "$tmp/p2/assets/base.mp4"; rc=$(run "$tmp/in.mp4" "$tmp/p2" "$tmp/o4.mp4"); python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d['pass'] is False and d['failed_stage']=='needs_build_file'" "$tmp/p2/timing.json" 2>/dev/null; jj=$?
[ "$rc" = 2 ] && [ ! -s "$LOG" ] && [ $jj = 0 ]; ok control_missing_build_file_refused $?
# 7 a fresh project runs prep once, then stops with instructions (2), and keeps its timing
rc=$(run "$tmp/in.mp4" "$tmp/p3" "$tmp/o5.mp4"); python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d['pass'] is False and 'prep' in d['seconds']" "$tmp/p3/timing.json" 2>/dev/null; pj=$?; [ "$rc" = 2 ] && [ "$(order)" = "prep " ] && grep -q 'Copy' "$tmp/e" && [ $pj = 0 ]; ok fresh_project_stops_after_prep $?
# 7b dry run creates nothing, not even a parent folder
rc=$(run "$tmp/in.mp4" "$tmp/new/parent/p" "$tmp/o8.mp4" --dry-run); [ "$rc" = 0 ] && [ ! -e "$tmp/new" ]; ok dry_run_creates_nothing $?
# 7c a render that writes no file is a failed render
rc=$(STUB_NO_OUT=1 run "$tmp/in.mp4" "$tmp/p1" "$tmp/o9.mp4"); python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d['failed_stage']=='render'" "$tmp/p1/timing.json" 2>/dev/null; jj=$?
[ "$rc" = 1 ] && [ $jj = 0 ]; ok control_missing_output_fails_render $?
# 7d a build file named like a python option: refused as an option value (2), and run as a file when given as ./-V (1, build failed)
cd "$tmp" && printf 'raise SystemExit(7)\n' > ./-V; rc1=$(run "$tmp/in.mp4" "$tmp/p1" "$tmp/o10.mp4" --build -V 2>/dev/null); rc2=$(run "$tmp/in.mp4" "$tmp/p1" "$tmp/o10.mp4" --build ./-V 2>/dev/null); cd "$here"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d['failed_stage']=='build'" "$tmp/p1/timing.json" 2>/dev/null; jj=$?
[ "$rc1" = 2 ] && [ "$rc2" = 1 ] && [ $jj = 0 ]; ok control_dash_build_file_handled $?
# 7e a path with a newline is refused
rc=$(run "$tmp/in.mp4" "$tmp/bad"$'\n'"dir" "$tmp/o11.mp4"); [ "$rc" = 2 ] && grep -q "newline" "$tmp/e" && [ ! -s "$LOG" ]; ok control_newline_path_refused $?
# 7f a render that writes nothing cannot pass for an old output file: the old file stays and the run fails
echo old > "$tmp/keep.mp4"; rc=$(STUB_NO_OUT=1 run "$tmp/in.mp4" "$tmp/p1" "$tmp/keep.mp4"); [ "$rc" = 1 ] && [ "$(cat "$tmp/keep.mp4")" = old ]; ok control_old_output_not_a_pass $?
# 7g the output may not be a folder or the timing file
mkdir -p "$tmp/adir"; rc1=$(run "$tmp/in.mp4" "$tmp/p1" "$tmp/adir"); rc2=$(run "$tmp/in.mp4" "$tmp/p1" "$tmp/p1/timing.json"); [ "$rc1" = 2 ] && [ "$rc2" = 2 ]; ok control_output_alias_refused $?
# 7h link/../file means the parent of the link target (filesystem meaning), not the parent of the link
mkdir -p "$tmp/real/nested"; ln -s "$tmp/real/nested" "$tmp/link"; echo x > "$tmp/real/sym.mp4"; rc=$(run "$tmp/link/../sym.mp4" "$tmp/p1" "$tmp/o12.mp4"); [ "$rc" = 0 ]; ok symlink_dotdot_resolves_like_the_filesystem $?
# 7i render options are forwarded to the render stage as given (a negative number is a value, not an option)
rc=$(run "$tmp/in.mp4" "$tmp/p1" "$tmp/o13.mp4" --pace 1.05 --end 98.9 --lufs -14); [ "$rc" = 0 ] && grep -q 'render --pace 1.05 --end 98.9 --lufs -14' "$LOG"; ok render_options_forwarded $?
rc=$(run "$tmp/in.mp4" "$tmp/p1" "$tmp/o14.mp4" --pace); [ "$rc" = 2 ] && [ ! -s "$LOG" ]; ok control_option_value_required $?
# 8 a missing skill script is refused (2)
rm "$S/render.sh"; rc=$(run "$tmp/in.mp4" "$tmp/p1" "$tmp/o6.mp4"); [ "$rc" = 2 ] && [ ! -s "$LOG" ]; ok control_missing_skill_script_refused $?

python3 - "$res" "${1:-}" <<'PY'
import json, sys
c = {a: b == "true" for a, b in (l.rstrip("\n").split("\t") for l in open(sys.argv[1]))}
v = {"checks": c, "pass": all(c.values()) and len(c) == 18}
s = json.dumps(v, indent=2); print(s)
if sys.argv[2]: open(sys.argv[2], "w").write(s + "\n")
sys.exit(0 if v["pass"] else 1)
PY
