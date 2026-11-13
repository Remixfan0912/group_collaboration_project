"""SYNC command implementation for groupctl."""
from pathlib import Path
from typing import Dict, Any, List
from groupctl.config import GroupConfig
from groupctl.repo import GitRepo
from groupctl.events import EventManager
from groupctl.validation import Validator


def run_sync(config: GroupConfig, repo: GitRepo, update_canonical: bool = True) -> Dict[str, Any]:
    print("=== [SYNC] Synchronizing with group repository ===")
    
    # 1. Record current state
    curr_branch = repo.get_current_branch()
    curr_commit = repo.get_current_commit(short=True)
    uncommitted = repo.get_uncommitted_changes()
    print(f"Current branch: {curr_branch or 'DETACHED'} ({curr_commit})")
    if uncommitted:
        print(f"Notice: {len(uncommitted)} uncommitted file(s) present.")

    # 2. Fetch remote
    repo.fetch_all()
    event_mgr = EventManager(config)
    last_sync_event = event_mgr.get_last_sync_event_id()

    # Discover and sync event files from all Git branches/refs
    event_mgr.sync_events_from_repo(repo)

    # 3 & 4. Discover new events
    new_events = event_mgr.get_events_after(last_sync_event)
    all_events = event_mgr.list_events()

    # 5 & 6. Canonical state comparison
    canonical = config.canonical_branch
    canonical_commit = repo.get_commit_for_ref(canonical, short=True) or repo.get_commit_for_ref(f"origin/{canonical}", short=True)
    
    ahead, behind = (0, 0)
    if curr_branch:
        ahead, behind = repo.get_ahead_behind(curr_branch, canonical)

    print(f"Canonical branch '{canonical}' commit: {canonical_commit}")
    print(f"Branch position: {ahead} commit(s) ahead, {behind} commit(s) behind canonical.")

    # 7. Update from canonical if on personal branch and safe
    merged_canonical = False
    if update_canonical and behind > 0 and not uncommitted:
        print(f"Attempting safe merge of canonical updates into {curr_branch}...")
        success, msg = repo.merge(canonical)
        if success:
            print("Successfully merged canonical updates.")
            merged_canonical = True
        else:
            print("Merge conflict or failure during canonical update. Aborting merge to protect local state.")
            repo.merge_abort()

    # Categorize new events
    changes_pub = [e for e in new_events if e.get("event_type") == "change_published"]
    reviews = [e for e in new_events if e.get("event_type") == "review"]
    test_results = [e for e in new_events if e.get("event_type") == "test_result"]
    integrations = [e for e in new_events if e.get("event_type") == "integration_result"]
    blockers = [e for e in new_events if e.get("event_type") == "blocker"]

    print("\n--- Group Events Summary ---")
    if not new_events:
        print("No new group events since last sync.")
    else:
        print(f"Discovered {len(new_events)} new event(s):")
        for ev in new_events:
            ev_id = ev.get("event_id")
            ev_type = ev.get("event_type")
            author = ev.get("person_id")
            if ev_type == "change_published":
                print(f"  * [CHANGE] {ev.get('change_id')}: {ev.get('summary')} (by {author}, branch: {ev.get('branch')})")
                if ev.get("interface_changes"):
                    print(f"    ! Interface changes: {', '.join(ev.get('interface_changes'))}")
            elif ev_type == "review":
                print(f"  * [REVIEW] For {ev.get('change_id')}: verdict={ev.get('verdict')} by {author}")
            elif ev_type == "integration_result":
                print(f"  * [INT] {ev.get('change_id')} into {ev.get('target_branch')}: {ev.get('result')}")
            elif ev_type == "test_result":
                print(f"  * [TEST] Scope {ev.get('scope')}: {ev.get('automated_result')} ({ev.get('passed')} pass, {ev.get('failed')} fail)")
            elif ev_type == "blocker":
                print(f"  * [BLOCKER] {ev.get('summary')} (requested action: {ev.get('requested_action')})")
            else:
                print(f"  * [{ev_type}] {ev_id} by {author}")

    # Update last sync pointer
    if all_events:
        event_mgr.set_last_sync_event_id(all_events[-1]["event_id"])

    # 11. Quick validation if code changed
    if merged_canonical:
        validator = Validator(config.root_dir)
        ok, issues = validator.mechanical_check()
        if not ok:
            print(f"Validation warning after sync: {issues}")

    print("=== [SYNC] Done ===\n")
    return {
        "new_events_count": len(new_events),
        "new_changes": changes_pub,
        "blockers": blockers,
        "canonical_commit": canonical_commit
    }
