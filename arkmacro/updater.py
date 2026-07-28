"""
Self-update straight from the repo this app is published to.

A.N.S Watcher ships a single exe, so it self-updates through a signed manifest
and an exe swap. Here the distribution *is* the git working copy, so the honest
mechanism is a fast-forward pull: no download to verify, no rename dance, and
`git reflog` is the undo button if a release goes wrong.

Everything runs through `git` as a subprocess — no extra dependency, and the
same binary the user already pushes with.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
from dataclasses import dataclass, field

from PySide6.QtCore import QThread, Signal

ROOT = pathlib.Path(__file__).resolve().parent.parent
TIMEOUT = 30
UNIT = "\x1f"  # field separator inside git log lines

# keep a console window from flashing on every git call
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git(*args: str, timeout: int = TIMEOUT) -> tuple[int, str, str]:
    """Run git inside the app folder. Returns (exit code, stdout, stderr)."""
    exe = shutil.which("git")
    if not exe:
        return 127, "", "git is not installed or not on PATH"
    try:
        done = subprocess.run(
            [exe, *args], cwd=str(ROOT), capture_output=True, text=True,
            timeout=timeout, creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"git {args[0]} timed out after {timeout}s"
    except OSError as error:
        return 1, "", str(error)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


@dataclass
class Repo:
    """What the local working copy looks like right now."""

    ok: bool = False
    reason: str = ""
    branch: str = ""
    upstream: str = ""
    sha: str = ""
    committed: str = ""
    dirty: bool = False


@dataclass
class Status:
    """Result of comparing the working copy against its upstream."""

    ok: bool = False
    error: str = ""
    behind: int = 0
    ahead: int = 0
    dirty: bool = False
    commits: list[tuple[str, str]] = field(default_factory=list)
    requirements_changed: bool = False

    @property
    def up_to_date(self) -> bool:
        return self.ok and self.behind == 0


def local_state() -> Repo:
    """Branch, commit and cleanliness of the working copy."""
    if not (ROOT / ".git").exists():
        return Repo(reason="this folder is not a git clone")

    code, branch, error = _git("rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        return Repo(reason=error or "cannot read the current branch")

    _code, upstream, _err = _git("rev-parse", "--abbrev-ref",
                                 "--symbolic-full-name", "@{u}")
    if not upstream:
        upstream = f"origin/{branch}"

    _code, sha, _err = _git("rev-parse", "--short", "HEAD")
    _code, committed, _err = _git("log", "-1", "--date=short", "--format=%ad")
    _code, porcelain, _err = _git("status", "--porcelain")

    return Repo(ok=True, branch=branch, upstream=upstream, sha=sha,
                committed=committed, dirty=bool(porcelain))


def check() -> Status:
    """Fetch and report how far behind the working copy is."""
    repo = local_state()
    if not repo.ok:
        return Status(error=repo.reason)

    remote = repo.upstream.split("/", 1)[0]
    code, _out, error = _git("fetch", "--quiet", remote, repo.branch)
    if code != 0:
        return Status(error=error or "could not reach the remote")

    code, counts, error = _git("rev-list", "--left-right", "--count",
                               f"HEAD...{repo.upstream}")
    if code != 0:
        return Status(error=error or f"no upstream branch {repo.upstream}")
    parts = counts.split()
    ahead = int(parts[0]) if parts else 0
    behind = int(parts[1]) if len(parts) > 1 else 0

    commits: list[tuple[str, str]] = []
    if behind:
        _code, log, _err = _git("log", f"--format=%h{UNIT}%s",
                                f"HEAD..{repo.upstream}")
        for line in log.splitlines():
            sha, _, subject = line.partition(UNIT)
            if sha:
                commits.append((sha, subject))

    _code, changed, _err = _git("diff", "--name-only", f"HEAD..{repo.upstream}")
    return Status(ok=True, behind=behind, ahead=ahead, dirty=repo.dirty,
                  commits=commits,
                  requirements_changed="requirements.txt" in changed.split())


def apply() -> tuple[bool, str]:
    """
    Fast-forward onto the upstream commit.

    Refuses on a dirty tree instead of stashing: silently moving someone's
    edits is worse than making them decide.
    """
    repo = local_state()
    if not repo.ok:
        return False, repo.reason
    if repo.dirty:
        return False, ("you have uncommitted changes here — commit or discard "
                       "them first, the updater will not touch your edits")

    remote = repo.upstream.split("/", 1)[0]
    code, out, error = _git("pull", "--ff-only", remote, repo.branch, timeout=90)
    if code != 0:
        detail = error or out
        lowered = detail.lower()
        # git words this several ways: "Not possible to fast-forward",
        # "non-fast-forward", "have diverged"
        if "fast-forward" in lowered or "diverge" in lowered:
            detail = ("your branch has commits the remote does not — push or "
                      "reset them before updating")
        return False, detail or "git pull failed"

    _code, sha, _err = _git("rev-parse", "--short", "HEAD")
    return True, f"updated to {sha}"


class UpdateWorker(QThread):
    """Runs a git round-trip off the UI thread."""

    checked = Signal(object)      # Status
    applied = Signal(bool, str)   # ok, message

    def __init__(self, mode: str, parent=None) -> None:
        super().__init__(parent)
        self.mode = mode

    def run(self) -> None:
        if self.mode == "check":
            self.checked.emit(check())
        else:
            ok, message = apply()
            self.applied.emit(ok, message)
