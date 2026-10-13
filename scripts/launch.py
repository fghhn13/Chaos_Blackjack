"""Start the game at a chosen code version (used by start_game.bat).

    python scripts/launch.py                 # menu of versions (Enter = default)
    python scripts/launch.py j54 --fullscreen
    python scripts/launch.py --list

Versions are registered in launch_versions.json. A version with a git `ref`
runs from its own worktree under .launch/<name>, moved to the latest local
commit of that ref before each start; the working checkout is never touched.
Options after the version go to `python -m chaos_blackjack.gui`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "launch_versions.json"
WORKTREES = ROOT / ".launch"


class LaunchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Version:
    name: str
    ref: str | None
    description: str = ""


def load_versions(path: Path = REGISTRY) -> tuple[list[Version], str]:
    """(versions in file order, default name)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    versions = [Version(name, v.get("ref"), v.get("description", "")) for name, v in data["versions"].items()]
    default = data.get("default", versions[0].name if versions else "")
    if default not in {v.name for v in versions}:
        raise LaunchError(f"{path.name}: default {default!r} is not a registered version")
    return versions, default


def split_args(argv: list[str], versions: list[Version]) -> tuple[str | None, list[str]]:
    """(version name or None, game options)."""
    if argv and not argv[0].startswith("-"):
        names = [v.name for v in versions]
        if argv[0] not in names:
            raise LaunchError(f"Unknown version {argv[0]!r}. Registered: {', '.join(names)}")
        return argv[0], argv[1:]
    return None, argv


def choose(versions: list[Version], default: str, read=input, write=print) -> str:
    """Ask for a version by number or name; Enter keeps the default."""
    write("Choose a version to start:")
    for i, v in enumerate(versions, 1):
        mark = "  (default)" if v.name == default else ""
        where = "this checkout" if v.ref is None else v.ref
        write(f"  {i}. {v.name:<10} {v.description} [{where}]{mark}")
    while True:
        answer = read(f"Version [{default}]: ").strip()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(versions):
            return versions[int(answer) - 1].name
        if answer in {v.name for v in versions}:
            return answer
        write(f"Type a number from 1 to {len(versions)} or a version name.")


def _git(*args: str, cwd: Path = ROOT) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise LaunchError(f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def checkout(version: Version) -> Path:
    """The directory to run `version` from (its worktree, created or updated)."""
    if version.ref is None:
        return ROOT
    commit = _git("rev-parse", "--verify", f"{version.ref}^{{commit}}")
    path = WORKTREES / version.name
    if not (path / ".git").exists():
        print(f"Preparing {version.name} ({version.ref}) in {path.relative_to(ROOT)} ...")
        _git("worktree", "add", "--detach", str(path), commit)
        return path
    if _git("rev-parse", "HEAD", cwd=path) != commit:
        if _git("status", "--porcelain", "--untracked-files=no", cwd=path):
            raise LaunchError(f"{path} has local changes; commit or discard them before updating it")
        print(f"Updating {version.name} to the latest {version.ref} ...")
        _git("checkout", "--detach", commit, cwd=path)
    return path


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        versions, default = load_versions()
        if argv[:1] == ["--list"]:
            for v in versions:
                print(f"{v.name:<10} {v.ref or '(this checkout)':<20} {v.description}")
            return 0
        name, game_args = split_args(argv, versions)
        if name is None:
            name = choose(versions, default) if sys.stdin.isatty() else default
        version = next(v for v in versions if v.name == name)
        where = checkout(version)
    except (LaunchError, OSError, KeyError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(f"Starting Chaos Blackjack: {version.name} ({version.ref or 'this checkout'})")
    # -m puts the working directory first on sys.path, so the chosen version's
    # package is used even when another checkout is installed in editable mode.
    return subprocess.run([sys.executable, "-m", "chaos_blackjack.gui", *game_args], cwd=where).returncode


if __name__ == "__main__":
    sys.exit(main())
