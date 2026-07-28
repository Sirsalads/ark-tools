"""
Updater tests. Git is faked, so nothing is fetched, pulled or written.

    python tests/test_updater.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from arkmacro import updater  # noqa: E402

UNIT = updater.UNIT
calls: list[tuple[str, ...]] = []


def fake_git(responses: dict[str, tuple[int, str, str]]):
    """Route git subcommands to canned replies, recording every call."""
    def run(*args: str, timeout: int = 0):
        calls.append(args)
        for key, reply in responses.items():
            if args[0] == key:
                return reply
        return 0, "", ""
    return run


CLEAN = {
    "rev-parse": (0, "main", ""),
    "log": (0, "2026-07-28", ""),
    "status": (0, "", ""),
    "fetch": (0, "", ""),
    "rev-list": (0, "0\t0", ""),
    "diff": (0, "", ""),
}


def with_git(overrides: dict) -> None:
    merged = dict(CLEAN)
    merged.update(overrides)
    updater._git = fake_git(merged)
    calls.clear()


# --------------------------------------------------- 1) real repo is readable
real = updater.local_state()
assert real.ok, f"the project itself should be a git clone: {real.reason}"
assert real.branch and real.sha, real
print(f"OK  reads the live working copy: {real.branch} @ {real.sha}")

# --------------------------------------------------- 2) missing git is graceful
updater._git = lambda *a, **k: (127, "", "git is not installed or not on PATH")
status = updater.check()
assert not status.ok and "not installed" in status.error, status
ok, message = updater.apply()
assert not ok and "not installed" in message
print("OK  a missing git degrades to a message, not a crash")

# --------------------------------------------------- 3) up to date
with_git({})
status = updater.check()
assert status.ok and status.up_to_date and status.behind == 0, status
assert any(c[0] == "fetch" for c in calls), "check must fetch first"
print("OK  clean and current reports up to date")

# --------------------------------------------------- 4) behind, with commits
with_git({
    "rev-list": (0, "0\t2", ""),
    "log": (0, f"abc1234{UNIT}fix drop timing\ndef5678{UNIT}new preset", ""),
    "diff": (0, "arkmacro/engine.py\nrequirements.txt", ""),
})
status = updater.check()
assert status.behind == 2 and not status.up_to_date
assert status.commits == [("abc1234", "fix drop timing"),
                          ("def5678", "new preset")], status.commits
assert status.requirements_changed is True
print("OK  counts incoming commits and flags requirement changes")

# --------------------------------------------------- 5) local commits ahead
with_git({"rev-list": (0, "3\t1", "")})
status = updater.check()
assert status.ahead == 3 and status.behind == 1
print("OK  reports local commits that are not pushed")

# --------------------------------------------------- 6) dirty tree is refused
with_git({"status": (0, " M arkmacro/engine.py", "")})
status = updater.check()
assert status.dirty is True
ok, message = updater.apply()
assert not ok and "uncommitted" in message, message
assert not any(c[0] == "pull" for c in calls), "it must not pull over edits"
print("OK  refuses to pull over uncommitted changes")

# --------------------------------------------------- 7) fast-forward only
with_git({"rev-list": (0, "0\t1", "")})
ok, message = updater.apply()
pull = next(c for c in calls if c[0] == "pull")
assert "--ff-only" in pull, pull
assert ok, message
print("OK  applies as a fast-forward and never merges")

# --------------------------------------------------- 8) diverged is explained
with_git({"pull": (1, "", "fatal: Not possible to fast-forward, aborting.")})
ok, message = updater.apply()
assert not ok and "push or reset" in message, message
print("OK  a diverged branch gets a plain-language reason")

# --------------------------------------------------- 9) unreachable remote
with_git({"fetch": (128, "", "fatal: unable to access ... Could not resolve host")})
status = updater.check()
assert not status.ok and "resolve host" in status.error
print("OK  an offline machine reports the network error")

print("\nALL UPDATER TESTS PASSED")
