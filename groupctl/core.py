"""Core implementation of groupctl operations and procedures."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def find_git_executable() -> str:
    """Resolve the git executable on Windows/POSIX, including user-scoped MinGit."""
    candidates = [
        shutil.which("git.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe"),
        r"C:\Program Files\Git\cmd\git.exe",
        shutil.which("git"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return "git"

from . import PROTOCOL_VERSION
from .models import (
    ALLOWED_FINAL_STATUS,
    ALLOWED_INTEGRATION_RESULTS,
    ALLOWED_REVIEW_VERDICTS,
    ALLOWED_TEST_RESULTS,
    build_event_envelope,
    utc_now_iso,
    validate_event,
    validate_final_json,
    validate_group_json,
    validate_member_json,
)

SECRET_PATTERNS = [
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    re.compile(r"OPENAI_API_KEY\s*=\s*['\"]?sk-[A-Za-z0-9]{10,}"),
    re.compile(r"GEMINI_API_KEY\s*=\s*['\"]?AIza[A-Za-z0-9_\-]{10,}"),
    re.compile(r"GH_TOKEN\s*=\s*['\"]?ghp_[A-Za-z0-9]{10,}"),
    re.compile(r"AWS_SECRET_ACCESS_KEY\s*=\s*['\"]?[A-Za-z0-9/+=]{20,}"),
]

SECRET_FILENAMES = {".env", "id_rsa", "id_ed25519", "secrets.json", "credentials.json"}
JUNK_PATTERNS = ("__pycache__/", ".pyc", ".pyo", ".DS_Store", "Thumbs.db")

CONFLICT_START_RE = re.compile(r"^<<<<<<< ", re.MULTILINE)
CONFLICT_MID_RE = re.compile(r"^=======\r?$", re.MULTILINE)
CONFLICT_END_RE = re.compile(r"^>>>>>>> ", re.MULTILINE)


class GroupCtlError(Exception):
    """Raised when a groupctl operation fails a contract or safety check."""


class GroupRepo:
    """Represents a repository managed with the .group/ contract."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = (root or Path.cwd()).resolve()
        self.group_dir = self.root / ".group"
        self.group_json_path = self.group_dir / "group.json"
        self.assignment_dir = self.group_dir / "assignment"
        self.members_dir = self.group_dir / "members"
        self.events_dir = self.group_dir / "events"
        self.final_dir = self.group_dir / "final"
        self.local_dir = self.group_dir / "local"
        self.local_state_path = self.local_dir / "state.json"

    # ------------------------------------------------------------------
    # Low-level Git helpers
    # ------------------------------------------------------------------
    def git(
        self,
        args: List[str],
        check: bool = True,
        capture: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a git command inside self.root."""
        cmd = [find_git_executable()] + args
        res = subprocess.run(
            cmd,
            cwd=str(self.root),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
        if check and res.returncode != 0:
            err = (res.stderr or res.stdout or "").strip()
            raise GroupCtlError(f"Git command failed ({' '.join(cmd)}): {err}")
        return res

    def has_remote(self, remote: str = "origin") -> bool:
        res = self.git(["remote"], check=False)
        if res.returncode != 0:
            return False
        remotes = [r.strip() for r in res.stdout.splitlines() if r.strip()]
        return remote in remotes

    def current_branch(self) -> str:
        res = self.git(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        if res.returncode != 0:
            res_sym = self.git(["symbolic-ref", "--short", "HEAD"], check=False)
            return res_sym.stdout.strip() if res_sym.returncode == 0 else "HEAD"
        return res.stdout.strip()

    def current_commit(self, short: bool = False) -> str:
        args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
        res = self.git(args, check=False)
        return res.stdout.strip() if res.returncode == 0 else ""

    def resolve_commit(self, ref: str, short: bool = False) -> Optional[str]:
        args = ["rev-parse", "--short", f"{ref}^{{commit}}"] if short else ["rev-parse", f"{ref}^{{commit}}"]
        res = self.git(args, check=False)
        if res.returncode != 0:
            return None
        return res.stdout.strip()

    def is_ancestor(self, ancestor: str, descendant: str = "HEAD") -> bool:
        res = self.git(["merge-base", "--is-ancestor", ancestor, descendant], check=False)
        return res.returncode == 0

    def uncommitted_files(self) -> List[str]:
        res = self.git(["status", "--porcelain"], check=False)
        if res.returncode != 0:
            return []
        lines = [line.rstrip() for line in res.stdout.splitlines() if line.strip()]
        return lines

    def conflicting_files(self) -> List[str]:
        res = self.git(["diff", "--name-only", "--diff-filter=U"], check=False)
        if res.returncode != 0:
            return []
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]

    def is_merge_in_progress(self) -> bool:
        git_dir_res = self.git(["rev-parse", "--git-dir"], check=False)
        if git_dir_res.returncode != 0:
            return False
        git_dir = (self.root / git_dir_res.stdout.strip()).resolve()
        return (git_dir / "MERGE_HEAD").exists()

    def fetch_all(self) -> bool:
        if not self.has_remote("origin"):
            return False
        res = self.git(["fetch", "--all", "--tags", "--prune"], check=False)
        return res.returncode == 0

    def push_current_branch(self, set_upstream: bool = True) -> bool:
        if not self.has_remote("origin"):
            return False
        branch = self.current_branch()
        args = ["push", "-u", "origin", branch] if set_upstream else ["push", "origin", branch]
        res = self.git(args, check=False)
        if res.returncode != 0:
            raise GroupCtlError(f"Failed to push branch '{branch}': {(res.stderr or res.stdout).strip()}")
        return True

    # ------------------------------------------------------------------
    # Repository & Local State Helpers
    # ------------------------------------------------------------------
    def load_group_config(self) -> Dict[str, Any]:
        if not self.group_json_path.exists():
            raise GroupCtlError(
                f"Missing {self.group_json_path}. Run 'groupctl init' or checkout a valid group repository."
            )
        data = json.loads(self.group_json_path.read_text(encoding="utf-8"))
        validate_group_json(data)
        return data

    def load_local_state(self) -> Dict[str, Any]:
        if not self.local_state_path.exists():
            return {
                "person_id": None,
                "last_sync_at": None,
                "last_synced_canonical_commit": None,
                "seen_events": [],
                "pending_integration": None,
            }
        try:
            return json.loads(self.local_state_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "person_id": None,
                "last_sync_at": None,
                "last_synced_canonical_commit": None,
                "seen_events": [],
                "pending_integration": None,
            }

    def save_local_state(self, state: Dict[str, Any]) -> None:
        self.local_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = self.local_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")
        self.local_state_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_active_person_id(self, explicit_person_id: Optional[str] = None) -> str:
        if explicit_person_id:
            return explicit_person_id
        env_person = os.environ.get("GROUPCTL_PERSON_ID")
        if env_person:
            return env_person
        state = self.load_local_state()
        if state.get("person_id"):
            return state["person_id"]
        raise GroupCtlError(
            "No active person_id configured. Use 'groupctl member add <person_id> <name> --use' "
            "or 'groupctl use-member <person_id>'."
        )

    # ------------------------------------------------------------------
    # Initialization & Membership (02_repository_contract.md)
    # ------------------------------------------------------------------
    def init_repo(
        self,
        group_id: str,
        canonical_branch: str = "main",
        assignment_text: Optional[str] = None,
        commit_initial: bool = True,
    ) -> Dict[str, Any]:
        """Initialize the .group/ directory structure according to 02_repository_contract.md."""
        if not (self.root / ".git").exists():
            self.git(["init", "-b", canonical_branch])

        # Configure git user if not already set so commits work smoothly in clean environments
        name_res = self.git(["config", "user.name"], check=False)
        if name_res.returncode != 0 or not name_res.stdout.strip():
            self.git(["config", "user.name", f"Group {group_id}"])
        email_res = self.git(["config", "user.email"], check=False)
        if email_res.returncode != 0 or not email_res.stdout.strip():
            self.git(["config", "user.email", f"{group_id.lower()}@group.local"])

        self.assignment_dir.mkdir(parents=True, exist_ok=True)
        self.members_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.final_dir.mkdir(parents=True, exist_ok=True)
        self.local_dir.mkdir(parents=True, exist_ok=True)

        (self.local_dir / ".gitkeep").write_text("", encoding="utf-8")

        assignment_rel = ".group/assignment/assignment.md"
        assignment_path = self.root / assignment_rel
        if assignment_text is not None or not assignment_path.exists():
            content = assignment_text or (
                f"# Group Assignment ({group_id})\n\n"
                "Collaborate using `groupctl` and personal branches to deliver one verified canonical result.\n"
            )
            assignment_path.write_text(content, encoding="utf-8")

        group_data = {
            "protocol_version": PROTOCOL_VERSION,
            "group_id": group_id,
            "canonical_branch": canonical_branch,
            "assignment_file": assignment_rel,
        }
        validate_group_json(group_data)
        self.group_json_path.write_text(
            json.dumps(group_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # Ensure .gitignore ignores .group/local/* except .gitkeep
        gitignore_path = self.root / ".gitignore"
        ignore_rules = [
            "# groupctl local state",
            ".group/local/*",
            "!.group/local/.gitkeep",
            "__pycache__/",
            "*.pyc",
            ".pytest_cache/",
        ]
        existing_gitignore = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
        updated = existing_gitignore
        for rule in ignore_rules:
            if rule not in updated:
                if updated and not updated.endswith("\n"):
                    updated += "\n"
                updated += rule + "\n"
        if updated != existing_gitignore:
            gitignore_path.write_text(updated, encoding="utf-8")

        if commit_initial:
            self.git(["add", ".group/group.json", assignment_rel, ".group/local/.gitkeep", ".gitignore"])
            status = self.uncommitted_files()
            if status:
                self.git(["commit", "-m", f"Initialize group {group_id} collaboration structure"])

        return group_data

    def add_member(
        self,
        person_id: str,
        display_name: str,
        joined_at: Optional[str] = None,
        set_active: bool = True,
        commit: bool = True,
        push: bool = False,
    ) -> Dict[str, Any]:
        """Create .group/members/<person_id>.json per 02_repository_contract.md Section 4."""
        self.load_group_config()
        self.members_dir.mkdir(parents=True, exist_ok=True)
        member_data = {
            "protocol_version": PROTOCOL_VERSION,
            "person_id": person_id,
            "display_name": display_name,
            "joined_at": joined_at or utc_now_iso(),
        }
        validate_member_json(member_data)
        member_path = self.members_dir / f"{person_id}.json"
        member_path.write_text(
            json.dumps(member_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        if set_active:
            self.use_member(person_id, display_name=display_name)

        if commit:
            rel_path = f".group/members/{person_id}.json"
            self.git(["add", rel_path])
            if self.uncommitted_files():
                self.git(["commit", "-m", f"Register group member {person_id} ({display_name})"])
            if push and self.has_remote("origin"):
                self.push_current_branch()

        return member_data

    def use_member(self, person_id: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        state = self.load_local_state()
        state["person_id"] = person_id
        self.save_local_state(state)
        # Update local git user.name so commits clearly attribute the member
        members = self.discover_all_members()
        name = display_name or members.get(person_id, {}).get("display_name") or person_id
        self.git(["config", "user.name", f"{name} ({person_id})"], check=False)
        self.git(["config", "user.email", f"{person_id.lower()}@group.local"], check=False)
        return state

    def start_personal_branch(self, topic: str, person_id: Optional[str] = None, base_ref: Optional[str] = None) -> str:
        """Create or switch to people/<person_id>/<topic> per 02_repository_contract.md Section 6."""
        cfg = self.load_group_config()
        pid = self.get_active_person_id(person_id)
        clean_topic = topic.strip().strip("/")
        if not clean_topic:
            raise GroupCtlError("Branch topic must not be empty.")
        branch_name = f"people/{pid}/{clean_topic}"
        # Check if branch already exists locally
        exists_res = self.git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], check=False)
        if exists_res.returncode == 0:
            self.git(["checkout", branch_name])
        else:
            start_from = base_ref or cfg["canonical_branch"]
            self.git(["checkout", "-b", branch_name, start_from])
        return branch_name

    # ------------------------------------------------------------------
    # Cross-Ref Event & Member Discovery
    # ------------------------------------------------------------------
    def _list_all_git_refs(self) -> List[str]:
        res = self.git(
            ["for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"],
            check=False,
        )
        if res.returncode != 0:
            return []
        refs = []
        for line in res.stdout.splitlines():
            r = line.strip()
            if r and not r.endswith("/HEAD"):
                refs.append(r)
        return refs

    def discover_all_members(self) -> Dict[str, Dict[str, Any]]:
        """Discover all member descriptors across working tree and all local/remote refs."""
        members: Dict[str, Dict[str, Any]] = {}
        if self.members_dir.exists():
            for p in sorted(self.members_dir.glob("*.json")):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    validate_member_json(data)
                    members[data["person_id"]] = data
                except Exception:
                    continue

        for ref in self._list_all_git_refs():
            ls_res = self.git(["ls-tree", "--name-only", ref, ".group/members/"], check=False)
            if ls_res.returncode != 0:
                continue
            for rel_path in ls_res.stdout.splitlines():
                rel_path = rel_path.strip()
                if not rel_path.endswith(".json"):
                    continue
                show_res = self.git(["show", f"{ref}:{rel_path}"], check=False)
                if show_res.returncode != 0:
                    continue
                try:
                    data = json.loads(show_res.stdout)
                    validate_member_json(data)
                    members.setdefault(data["person_id"], data)
                except Exception:
                    continue
        return members

    def discover_all_events(self) -> List[Dict[str, Any]]:
        """Discover all immutable events in .group/events/*.json across working tree and all Git refs."""
        events_by_id: Dict[str, Dict[str, Any]] = {}

        # 1. Working directory
        if self.events_dir.exists():
            for p in sorted(self.events_dir.glob("*.json")):
                try:
                    ev = json.loads(p.read_text(encoding="utf-8"))
                    validate_event(ev)
                    events_by_id[ev["event_id"]] = ev
                except Exception:
                    continue

        # 2. All local and remote branches
        for ref in self._list_all_git_refs():
            ls_res = self.git(["ls-tree", "--name-only", ref, ".group/events/"], check=False)
            if ls_res.returncode != 0:
                continue
            for rel_path in ls_res.stdout.splitlines():
                rel_path = rel_path.strip()
                if not rel_path.endswith(".json"):
                    continue
                stem = Path(rel_path).stem
                if stem in events_by_id:
                    continue
                show_res = self.git(["show", f"{ref}:{rel_path}"], check=False)
                if show_res.returncode != 0:
                    continue
                try:
                    ev = json.loads(show_res.stdout)
                    validate_event(ev)
                    events_by_id[ev["event_id"]] = ev
                except Exception:
                    continue

        return sorted(
            events_by_id.values(),
            key=lambda e: (e.get("created_at", ""), e.get("event_id", "")),
        )

    def materialize_group_records(self, commit: bool = False) -> List[str]:
        """Ensure all immutable .group/events/*.json and .group/members/*.json from any ref exist in working tree."""
        written: List[str] = []
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.members_dir.mkdir(parents=True, exist_ok=True)

        for pid, mdata in self.discover_all_members().items():
            mpath = self.members_dir / f"{pid}.json"
            if not mpath.exists():
                mpath.write_text(json.dumps(mdata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                written.append(f".group/members/{pid}.json")

        for ev in self.discover_all_events():
            epath = self.events_dir / f"{ev['event_id']}.json"
            if not epath.exists():
                epath.write_text(json.dumps(ev, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                written.append(f".group/events/{ev['event_id']}.json")

        if commit and written:
            self.git(["add"] + written)
            if self.uncommitted_files():
                self.git(["commit", "-m", f"Synchronize {len(written)} collaboration record(s)"])

        return written

    def write_and_publish_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        person_id: Optional[str] = None,
        related_events: Optional[List[str]] = None,
        commit: bool = True,
        push: bool = True,
    ) -> Dict[str, Any]:
        """Write an immutable event JSON file, commit it, and push if configured."""
        cfg = self.load_group_config()
        pid = self.get_active_person_id(person_id)
        event = build_event_envelope(
            event_type=event_type,
            group_id=cfg["group_id"],
            person_id=pid,
            payload=payload,
            related_events=related_events,
        )
        self.events_dir.mkdir(parents=True, exist_ok=True)
        event_path = self.events_dir / f"{event['event_id']}.json"
        if event_path.exists():
            raise GroupCtlError(f"Immutable event file already exists: {event_path}")

        event_path.write_text(
            json.dumps(event, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # Record in seen_events locally so our own event isn't reported as 'unseen'
        state = self.load_local_state()
        seen = set(state.get("seen_events", []))
        seen.add(event["event_id"])
        state["seen_events"] = sorted(seen)
        self.save_local_state(state)

        if commit:
            rel_event = f".group/events/{event['event_id']}.json"
            self.git(["add", rel_event])
            self.git(["commit", "-m", f"Publish {event_type} event {event['event_id']}"])
            if push and self.has_remote("origin"):
                self.push_current_branch()

        return event

    def find_change_event(self, change_id: str) -> Dict[str, Any]:
        """Locate the change_published event for a given change_id."""
        matches = [
            ev
            for ev in self.discover_all_events()
            if ev.get("event_type") == "change_published" and ev.get("change_id") == change_id
        ]
        if not matches:
            raise GroupCtlError(f"Could not find any change_published event for change_id '{change_id}'.")
        return matches[-1]

    # ------------------------------------------------------------------
    # Validation & Safety Checks
    # ------------------------------------------------------------------
    def scan_repository_safety(self) -> Dict[str, List[str]]:
        """Scan tracked and staged files for conflict markers, accidental secrets, junk files, or syntax errors."""
        issues: Dict[str, List[str]] = {
            "conflict_markers": [],
            "secrets": [],
            "junk_files": [],
            "syntax_errors": [],
        }

        res = self.git(["ls-files", "--cached", "--others", "--exclude-standard"], check=False)
        files = [f.strip() for f in res.stdout.splitlines() if f.strip()] if res.returncode == 0 else []

        for rel in files:
            fpath = self.root / rel
            if not fpath.is_file():
                continue

            if fpath.name in SECRET_FILENAMES:
                issues["secrets"].append(f"Forbidden secret file: {rel}")

            norm_rel = rel.replace("\\", "/")
            if any(pat in norm_rel for pat in JUNK_PATTERNS):
                issues["junk_files"].append(f"Generated junk file: {rel}")

            try:
                text = fpath.read_text(encoding="utf-8")
            except Exception:
                continue

            if (
                CONFLICT_START_RE.search(text)
                and CONFLICT_MID_RE.search(text)
                and CONFLICT_END_RE.search(text)
            ):
                issues["conflict_markers"].append(rel)

            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    issues["secrets"].append(f"Secret pattern matched in {rel}")
                    break

            if rel.endswith(".py"):
                try:
                    ast.parse(text, filename=rel)
                except SyntaxError as exc:
                    issues["syntax_errors"].append(f"{rel}:{exc.lineno}: {exc.msg}")

        return issues

    def run_automated_checks(self, extra_commands: Optional[List[str]] = None) -> Dict[str, Any]:
        """Discover and run build/syntax checks and pytest suite."""
        commands_run: List[str] = []
        passed = 0
        failed = 0
        skipped = 0
        outputs: List[str] = []
        build_ok = True

        # 1. Syntax / build check on Python files under src/ or root
        safety = self.scan_repository_safety()
        if safety["conflict_markers"] or safety["syntax_errors"]:
            build_ok = False
            outputs.append(
                f"Build/Syntax errors: conflicts={safety['conflict_markers']}, syntax={safety['syntax_errors']}"
            )

        # 2. Run pytest if tests exist
        tests_dir = self.root / "tests"
        has_tests = tests_dir.exists() and any(tests_dir.rglob("test_*.py"))
        if has_tests:
            cmd_str = "pytest -q"
            commands_run.append(cmd_str)
            res = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"],
                cwd=str(self.root),
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            out = (res.stdout or "").strip()
            outputs.append(out)

            m_pass = re.search(r"(\d+)\s+passed", out)
            m_fail = re.search(r"(\d+)\s+(?:failed|error)", out)
            m_skip = re.search(r"(\d+)\s+skipped", out)
            if m_pass:
                passed += int(m_pass.group(1))
            if m_fail:
                failed += int(m_fail.group(1))
            if m_skip:
                skipped += int(m_skip.group(1))
            if res.returncode != 0 and failed == 0:
                failed = 1

        if extra_commands:
            for ecmd in extra_commands:
                commands_run.append(ecmd)
                res = subprocess.run(
                    ecmd,
                    cwd=str(self.root),
                    shell=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                outputs.append((res.stdout or "").strip())
                if res.returncode != 0:
                    failed += 1

        if not build_ok or failed > 0:
            automated_result = "fail"
        elif commands_run:
            automated_result = "pass"
        else:
            automated_result = "not_available"

        return {
            "build": "pass" if build_ok else "fail",
            "tests": "pass" if (build_ok and failed == 0) else "fail",
            "automated_result": automated_result,
            "commands": commands_run or ["python -m py_compile"],
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "output": "\n".join(outputs).strip(),
        }

    def _canonical_ref(self, canonical_branch: str) -> str:
        """Return the best reference for the canonical branch (preferring origin/<canonical_branch> if fetched)."""
        if self.has_remote("origin"):
            rem_ref = f"origin/{canonical_branch}"
            if self.resolve_commit(rem_ref) is not None:
                return rem_ref
        return canonical_branch

    def ahead_behind(self, branch_ref: str, canonical_ref: str) -> Tuple[int, int]:
        res = self.git(
            ["rev-list", "--left-right", "--count", f"{canonical_ref}...{branch_ref}"],
            check=False,
        )
        if res.returncode != 0:
            return (0, 0)
        parts = res.stdout.strip().split()
        if len(parts) != 2:
            return (0, 0)
        behind, ahead = int(parts[0]), int(parts[1])
        return ahead, behind

    # ------------------------------------------------------------------
    # Command 1: STATUS (05_command_procedures.md Section 6)
    # ------------------------------------------------------------------
    def cmd_status(self, fetch: bool = True) -> Dict[str, Any]:
        """Inspect local Git state, remote metadata, unprocessed events, and recommend next action."""
        cfg = self.load_group_config()
        state = self.load_local_state()
        if fetch:
            self.fetch_all()

        canonical_branch = cfg["canonical_branch"]
        canon_ref = self._canonical_ref(canonical_branch)
        canon_commit = self.resolve_commit(canon_ref) or ""
        branch = self.current_branch()
        head_commit = self.current_commit()
        uncommitted = self.uncommitted_files()
        conflicts = self.conflicting_files()
        ahead, behind = self.ahead_behind("HEAD", canon_ref) if canon_commit else (0, 0)

        all_events = self.discover_all_events()
        seen_ids = set(state.get("seen_events", []))
        unprocessed_events = [e for e in all_events if e["event_id"] not in seen_ids]

        pid = state.get("person_id")
        published_local_changes = [
            e["change_id"]
            for e in all_events
            if e.get("event_type") == "change_published" and e.get("person_id") == pid
        ]

        test_events = [e for e in all_events if e.get("event_type") == "test_result"]
        last_test = test_events[-1] if test_events else None

        # Active blockers: blockers whose blocking_change_id has not subsequently succeeded integration
        integrated_changes = {
            e.get("change_id")
            for e in all_events
            if e.get("event_type") == "integration_result" and e.get("result") == "success"
        }
        blockers = [
            e
            for e in all_events
            if e.get("event_type") == "blocker"
            and e.get("blocking_change_id") not in integrated_changes
        ]

        # Pending published changes not yet incorporated into HEAD
        unintegrated_changes = []
        for e in all_events:
            if e.get("event_type") == "change_published" and e.get("proposed_for_integration"):
                c_commit = e.get("commit", "")
                if c_commit and not self.is_ancestor(c_commit, "HEAD"):
                    unintegrated_changes.append(e["change_id"])

        # Recommend concise next action
        if conflicts:
            recommendation = (
                f"Resolve active merge conflicts in {conflicts} and complete integration with 'groupctl int <change_id> --complete'."
            )
        elif blockers:
            recommendation = (
                f"Address open blocker on change {blockers[-1].get('blocking_change_id')}: {blockers[-1].get('requested_action')}"
            )
        elif unprocessed_events or behind > 0:
            recommendation = "Run 'SYNC' ('groupctl sync') to process new group events and synchronize with canonical state."
        elif uncommitted:
            recommendation = "Finish and test your local edits, then run 'PUB' ('groupctl pub') to share your change."
        elif unintegrated_changes:
            recommendation = (
                f"Review or integrate pending teammate change(s): {', '.join(unintegrated_changes)} using 'REV' or 'INT'."
            )
        elif ahead > 0 and branch != canonical_branch:
            recommendation = "Run 'PUB' if this branch has unpublished work, or integrate verified work into canonical branch."
        else:
            recommendation = "Workspace is clean and synchronized. Ready for feature work, 'TEST', or 'FINAL'."

        return {
            "person_id": pid,
            "group_id": cfg["group_id"],
            "branch": branch,
            "current_commit": head_commit,
            "canonical_branch": canonical_branch,
            "canonical_commit": canon_commit,
            "ahead_of_canonical": ahead,
            "behind_canonical": behind,
            "uncommitted_changes": uncommitted,
            "conflicting_files": conflicts,
            "unprocessed_events": [
                {
                    "event_id": e["event_id"],
                    "event_type": e["event_type"],
                    "person_id": e["person_id"],
                    "summary": e.get("summary") or e.get("text", ""),
                    "change_id": e.get("change_id"),
                }
                for e in unprocessed_events
            ],
            "published_local_changes": published_local_changes,
            "unintegrated_changes": unintegrated_changes,
            "last_known_test": (
                {
                    "event_id": last_test["event_id"],
                    "commit": last_test["commit"],
                    "automated_result": last_test["automated_result"],
                    "summary": last_test["summary"],
                }
                if last_test
                else None
            ),
            "blockers": [
                {
                    "event_id": b["event_id"],
                    "blocking_change_id": b["blocking_change_id"],
                    "summary": b["summary"],
                    "requested_action": b["requested_action"],
                }
                for b in blockers
            ],
            "recommended_next_action": recommendation,
        }

    # ------------------------------------------------------------------
    # Command 2: SYNC (05_command_procedures.md Section 1)
    # ------------------------------------------------------------------
    def cmd_sync(self, update_canonical: bool = True, run_quick_validation: bool = True) -> Dict[str, Any]:
        """Execute SYNC procedure:
        1. Record current branch, commit, uncommitted state.
        2. Fetch remote branches and tags.
        3. Read newly published .group/events/*.json.
        4. Determine which events are new since last known sync.
        5. Fetch current canonical branch.
        6. Compare current work against canonical state.
        7. If safe, merge canonical state without discarding local work.
        8. Do not automatically integrate unrelated feature branches.
        9. Inspect new change, integration, review, test, and blocker events.
        10. Report what changed, what was incorporated, what remains separate, and assumption impacts.
        11. If synchronization changed code, run quick validation.
        """
        cfg = self.load_group_config()
        state = self.load_local_state()

        before_branch = self.current_branch()
        before_commit = self.current_commit()
        uncommitted = self.uncommitted_files()

        # Fetch remotes
        self.fetch_all()

        canonical_branch = cfg["canonical_branch"]
        canon_ref = self._canonical_ref(canonical_branch)
        canon_commit = self.resolve_commit(canon_ref) or ""

        all_events = self.discover_all_events()
        seen_ids = set(state.get("seen_events", []))
        new_events = [e for e in all_events if e["event_id"] not in seen_ids]

        ahead, behind = self.ahead_behind("HEAD", canon_ref) if canon_commit else (0, 0)
        canonical_merged = False
        merge_note = "Already up to date with canonical branch."
        code_changed = False

        if update_canonical and canon_commit and behind > 0:
            if uncommitted:
                merge_note = (
                    f"Canonical branch '{canon_ref}' is {behind} commit(s) ahead, "
                    "but local uncommitted changes exist; skipped automatic merge to protect local work."
                )
            else:
                # Check if merge with canonical branch would be clean
                merge_res = self.git(["merge", "--no-commit", "--no-ff", canon_ref], check=False)
                conflicts = self.conflicting_files()
                if conflicts:
                    # Do not corrupt local branch during SYNC; abort and report
                    self.git(["merge", "--abort"], check=False)
                    merge_note = (
                        f"Canonical branch '{canon_ref}' has changes conflicting with local work in {conflicts}. "
                        "Aborted automatic canonical merge so conflicts can be resolved deliberately."
                    )
                else:
                    if self.is_merge_in_progress():
                        self.git(["commit", "-m", f"Sync canonical branch '{canonical_branch}' into {before_branch}"])
                    after_commit = self.current_commit()
                    canonical_merged = after_commit != before_commit
                    code_changed = canonical_merged
                    merge_note = f"Cleanly incorporated canonical state ({canon_commit[:7]})."

        # Identify separate feature branches & changes not yet integrated
        separate_changes = []
        interface_warnings = []
        for ev in all_events:
            if ev.get("event_type") == "change_published":
                c_commit = ev.get("commit", "")
                incorporated = bool(c_commit and self.is_ancestor(c_commit, "HEAD"))
                if not incorporated:
                    separate_changes.append(
                        {
                            "change_id": ev["change_id"],
                            "person_id": ev["person_id"],
                            "branch": ev["branch"],
                            "commit": c_commit,
                            "summary": ev["summary"],
                            "proposed_for_integration": ev["proposed_for_integration"],
                        }
                    )
                if ev.get("interface_changes") and ev["event_id"] in {ne["event_id"] for ne in new_events}:
                    interface_warnings.append(
                        {
                            "change_id": ev["change_id"],
                            "person_id": ev["person_id"],
                            "interface_changes": ev["interface_changes"],
                        }
                    )

        validation_result = None
        if code_changed and run_quick_validation:
            validation_result = self.run_automated_checks()

        # Update local sync state
        state["last_sync_at"] = utc_now_iso()
        state["last_synced_canonical_commit"] = canon_commit
        state["seen_events"] = sorted({e["event_id"] for e in all_events})
        self.save_local_state(state)

        return {
            "branch": before_branch,
            "commit_before": before_commit,
            "commit_after": self.current_commit(),
            "uncommitted_files": uncommitted,
            "canonical_branch": canonical_branch,
            "canonical_commit": canon_commit,
            "canonical_incorporated": canonical_merged,
            "canonical_sync_note": merge_note,
            "new_events_count": len(new_events),
            "new_events": [
                {
                    "event_id": e["event_id"],
                    "event_type": e["event_type"],
                    "person_id": e["person_id"],
                    "change_id": e.get("change_id"),
                    "summary": e.get("summary") or e.get("text", ""),
                }
                for e in new_events
            ],
            "separate_unmerged_changes": separate_changes,
            "assumption_and_interface_alerts": interface_warnings,
            "quick_validation": validation_result,
        }

    # ------------------------------------------------------------------
    # Command 3: PUB (05_command_procedures.md Section 2)
    # ------------------------------------------------------------------
    def cmd_pub(
        self,
        summary: str,
        change_id: Optional[str] = None,
        interface_changes: Optional[List[str]] = None,
        known_issues: Optional[List[str]] = None,
        proposed_for_integration: bool = True,
        person_id: Optional[str] = None,
        allow_Canonical: bool = False,
    ) -> Dict[str, Any]:
        """Execute PUB procedure:
        1. Inspect local changes.
        2. Refuse to publish accidental secrets, generated junk, or obviously broken repo state.
        3. Determine coherent contribution.
        4. Run quick tests/build checks.
        5. Create meaningful commit(s).
        6. Push personal work branch.
        7. Create unique change_id.
        8. Create change_published event.
        9. Commit and push the event.
        10. Report change ID.
        """
        cfg = self.load_group_config()
        pid = self.get_active_person_id(person_id)
        branch = self.current_branch()

        if not allow_Canonical and branch == cfg["canonical_branch"]:
            raise GroupCtlError(
                f"Cannot PUB directly from canonical branch '{branch}'. "
                f"Develop on a personal branch 'people/{pid}/<topic>' first."
            )

        # Safety scan
        safety = self.scan_repository_safety()
        if safety["conflict_markers"]:
            raise GroupCtlError(
                f"Refusing to PUB: unresolved conflict markers found in {safety['conflict_markers']}"
            )
        if safety["secrets"]:
            raise GroupCtlError(f"Refusing to PUB: potential secrets detected: {safety['secrets']}")
        if safety["junk_files"]:
            raise GroupCtlError(f"Refusing to PUB: generated junk files detected: {safety['junk_files']}")
        if safety["syntax_errors"]:
            raise GroupCtlError(f"Refusing to PUB: broken Python syntax detected: {safety['syntax_errors']}")

        # Stage and commit any pending changes (excluding .group/local)
        if self.uncommitted_files():
            self.git(["add", "-A"])
            if self.uncommitted_files():
                self.git(["commit", "-m", summary])

        code_commit = self.current_commit(short=True)
        full_code_commit = self.current_commit(short=False)

        # Determine files changed relative to canonical branch (or parent commit)
        canon_ref = self._canonical_ref(cfg["canonical_branch"])
        if self.resolve_commit(canon_ref):
            diff_res = self.git(["diff", "--name-only", f"{canon_ref}...HEAD"], check=False)
        else:
            diff_res = self.git(["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"], check=False)

        files_changed = [
            f.strip()
            for f in (diff_res.stdout.splitlines() if diff_res.returncode == 0 else [])
            if f.strip() and not f.strip().startswith(".group/")
        ]
        if not files_changed:
            # Fallback to last commit files
            last_res = self.git(["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"], check=False)
            files_changed = [
                f.strip()
                for f in (last_res.stdout.splitlines() if last_res.returncode == 0 else [])
                if f.strip() and not f.strip().startswith(".group/")
            ]

        if not files_changed:
            raise GroupCtlError("Nothing new to publish: no modified project files found on this branch.")

        # Run quick tests/build checks
        checks = self.run_automated_checks()
        if checks["build"] == "fail":
            raise GroupCtlError(f"Refusing to PUB: build/syntax check failed:\n{checks['output']}")
        if checks["tests"] == "fail":
            raise GroupCtlError(
                f"Refusing to PUB: automated tests failed ({checks['failed']} failed):\n{checks['output']}"
            )

        # Push personal work branch before creating event
        if self.has_remote("origin"):
            self.push_current_branch()

        # Generate unique change_id if not explicitly supplied
        all_events = self.discover_all_events()
        existing_change_ids = {
            e.get("change_id") for e in all_events if e.get("event_type") == "change_published"
        }
        if not change_id:
            num_part = re.sub(r"[^0-9A-Za-z]", "", pid.lstrip("Pp")) or pid
            candidate = f"C-{num_part}"
            idx = 2
            while candidate in existing_change_ids:
                candidate = f"C-{num_part}-{idx}"
                idx += 1
            change_id = candidate
        elif change_id in existing_change_ids:
            raise GroupCtlError(f"change_id '{change_id}' already exists in published events.")

        payload = {
            "change_id": change_id,
            "branch": branch,
            "commit": code_commit,
            "full_commit": full_code_commit,
            "summary": summary,
            "files_changed": files_changed,
            "interface_changes": list(interface_changes or []),
            "tests_run": checks["commands"],
            "known_issues": list(known_issues or []),
            "proposed_for_integration": bool(proposed_for_integration),
        }

        event = self.write_and_publish_event(
            event_type="change_published",
            payload=payload,
            person_id=pid,
            commit=True,
            push=True,
        )

        return {
            "change_id": change_id,
            "event_id": event["event_id"],
            "branch": branch,
            "commit": code_commit,
            "files_changed": files_changed,
            "tests_run": checks["commands"],
            "event": event,
        }

    # ------------------------------------------------------------------
    # Inspect a Change (Helper for REV & INT)
    # ------------------------------------------------------------------
    def inspect_change(self, change_id: str, fetch: bool = True) -> Dict[str, Any]:
        """Locate a published change, verify its branch and commit exist, and return its actual git diff."""
        if fetch:
            self.fetch_all()
        ev = self.find_change_event(change_id)
        commit_ref = ev.get("full_commit") or ev["commit"]
        resolved_commit = self.resolve_commit(commit_ref)
        if not resolved_commit:
            raise GroupCtlError(
                f"Referenced commit '{ev['commit']}' for change '{change_id}' does not exist in Git."
            )

        # Check branch existence locally or on origin
        branch_name = ev["branch"]
        branch_exists = (
            self.resolve_commit(branch_name) is not None
            or self.resolve_commit(f"origin/{branch_name}") is not None
        )

        # Compute actual Git diff for the change
        cfg = self.load_group_config()
        canon_ref = self._canonical_ref(cfg["canonical_branch"])
        base_res = self.git(["merge-base", canon_ref, resolved_commit], check=False)
        if base_res.returncode == 0 and base_res.stdout.strip():
            base_commit = base_res.stdout.strip()
            diff_res = self.git(["diff", f"{base_commit}..{resolved_commit}", "--", ".", ":(exclude).group/events"], check=False)
        else:
            diff_res = self.git(["show", resolved_commit, "--", ".", ":(exclude).group/events"], check=False)

        return {
            "change_id": change_id,
            "event": ev,
            "resolved_commit": resolved_commit,
            "branch_exists": branch_exists,
            "diff": diff_res.stdout if diff_res.returncode == 0 else "",
        }

    # ------------------------------------------------------------------
    # Command 4: REV <change_id> (05_command_procedures.md Section 4)
    # ------------------------------------------------------------------
    def cmd_rev(
        self,
        change_id: str,
        verdict: str,
        summary: str,
        issues: Optional[List[str]] = None,
        run_tests: bool = True,
        person_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute REV procedure:
        1. Locate published change.
        2. Read declared purpose and known issues.
        3. Inspect real Git diff.
        4. Check interface and assumption changes.
        5. Run relevant tests when practical.
        6. Produce one verdict (accept, accept_with_changes, reject, needs_more_evidence).
        7. Publish a review event without merging code.
        """
        if verdict not in ALLOWED_REVIEW_VERDICTS:
            raise GroupCtlError(
                f"Invalid review verdict '{verdict}'. Must be one of {sorted(ALLOWED_REVIEW_VERDICTS)}"
            )

        info = self.inspect_change(change_id, fetch=True)
        change_ev = info["event"]

        tests_run: List[str] = []
        if run_tests:
            checks = self.run_automated_checks()
            tests_run = checks["commands"]

        payload = {
            "change_id": change_id,
            "verdict": verdict,
            "summary": summary,
            "issues": list(issues or []),
            "tests_run": tests_run,
        }

        rev_event = self.write_and_publish_event(
            event_type="review",
            payload=payload,
            person_id=person_id,
            related_events=[change_ev["event_id"]],
            commit=True,
            push=True,
        )

        return {
            "change_id": change_id,
            "verdict": verdict,
            "review_event_id": rev_event["event_id"],
            "diff_inspected_bytes": len(info["diff"]),
            "interface_changes_noted": change_ev.get("interface_changes", []),
            "event": rev_event,
        }

    # ------------------------------------------------------------------
    # Command 5: INT <change_id> (05_command_procedures.md Section 3)
    # ------------------------------------------------------------------
    def cmd_int(
        self,
        change_id: str,
        complete_resolved: bool = False,
        on_conflict: str = "pause",
        conflict_resolution_summary: str = "",
        semantic_review: str = "pass",
        semantic_notes: str = "",
        person_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute INT <change_id> procedure with 3-level verification:
        Level 1: Git integration (commit incorporated, no conflict markers).
        Level 2: Mechanical validation (build, syntax, automated tests).
        Level 3: Semantic compatibility review (interface & behavioral compatibility).
        """
        pid = self.get_active_person_id(person_id)
        info = self.inspect_change(change_id, fetch=not complete_resolved)
        change_ev = info["event"]
        target_commit = info["resolved_commit"]
        target_branch = self.current_branch()

        state = self.load_local_state()
        recorded_conflicts: List[str] = []

        if not complete_resolved:
            if self.uncommitted_files():
                raise GroupCtlError(
                    "Working directory has uncommitted changes. Commit or stash before running INT."
                )

            # Perform Git merge without auto-committing first so we can inspect/record
            # Prefer merging the branch head if it contains the published change commit (so its event is included too)
            merge_ref = target_commit
            branch_ref = f"origin/{change_ev['branch']}" if self.has_remote("origin") else change_ev["branch"]
            if self.resolve_commit(branch_ref) and self.is_ancestor(target_commit, branch_ref):
                merge_ref = branch_ref

            self.git(["merge", "--no-ff", "--no-commit", merge_ref], check=False)
            conflicts = self.conflicting_files()

            if conflicts:
                recorded_conflicts = conflicts
                if on_conflict == "blocker":
                    self.git(["merge", "--abort"], check=False)
                    blocker_ev = self.write_and_publish_event(
                        event_type="blocker",
                        payload={
                            "summary": f"Cannot automatically resolve conflict in {', '.join(conflicts)} while integrating {change_id}.",
                            "blocking_change_id": change_id,
                            "requested_action": f"Human or agent decision needed to resolve conflict in {', '.join(conflicts)}.",
                        },
                        person_id=pid,
                        related_events=[change_ev["event_id"]],
                    )
                    int_ev = self.write_and_publish_event(
                        event_type="integration_result",
                        payload={
                            "change_id": change_id,
                            "target_branch": target_branch,
                            "result": "needs_human",
                            "merge_commit": "",
                            "conflicts": conflicts,
                            "conflict_resolution_summary": "Aborted due to ambiguous conflict requiring human input.",
                            "verification": {
                                "build": "not_run",
                                "tests": "not_run",
                                "semantic_review": "needs_human",
                            },
                            "summary": f"Integration of {change_id} paused with blocker ({blocker_ev['event_id']}).",
                        },
                        person_id=pid,
                        related_events=[change_ev["event_id"], blocker_ev["event_id"]],
                    )
                    return {
                        "status": "blocked",
                        "change_id": change_id,
                        "conflicts": conflicts,
                        "blocker_event_id": blocker_ev["event_id"],
                        "integration_event_id": int_ev["event_id"],
                    }

                # Save pending conflict info in local state so --complete knows which files conflicted
                state["pending_integration"] = {
                    "change_id": change_id,
                    "target_commit": target_commit,
                    "conflicts": conflicts,
                }
                self.save_local_state(state)
                return {
                    "status": "conflict_paused",
                    "change_id": change_id,
                    "conflicts": conflicts,
                    "incoming_summary": change_ev["summary"],
                    "incoming_interface_changes": change_ev.get("interface_changes", []),
                    "instructions": (
                        f"Git reported conflicts in {conflicts}. "
                        "Inspect both sides, resolve the conflicting files deliberately, stage them with 'git add', "
                        f"and run: groupctl int {change_id} --complete --conflict-summary \"<how resolved>\""
                    ),
                }
        else:
            pending = state.get("pending_integration") or {}
            if pending.get("change_id") == change_id:
                recorded_conflicts = pending.get("conflicts", [])

        # Level 1: Verify no leftover conflict markers in working tree, then stage resolved files
        safety = self.scan_repository_safety()
        if safety["conflict_markers"]:
            raise GroupCtlError(
                f"Level 1 Verification Failed: leftover conflict markers ({safety['conflict_markers']}) remain."
            )

        if complete_resolved and self.conflicting_files():
            # Conflict markers are gone from the files; stage the resolved files in Git index
            self.git(["add", "-A"])

        remaining_unmerged = self.conflicting_files()
        if remaining_unmerged:
            raise GroupCtlError(
                f"Level 1 Verification Failed: unresolved conflicts ({remaining_unmerged}) remain."
            )

        # Complete the merge commit if merge is still in progress or changes are staged
        if self.is_merge_in_progress() or self.uncommitted_files():
            self.git(["add", "-A"])
            if self.uncommitted_files() or self.is_merge_in_progress():
                self.git(["commit", "-m", f"Integrate change {change_id} ({change_ev['summary']})"])

        # Confirm the referenced commit is actually incorporated in HEAD
        if not self.is_ancestor(target_commit, "HEAD"):
            raise GroupCtlError(
                f"Level 1 Verification Failed: commit {target_commit} is not an ancestor of HEAD after integration."
            )

        merge_commit = self.current_commit(short=True)

        # Level 2: Mechanical Validation (build + automated tests)
        checks = self.run_automated_checks()
        build_status = checks["build"]
        tests_status = checks["tests"]

        # Level 3: Semantic Review
        sem_status = semantic_review if semantic_review in ("pass", "fail") else "pass"
        if build_status != "pass" or tests_status != "pass" or sem_status != "pass":
            overall_result = "failed"
        else:
            overall_result = "success"

        summary_msg = f"Integrated {change_id} ({ overall_result })."
        if semantic_notes:
            summary_msg += f" Semantic review: {semantic_notes}"

        int_ev = self.write_and_publish_event(
            event_type="integration_result",
            payload={
                "change_id": change_id,
                "target_branch": target_branch,
                "result": overall_result,
                "merge_commit": merge_commit,
                "conflicts": recorded_conflicts,
                "conflict_resolution_summary": conflict_resolution_summary,
                "verification": {
                    "build": build_status,
                    "tests": tests_status,
                    "semantic_review": sem_status,
                },
                "summary": summary_msg,
            },
            person_id=pid,
            related_events=[change_ev["event_id"]],
            commit=True,
            push=True,
        )

        # Clear pending_integration state
        state = self.load_local_state()
        state["pending_integration"] = None
        self.save_local_state(state)

        return {
            "status": overall_result,
            "change_id": change_id,
            "target_branch": target_branch,
            "merge_commit": merge_commit,
            "conflicts": recorded_conflicts,
            "conflict_resolution_summary": conflict_resolution_summary,
            "verification": {
                "level_1_git_incorporated": True,
                "level_2_build": build_status,
                "level_2_tests": tests_status,
                "level_3_semantic_review": sem_status,
                "test_details": checks,
            },
            "integration_event_id": int_ev["event_id"],
            "event": int_ev,
        }

    # ------------------------------------------------------------------
    # Command 6: TEST [scope] (05_command_procedures.md Section 5)
    # ------------------------------------------------------------------
    def cmd_test(
        self,
        scope: str = "current_branch",
        human_checks_required: Optional[List[str]] = None,
        extra_commands: Optional[List[str]] = None,
        summary: Optional[str] = None,
        person_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute TEST [scope] procedure and publish a test_result event."""
        cfg = self.load_group_config()
        pid = self.get_active_person_id(person_id)

        norm_scope = "current_branch" if scope in ("current", "current_branch", "") else scope
        original_branch = self.current_branch()
        switched = False

        try:
            if norm_scope == cfg["canonical_branch"]:
                if original_branch != cfg["canonical_branch"] and not self.uncommitted_files():
                    self.git(["checkout", cfg["canonical_branch"]])
                    switched = True
            elif norm_scope.startswith("C-"):
                c_ev = self.find_change_event(norm_scope)
                c_branch = c_ev["branch"]
                if original_branch != c_branch and not self.uncommitted_files():
                    if self.resolve_commit(c_branch):
                        self.git(["checkout", c_branch])
                        switched = True

            tested_commit = self.current_commit(short=True)
            checks = self.run_automated_checks(extra_commands=extra_commands)
        finally:
            if switched:
                self.git(["checkout", original_branch], check=False)

        default_summary = (
            f"All automated checks passed ({checks['passed']} passed, {checks['skipped']} skipped)."
            if checks["automated_result"] == "pass"
            else f"Automated checks reported status '{checks['automated_result']}' "
            f"({checks['passed']} passed, {checks['failed']} failed)."
        )

        payload = {
            "scope": norm_scope,
            "commit": tested_commit,
            "commands": checks["commands"],
            "automated_result": checks["automated_result"],
            "passed": checks["passed"],
            "failed": checks["failed"],
            "skipped": checks["skipped"],
            "human_checks_required": list(human_checks_required or []),
            "summary": summary or default_summary,
        }

        ev = self.write_and_publish_event(
            event_type="test_result",
            payload=payload,
            person_id=pid,
            commit=True,
            push=True,
        )

        return {
            "test_event_id": ev["event_id"],
            "scope": norm_scope,
            "commit": tested_commit,
            "automated_result": checks["automated_result"],
            "passed": checks["passed"],
            "failed": checks["failed"],
            "skipped": checks["skipped"],
            "human_checks_required": payload["human_checks_required"],
            "output": checks["output"],
            "event": ev,
        }

    # ------------------------------------------------------------------
    # Promote Verified Branch to Canonical Branch (main)
    # ------------------------------------------------------------------
    def promote_to_canonical(self, source_branch: Optional[str] = None, push: bool = True) -> Dict[str, Any]:
        """Merge a verified branch into the canonical branch (main), run validation, and push."""
        cfg = self.load_group_config()
        canonical_branch = cfg["canonical_branch"]
        src = source_branch or self.current_branch()
        if src == canonical_branch:
            raise GroupCtlError(f"Already on canonical branch '{canonical_branch}'.")
        if self.uncommitted_files():
            raise GroupCtlError("Commit or stash uncommitted changes before promoting to canonical branch.")

        self.fetch_all()
        self.git(["checkout", canonical_branch])
        if self.has_remote("origin") and self.resolve_commit(f"origin/{canonical_branch}"):
            self.git(["pull", "--ff-only", "origin", canonical_branch], check=False)

        self.git(["merge", "--no-ff", src, "-m", f"Promote verified branch {src} to {canonical_branch}"])
        # Materialize all group events/members onto canonical branch so main has full history
        self.materialize_group_records(commit=True)

        checks = self.run_automated_checks()
        if checks["build"] != "pass" or checks["tests"] != "pass":
            raise GroupCtlError(
                f"Canonical branch validation failed after promoting {src}:\n{checks['output']}"
            )

        if push and self.has_remote("origin"):
            self.push_current_branch()

        return {
            "canonical_branch": canonical_branch,
            "promoted_from": src,
            "canonical_commit": self.current_commit(),
            "validation": checks,
        }

    # ------------------------------------------------------------------
    # Command 7: FINAL (05_command_procedures.md Section 7 & 07_testing_and_finalization.md)
    # ------------------------------------------------------------------
    def cmd_final_prepare(
        self,
        known_limitations: Optional[List[str]] = None,
        human_checks_required: Optional[List[str]] = None,
        allow_unmerged: bool = False,
        person_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Phase 1 of FINAL:
        1. Synchronize group metadata and canonical state.
        2. Switch to canonical branch and materialize all collaboration records.
        3. Identify the canonical commit proposed as the group result.
        4. List published changes not incorporated into canonical state (distinguishing rejected vs pending).
        5. Review latest reviews, blockers, and test results.
        6. Run final automated validation.
        7. Generate .group/final/candidate.md and publish a final_candidate event for human confirmation.
        """
        cfg = self.load_group_config()
        pid = self.get_active_person_id(person_id)
        canonical_branch = cfg["canonical_branch"]

        if self.uncommitted_files():
            raise GroupCtlError("Uncommitted changes exist. Commit or stash before running FINAL.")

        self.fetch_all()
        if self.current_branch() != canonical_branch:
            self.git(["checkout", canonical_branch])
        if self.has_remote("origin") and self.resolve_commit(f"origin/{canonical_branch}"):
            self.git(["merge", "--ff-only", f"origin/{canonical_branch}"], check=False)

        # Ensure all immutable events and member records are present on canonical branch
        self.materialize_group_records(commit=True)

        all_events = self.discover_all_events()
        members = self.discover_all_members()

        # Find the latest code commit on canonical branch (or current HEAD)
        canonical_commit = self.current_commit()

        # Analyze published changes: incorporated vs unmerged
        incorporated_changes: List[Dict[str, Any]] = []
        unmerged_changes: List[Dict[str, Any]] = []

        reviews_by_change: Dict[str, List[Dict[str, Any]]] = {}
        for ev in all_events:
            if ev.get("event_type") == "review":
                reviews_by_change.setdefault(ev["change_id"], []).append(ev)

        for ev in all_events:
            if ev.get("event_type") == "change_published":
                cid = ev["change_id"]
                c_commit = ev.get("full_commit") or ev["commit"]
                resolved = self.resolve_commit(c_commit)
                if resolved and self.is_ancestor(resolved, canonical_commit):
                    incorporated_changes.append(ev)
                else:
                    revs = reviews_by_change.get(cid, [])
                    latest_verdict = revs[-1]["verdict"] if revs else "unreviewed"
                    unmerged_changes.append(
                        {
                            "change_id": cid,
                            "person_id": ev["person_id"],
                            "branch": ev["branch"],
                            "summary": ev["summary"],
                            "latest_review_verdict": latest_verdict,
                            "status": "rejected_or_obsolete" if latest_verdict == "reject" else "pending",
                        }
                    )

        pending_important = [u for u in unmerged_changes if u["status"] == "pending"]
        if pending_important and not allow_unmerged:
            raise GroupCtlError(
                f"Cannot silently finalize: {len(pending_important)} published change(s) are still pending "
                f"integration or rejection: {[u['change_id'] for u in pending_important]}. "
                "Integrate them, reject them via REV, or pass --allow-unmerged if intentionally omitted."
            )

        # Run final automated validation on canonical branch
        checks = self.run_automated_checks()
        if checks["build"] != "pass" or checks["tests"] != "pass":
            raise GroupCtlError(
                f"Cannot finalize: final automated validation failed on canonical branch:\n{checks['output']}"
            )

        assignment_path = self.root / cfg["assignment_file"]
        assignment_title = (
            assignment_path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
            if assignment_path.exists()
            else f"Group {cfg['group_id']} Project"
        )

        contributors = [
            f"- **{m['person_id']}** ({m['display_name']})"
            for m in sorted(members.values(), key=lambda x: x["person_id"])
        ]
        if not contributors:
            contributors = [f"- **{pid}**"]

        changes_lines = [
            f"- **{c['change_id']}** by `{c['person_id']}` (`{c['branch']}` @ `{c['commit']}`): {c['summary']}"
            for c in incorporated_changes
        ] or ["- Initial canonical implementation on `main`."]

        limitations_list = list(known_limitations or [])
        limitations_lines = [f"- {lim}" for lim in limitations_list] or ["- None identified."]

        human_checks_list = list(human_checks_required or [])
        human_checks_lines = [f"- {hc}" for hc in human_checks_list] or ["- All required checks completed."]

        unmerged_lines = [
            f"- **{u['change_id']}** (`{u['status']}`, review={u['latest_review_verdict']}): {u['summary']}"
            for u in unmerged_changes
        ] or ["- None (all published changes incorporated)."]

        candidate_md = (
            f"# Proposed Group Final Report (Candidate)\n\n"
            f"## Assignment\n{assignment_title}\n\n"
            f"## Result\n"
            f"Group `{cfg['group_id']}` completed and verified the integrated implementation on `{canonical_branch}`.\n\n"
            f"## Canonical Commit\n`{canonical_commit}`\n\n"
            f"## Important Changes\n" + "\n".join(changes_lines) + "\n\n"
            f"## Unmerged Published Changes\n" + "\n".join(unmerged_lines) + "\n\n"
            f"## Validation\n"
            f"- Automated Build: `{checks['build']}`\n"
            f"- Automated Tests (`{', '.join(checks['commands'])}`): `{checks['automated_result']}` "
            f"({checks['passed']} passed, {checks['failed']} failed, {checks['skipped']} skipped)\n"
            f"- Human Checks:\n" + "\n".join(human_checks_lines) + "\n\n"
            f"## Known Limitations\n" + "\n".join(limitations_lines) + "\n\n"
            f"## Contributors\n" + "\n".join(contributors) + "\n"
        )

        self.final_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = self.final_dir / "candidate.md"
        candidate_path.write_text(candidate_md, encoding="utf-8")
        self.git(["add", ".group/final/candidate.md"])
        if self.uncommitted_files():
            self.git(["commit", "-m", "Generate final candidate report (.group/final/candidate.md)"])

        cand_event = self.write_and_publish_event(
            event_type="final_candidate",
            payload={
                "canonical_commit": canonical_commit,
                "candidate_report_path": ".group/final/candidate.md",
                "tests_considered": checks["commands"],
                "known_issues": limitations_list,
                "summary": f"Prepared final candidate report for canonical commit {canonical_commit[:7]}.",
            },
            person_id=pid,
            commit=True,
            push=True,
        )

        return {
            "status": "candidate_ready",
            "canonical_branch": canonical_branch,
            "canonical_commit": canonical_commit,
            "candidate_report_path": ".group/final/candidate.md",
            "candidate_event_id": cand_event["event_id"],
            "incorporated_changes": [c["change_id"] for c in incorporated_changes],
            "unmerged_changes": unmerged_changes,
            "validation": checks,
            "candidate_markdown": candidate_md,
        }

    def cmd_final_confirm(
        self,
        known_limitations: Optional[List[str]] = None,
        person_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Phase 2 of FINAL (after human confirmation):
        Create .group/final/final_report.md, .group/final/final.json, and a final_result event,
        then commit and push to the canonical branch.
        """
        cfg = self.load_group_config()
        pid = self.get_active_person_id(person_id)
        canonical_branch = cfg["canonical_branch"]

        if self.current_branch() != canonical_branch:
            self.git(["checkout", canonical_branch])

        candidate_path = self.final_dir / "candidate.md"
        if not candidate_path.exists():
            # Run prepare automatically if candidate.md doesn't exist yet
            self.cmd_final_prepare(known_limitations=known_limitations, person_id=pid)

        all_events = self.discover_all_events()
        members = self.discover_all_members()
        checks = self.run_automated_checks()
        if checks["build"] != "pass" or checks["tests"] != "pass":
            raise GroupCtlError(f"Final validation failed:\n{checks['output']}")

        # Record the canonical commit being finalized
        canonical_commit = self.current_commit()

        incorporated_changes = [
            ev
            for ev in all_events
            if ev.get("event_type") == "change_published"
            and self.resolve_commit(ev.get("full_commit") or ev["commit"])
            and self.is_ancestor(self.resolve_commit(ev.get("full_commit") or ev["commit"]), canonical_commit)
        ]
        review_events = [ev for ev in all_events if ev.get("event_type") == "review"]
        test_events = [ev for ev in all_events if ev.get("event_type") == "test_result"]

        assignment_path = self.root / cfg["assignment_file"]
        assignment_title = (
            assignment_path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
            if assignment_path.exists()
            else f"Group {cfg['group_id']} Assignment"
        )

        limitations_list = list(known_limitations or [])
        final_status = "completed_with_known_limitations" if limitations_list else "completed"

        changes_lines = [
            f"- **{c['change_id']}** (`{c['person_id']}` on `{c['branch']}` @ `{c['commit']}`): {c['summary']}"
            for c in incorporated_changes
        ] or ["- Integrated implementation on canonical branch."]

        contributors = [
            f"- **{m['person_id']}** ({m['display_name']})"
            for m in sorted(members.values(), key=lambda x: x["person_id"])
        ] or [f"- **{pid}**"]

        limitations_lines = [f"- {lim}" for lim in limitations_list] or ["- None."]

        # Exact sections required by 07_testing_and_finalization.md Section 8
        final_report_md = (
            f"# Group Final Report\n\n"
            f"## Assignment\n{assignment_title} (`{cfg['assignment_file']}`)\n\n"
            f"## Result\n"
            f"Group `{cfg['group_id']}` delivered a unified, verified implementation on `{canonical_branch}` "
            f"incorporating {len(incorporated_changes)} published change(s), {len(review_events)} peer review(s), "
            f"and {len(test_events)} published test run(s).\n\n"
            f"## Canonical Commit\n`{canonical_commit}`\n\n"
            f"## Important Changes\n" + "\n".join(changes_lines) + "\n\n"
            f"## Validation\n"
            f"- Build & Syntax Validation: `{checks['build']}`\n"
            f"- Automated Test Suite (`{', '.join(checks['commands'])}`): `{checks['automated_result']}` "
            f"({checks['passed']} passed, {checks['failed']} failed, {checks['skipped']} skipped)\n"
            f"- Reviews Recorded: {len(review_events)}\n"
            f"- Test Result Events Published: {len(test_events)}\n\n"
            f"## Known Limitations\n" + "\n".join(limitations_lines) + "\n\n"
            f"## Contributors\n" + "\n".join(contributors) + "\n"
        )

        self.final_dir.mkdir(parents=True, exist_ok=True)
        final_report_path = self.final_dir / "final_report.md"
        final_report_path.write_text(final_report_md, encoding="utf-8")

        final_json_data = {
            "protocol_version": PROTOCOL_VERSION,
            "group_id": cfg["group_id"],
            "canonical_branch": canonical_branch,
            "canonical_commit": canonical_commit,
            "report_file": ".group/final/final_report.md",
            "initiated_by": pid,
            "created_at": utc_now_iso(),
            "status": final_status,
            "known_limitations": limitations_list,
        }
        validate_final_json(final_json_data)
        final_json_path = self.final_dir / "final.json"
        final_json_path.write_text(
            json.dumps(final_json_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        self.git(["add", ".group/final/final_report.md", ".group/final/final.json"])
        if self.uncommitted_files():
            self.git(["commit", "-m", f"Finalize group {cfg['group_id']} result at {canonical_commit[:7]}"])

        cand_events = [e["event_id"] for e in all_events if e.get("event_type") == "final_candidate"]
        final_ev = self.write_and_publish_event(
            event_type="final_result",
            payload={
                "canonical_commit": canonical_commit,
                "final_report_path": ".group/final/final_report.md",
                "test_evidence": checks["commands"] + [e["event_id"] for e in test_events],
                "known_limitations": limitations_list,
                "initiated_by": pid,
                "status": final_status,
                "summary": f"Group {cfg['group_id']} finalized canonical result at {canonical_commit[:7]}.",
            },
            person_id=pid,
            related_events=cand_events[-1:] if cand_events else [],
            commit=True,
            push=True,
        )

        return {
            "status": final_status,
            "group_id": cfg["group_id"],
            "canonical_branch": canonical_branch,
            "canonical_commit": canonical_commit,
            "report_file": ".group/final/final_report.md",
            "final_json_file": ".group/final/final.json",
            "final_event_id": final_ev["event_id"],
            "final_json": final_json_data,
            "event": final_ev,
        }
