"""Command Line Interface for groupctl."""
import sys
import argparse
from pathlib import Path
from groupctl.config import GroupConfig, find_group_root
from groupctl.repo import GitRepo
from groupctl.commands.init_cmd import run_init
from groupctl.commands.sync_cmd import run_sync
from groupctl.commands.pub_cmd import run_pub
from groupctl.commands.int_cmd import run_int
from groupctl.commands.rev_cmd import run_rev
from groupctl.commands.test_cmd import run_test
from groupctl.commands.status_cmd import run_status
from groupctl.commands.final_cmd import run_final
from groupctl.events import EventManager


def main():
    parser = argparse.ArgumentParser(
        prog="groupctl",
        description="Group collaboration tool for multi-agent and human engineering teams."
    )
    parser.add_argument("--person-id", help="Override person_id for this operation")
    parser.add_argument("--repo-dir", help="Path to repository root (defaults to auto-discovery)")

    subparsers = parser.add_subparsers(dest="command", help="Collaboration command to run")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize .group directory structure")
    init_parser.add_argument("--group-id", default="G-01", help="Group identifier, e.g. G-12")
    init_parser.add_argument("--canonical-branch", default="main", help="Canonical branch name")
    init_parser.add_argument("--person-id", default="P01", help="Initial person ID, e.g. P17")
    init_parser.add_argument("--name", default="Student", help="Display name for person")

    # config
    cfg_parser = subparsers.add_parser("config", help="View or update local group configuration")
    cfg_parser.add_argument("--set-person-id", help="Set local active person ID")
    cfg_parser.add_argument("--name", help="Display name for person")

    # SYNC
    sync_parser = subparsers.add_parser("sync", help="Bring working context up to date with group")
    sync_parser.add_argument("--no-canonical-merge", action="store_true", help="Skip auto-merging canonical updates")

    # PUB
    pub_parser = subparsers.add_parser("pub", help="Publish local work as a structured change")
    pub_parser.add_argument("-m", "--summary", required=True, help="Summary of work completed")
    pub_parser.add_argument("--interfaces", nargs="*", help="List of modified interfaces or assumptions")
    pub_parser.add_argument("--issues", nargs="*", help="List of known issues or limitations")
    pub_parser.add_argument("--no-proposal", action="store_true", help="Do not propose for integration")

    # INT
    int_parser = subparsers.add_parser("int", help="Integrate a teammate's published change")
    int_parser.add_argument("change_id", help="Change ID to integrate, e.g. C-17")
    int_parser.add_argument("--semantic-verdict", default="pass", choices=["pass", "fail", "needs_attention"], help="Semantic review verdict")

    # REV
    rev_parser = subparsers.add_parser("rev", help="Review a teammate's published change")
    rev_parser.add_argument("change_id", help="Change ID to review, e.g. C-17")
    rev_parser.add_argument("--verdict", default="accept", choices=["accept", "accept_with_changes", "reject", "needs_more_evidence"], help="Review verdict")
    rev_parser.add_argument("-m", "--summary", help="Review comments summary")
    rev_parser.add_argument("--issues", nargs="*", help="Specific issues found")

    # TEST
    test_parser = subparsers.add_parser("test", help="Run tests and publish test evidence")
    test_parser.add_argument("scope", nargs="?", default="current_branch", help="Scope of test (current_branch, main, or change_id)")
    test_parser.add_argument("--human-checks", nargs="*", help="List of required human checks")

    # STATUS
    subparsers.add_parser("status", help="Report status relative to canonical state and events")

    # FINAL
    final_parser = subparsers.add_parser("final", help="Begin or finalize group project result")
    final_parser.add_argument("--confirm", action="store_true", help="Confirm candidate and finalize result")
    final_parser.add_argument("--limitations", nargs="*", help="Known limitations to record in report")

    # event helper
    ev_parser = subparsers.add_parser("event", help="Direct event operations")
    ev_sub = ev_parser.add_subparsers(dest="event_cmd")
    ev_add = ev_sub.add_parser("add", help="Add a custom event")
    ev_add.add_argument("--type", required=True, choices=["finding", "question", "answer", "blocker"], help="Event type")
    ev_add.add_argument("-m", "--summary", required=True, help="Summary or text")
    ev_add.add_argument("--related", nargs="*", help="Related event IDs")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    target_root = Path(args.repo_dir).resolve() if args.repo_dir else find_group_root()

    if args.command == "init":
        run_init(
            target_root,
            group_id=args.group_id,
            canonical_branch=args.canonical_branch,
            person_id=args.person_id,
            display_name=args.name
        )
        return

    # Load configuration
    config = GroupConfig(target_root, person_id=args.person_id)
    repo = GitRepo(config.root_dir)

    if args.command == "config":
        if args.set_person_id:
            config.set_local_person_id(args.set_person_id, display_name=args.name)
            print(f"Set active local person ID: {args.set_person_id}")
        else:
            print(f"Group ID: {config.group_id}")
            print(f"Person ID: {config.person_id}")
            print(f"Canonical Branch: {config.canonical_branch}")
        return

    if args.command == "sync":
        run_sync(config, repo, update_canonical=not args.no_canonical_merge)

    elif args.command == "pub":
        run_pub(
            config,
            repo,
            summary=args.summary,
            interface_changes=args.interfaces,
            known_issues=args.issues,
            proposed_for_integration=not args.no_proposal
        )

    elif args.command == "int":
        run_int(
            config,
            repo,
            change_id=args.change_id,
            semantic_review_verdict=args.semantic_verdict
        )

    elif args.command == "rev":
        run_rev(
            config,
            repo,
            change_id=args.change_id,
            verdict=args.verdict,
            summary=args.summary,
            issues=args.issues
        )

    elif args.command == "test":
        run_test(
            config,
            repo,
            scope=args.scope,
            human_checks_required=args.human_checks
        )

    elif args.command == "status":
        run_status(config, repo)

    elif args.command == "final":
        run_final(
            config,
            repo,
            confirmed=args.confirm,
            known_limitations=args.limitations
        )

    elif args.command == "event":
        if args.event_cmd == "add":
            em = EventManager(config)
            data = {"summary": args.summary}
            if args.type == "question":
                data = {"question_id": f"Q-{config.person_id}", "text": args.summary, "blocking": False}
            elif args.type == "answer":
                data = {"question_id": f"Q-ref", "text": args.summary}
            elif args.type == "blocker":
                data = {"summary": args.summary, "blocking_change_id": "none", "requested_action": "review"}
            elif args.type == "finding":
                data = {"summary": args.summary, "evidence": []}

            ev = em.create_event(args.type, data, related_events=args.related, person_id=config.person_id)
            print(f"Created event: {ev['event_id']}")


if __name__ == "__main__":
    main()
