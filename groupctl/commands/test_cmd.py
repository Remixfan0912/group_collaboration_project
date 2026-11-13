"""TEST command implementation for groupctl."""
from pathlib import Path
from typing import Optional, Dict, Any, List
from groupctl.config import GroupConfig
from groupctl.repo import GitRepo
from groupctl.events import EventManager
from groupctl.validation import Validator


def run_test(
    config: GroupConfig,
    repo: GitRepo,
    scope: str = "current_branch",
    human_checks_required: Optional[List[str]] = None,
    summary_override: Optional[str] = None
) -> Dict[str, Any]:
    print(f"=== [TEST] Running tests (scope: {scope}) ===")
    
    # 1 & 2. Resolve scope & commit
    curr_commit = repo.get_current_commit()
    curr_branch = repo.get_current_branch()
    print(f"Testing commit: {curr_commit[:8] if curr_commit else 'unknown'} on branch: {curr_branch}")

    # 3 & 4. Run automated checks
    validator = Validator(config.root_dir)
    mech_ok, issues = validator.mechanical_check()
    test_data = validator.run_tests(scope=scope)

    if not mech_ok:
        print(f"Mechanical checks failed:\n" + "\n".join(f"  - {i}" for i in issues))
        auto_result = "fail"
    else:
        auto_result = test_data.get("automated_result", "not_available")

    passed = test_data.get("passed", 0)
    failed = test_data.get("failed", 0) + (1 if not mech_ok else 0)
    skipped = test_data.get("skipped", 0)
    commands = test_data.get("commands", [])

    summary = summary_override or f"All automated checks passed ({passed} passed)." if auto_result == "pass" else f"Test run produced failures ({failed} failed, {passed} passed)."

    event_data = {
        "scope": scope,
        "commit": curr_commit,
        "commands": commands,
        "automated_result": auto_result,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "human_checks_required": human_checks_required or [],
        "summary": summary
    }

    event_mgr = EventManager(config)
    event = event_mgr.create_event(
        event_type="test_result",
        specific_data=event_data,
        person_id=config.person_id
    )

    event_file_rel = f".group/events/{event['event_id']}.json"
    repo.add(event_file_rel)
    repo.commit(f"Publish test result for {curr_commit[:8]} ({auto_result})")
    if curr_branch:
        repo.push(branch=curr_branch)

    print(f"\n[TEST Result] {auto_result.upper()} - {passed} passed, {failed} failed, {skipped} skipped.")
    print(f"  Event ID: {event['event_id']}")
    if human_checks_required:
        print(f"  Human checks required:")
        for hc in human_checks_required:
            print(f"    - {hc}")
    print("=== [TEST] Done ===\n")

    return event
