"""REV command implementation for groupctl."""
from pathlib import Path
from typing import Optional, Dict, Any, List
from groupctl.config import GroupConfig
from groupctl.repo import GitRepo
from groupctl.events import EventManager
from groupctl.validation import Validator


ALLOWED_VERDICTS = ["accept", "accept_with_changes", "reject", "needs_more_evidence"]


def run_rev(
    config: GroupConfig,
    repo: GitRepo,
    change_id: str,
    verdict: str = "accept",
    summary: Optional[str] = None,
    issues: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    print(f"=== [REV] Reviewing change {change_id} ===")
    
    if verdict not in ALLOWED_VERDICTS:
        print(f"Error: Verdict must be one of {ALLOWED_VERDICTS}, got '{verdict}'.")
        return None

    repo.fetch_all()
    event_mgr = EventManager(config)
    event_mgr.sync_events_from_repo(repo)
    
    change_event = event_mgr.find_change_event(change_id)
    if not change_event:
        print(f"Error: Change '{change_id}' not found.")
        return None

    src_commit = change_event.get("commit", "HEAD")
    src_branch = change_event.get("branch", "")
    print(f"Target Change: {change_id} (Branch: {src_branch}, Commit: {src_commit[:8] if src_commit else 'unknown'})")
    print(f"Declared Summary: {change_event.get('summary')}")
    if change_event.get("interface_changes"):
        print(f"Interface changes: {', '.join(change_event.get('interface_changes'))}")

    # Inspect diff against canonical branch
    canonical = config.canonical_branch
    diff = repo.get_diff_between(canonical, src_commit)
    print(f"Inspected diff: {len(diff.splitlines())} lines.")

    # Run tests on current state to check for regressions
    validator = Validator(config.root_dir)
    test_data = validator.run_tests()
    tests_run = test_data.get("commands", [])

    rev_summary = summary or f"Reviewed {change_id}: verdict is {verdict}."
    rev_issues = issues or []

    review_data = {
        "change_id": change_id,
        "verdict": verdict,
        "summary": rev_summary,
        "issues": rev_issues,
        "tests_run": tests_run
    }

    event = event_mgr.create_event(
        event_type="review",
        specific_data=review_data,
        related_events=[change_event["event_id"]],
        person_id=config.person_id
    )

    curr_branch = repo.get_current_branch()
    event_file_rel = f".group/events/{event['event_id']}.json"
    repo.add(event_file_rel)
    repo.commit(f"Publish review for {change_id}: verdict {verdict}")
    if curr_branch:
        repo.push(branch=curr_branch)

    print(f"\n[REV Success] Published review for {change_id}!")
    print(f"  Verdict: {verdict}")
    print(f"  Summary: {rev_summary}")
    if rev_issues:
        print(f"  Issues noted: {', '.join(rev_issues)}")
    print("=== [REV] Done ===\n")

    return event
