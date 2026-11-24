# th-graphics

One command for the talking-head-graphics pipeline. It runs prep, build, cutouts and render in order, stops at the first failing stage, and records how long each stage took.

```bash
th-graphics IN-edited.mp4 PROJECT_DIR OUT.mp4 [--skill DIR] [--build FILE] [--pace F] [--end S] [--lufs L] [--force] [--dry-run]
```

- **Skill scripts** come from `--skill`, then `TH_SKILL_DIR`, then `$HOME/Documents/Personal/skills/talking-head-graphics/scripts`. Missing scripts stop the run (status 2).
- **Build file.** `PROJECT_DIR/build.py` (or `--build FILE`) is the per-video timeline: a copy of the skill's `build.py` with your beat times. On a new project the command runs prep, writes the timing file with `"failed_stage": "needs_build_file"`, and stops with the copy instruction (status 2). Run it again once the file is there.
- **Render options** `--pace`, `--end` and `--lufs` are passed to the render stage (see the skill's `render.sh`). A value may be a negative number (`--lufs -14`).
- **Prep is skipped** when `assets/base.mp4` exists. `--force` runs it again.
- **Output.** After setup succeeds, stdout is one JSON line (setup errors, status 2 before any stage, print only to stderr, except the missing-build case, which also prints the failure JSON): `{"pass", "failed_stage", "seconds": {stage: s}, "total_seconds"}`. `PROJECT_DIR/timing.json` holds the same JSON. Stage logs go to stderr. `total_seconds` is elapsed time on a monotonic clock. The render goes to a fresh temp file first, so a render that writes nothing fails even when an old output file exists. The output may not be a folder or the timing file.
- **Status** 0 ok, 1 a stage failed, 2 usage or setup.
- **Paths** are resolved with `realpath` (so `link/../x` follows the link target). A path with a newline is refused. A value after `--build` or `--skill` may not start with `-` (use `./-name`). `--` ends options.
- **`--dry-run`** prints the stages and runs or creates nothing, and prints no JSON.
- Every stage runs with stdin closed, because a tool that reads stdin inside a loop eats the next input.

Test: `./th-graphics.test.sh` (18 checks, stub skill scripts, no network).
