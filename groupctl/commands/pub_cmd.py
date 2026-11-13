"""PUB command implementation for groupctl."""
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from groupctl.config import GroupConfig
from groupctl.repo import GitRepo
from groupctl.events import EventManager
from groupctl.validation import Validator


def get_next_change_id(event_mgr: EventManager, person_id: str) -> str:
    """Generate next change ID, e.g. C-17 or C-<num>."""
    events = event_mgr.list_events()
    max_num = 0
    for ev in events:
        cid = ev.get("change_id", "")
        m = re.match(r"C-(\d+)", cid)
        if m:
            max_num = max(max_num, int(m.group(1)))
    
    # Try extracting number from person_id, e.g. P17 -> C-17 if available, else sequential
    p_num = re.findall(r"\d+", person_id)
    if p_num:
        candidate = f"C-{p_num[0]}"
        # If candidate already used, find next unused
        used_cids = {ev.get("change_id") for ev in events if ev.get("change_id")}
        if candidate not in used_cids:
            return candidate
    return f"C-{max_num + 1}"


def run_pub(
    config: GroupConfig,
    repo: GitRepo,
    summary: str,
    interface_changes: Optional[List[str]] = None,
    known_issues: Optional[List[str]] = None,
    proposed_for_integration: bool = True,
    commit_msg: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    print("=== [PUB] Publishing local contribution ===")
    
    curr_branch = repo.get_current_branch()
    if not curr_branch:
        print("Error: Detached HEAD state. Cannot publish from detached HEAD.")
        return None

    if curr_branch == config.canonical_branch:
        print(f"Warning: Direct publishing on canonical branch '{config.canonical_branch}' is discouraged.")
        print(f"Expected personal branch format: people/{config.person_id}/<topic>")

    # 1 & 2. Inspect local changes & sanity checks
    uncommitted = repo.get_uncommitted_changes()
    validator = Validator(config.root_dir)
    ok, issues = validator.mechanical_check()
    if not ok:
        print("Error: Mechanical validation failed before publishing:")
        for issue in issues:
            print(f"  - {issue}")
        return None

    # 4. Run tests
    print("Running validation checks...")
    test_result = validator.run_tests()
    if test_result.get("automated_result") == "fail":
        print("Warning: Automated tests failed!")
        print(test_result.get("summary"))
        print("Please fix tests before publishing, or specify known issues.")

    # 5. Commit any pending working files if provided
    if uncommitted:
        print(f"Staging and committing {len(uncommitted)} changed file(s)...")
        repo.add(".")
        msg = commit_msg or f"Work on {curr_branch}: {summary}"
        repo.commit(msg)

    curr_commit = repo.get_current_commit()
    if not curr_commit:
        print("Error: No commits found on current branch.")
        return None

    # Push work branch to remote if remote exists
    print(f"Pushing personal branch '{curr_branch}'...")
    repo.push(branch=curr_branch)

    # 7. Create change ID
    event_mgr = EventManager(config)
    change_id = get_next_change_id(event_mgr, config.person_id or "P01")

    # Determine files changed
    files_changed = repo.get_changed_files(config.canonical_branch, curr_branch)
    if not files_changed:
        files_changed = ["(recent commits)"]

    tests_run = test_result.get("commands", [])

    # 8. Create change_published event
    event_data = {
        "change_id": change_id,
        "branch": curr_branch,
        "commit": curr_commit,
        "summary": summary,
        "files_changed": files_changed,
        "interface_changes": interface_changes or [],
        "tests_run": tests_run,
        "known_issues": known_issues or [],
        "proposed_for_integration": proposed_for_integration
    }
    
    event = event_mgr.create_event(
        event_type="change_published",
        specific_data=event_data,
        person_id=config.person_id
    )

    # 9. Commit and push event file
    event_file_rel = f".group/events/{event['event_id']}.json"
    repo.add(event_file_rel)
    repo.commit(f"Publish change event {change_id} ({event['event_id']})")
    repo.push(branch=curr_branch)

    print(f"\n[PUB Success] Published change {change_id}!")
    print(f"  Event ID: {event['event_id']}")
    print(f"  Branch: {curr_branch}")
    print(f"  Commit: {curr_commit[:8]}")
    print(f"  Summary: {summary}")
    if interface_changes:
        print(f"  Interfaces changed: {', '.join(interface_changes)}")
    print("=== [PUB] Done ===\n")

    return event
