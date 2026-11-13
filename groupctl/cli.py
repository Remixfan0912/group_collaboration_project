"""Command-line interface for groupctl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional

from .core import GroupCtlError, GroupRepo


def _print_output(data: Any, as_json: bool = False, title: Optional[str] = None) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if title:
        print(f"=== {title} ===")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groupctl",
        description="Deterministic collaboration CLI for Human + AI programming groups (Protocol v0.1).",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Path to the Git repository root (defaults to current working directory).",
    )
    parser.add_argument(
        "--person",
        type=str,
        default=None,
        help="Override active person_id for this invocation.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON only.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize .group/ repository structure.")
    p_init.add_argument("--group-id", required=True, help="Group identifier (e.g. G-12).")
    p_init.add_argument("--canonical-branch", default="main", help="Canonical branch name (default: main).")
    p_init.add_argument("--assignment", default=None, help="Initial assignment markdown content.")
    p_init.add_argument("--no-commit", action="store_true", help="Do not create an initial Git commit.")

    # member
    p_member = subparsers.add_parser("member", help="Manage group membership descriptors.")
    member_sub = p_member.add_subparsers(dest="member_cmd", required=True)

    p_m_add = member_sub.add_parser("add", help="Register a member in .group/members/<person_id>.json.")
    p_m_add.add_argument("person_id", help="Person ID (e.g. P17).")
    p_m_add.add_argument("display_name", help="Human display name (e.g. Susan).")
    p_m_add.add_argument("--no-use", action="store_true", help="Do not set as active local person_id.")
    p_m_add.add_argument("--no-commit", action="store_true", help="Do not commit the member file immediately.")
    p_m_add.add_argument("--push", action="store_true", help="Push current branch after committing.")

    member_sub.add_parser("list", help="List all discovered group members.")

    # use-member
    p_use = subparsers.add_parser("use-member", help="Set the active local person_id in .group/local/state.json.")
    p_use.add_argument("person_id", help="Person ID (e.g. P17).")

    # branch
    p_branch = subparsers.add_parser("branch", help="Create or switch to personal work branch people/<person_id>/<topic>.")
    p_branch.add_argument("topic", help="Branch topic (e.g. parser, renderer, tests).")
    p_branch.add_argument("--base", default=None, help="Base branch/ref to branch from (default: canonical branch).")

    # status / STATUS
    p_status = subparsers.add_parser("status", aliases=["STATUS"], help="Report local state relative to the group.")
    p_status.add_argument("--no-fetch", action="store_true", help="Skip fetching remote metadata.")

    # sync / SYNC
    p_sync = subparsers.add_parser("sync", aliases=["SYNC"], help="Synchronize working context with the group.")
    p_sync.add_argument("--no-update-canonical", action="store_true", help="Do not merge canonical branch updates.")
    p_sync.add_argument("--no-validate", action="store_true", help="Skip quick validation after canonical update.")

    # pub / PUB
    p_pub = subparsers.add_parser("pub", aliases=["PUB"], help="Publish completed local work and a change_published event.")
    p_pub.add_argument("-m", "--summary", required=True, help="Summary of the change being published.")
    p_pub.add_argument("--change-id", default=None, help="Explicit change ID (e.g. C-17). Auto-generated if omitted.")
    p_pub.add_argument(
        "--interface-change",
        action="append",
        default=[],
        help="Interface or assumption change notice (may be passed multiple times).",
    )
    p_pub.add_argument(
        "--known-issue",
        action="append",
        default=[],
        help="Known issue in this change (may be passed multiple times).",
    )
    p_pub.add_argument("--no-propose", action="store_true", help="Set proposed_for_integration=false.")

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect a published change event and its actual Git diff.")
    p_inspect.add_argument("change_id", help="Change ID (e.g. C-17).")

    # rev / REV
    p_rev = subparsers.add_parser("rev", aliases=["REV"], help="Review a teammate's published change and publish a review event.")
    p_rev.add_argument("change_id", help="Change ID to review (e.g. C-17).")
    p_rev.add_argument(
        "--verdict",
        required=True,
        choices=["accept", "accept_with_changes", "reject", "needs_more_evidence"],
        help="Review verdict.",
    )
    p_rev.add_argument("-m", "--summary", required=True, help="Review summary.")
    p_rev.add_argument("--issue", action="append", default=[], help="Specific issue found (repeatable).")
    p_rev.add_argument("--no-tests", action="store_true", help="Skip running automated tests during review.")

    # int / INT
    p_int = subparsers.add_parser("int", aliases=["INT"], help="Integrate a teammate's published change and verify 3 levels.")
    p_int.add_argument("change_id", help="Change ID to integrate (e.g. C-17).")
    p_int.add_argument(
        "--complete",
        action="store_true",
        help="Complete an integration after conflicts were resolved in the working tree.",
    )
    p_int.add_argument(
        "--on-conflict",
        choices=["pause", "blocker"],
        default="pause",
        help="Behavior when Git reports a conflict: 'pause' for resolution (default) or abort and publish a 'blocker'.",
    )
    p_int.add_argument(
        "--conflict-summary",
        default="",
        help="Explanation of how conflicts were resolved.",
    )
    p_int.add_argument(
        "--semantic-review",
        choices=["pass", "fail"],
        default="pass",
        help="Level 3 semantic review outcome assessed by the agent.",
    )
    p_int.add_argument(
        "--semantic-notes",
        default="",
        help="Notes from the Level 3 semantic compatibility review.",
    )

    # test / TEST
    p_test = subparsers.add_parser("test", aliases=["TEST"], help="Run tests and publish a test_result event.")
    p_test.add_argument("scope", nargs="?", default="current_branch", help="Scope: current_branch (default), main, or C-<id>.")
    p_test.add_argument(
        "--human-check",
        action="append",
        default=[],
        help="Concrete human check procedure required (repeatable).",
    )
    p_test.add_argument(
        "--cmd",
        action="append",
        default=[],
        help="Additional test command to execute (repeatable).",
    )
    p_test.add_argument("-m", "--summary", default=None, help="Custom test result summary.")

    # promote
    p_promote = subparsers.add_parser("promote", help="Promote a verified branch into the canonical branch (main).")
    p_promote.add_argument("branch", nargs="?", default=None, help="Source branch to promote (defaults to current branch).")

    # final / FINAL
    p_final = subparsers.add_parser("final", aliases=["FINAL"], help="Prepare or confirm group finalization.")
    p_final.add_argument(
        "--prepare",
        action="store_true",
        help="Generate .group/final/candidate.md and publish a final_candidate event (default if --confirm is not set).",
    )
    p_final.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm finalization: generate final_report.md, final.json, and publish final_result.",
    )
    p_final.add_argument(
        "--limitation",
        action="append",
        default=[],
        help="Known limitation to record in the final report (repeatable).",
    )
    p_final.add_argument(
        "--human-check",
        action="append",
        default=[],
        help="Human check status note for candidate report (repeatable).",
    )
    p_final.add_argument(
        "--allow-unmerged",
        action="store_true",
        help="Allow finalization even if unreviewed/unintegrated published changes exist.",
    )

    # events
    p_events = subparsers.add_parser("events", help="List discovered collaboration events.")
    p_events.add_argument("--type", dest="event_type", default=None, help="Filter by event_type.")

    # finding / question / answer / blocker
    p_finding = subparsers.add_parser("finding", help="Publish a finding event.")
    p_finding.add_argument("-m", "--summary", required=True, help="Finding summary.")
    p_finding.add_argument("--evidence", action="append", default=[], help="Evidence item (repeatable).")

    p_question = subparsers.add_parser("question", help="Publish a question event.")
    p_question.add_argument("--id", required=True, dest="question_id", help="Question ID (e.g. Q-31).")
    p_question.add_argument("-m", "--text", required=True, help="Question text.")
    p_question.add_argument("--blocking", action="store_true", help="Mark question as blocking.")

    p_answer = subparsers.add_parser("answer", help="Publish an answer event.")
    p_answer.add_argument("--id", required=True, dest="question_id", help="Question ID being answered (e.g. Q-31).")
    p_answer.add_argument("-m", "--text", required=True, help="Answer text.")
    p_answer.add_argument("--question-event", default=None, help="Related question event_id.")

    p_blocker = subparsers.add_parser("blocker", help="Publish a blocker event.")
    p_blocker.add_argument("--change-id", required=True, help="Blocking change ID (e.g. C-17).")
    p_blocker.add_argument("-m", "--summary", required=True, help="Blocker summary.")
    p_blocker.add_argument("--action", required=True, help="Requested human/group action.")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = Path(args.repo).resolve() if args.repo else Path.cwd().resolve()
    repo = GroupRepo(repo_root)
    cmd = args.command.lower()

    try:
        if cmd == "init":
            out = repo.init_repo(
                group_id=args.group_id,
                canonical_branch=args.canonical_branch,
                assignment_text=args.assignment,
                commit_initial=not args.no_commit,
            )
            _print_output(out, as_json=args.json, title="Initialized Group Repository")

        elif cmd == "member":
            if args.member_cmd == "add":
                out = repo.add_member(
                    person_id=args.person_id,
                    display_name=args.display_name,
                    set_active=not args.no_use,
                    commit=not args.no_commit,
                    push=args.push,
                )
                _print_output(out, as_json=args.json, title=f"Registered Member {args.person_id}")
            elif args.member_cmd == "list":
                out = repo.discover_all_members()
                _print_output(out, as_json=args.json, title="Group Members")

        elif cmd == "use-member":
            out = repo.use_member(args.person_id)
            _print_output(out, as_json=args.json, title=f"Active Member Set to {args.person_id}")

        elif cmd == "branch":
            branch_name = repo.start_personal_branch(
                topic=args.topic,
                person_id=args.person,
                base_ref=args.base,
            )
            _print_output(
                {"branch": branch_name, "commit": repo.current_commit(short=True)},
                as_json=args.json,
                title="Switched to Personal Branch",
            )

        elif cmd == "status":
            out = repo.cmd_status(fetch=not args.no_fetch)
            _print_output(out, as_json=args.json, title="STATUS")

        elif cmd == "sync":
            out = repo.cmd_sync(
                update_canonical=not args.no_update_canonical,
                run_quick_validation=not args.no_validate,
            )
            _print_output(out, as_json=args.json, title="SYNC")

        elif cmd == "pub":
            out = repo.cmd_pub(
                summary=args.summary,
                change_id=args.change_id,
                interface_changes=args.interface_change,
                known_issues=args.known_issue,
                proposed_for_integration=not args.no_propose,
                person_id=args.person,
            )
            _print_output(out, as_json=args.json, title=f"PUB ({out['change_id']})")

        elif cmd == "inspect":
            out = repo.inspect_change(args.change_id)
            _print_output(out, as_json=args.json, title=f"INSPECT {args.change_id}")

        elif cmd == "rev":
            out = repo.cmd_rev(
                change_id=args.change_id,
                verdict=args.verdict,
                summary=args.summary,
                issues=args.issue,
                run_tests=not args.no_tests,
                person_id=args.person,
            )
            _print_output(out, as_json=args.json, title=f"REV {args.change_id} ({args.verdict})")

        elif cmd == "int":
            out = repo.cmd_int(
                change_id=args.change_id,
                complete_resolved=args.complete,
                on_conflict=args.on_conflict,
                conflict_resolution_summary=args.conflict_summary,
                semantic_review=args.semantic_review,
                semantic_notes=args.semantic_notes,
                person_id=args.person,
            )
            _print_output(out, as_json=args.json, title=f"INT {args.change_id} ({out['status']})")
            if out["status"] in ("conflict_paused", "blocked", "failed"):
                return 2

        elif cmd == "test":
            out = repo.cmd_test(
                scope=args.scope,
                human_checks_required=args.human_check,
                extra_commands=args.cmd,
                summary=args.summary,
                person_id=args.person,
            )
            _print_output(out, as_json=args.json, title=f"TEST ({out['automated_result']})")

        elif cmd == "promote":
            out = repo.promote_to_canonical(source_branch=args.branch)
            _print_output(out, as_json=args.json, title="PROMOTE TO CANONICAL")

        elif cmd == "final":
            if args.confirm:
                out = repo.cmd_final_confirm(
                    known_limitations=args.limitation,
                    person_id=args.person,
                )
                _print_output(out, as_json=args.json, title="FINAL CONFIRMED")
            else:
                out = repo.cmd_final_prepare(
                    known_limitations=args.limitation,
                    human_checks_required=args.human_check,
                    allow_unmerged=args.allow_unmerged,
                    person_id=args.person,
                )
                _print_output(out, as_json=args.json, title="FINAL CANDIDATE PREPARED")

        elif cmd == "events":
            evs = repo.discover_all_events()
            if args.event_type:
                evs = [e for e in evs if e.get("event_type") == args.event_type]
            _print_output(evs, as_json=args.json, title=f"Collaboration Events ({len(evs)})")

        elif cmd == "finding":
            ev = repo.write_and_publish_event(
                event_type="finding",
                payload={"summary": args.summary, "evidence": args.evidence or ["Observed in local testing."]},
                person_id=args.person,
            )
            _print_output(ev, as_json=args.json, title="Published Finding")

        elif cmd == "question":
            ev = repo.write_and_publish_event(
                event_type="question",
                payload={"question_id": args.question_id, "text": args.text, "blocking": bool(args.blocking)},
                person_id=args.person,
            )
            _print_output(ev, as_json=args.json, title=f"Published Question {args.question_id}")

        elif cmd == "answer":
            related = [args.question_event] if args.question_event else []
            if not related:
                # Auto-discover matching question event_id
                for e in repo.discover_all_events():
                    if e.get("event_type") == "question" and e.get("question_id") == args.question_id:
                        related.append(e["event_id"])
            ev = repo.write_and_publish_event(
                event_type="answer",
                payload={"question_id": args.question_id, "text": args.text},
                related_events=related,
                person_id=args.person,
            )
            _print_output(ev, as_json=args.json, title=f"Published Answer to {args.question_id}")

        elif cmd == "blocker":
            ev = repo.write_and_publish_event(
                event_type="blocker",
                payload={
                    "blocking_change_id": args.change_id,
                    "summary": args.summary,
                    "requested_action": args.action,
                },
                person_id=args.person,
            )
            _print_output(ev, as_json=args.json, title=f"Published Blocker for {args.change_id}")

        return 0

    except GroupCtlError as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[groupctl error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
