"""Data models and schema validation for the .group/ repository and event contracts."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional

from . import PROTOCOL_VERSION

SUPPORTED_EVENT_TYPES = {
    "change_published",
    "finding",
    "question",
    "answer",
    "review",
    "test_result",
    "integration_result",
    "blocker",
    "final_candidate",
    "final_result",
}

ALLOWED_REVIEW_VERDICTS = {
    "accept",
    "accept_with_changes",
    "reject",
    "needs_more_evidence",
}

ALLOWED_TEST_RESULTS = {
    "pass",
    "fail",
    "partial",
    "not_available",
}

ALLOWED_INTEGRATION_RESULTS = {
    "success",
    "failed",
    "needs_human",
}

ALLOWED_FINAL_STATUS = {
    "completed",
    "completed_with_known_limitations",
}

COMMON_EVENT_FIELDS = [
    "protocol_version",
    "event_id",
    "event_type",
    "group_id",
    "person_id",
    "created_at",
    "related_events",
]

EVENT_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "change_published": [
        "change_id",
        "branch",
        "commit",
        "summary",
        "files_changed",
        "interface_changes",
        "tests_run",
        "known_issues",
        "proposed_for_integration",
    ],
    "finding": [
        "summary",
        "evidence",
    ],
    "question": [
        "question_id",
        "text",
        "blocking",
    ],
    "answer": [
        "question_id",
        "text",
    ],
    "review": [
        "change_id",
        "verdict",
        "summary",
        "issues",
        "tests_run",
    ],
    "test_result": [
        "scope",
        "commit",
        "commands",
        "automated_result",
        "passed",
        "failed",
        "skipped",
        "human_checks_required",
        "summary",
    ],
    "integration_result": [
        "change_id",
        "target_branch",
        "result",
        "merge_commit",
        "conflicts",
        "conflict_resolution_summary",
        "verification",
        "summary",
    ],
    "blocker": [
        "summary",
        "blocking_change_id",
        "requested_action",
    ],
    "final_candidate": [
        "canonical_commit",
        "candidate_report_path",
        "tests_considered",
        "known_issues",
    ],
    "final_result": [
        "canonical_commit",
        "final_report_path",
        "test_evidence",
        "known_limitations",
        "initiated_by",
    ],
}


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format with Z suffix."""
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_event_id(person_id: str, now: Optional[datetime.datetime] = None) -> str:
    """Generate an immutable event ID per 02_repository_contract.md Section 8:
    E-<UTC timestamp>-<person_id>-<short unique suffix>
    Example: E-20261016T021530Z-P17-a91f
    """
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:4]
    return f"E-{ts}-{person_id}-{suffix}"


def build_event_envelope(
    event_type: str,
    group_id: str,
    person_id: str,
    payload: Dict[str, Any],
    related_events: Optional[List[str]] = None,
    event_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Construct and validate a complete collaboration event dictionary."""
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise ValueError(f"Unsupported event_type: {event_type}")

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    ev: Dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "event_id": event_id or generate_event_id(person_id, now_dt),
        "event_type": event_type,
        "group_id": group_id,
        "person_id": person_id,
        "created_at": created_at or now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "related_events": list(related_events) if related_events else [],
    }
    ev.update(payload)
    validate_event(ev)
    return ev


def validate_event(event: Dict[str, Any]) -> None:
    """Validate an event dictionary against 03_event_format_contract.md."""
    for field in COMMON_EVENT_FIELDS:
        if field not in event:
            raise ValueError(f"Event missing required common field: '{field}'")

    if event["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError(
            f"Unsupported protocol_version '{event['protocol_version']}', expected '{PROTOCOL_VERSION}'"
        )

    event_type = event["event_type"]
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise ValueError(f"Unsupported event_type: '{event_type}'")

    if not isinstance(event["related_events"], list):
        raise ValueError("'related_events' must be a list")

    for req_field in EVENT_REQUIRED_FIELDS.get(event_type, []):
        if req_field not in event:
            raise ValueError(f"Event '{event_type}' missing required field: '{req_field}'")

    if event_type == "review":
        if event["verdict"] not in ALLOWED_REVIEW_VERDICTS:
            raise ValueError(
                f"Invalid review verdict '{event['verdict']}'. Allowed: {sorted(ALLOWED_REVIEW_VERDICTS)}"
            )
    elif event_type == "test_result":
        if event["automated_result"] not in ALLOWED_TEST_RESULTS:
            raise ValueError(
                f"Invalid automated_result '{event['automated_result']}'. Allowed: {sorted(ALLOWED_TEST_RESULTS)}"
            )
    elif event_type == "integration_result":
        if event["result"] not in ALLOWED_INTEGRATION_RESULTS:
            raise ValueError(
                f"Invalid integration result '{event['result']}'. Allowed: {sorted(ALLOWED_INTEGRATION_RESULTS)}"
            )
        ver = event.get("verification")
        if not isinstance(ver, dict):
            raise ValueError("'verification' in integration_result must be an object")
        for k in ("build", "tests", "semantic_review"):
            if k not in ver:
                raise ValueError(f"'verification' in integration_result missing '{k}'")


def validate_group_json(data: Dict[str, Any]) -> None:
    """Validate .group/group.json per 02_repository_contract.md Section 3."""
    for field in ("protocol_version", "group_id", "canonical_branch", "assignment_file"):
        if field not in data:
            raise ValueError(f"group.json missing required field: '{field}'")


def validate_member_json(data: Dict[str, Any]) -> None:
    """Validate .group/members/<person_id>.json per 02_repository_contract.md Section 4."""
    for field in ("protocol_version", "person_id", "display_name", "joined_at"):
        if field not in data:
            raise ValueError(f"member descriptor missing required field: '{field}'")


def validate_final_json(data: Dict[str, Any]) -> None:
    """Validate .group/final/final.json per 07_testing_and_finalization.md Section 9."""
    required = (
        "protocol_version",
        "group_id",
        "canonical_branch",
        "canonical_commit",
        "report_file",
        "initiated_by",
        "created_at",
        "status",
        "known_limitations",
    )
    for field in required:
        if field not in data:
            raise ValueError(f"final.json missing required field: '{field}'")
    if data["status"] not in ALLOWED_FINAL_STATUS:
        raise ValueError(
            f"Invalid final.json status '{data['status']}'. Allowed: {sorted(ALLOWED_FINAL_STATUS)}"
        )
