"""INT command implementation for groupctl."""
from pathlib import Path
from typing import Optional, Dict, Any, List
from groupctl.config import GroupConfig
from groupctl.repo import GitRepo
from groupctl.events import EventManager
from groupctl.validation import Validator


def run_int(
    config: GroupConfig,
    repo: GitRepo,
    change_id: str,
    semantic_review_verdict: str = "pass",
    auto_resolve_handler=None
) -> Optional[Dict[str, Any]]:
    print(f"=== [INT] Integrating change {change_id} ===")
    
    # 1. Fetch remote & metadata discovery
    repo.fetch_all()
    event_mgr = EventManager(config)
    event_mgr.sync_events_from_repo(repo)
    
    # 2. Locate change_published event
    change_event = event_mgr.find_change_event(change_id)
    if not change_event:
        print(f"Error: Change '{change_id}' not found in .group/events/.")
        return None

    src_branch = change_event.get("branch")
    src_commit = change_event.get("commit")
    target_branch = repo.get_current_branch()

    print(f"Integrating {change_id} ({src_branch} @ {src_commit[:8] if src_commit else 'unknown'}) into {target_branch}")
    print(f"Summary: {change_event.get('summary')}")
    if change_event.get("interface_changes"):
        print(f"Interface changes: {', '.join(change_event.get('interface_changes'))}")

    # 5. Inspect diff
    diff_text = repo.get_diff_between(target_branch, src_commit)
    print(f"Inspected diff size: {len(diff_text.splitlines())} line(s).")

    # 7. Merge into current target branch
    print(f"Executing git merge for {src_commit[:8]}...")
    merge_ok, merge_msg = repo.merge(src_commit, message=f"Integrate {change_id} from {src_branch}")
    
    conflicted_files = []
    conflict_resolution_summary = ""
    result_status = "success"

    # 8. Check conflicts
    if not merge_ok or repo.has_conflicts():
        conflicted_files = repo.get_conflicted_files()
        print(f"\n[CONFLICT DETECTED] in files: {', '.join(conflicted_files)}")
        
        if auto_resolve_handler:
            print("Invoking conflict resolution handler...")
            res_ok, summary_text = auto_resolve_handler(conflicted_files, repo)
            if res_ok:
                conflict_resolution_summary = summary_text
                print(f"Resolved conflict: {summary_text}")
                repo.add(*conflicted_files)
                repo.commit(f"Resolve conflict integrating {change_id}: {summary_text}")
            else:
                result_status = "needs_human"
                conflict_resolution_summary = "Automatic/Agent resolution failed; human intervention required."
                print(conflict_resolution_summary)
        else:
            result_status = "needs_human"
            conflict_resolution_summary = f"Git conflicts present in {conflicted_files}. Agent or human resolution needed."
            print("Please resolve conflicts, or groupctl will record a blocker.")

    # If merge still conflicted
    if repo.has_conflicts() or result_status == "needs_human":
        # Create blocker event
        blocker = event_mgr.create_event(
            event_type="blocker",
            specific_data={
                "summary": f"Cannot safely resolve conflicts integrating {change_id}",
                "blocking_change_id": change_id,
                "requested_action": f"Resolve conflict in {', '.join(conflicted_files)} and complete verification."
            },
            related_events=[change_event["event_id"]],
            person_id=config.person_id
        )
        print(f"Recorded blocker event {blocker['event_id']}")
        return {
            "result": "needs_human",
            "conflicts": conflicted_files,
            "blocker_event": blocker["event_id"]
        }

    # 10 & 11. Mechanical checks
    validator = Validator(config.root_dir)
    mech_ok, issues = validator.mechanical_check()
    build_verdict = "pass" if mech_ok else "fail"
    if not mech_ok:
        print(f"Mechanical check failed: {issues}")
        result_status = "failed"

    # 12. Run tests
    test_data = validator.run_tests()
    test_verdict = test_data.get("automated_result", "not_available")
    if test_verdict != "pass":
        print(f"Automated tests failed after integration: {test_data.get('summary')}")
        result_status = "failed"
    else:
        print(f"Automated tests passed: {test_data.get('passed')} test(s).")

    # 13. Semantic review
    print(f"Semantic compatibility review: {semantic_review_verdict}")
    if semantic_review_verdict != "pass":
        result_status = "failed"

    curr_merge_commit = repo.get_current_commit()

    # 14. Create integration_result event
    int_event_data = {
        "change_id": change_id,
        "target_branch": target_branch,
        "result": result_status,
        "merge_commit": curr_merge_commit,
        "conflicts": conflicted_files,
        "conflict_resolution_summary": conflict_resolution_summary or "Clean merge, no conflicts.",
        "verification": {
            "build": build_verdict,
            "tests": test_verdict,
            "semantic_review": semantic_review_verdict
        },
        "summary": f"Integration of {change_id} into {target_branch}: {result_status}"
    }

    event = event_mgr.create_event(
        event_type="integration_result",
        specific_data=int_event_data,
        related_events=[change_event["event_id"]],
        person_id=config.person_id
    )

    # Commit event
    event_file_rel = f".group/events/{event['event_id']}.json"
    repo.add(event_file_rel)
    repo.commit(f"Record integration result for {change_id} ({event['event_id']})")
    repo.push(branch=target_branch)

    print(f"\n[INT Result] {result_status.upper()}")
    print(f"  Event ID: {event['event_id']}")
    print(f"  Verification: {int_event_data['verification']}")
    print("=== [INT] Done ===\n")

    return event
