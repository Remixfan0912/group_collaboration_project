"""FINAL command implementation for groupctl."""
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from groupctl.config import GroupConfig
from groupctl.repo import GitRepo
from groupctl.events import EventManager, get_iso_now
from groupctl.validation import Validator


def run_final(
    config: GroupConfig,
    repo: GitRepo,
    confirmed: bool = False,
    known_limitations: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    print("=== [FINAL] Beginning Group Finalization Procedure ===")
    
    # 1. Sync group metadata & canonical branch
    repo.fetch_all()
    canonical = config.canonical_branch
    canonical_commit = repo.get_commit_for_ref(canonical)
    if not canonical_commit:
        canonical_commit = repo.get_commit_for_ref(f"origin/{canonical}")
    
    if not canonical_commit:
        # Fallback to current commit if canonical branch ref isn't yet pushed
        canonical_commit = repo.get_current_commit()

    print(f"Target Canonical Branch: {canonical} (@ {canonical_commit[:8] if canonical_commit else 'unknown'})")

    # 3. Check published changes
    event_mgr = EventManager(config)
    all_events = event_mgr.list_events()

    published_changes = [e for e in all_events if e.get("event_type") == "change_published"]
    integration_results = [e for e in all_events if e.get("event_type") == "integration_result"]
    reviews = [e for e in all_events if e.get("event_type") == "review"]
    blockers = [e for e in all_events if e.get("event_type") == "blocker"]

    print(f"Total Published Changes: {len(published_changes)}")
    print(f"Total Integrations: {len(integration_results)}")
    print(f"Active Blockers: {len(blockers)}")

    # 6. Run final automated validation against current working tree
    validator = Validator(config.root_dir)
    mech_ok, mech_issues = validator.mechanical_check()
    test_data = validator.run_tests()

    auto_result = test_data.get("automated_result", "fail")
    print(f"Final Validation: {auto_result.upper()} ({test_data.get('passed')} passed, {test_data.get('failed')} failed)")

    limitations = known_limitations or []
    if auto_result != "pass":
        limitations.append(f"Automated tests failed during finalization: {test_data.get('summary')}")

    # Contributors list
    members = []
    if config.members_dir.exists():
        for m_file in config.members_dir.glob("*.json"):
            try:
                with open(m_file, "r", encoding="utf-8") as f:
                    m_data = json.load(f)
                    members.append(f"{m_data.get('person_id')} ({m_data.get('display_name')})")
            except Exception:
                pass
    if not members:
        members = [config.person_id or "P01"]

    # 9. Generate .group/final/candidate.md
    config.final_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = config.final_dir / "candidate.md"
    
    candidate_content = f"""# Proposed Final Candidate

## Canonical Commit
`{canonical_commit}`

## Status
{auto_result.upper()} (Passed: {test_data.get('passed')}, Failed: {test_data.get('failed')})

## Changes Considered
{chr(10).join(f"- {c.get('change_id')}: {c.get('summary')} (by {c.get('person_id')})" for c in published_changes) if published_changes else "None"}

## Known Limitations
{chr(10).join(f"- {lim}" for lim in limitations) if limitations else "- None identified."}

## Contributors
{', '.join(members)}
"""
    with open(candidate_path, "w", encoding="utf-8") as f:
        f.write(candidate_content)

    # 12. Create final_candidate event
    candidate_event = event_mgr.create_event(
        event_type="final_candidate",
        specific_data={
            "canonical_commit": canonical_commit,
            "candidate_report_path": ".group/final/candidate.md",
            "tests_considered": test_data.get("commands", []),
            "known_issues": limitations,
            "summary": "Generated final candidate report for human review."
        },
        person_id=config.person_id
    )

    print(f"\n[Generated Candidate Report]: {candidate_path}")
    print(candidate_content)

    if not confirmed:
        print("Final candidate generated. Review candidate.md above.")
        print("To complete finalization, invoke 'groupctl final --confirm'.")
        return {"candidate": str(candidate_path), "status": "candidate_generated"}

    # 11. Final confirmation: create final_report.md and final.json
    final_report_path = config.final_dir / "final_report.md"
    final_report_content = f"""# Group Final Report

## Assignment
Group Collaboration Programming Project (Group {config.group_id})

## Result
Integrated, verified multi-agent collaborative software system.

## Canonical Commit
`{canonical_commit}`

## Important Changes
{chr(10).join(f"- {c.get('change_id')}: {c.get('summary')} by {c.get('person_id')}" for c in published_changes) if published_changes else "Initial baseline implementation."}

## Validation
- Mechanical validation: {"PASS" if mech_ok else "FAIL"}
- Automated test suite: {auto_result.upper()} ({test_data.get('passed')} passed, {test_data.get('failed')} failed)
- Test commands run: {', '.join(test_data.get('commands', []))}

## Known Limitations
{chr(10).join(f"- {lim}" for lim in limitations) if limitations else "- None recorded."}

## Contributors
{', '.join(members)}
"""
    with open(final_report_path, "w", encoding="utf-8") as f:
        f.write(final_report_content)

    # Write final.json
    final_json_path = config.final_dir / "final.json"
    final_status = "completed_with_known_limitations" if limitations else "completed"
    final_json_data = {
        "protocol_version": config.protocol_version,
        "group_id": config.group_id,
        "canonical_branch": canonical,
        "canonical_commit": canonical_commit,
        "report_file": ".group/final/final_report.md",
        "initiated_by": config.person_id or "unknown",
        "created_at": get_iso_now(),
        "status": final_status,
        "known_limitations": limitations
    }
    with open(final_json_path, "w", encoding="utf-8") as f:
        json.dump(final_json_data, f, indent=2)

    # Create final_result event
    final_event = event_mgr.create_event(
        event_type="final_result",
        specific_data={
            "canonical_commit": canonical_commit,
            "final_report_path": ".group/final/final_report.md",
            "test_evidence": [f"{test_data.get('passed')} tests passed, automated_result={auto_result}"],
            "known_limitations": limitations,
            "initiated_by": config.person_id
        },
        related_events=[candidate_event["event_id"]],
        person_id=config.person_id
    )

    # Commit and push finalization artifacts to canonical branch
    repo.add(".group/final/", f".group/events/{final_event['event_id']}.json", f".group/events/{candidate_event['event_id']}.json")
    repo.commit(f"Finalize group project: {final_status} ({canonical_commit[:8]})")
    repo.push(branch=repo.get_current_branch())

    print(f"\n[FINAL Completed Successfully!]")
    print(f"  Final Report: {final_report_path}")
    print(f"  Final Envelope: {final_json_path}")
    print(f"  Final Result Event: {final_event['event_id']}")
    print(f"  Status: {final_status}")
    print("=== [FINAL] Done ===\n")

    return final_json_data
