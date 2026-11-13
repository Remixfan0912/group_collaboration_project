"""STATUS command implementation for groupctl."""
from pathlib import Path
from typing import Dict, Any
from groupctl.config import GroupConfig
from groupctl.repo import GitRepo
from groupctl.events import EventManager


def run_status(config: GroupConfig, repo: GitRepo) -> Dict[str, Any]:
    print("=== [STATUS] Group Collaboration Status ===")
    
    # 1. Inspect local git state
    curr_branch = repo.get_current_branch()
    curr_commit = repo.get_current_commit(short=True)
    uncommitted = repo.get_uncommitted_changes()

    # 2. Fetch metadata if remote available
    repo.fetch_all()

    # Identity and config
    print(f"Group ID: {config.group_id}")
    print(f"Current Person: {config.person_id or 'Not configured'}")
    print(f"Current Branch: {curr_branch or 'DETACHED'} ({curr_commit})")
    print(f"Uncommitted Changes: {len(uncommitted)} file(s)")
    if uncommitted:
        for u in uncommitted[:5]:
            print(f"  {u}")
        if len(uncommitted) > 5:
            print(f"  ... and {len(uncommitted) - 5} more")

    # Canonical status
    canonical = config.canonical_branch
    canonical_commit = repo.get_commit_for_ref(canonical, short=True) or repo.get_commit_for_ref(f"origin/{canonical}", short=True)
    ahead, behind = (0, 0)
    if curr_branch:
        ahead, behind = repo.get_ahead_behind(curr_branch, canonical)
    print(f"Canonical Branch ({canonical}): {canonical_commit}")
    print(f"Relation to Canonical: {ahead} commit(s) ahead, {behind} commit(s) behind")

    # Events and history
    event_mgr = EventManager(config)
    all_events = event_mgr.list_events()
    last_sync = event_mgr.get_last_sync_event_id()
    new_events = event_mgr.get_events_after(last_sync)

    print(f"Total Group Events: {len(all_events)}")
    print(f"Unprocessed Events since sync: {len(new_events)}")

    # Active blockers
    active_blockers = [e for e in all_events if e.get("event_type") == "blocker"]
    if active_blockers:
        print("\n[!] ACTIVE BLOCKERS:")
        for b in active_blockers:
            print(f"  - {b.get('summary')} (Change: {b.get('blocking_change_id')})")
    else:
        print("Active Blockers: None")

    # Latest test result
    test_events = [e for e in all_events if e.get("event_type") == "test_result"]
    if test_events:
        latest_test = test_events[-1]
        print(f"Last Test Result: {latest_test.get('automated_result')} ({latest_test.get('summary')})")

    # Recommendation
    print("\n--- Recommendation ---")
    if uncommitted:
        print("You have uncommitted changes. Consider testing and using 'groupctl pub' when ready.")
    elif new_events:
        print("There are new group events. Run 'groupctl sync' to review teammates' updates.")
    elif behind > 0:
        print(f"Your branch is {behind} commits behind canonical. Run 'groupctl sync' to catch up.")
    else:
        print("Your working branch is up-to-date with canonical branch and event stream.")

    print("=== [STATUS] Done ===\n")
    return {
        "branch": curr_branch,
        "commit": curr_commit,
        "uncommitted_count": len(uncommitted),
        "ahead": ahead,
        "behind": behind,
        "active_blockers": len(active_blockers)
    }
