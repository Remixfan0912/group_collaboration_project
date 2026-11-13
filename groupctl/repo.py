"""Git operations wrapper for groupctl."""
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Dict


class GitRepo:
    def __init__(self, working_dir: Path):
        self.working_dir = working_dir

    def run(self, *args, check: bool = False) -> Tuple[int, str, str]:
        cmd = ["git"] + list(args)
        proc = subprocess.run(
            cmd,
            cwd=str(self.working_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if check and proc.returncode != 0:
            raise RuntimeError(f"Git command failed: {' '.join(cmd)}\nStderr: {proc.stderr}")
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def has_remote(self, remote: str = "origin") -> bool:
        code, out, _ = self.run("remote")
        return code == 0 and remote in out.splitlines()

    def get_current_branch(self) -> str:
        code, out, _ = self.run("rev-parse", "--abbrev-ref", "HEAD")
        return out if code == 0 else ""

    def get_current_commit(self, short: bool = False) -> str:
        args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
        code, out, _ = self.run(*args)
        return out if code == 0 else ""

    def get_commit_for_ref(self, ref: str, short: bool = False) -> str:
        args = ["rev-parse", "--short", ref] if short else ["rev-parse", ref]
        code, out, _ = self.run(*args)
        return out if code == 0 else ""

    def get_uncommitted_changes(self) -> List[str]:
        code, out, _ = self.run("status", "--porcelain")
        if code != 0 or not out:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    def is_dirty(self) -> bool:
        return len(self.get_uncommitted_changes()) > 0

    def fetch(self, remote: str = "origin") -> bool:
        if not self.has_remote(remote):
            return True
        code, _, _ = self.run("fetch", remote)
        return code == 0

    def fetch_all(self) -> bool:
        code, out, _ = self.run("remote")
        if code != 0 or not out.strip():
            return True
        code, _, _ = self.run("fetch", "--all")
        return code == 0

    def checkout(self, branch: str, create: bool = False) -> bool:
        args = ["checkout", "-b", branch] if create else ["checkout", branch]
        code, _, _ = self.run(*args)
        return code == 0

    def add(self, *paths: str) -> bool:
        code, _, _ = self.run("add", *paths)
        return code == 0

    def commit(self, message: str) -> bool:
        code, _, _ = self.run("commit", "-m", message)
        return code == 0

    def push(self, remote: str = "origin", branch: Optional[str] = None, set_upstream: bool = True) -> bool:
        if not self.has_remote(remote):
            return True
        curr = branch or self.get_current_branch()
        args = ["push"]
        if set_upstream:
            args.extend(["-u", remote, curr])
        else:
            args.extend([remote, curr])
        code, _, _ = self.run(*args)
        return code == 0

    def merge(self, target: str, message: Optional[str] = None) -> Tuple[bool, str]:
        args = ["merge", "--no-edit"]
        if message:
            args.extend(["-m", message])
        args.append(target)
        code, out, err = self.run(*args)
        return (code == 0), (out + "\n" + err).strip()

    def merge_abort(self):
        self.run("merge", "--abort")

    def has_conflicts(self) -> bool:
        code, out, _ = self.run("diff", "--name-only", "--diff-filter=U")
        return code == 0 and bool(out.strip())

    def get_conflicted_files(self) -> List[str]:
        code, out, _ = self.run("diff", "--name-only", "--diff-filter=U")
        if code != 0 or not out.strip():
            return []
        return [f.strip() for f in out.strip().splitlines() if f.strip()]

    def get_diff(self, target: str = "HEAD") -> str:
        code, out, _ = self.run("diff", target)
        return out if code == 0 else ""

    def get_diff_between(self, ref1: str, ref2: str) -> str:
        code, out, _ = self.run("diff", f"{ref1}..{ref2}")
        return out if code == 0 else ""

    def get_changed_files(self, base_ref: str, head_ref: str = "HEAD") -> List[str]:
        code, out, _ = self.run("diff", "--name-only", f"{base_ref}..{head_ref}")
        if code != 0 or not out.strip():
            return []
        return [f.strip() for f in out.strip().splitlines() if f.strip()]

    def is_ancestor(self, ancestor: str, descendant: str = "HEAD") -> bool:
        code, _, _ = self.run("merge-base", "--is-ancestor", ancestor, descendant)
        return code == 0

    def get_ahead_behind(self, branch: str, upstream: str) -> Tuple[int, int]:
        code, out, _ = self.run("rev-list", "--left-right", "--count", f"{branch}...{upstream}")
        if code != 0 or not out.strip():
            return (0, 0)
        parts = out.strip().split()
        if len(parts) == 2:
            return (int(parts[0]), int(parts[1]))
        return (0, 0)

    def has_conflict_markers(self) -> List[str]:
        """Check tracked files for leftover merge conflict markers."""
        code, out, _ = self.run("grep", "-I", "-n", "^<<<<<<<")
        if code != 0 or not out.strip():
            return []
        return [line.strip() for line in out.strip().splitlines() if line.strip()]
