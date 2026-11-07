#!/usr/bin/env python3
"""Drive the generated pre-push hook, not the installer that writes it.

The hook is the thing that runs on every push, and it embeds its own copy of the
branch rule. That copy drifted from pr-standards.mjs once already: it accepted
cr-0-x and cr-007-x, imposed no slug length, and exempted master, which the
canonical validator does not. These cases pin the two together.
"""
import pathlib
import re, subprocess, os, tempfile, json, sys
HERE = pathlib.Path(__file__).parent
# The installer writes the PreToolUse guard under $HOME/.local/share. Pin HOME
# to a throwaway directory so this suite cannot touch the real one, ~/.claude*,
# or any real settings file.
os.environ["HOME"] = tempfile.mkdtemp()
src = (HERE / "install-pr-hooks").read_text()
k = "read -r -d '' HOOK_BODY <<'HOOK' || true\n"
body = src[src.index(k)+len(k):]
body = body[:body.index("\nHOOK\n")]
d = tempfile.mkdtemp(); os.makedirs(f"{d}/.github", exist_ok=True)
hook = f"{d}/pre-push"; pathlib.Path(hook).write_text(body + "\n"); os.chmod(hook, 0o755)
def push(branch, cfg):
    pathlib.Path(f"{d}/.github/pr-standards.json").write_text(json.dumps(cfg))
    line = f"refs/heads/{branch} abc refs/heads/{branch} 000\n"
    return subprocess.run(["bash", hook], cwd=d, input=line, capture_output=True, text=True).returncode
base = {"prefix": "cr"}
cases = [
    ("cr-142-fix-onboarding", base, 0, "valid branch"),
    ("cr-0-fix-it", base, 1, "issue zero"),
    ("cr-007-fix-it", base, 1, "leading zeros"),
    ("cr-1-ab", base, 1, "slug too short"),
    ("cr-1-"+"a"*49, base, 1, "slug too long"),
    ("cr-1-"+"a"*48, base, 0, "slug at the limit"),
    ("master", base, 1, "master no longer exempt"),
    ("main", base, 0, "main exempt"),
    ("release/1.2", base, 0, "release/* exempt"),
    ("chore/bump", base, 1, "chore refused by default"),
    ("chore/bump", {**base,"allowChoreEscape":True}, 0, "chore allowed when configured"),
    ("legacy", {**base,"exemptBranches":["legacy"]}, 0, "configured exemption honoured"),
    ("cr-1-ok-slug", {**base,"allowChoreEscape":"true"}, 1, "string bool fails closed"),
    ("cr-1-ok-slug", {**base,"exemptBranches":"legacy"}, 1, "string list fails closed"),
    ("cr-1-ok-slug", {**base,"exemptBranches":["legacy\nmaster"]}, 1, "embedded newline in exemption fails closed"),
]
bad = 0
for branch, cfg, want, label in cases:
    got = push(branch, cfg)
    okk = (got != 0) == (want != 0)
    bad += 0 if okk else 1
    print(f"  {'OK ' if okk else 'FAIL'} {label:<32} exit={got} want={'reject' if want else 'accept'}")
print("ALL PASS" if bad == 0 else f"{bad} MISMATCH")
ALL_OK = bad == 0


