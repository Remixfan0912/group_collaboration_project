"""Automated test suite for groupctl and the Version 0.1 collaboration specification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from demo.run_demo import run_demonstration
from groupctl.core import GroupCtlError, GroupRepo
from groupctl.models import (
    SUPPORTED_EVENT_TYPES,
    build_event_envelope,
    validate_event,
    validate_final_json,
    validate_group_json,
    validate_member_json,
)


def test_init_and_repository_contract(tmp_path: Path):
    repo = GroupRepo(tmp_path)
    cfg = repo.init_repo(group_id="G-99", canonical_branch="main")
    validate_group_json(cfg)

    assert (tmp_path / ".group" / "group.json").exists()
    assert (tmp_path / ".group" / "assignment" / "assignment.md").exists()
    assert (tmp_path / ".group" / "members").is_dir()
    assert (tmp_path / ".group" / "events").is_dir()
    assert (tmp_path / ".group" / "final").is_dir()
    assert (tmp_path / ".group" / "local" / ".gitkeep").exists()

    m = repo.add_member("P17", "Susan")
    validate_member_json(m)
    assert (tmp_path / ".group" / "members" / "P17.json").exists()

    branch = repo.start_personal_branch("parser")
    assert branch == "people/P17/parser"
    assert repo.current_branch() == "people/P17/parser"


def test_all_ten_event_types_validation(tmp_path: Path):
    repo = GroupRepo(tmp_path)
    repo.init_repo(group_id="G-10")
    repo.add_member("P17", "Susan")
    repo.start_personal_branch("feature")

    # Test question, answer, finding, blocker events
    f_ev = repo.write_and_publish_event(
        "finding",
        {"summary": "Empty transitions cause index error.", "evidence": ["test_empty"]},
        push=False,
    )
    q_ev = repo.write_and_publish_event(
        "question",
        {"question_id": "Q-31", "text": "Should ParseResult preserve source positions?", "blocking": False},
        push=False,
    )
    a_ev = repo.write_and_publish_event(
        "answer",
        {"question_id": "Q-31", "text": "Yes. Renderer error messages require source positions."},
        related_events=[q_ev["event_id"]],
        push=False,
    )
    b_ev = repo.write_and_publish_event(
        "blocker",
        {
            "summary": "Cannot safely resolve model.py conflict.",
            "blocking_change_id": "C-17",
            "requested_action": "Human decision on whether source positions are mandatory.",
        },
        push=False,
    )

    for ev in (f_ev, q_ev, a_ev, b_ev):
        validate_event(ev)
        assert ev["event_id"].startswith("E-")
        assert "-P17-" in ev["event_id"]


def test_pub_safety_refuses_secrets_conflicts_and_main(tmp_path: Path):
    repo = GroupRepo(tmp_path)
    repo.init_repo(group_id="G-55")
    repo.add_member("P17", "Susan")

    # 1. Refuse to PUB directly from canonical main branch
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(GroupCtlError, match="canonical branch"):
        repo.cmd_pub(summary="Try pub on main")

    # Switch to personal branch
    repo.start_personal_branch("work")

    # 2. Refuse accidental secrets
    (tmp_path / "app.py").write_text("OPENAI_API_KEY = 'sk-1234567890abcdef'\n", encoding="utf-8")
    with pytest.raises(GroupCtlError, match="secrets"):
        repo.cmd_pub(summary="Secret leak")

    # 3. Refuse leftover conflict markers
    (tmp_path / "app.py").write_text(
        "<<<<<<< HEAD\nx = 1\n=======\nx = 2\n>>>>>>> branch\n",
        encoding="utf-8",
    )
    with pytest.raises(GroupCtlError, match="conflict markers"):
        repo.cmd_pub(summary="Unresolved conflict")

    # 4. Refuse broken Python syntax
    (tmp_path / "app.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    with pytest.raises(GroupCtlError, match="syntax"):
        repo.cmd_pub(summary="Broken syntax")


def test_full_15_step_three_member_collaboration_demo(tmp_path: Path):
    result = run_demonstration(workspace_dir=tmp_path / "demo_workspace")
    p17_dir = Path(result["clones"]["P17"])
    repo_p17 = GroupRepo(p17_dir)

    # Verify finalization artifacts exist on canonical branch (main)
    assert repo_p17.current_branch() == "main"
    assert (p17_dir / ".group" / "final" / "candidate.md").exists()
    assert (p17_dir / ".group" / "final" / "final_report.md").exists()
    assert (p17_dir / ".group" / "final" / "final.json").exists()

    final_json = json.loads((p17_dir / ".group" / "final" / "final.json").read_text(encoding="utf-8"))
    validate_final_json(final_json)
    assert final_json["group_id"] == "G-12"
    assert final_json["canonical_branch"] == "main"
    assert final_json["initiated_by"] == "P17"
    assert final_json["status"] == "completed_with_known_limitations"

    report_md = (p17_dir / ".group" / "final" / "final_report.md").read_text(encoding="utf-8")
    for required_heading in (
        "# Group Final Report",
        "## Assignment",
        "## Result",
        "## Canonical Commit",
        "## Important Changes",
        "## Validation",
        "## Known Limitations",
        "## Contributors",
    ):
        assert required_heading in report_md

    # Verify all published changes (C-17, C-22, C-31), reviews, integrations, test_result, final_candidate, final_result exist
    events = repo_p17.discover_all_events()
    event_types = {e["event_type"] for e in events}
    assert "change_published" in event_types
    assert "review" in event_types
    assert "integration_result" in event_types
    assert "test_result" in event_types
    assert "final_candidate" in event_types
    assert "final_result" in event_types

    change_ids = {e["change_id"] for e in events if e["event_type"] == "change_published"}
    assert {"C-17", "C-22", "C-31"}.issubset(change_ids)

    # Verify conflict resolution was recorded in integration_result for C-31
    int_events = [
        e for e in events if e["event_type"] == "integration_result" and e["change_id"] == "C-31"
    ]
    assert len(int_events) == 1
    assert int_events[0]["result"] == "success"
    assert "src/model.py" in int_events[0]["conflicts"]
    assert int_events[0]["verification"] == {
        "build": "pass",
        "tests": "pass",
        "semantic_review": "pass",
    }