def test_symlinked_hook_dir_is_refused():
    """A .git/hooks that is a symlink must not be followed.

    stow and chezmoi both symlink it. Following it writes the hook into a
    directory shared with other checkouts, including work ones. The containment
    check used to run only when core.hooksPath was set, so this path was open.
    """
    import shutil, subprocess as sp
    d = tempfile.mkdtemp()
    repo = f"{d}/repo"
    os.makedirs(f"{repo}/.github"); os.makedirs(f"{d}/shared-hooks")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null"}
    sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
    sp.run(["git", "-C", repo, "remote", "add", "origin",
            "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
    pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
    shutil.rmtree(f"{repo}/.git/hooks")
    os.symlink(f"{d}/shared-hooks", f"{repo}/.git/hooks")
    out = sp.run([str(HERE / "install-pr-hooks"), "--root", d],
                 capture_output=True, text=True, env=env).stdout
    shutil.rmtree(d, ignore_errors=True)
    ok = "SKIP" in out and "resolves outside the repo" in out
    print(f"  {'OK ' if ok else 'FAIL'} symlinked .git/hooks refused")
    return ok


def test_dangling_pre_push_symlink_is_refused():
    """A dangling pre-push symlink must not be silently replaced.

    -e follows symlinks, so one whose target is missing reads as absent and
    --apply would treat "no hook installed" as license to overwrite it,
    destroying a symlink someone else's tooling put there.
    """
    import shutil, subprocess as sp
    d = tempfile.mkdtemp()
    repo = f"{d}/repo"
    os.makedirs(f"{repo}/.github")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null"}
    sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
    sp.run(["git", "-C", repo, "remote", "add", "origin",
            "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
    pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
    os.symlink(f"{d}/nonexistent-target", f"{repo}/.git/hooks/pre-push")
    out = sp.run([str(HERE / "install-pr-hooks"), "--apply", "--root", d],
                 capture_output=True, text=True, env=env).stdout
    still_symlink = os.path.islink(f"{repo}/.git/hooks/pre-push")
    shutil.rmtree(d, ignore_errors=True)
    ok = "SKIP" in out and still_symlink
    print(f"  {'OK ' if ok else 'FAIL'} dangling pre-push symlink refused")
    return ok


def test_symlinked_pre_push_is_refused_not_chmod_through():
    """A pre-push symlink must not be chmod'd through to its target.

    -f follows a symlink, so one pointing at an external file that happens to
    carry the exact version sentinel (e.g. a hook installed elsewhere by this
    same tool) would be read as "ours, but not executable" and chmod +x'd.
    chmod always follows a symlink to its target, so that would flip the
    execute bit on a file that can live anywhere on disk, outside this repo.
    """
    import shutil, subprocess as sp
    d = tempfile.mkdtemp()
    repo = f"{d}/repo"
    os.makedirs(f"{repo}/.github")
    target = f"{d}/external-hook"
    pathlib.Path(target).write_text(
        "#!/bin/bash\n"
        "# Installed by itsryanarmani/scripts install-pr-hooks. Do not edit here; edit there.\n"
        "# install-pr-hooks v4\n"
    )
    os.chmod(target, 0o644)
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null"}
    sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
    sp.run(["git", "-C", repo, "remote", "add", "origin",
            "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
    pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
    os.symlink(target, f"{repo}/.git/hooks/pre-push")
    out = sp.run([str(HERE / "install-pr-hooks"), "--apply", "--root", d],
                 capture_output=True, text=True, env=env).stdout
    target_untouched = (os.stat(target).st_mode & 0o111) == 0
    shutil.rmtree(d, ignore_errors=True)
    ok = "SKIP" in out and target_untouched
    print(f"  {'OK ' if ok else 'FAIL'} symlinked pre-push refused, not chmod'd through")
    return ok


def test_symlinked_root_is_scanned():
    """A --root that is itself a symlink to a directory must still be scanned.

    find runs without -L, so a symlink given as the search root is treated as
    a leaf and never descended into -- unless the root is resolved to its
    physical path first. Otherwise every repo under a symlinked --root (e.g.
    a stow/chezmoi-managed ~/Documents/Personal) goes silently unscanned
    while the run still reports success.
    """
    import shutil, subprocess as sp
    d = tempfile.mkdtemp()
    real = f"{d}/real"
    repo = f"{real}/repo"
    os.makedirs(f"{repo}/.github")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null"}
    sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
    sp.run(["git", "-C", repo, "remote", "add", "origin",
            "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
    pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
    os.symlink(real, f"{d}/linked-root")
    out = sp.run([str(HERE / "install-pr-hooks"), "--root", f"{d}/linked-root"],
                 capture_output=True, text=True, env=env).stdout
    shutil.rmtree(d, ignore_errors=True)
    ok = "INSTALL" in out and repo in out
    print(f"  {'OK ' if ok else 'FAIL'} symlinked --root is scanned")
    return ok


def test_deeply_nested_repo_is_scanned():
    """A repo nested deeper than the old fixed find depth must still be scanned.

    A prior version capped the scan with -maxdepth 4, so a repo any deeper
    than that went silently unscanned while the run still reported success.
    """
    import shutil, subprocess as sp
    d = tempfile.mkdtemp()
    repo = f"{d}/a/b/c/d/e/repo"
    os.makedirs(f"{repo}/.github")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null"}
    sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
    sp.run(["git", "-C", repo, "remote", "add", "origin",
            "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
    pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
    out = sp.run([str(HERE / "install-pr-hooks"), "--root", d],
                 capture_output=True, text=True, env=env).stdout
    shutil.rmtree(d, ignore_errors=True)
    ok = "INSTALL" in out and repo in out
    print(f"  {'OK ' if ok else 'FAIL'} deeply nested repo is scanned")
    return ok


if not test_symlinked_hook_dir_is_refused():
    sys.exit(1)

if not test_dangling_pre_push_symlink_is_refused():
    sys.exit(1)

if not test_symlinked_pre_push_is_refused_not_chmod_through():
    sys.exit(1)

if not test_symlinked_root_is_scanned():
    sys.exit(1)

if not test_deeply_nested_repo_is_scanned():
    sys.exit(1)


def test_eligibility_checks_the_push_url_too():
    """A repo that pushes somewhere else is not eligible, whatever it fetches from.

    This hook runs on push. remote.origin.pushurl can differ from the fetch URL,
    so checking only the fetch URL would install into a repo that pushes to a
    work remote -- the one thing this tool must never do. A remote can also carry
    more than one push URL, and git pushes to all of them, so every one of them
    has to be checked, not just the first.
    """
    import shutil, subprocess as sp
    results = []
    for label, pushurl, want in [
        ("no pushurl", None, True),
        ("personal pushurl", "git@github.com:itsryanarmani/other.git", True),
        ("work pushurl", "git@github.com:some-employer/thing.git", False),
        ("explicit-port ssh", "ssh://git@github.com:22/itsryanarmani/other.git", True),
        ("second pushurl is work", [
            "git@github.com:itsryanarmani/other.git",
            "git@github.com:some-employer/thing.git",
        ], False),
    ]:
        d = tempfile.mkdtemp(); repo = f"{d}/repo"
        os.makedirs(f"{repo}/.github")
        env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null"}
        sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
        sp.run(["git", "-C", repo, "remote", "add", "origin",
                "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
        if pushurl:
            urls = pushurl if isinstance(pushurl, list) else [pushurl]
            sp.run(["git", "-C", repo, "remote", "set-url", "--push", "origin", urls[0]],
                   check=True, env=env)
            for extra in urls[1:]:
                sp.run(["git", "-C", repo, "remote", "set-url", "--push", "--add", "origin", extra],
                       check=True, env=env)
        pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
        out = sp.run([str(HERE / "install-pr-hooks"), "--root", d],
                     capture_output=True, text=True, env=env).stdout
        eligible = "INSTALL" in out
        shutil.rmtree(d, ignore_errors=True)
        ok = eligible == want
        results.append(ok)
        print(f"  {'OK ' if ok else 'FAIL'} {label:<20} eligible={eligible} want={want}")
    return all(results)


if not test_eligibility_checks_the_push_url_too():
    ALL_OK = False



def test_global_hooks_path_shapes():
    """A global core.hooksPath must not turn every repo into a skip.

    core.hooksPath replaces git's search path, so .git/hooks is dead -- unless
    the pre-push in the shared directory chains back to it, which is what
    ~/.git-hooks/pre-push on this machine does. Before this, the installer
    refused all three shapes alike and reported 71 skips and 0 installs on the
    machine the standard was written for, so the git-hook layer existed nowhere.

    The shared directory itself is still never written to: that would put the
    hook in front of pushes from work repos.
    """
    import shutil, subprocess as sp
    # The marker is the contract. It is read out of the installer rather than
    # retyped, so a change to the line there fails this test instead of quietly
    # making every real delegator on the fleet look unmarked.
    marker = next(
        ln.split("=", 1)[1].strip().strip("'")
        for ln in (HERE / "install-pr-hooks").read_text().splitlines()
        if ln.startswith("DELEGATION_MARKER=")
    )
    delegator = (
        "#!/bin/bash\n"
        f"{marker}\n"
        'exec "$(git rev-parse --git-common-dir)/hooks/pre-push" "$@"\n'
    )
    own_policy = "#!/bin/bash\nexit 0\n"
    # A real delegator that never declared itself. This is what the explicit
    # contract costs, and it is deliberate: the SKIP message prints the line to
    # add, and a missed install is recoverable in a way a false INSTALL is not.
    unmarked_delegator = (
        "#!/bin/bash\n"
        'exec "$(git rev-parse --git-common-dir)/hooks/pre-push" "$@"\n'
    )
    # Everything three rounds of heuristic looked for, in a hook that always
    # execs somebody else's shared file and never this repo's. It mentions
    # git-common-dir outside a comment and contains the substring
    # "hooks/pre-push" in an unrelated path. Any grep-based check passes it;
    # the marker does not.
    heuristic_bait = (
        "#!/bin/bash\n"
        'echo "common dir is $(git rev-parse --git-common-dir)" >> /tmp/hooklog\n'
        'exec "/opt/shared-hooks/pre-push" "$@"\n'
    )
    results = []
    for label, global_hook, want_install, mode in [
        ("no hooksPath", None, True, 0o755),
        ("hooksPath with a declared delegator", delegator, True, 0o755),
        ("hooksPath without a delegator", own_policy, False, 0o755),
        ("hooksPath delegating but not declaring it", unmarked_delegator, False, 0o755),
        ("hooksPath baiting every heuristic, no marker", heuristic_bait, False, 0o755),
        # Declared, but git will not run it. Installing on the strength of the
        # marker alone would print INSTALL for a hook that never fires, which
        # is the failure the marker exists to rule out.
        ("hooksPath declaring delegation but not executable", delegator, False, 0o644),
    ]:
        d = tempfile.mkdtemp(); repo = f"{d}/repo"
        os.makedirs(f"{repo}/.github")
        cfg = f"{d}/gitconfig"; pathlib.Path(cfg).write_text("")
        shared = f"{d}/global-hooks"
        if global_hook is not None:
            os.makedirs(shared)
            gh = f"{shared}/pre-push"
            pathlib.Path(gh).write_text(global_hook)
            os.chmod(gh, mode)
            pathlib.Path(cfg).write_text(f"[core]\n\thooksPath = {shared}\n")
        env = {**os.environ, "GIT_CONFIG_GLOBAL": cfg}
        sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
        sp.run(["git", "-C", repo, "remote", "add", "origin",
                "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
        pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
        out = sp.run([str(HERE / "install-pr-hooks"), "--apply", "--root", d],
                     capture_output=True, text=True, env=env).stdout
        # The hook has to land in the repo, not merely be announced.
        installed = os.path.isfile(f"{repo}/.git/hooks/pre-push")
        # The shared directory must come out of an --apply run unchanged.
        shared_intact = global_hook is None or \
            pathlib.Path(f"{shared}/pre-push").read_text() == global_hook
        shutil.rmtree(d, ignore_errors=True)
        ok = installed == want_install and shared_intact
        results.append(ok)
        print(f"  {'OK ' if ok else 'FAIL'} {label:<32} installed={installed} want={want_install}")
    return all(results)


if not test_global_hooks_path_shapes():
    ALL_OK = False


def test_relative_global_hooks_path_resolves_against_repo():
    """A relative global core.hooksPath is resolved per-repo, like git does.

    git resolves a relative core.hooksPath against the repo's own working
    tree (githooks(5)), not against wherever install-pr-hooks happens to be
    invoked from. A global hooksPath of ".githooks" is how a shared
    delegating policy is normally paired with a per-repo delegate target, so
    the delegation check has to look in the repo, not in this script's own
    cwd (which has no ".githooks" of its own).
    """
    import shutil, subprocess as sp
    d = tempfile.mkdtemp(); repo = f"{d}/repo"
    os.makedirs(f"{repo}/.github")
    os.makedirs(f"{repo}/.githooks")
    delegate = f"{repo}/.githooks/pre-push"
    marker = next(
        ln.split("=", 1)[1].strip().strip("'")
        for ln in (HERE / "install-pr-hooks").read_text().splitlines()
        if ln.startswith("DELEGATION_MARKER=")
    )
    pathlib.Path(delegate).write_text(
        "#!/bin/bash\n"
        f"{marker}\n"
        'exec "$(git rev-parse --git-common-dir)/hooks/pre-push" "$@"\n'
    )
    os.chmod(delegate, 0o755)
    cfg = f"{d}/gitconfig"
    pathlib.Path(cfg).write_text("[core]\n\thooksPath = .githooks\n")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": cfg}
    sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
    sp.run(["git", "-C", repo, "remote", "add", "origin",
            "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
    pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
    sp.run([str(HERE / "install-pr-hooks"), "--apply", "--root", d],
           capture_output=True, text=True, env=env, cwd=str(HERE))
    installed = os.path.isfile(f"{repo}/.git/hooks/pre-push")
    shutil.rmtree(d, ignore_errors=True)
    ok = installed
    print(f"  {'OK ' if ok else 'FAIL'} relative global hooksPath delegates to its own repo   installed={installed} want=True")
    return ok


if not test_relative_global_hooks_path_resolves_against_repo():
    ALL_OK = False


def test_global_hooks_path_matching_the_default_needs_no_delegator():
    """A global hooksPath that just spells out the default must still install.

    core.hooksPath resolves a relative value against each repo's own working
    tree, so a global (or system) value of ".git/hooks" lands on the exact
    same directory as the plain default for every repo -- there is no
    separate shared directory here, and nothing to delegate from. Demanding
    the delegation marker in that case can never succeed: it asks the hook
    this run is about to write to already declare, before being written,
    that it forwards to itself.
    """
    import shutil, subprocess as sp
    d = tempfile.mkdtemp(); repo = f"{d}/repo"
    os.makedirs(f"{repo}/.github")
    cfg = f"{d}/gitconfig"
    pathlib.Path(cfg).write_text("[core]\n\thooksPath = .git/hooks\n")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": cfg}
    sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
    sp.run(["git", "-C", repo, "remote", "add", "origin",
            "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
    pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
    out = sp.run([str(HERE / "install-pr-hooks"), "--apply", "--root", d],
                 capture_output=True, text=True, env=env).stdout
    installed = os.path.isfile(f"{repo}/.git/hooks/pre-push")
    shutil.rmtree(d, ignore_errors=True)
    ok = installed and "SKIP" not in out
    print(f"  {'OK ' if ok else 'FAIL'} global hooksPath matching the default installs directly   installed={installed} want=True")
    return ok


if not test_global_hooks_path_matching_the_default_needs_no_delegator():
    ALL_OK = False


def test_global_hooks_path_matching_the_default_in_other_spellings():
    """Any lexical spelling of the default hooksPath must still install.

    `git config --path` returns the value exactly as configured -- it does
    not strip a trailing slash, collapse a "./" prefix, or fold doubled
    slashes. The default-hooksPath check must compare normalized paths, not
    raw strings, or a hooksPath that names the default directory in any but
    the one literal spelling ".git/hooks" falls through to the delegation
    check and gets skipped for lacking a delegator it was never meant to need.
    """
    import shutil, subprocess as sp
    results = []
    for spelling in (".git/hooks/", "./.git/hooks", ".git//hooks"):
        d = tempfile.mkdtemp(); repo = f"{d}/repo"
        os.makedirs(f"{repo}/.github")
        cfg = f"{d}/gitconfig"
        pathlib.Path(cfg).write_text(f"[core]\n\thooksPath = {spelling}\n")
        env = {**os.environ, "GIT_CONFIG_GLOBAL": cfg}
        sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
        sp.run(["git", "-C", repo, "remote", "add", "origin",
                "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
        pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
        out = sp.run([str(HERE / "install-pr-hooks"), "--apply", "--root", d],
                     capture_output=True, text=True, env=env).stdout
        installed = os.path.isfile(f"{repo}/.git/hooks/pre-push")
        shutil.rmtree(d, ignore_errors=True)
        ok = installed and "SKIP" not in out
        results.append(ok)
        print(f"  {'OK ' if ok else 'FAIL'} hooksPath spelled {spelling!r:<16} installed={installed} want=True")
    return all(results)


if not test_global_hooks_path_matching_the_default_in_other_spellings():
    ALL_OK = False


def _guard_harness():
    """Throwaway HOME plus an empty --root, so the pre-push scan is a no-op."""
    import subprocess as sp
    home = tempfile.mkdtemp()
    root = tempfile.mkdtemp()
    env = {**os.environ, "HOME": home, "GIT_CONFIG_GLOBAL": "/dev/null"}
    dest = os.path.join(home, ".local", "share", "pr-standards", "pr-standards-guard.sh")
    return home, root, env, dest, sp


def _guard_run(sp, env, *args):
    return sp.run([str(HERE / "install-pr-hooks"), *args],
                  capture_output=True, text=True, env=env)


def _expected_sha(sp):
    return sp.check_output(
        ["git", "-C", str(HERE), "rev-parse", "HEAD:hooks/pr-standards-guard.sh"],
        text=True,
    ).strip()


def _strip_stamp(text):
    body, stamp = [], None
    for line in text.splitlines(keepends=True):
        if line.startswith("# pr-standards-guard installed from "):
            stamp = line
            continue
        body.append(line)
    return "".join(body), stamp


def _body_sha(sp, dest):
    text = pathlib.Path(dest).read_text()
    body, _ = _strip_stamp(text)
    return sp.check_output(["git", "hash-object", "--stdin"], input=body.encode()).decode().strip()


def test_pretooluse_dry_run_writes_nothing():
    """No --apply reports the PreToolUse path and writes nothing."""
    home, root, env, dest, sp = _guard_harness()
    out = _guard_run(sp, env, "--root", root).stdout
    wrote = os.path.exists(dest)
    ok = (not wrote) and ("would write" in out) and (dest in out) and ("settings.json" in out)
    print(f"  {'OK ' if ok else 'FAIL'} dry-run reports PreToolUse guard, writes nothing")
    return ok


def test_pretooluse_apply_writes_stamped_copy_and_snippet():
    """--apply writes a copy identical to the source aside from the stamp line."""
    home, root, env, dest, sp = _guard_harness()
    out = _guard_run(sp, env, "--apply", "--root", root).stdout
    src = (HERE / "hooks/pr-standards-guard.sh").read_text()
    text = pathlib.Path(dest).read_text()
    body, stamp = _strip_stamp(text)
    expected = _expected_sha(sp)
    stamp_ok = (
        stamp is not None
        and stamp.startswith(f"# pr-standards-guard installed from {expected} on ")
    )
    snippet = "settings.json" in out and dest in out and "does not edit" in out
    ok = body == src and stamp_ok and snippet and os.access(dest, os.X_OK)
    print(f"  {'OK ' if ok else 'FAIL'} --apply writes stamped guard and prints snippet")
    return ok


def test_pretooluse_apply_is_idempotent():
    """A second --apply reports no change and does not rewrite the file."""
    home, root, env, dest, sp = _guard_harness()
    _guard_run(sp, env, "--apply", "--root", root)
    before = pathlib.Path(dest).read_bytes()
    out = _guard_run(sp, env, "--apply", "--root", root).stdout
    after = pathlib.Path(dest).read_bytes()
    ok = after == before and "already installed" in out
    print(f"  {'OK ' if ok else 'FAIL'} second --apply reports no change")
    return ok


def test_pretooluse_drift_reports_stale_after_hand_edit():
    """A hand-edited install is stale, and the check names both revisions."""
    home, root, env, dest, sp = _guard_harness()
    _guard_run(sp, env, "--apply", "--root", root)
    pathlib.Path(dest).write_text(pathlib.Path(dest).read_text() + "# hand-edit\n")
    out = _guard_run(sp, env, "--drift").stdout
    expected = _expected_sha(sp)
    installed = _body_sha(sp, dest)
    ok = (
        "stale" in out
        and expected in out
        and installed in out
        and expected != installed
    )
    print(f"  {'OK ' if ok else 'FAIL'} drift names both revisions when stale")
    return ok


def test_pretooluse_dry_run_distinguishes_edited_from_older():
    """The dry-run message must not print one revision twice.

    --drift computes a content sha, so it names two different values. The
    dry-run install path prints the STAMP twice, and a stamp is unchanged by a
    hand edit -- so it read "stale; installed X expected X", which tells the
    reader nothing and looks like a broken tool. Two causes, two messages.
    """
    home, root, env, dest, sp = _guard_harness()
    _guard_run(sp, env, "--apply", "--root", root)

    # Cause 1: edited after install. The stamp still matches.
    pathlib.Path(dest).write_text(pathlib.Path(dest).read_text() + "# hand-edit\n")
    edited = _guard_run(sp, env, "--root", root).stdout
    ok = "edited since install" in edited and "expected" not in edited

    # Cause 2: installed from an older revision. The stamp differs.
    old = "0" * 40
    pathlib.Path(dest).write_text(
        re.sub(r"(installed from )[0-9a-f]{40}", r"\g<1>" + old, pathlib.Path(dest).read_text(), count=1)
    )
    older = _guard_run(sp, env, "--root", root).stdout
    ok = ok and "stale" in older and old in older and _expected_sha(sp) in older

    print(f"  {'OK ' if ok else 'FAIL'} dry run tells an edit apart from an older revision")
    return ok


def test_pretooluse_drift_absent_is_not_installed_not_stale():
    """No installed file is 'not installed', never 'stale'."""
    home, root, env, dest, sp = _guard_harness()
    out = _guard_run(sp, env, "--drift").stdout
    ok = "not installed" in out and "stale" not in out
    print(f"  {'OK ' if ok else 'FAIL'} absent guard is not installed, not stale")
    return ok


def test_pretooluse_uninstall_removes_and_drift_says_not_installed():
    """--uninstall --apply removes the guard; drift then says not installed."""
    home, root, env, dest, sp = _guard_harness()
    _guard_run(sp, env, "--apply", "--root", root)
    _guard_run(sp, env, "--uninstall", "--apply", "--root", root)
    out = _guard_run(sp, env, "--drift").stdout
    ok = (not os.path.exists(dest)) and ("not installed" in out) and ("stale" not in out)
    print(f"  {'OK ' if ok else 'FAIL'} uninstall removes guard; drift says not installed")
    return ok


def test_pretooluse_never_writes_settings_or_outside_owned_dir():
    """The installer never edits settings and never writes outside its owned dir."""
    home, root, env, dest, sp = _guard_harness()
    settings = pathlib.Path(home) / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text('{"keep":true}\n')
    private = pathlib.Path(home) / "private-repo-b1e6" / "hooks" / "pr-standards-guard.sh"
    private.parent.mkdir(parents=True)
    private.write_text("foreign\n")
    _guard_run(sp, env, "--apply", "--root", root)
    owned = os.path.join(home, ".local", "share", "pr-standards")
    extras = []
    for dirpath, dirnames, filenames in os.walk(home):
        if dirpath.startswith(owned):
            continue
        for name in filenames:
            extras.append(os.path.join(dirpath, name))
    ok = (
        settings.read_text() == '{"keep":true}\n'
        and private.read_text() == "foreign\n"
        and os.path.isfile(dest)
        and set(extras) == {str(settings), str(private)}
    )
    print(f"  {'OK ' if ok else 'FAIL'} no settings edit, no write outside owned dir")
    return ok


def test_pre_push_still_installs_alongside_the_guard():
    """Pre-push install is unchanged: an eligible repo still gets the hook."""
    import shutil, subprocess as sp
    home, root, env, dest, _ = _guard_harness()
    repo = f"{root}/repo"
    os.makedirs(f"{repo}/.github")
    sp.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
    sp.run(["git", "-C", repo, "remote", "add", "origin",
            "https://github.com/itsryanarmani/example-repo.git"], check=True, env=env)
    pathlib.Path(f"{repo}/.github/pr-standards.json").write_text('{"prefix":"tt"}')
    out = _guard_run(sp, env, "--apply", "--root", root).stdout
    hook = f"{repo}/.git/hooks/pre-push"
    ok = os.path.isfile(hook) and os.path.isfile(dest) and "INSTALL" in out and repo in out
    shutil.rmtree(home, ignore_errors=True)
    shutil.rmtree(root, ignore_errors=True)
    print(f"  {'OK ' if ok else 'FAIL'} pre-push still installs alongside the guard")
    return ok


def test_pretooluse_drift_reports_not_executable():
    """A missing execute bit is reported distinctly, not as stale with two shas."""
    home, root, env, dest, sp = _guard_harness()
    _guard_run(sp, env, "--apply", "--root", root)
    os.chmod(dest, 0o644)
    out = _guard_run(sp, env, "--drift")
    expected = _expected_sha(sp)
    ok = out.returncode != 0 and "not executable" in out.stdout and expected in out.stdout and "stale" not in out.stdout and "installed" not in out.stdout
    print(f"  {'OK ' if ok else 'FAIL'} drift reports not executable, not duplicate shas")
    return ok


def test_pretooluse_apply_refuses_symlinked_guard_dir():
    """A symlinked parent of the guard directory must not redirect the write."""
    home, root, env, dest, sp = _guard_harness()
    real_share = os.path.join(home, "real-share")
    os.makedirs(real_share)
    os.makedirs(os.path.join(home, ".local"))
    os.symlink(real_share, os.path.join(home, ".local", "share"))
    out = _guard_run(sp, env, "--apply", "--root", root)
    outside = os.path.join(real_share, "pr-standards", "pr-standards-guard.sh")
    ok = out.returncode != 0 and "resolves outside" in out.stdout and not os.path.exists(outside)
    print(f"  {'OK ' if ok else 'FAIL'} apply refuses a symlinked guard directory")
    return ok


def test_installer_invoked_through_symlinked_script():
    home, root, env, dest, sp = _guard_harness()
    link = os.path.join(home, "install-pr-hooks-link")
    os.symlink(str(HERE / "install-pr-hooks"), link)
    out = sp.run([link, "--apply", "--root", root], capture_output=True, text=True, env=env)
    ok = out.returncode == 0 and os.path.isfile(dest) and "wrote" in out.stdout
    print(f"  {'OK ' if ok else 'FAIL'} installer works through a symlinked $0")
    return ok

def test_uninstall_succeeds_when_guard_blob_unresolvable():
    """Uninstall does not need HEAD:hooks/pr-standards-guard.sh to resolve."""
    home, root, env, dest, sp = _guard_harness()
    _guard_run(sp, env, "--apply", "--root", root)
    copy = os.path.join(home, "install-pr-hooks-copy")
    pathlib.Path(copy).write_bytes(pathlib.Path(HERE / "install-pr-hooks").read_bytes())
    os.chmod(copy, 0o755)
    out = sp.run([copy, "--uninstall", "--apply", "--root", root], capture_output=True, text=True, env=env)
    ok = out.returncode == 0 and not os.path.exists(dest) and "removed" in out.stdout
    print(f"  {'OK ' if ok else 'FAIL'} uninstall works when guard source is unresolvable")
    return ok


def test_uninstall_removes_symlinked_guard():
    """A symlinked GUARD_DST is removed, not followed, on uninstall."""
    home, root, env, dest, sp = _guard_harness()
    _guard_run(sp, env, "--apply", "--root", root)
    other = os.path.join(home, "other-guard")
    pathlib.Path(other).write_text("foreign\n")
    os.remove(dest)
    os.symlink(other, dest)
    out = _guard_run(sp, env, "--uninstall", "--apply", "--root", root)
    ok = out.returncode == 0 and not os.path.exists(dest) and not os.path.islink(dest) and os.path.isfile(other)
    print(f"  {'OK ' if ok else 'FAIL'} uninstall removes a symlinked guard")
    return ok


for _guard_test in (
    test_pretooluse_dry_run_writes_nothing,
    test_pretooluse_apply_writes_stamped_copy_and_snippet,
    test_pretooluse_apply_is_idempotent,
    test_pretooluse_drift_reports_stale_after_hand_edit,
    test_pretooluse_dry_run_distinguishes_edited_from_older,
    test_pretooluse_drift_absent_is_not_installed_not_stale,
    test_pretooluse_uninstall_removes_and_drift_says_not_installed,
    test_pretooluse_never_writes_settings_or_outside_owned_dir,
    test_pre_push_still_installs_alongside_the_guard,
    test_pretooluse_drift_reports_not_executable,
    test_pretooluse_apply_refuses_symlinked_guard_dir,
    test_installer_invoked_through_symlinked_script,
    test_uninstall_succeeds_when_guard_blob_unresolvable,
    test_uninstall_removes_symlinked_guard,
):
    if not _guard_test():
        ALL_OK = False

sys.exit(0 if ALL_OK else 1)
