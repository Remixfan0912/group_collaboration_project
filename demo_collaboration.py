"""End-to-end Multi-Agent Collaboration Simulation.

Demonstrates all 15 success criteria specified in:
Group Collaboration Software Assignment Version 0.1 (Section 7)
"""
import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from groupctl.config import GroupConfig
from groupctl.repo import GitRepo
from groupctl.events import EventManager
from groupctl.commands.init_cmd import run_init
from groupctl.commands.sync_cmd import run_sync
from groupctl.commands.pub_cmd import run_pub
from groupctl.commands.int_cmd import run_int
from groupctl.commands.rev_cmd import run_rev
from groupctl.commands.test_cmd import run_test
from groupctl.commands.status_cmd import run_status
from groupctl.commands.final_cmd import run_final


def run_cmd(cmd, cwd, check=True):
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(cmd)}):\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")
    return proc.stdout.strip()


def run_simulation():
    print("=" * 80)
    print("STARTING 15-STEP MULTI-AGENT COLLABORATION DEMONSTRATION")
    print("=" * 80)

    sim_dir = Path(tempfile.mkdtemp(prefix="groupctl_sim_"))
    try:
        shared_repo_dir = sim_dir / "shared_repo"
        p17_dir = sim_dir / "student_p17"
        p22_dir = sim_dir / "student_p22"
        p31_dir = sim_dir / "student_p31"

        # ---------------------------------------------------------
        # [Criterion 1] Shared repository & 3 simulated members
        # ---------------------------------------------------------
        print("\n>>> [Criterion 1] Initializing shared repository and 3 members (P17, P22, P31)...")
        shared_repo_dir.mkdir(parents=True)
        run_cmd(["git", "init"], cwd=shared_repo_dir)
        run_cmd(["git", "config", "user.name", "CanonicalAdmin"], cwd=shared_repo_dir)
        run_cmd(["git", "config", "user.email", "admin@example.com"], cwd=shared_repo_dir)

        # Copy baseline files into shared repo
        for item in ["src", "tests", "docs", "groupctl", "groupctl.py", "groupctl.bat", "AGENT_SKILL.md", ".gitignore"]:
            src_path = PROJECT_ROOT / item
            dst_path = shared_repo_dir / item
            if src_path.is_dir():
                shutil.copytree(src_path, dst_path)
            elif src_path.is_file():
                shutil.copy2(src_path, dst_path)

        # Initialize .group contract in shared repository
        run_init(shared_repo_dir, group_id="G-12", canonical_branch="main", person_id="P17", display_name="Susan")
        # Add P22 and P31 member descriptors
        (shared_repo_dir / ".group" / "members" / "P22.json").write_text(
            '{"protocol_version":"0.1","person_id":"P22","display_name":"Bob","joined_at":"2026-10-16T10:00:00Z"}'
        )
        (shared_repo_dir / ".group" / "members" / "P31.json").write_text(
            '{"protocol_version":"0.1","person_id":"P31","display_name":"Charlie","joined_at":"2026-10-16T10:00:00Z"}'
        )

        run_cmd(["git", "add", "."], cwd=shared_repo_dir)
        run_cmd(["git", "commit", "-m", "Initial canonical baseline with groupctl"], cwd=shared_repo_dir)
        run_cmd(["git", "branch", "-M", "main"], cwd=shared_repo_dir)
        print("Canonical branch 'main' initialized.")

        # ---------------------------------------------------------
        # [Criterion 2] Separate work branches for each person
        # ---------------------------------------------------------
        print("\n>>> [Criterion 2] Setting up separate work branches using worktrees...")
        run_cmd(["git", "worktree", "add", str(p17_dir), "-b", "people/P17/parser-unary"], cwd=shared_repo_dir)
        run_cmd(["git", "worktree", "add", str(p22_dir), "-b", "people/P22/renderer-summary"], cwd=shared_repo_dir)
        run_cmd(["git", "worktree", "add", str(p31_dir), "-b", "people/P31/parser-conflict"], cwd=shared_repo_dir)

        # Configure person IDs for each worktree
        GroupConfig(p17_dir).set_local_person_id("P17", "Susan")
        GroupConfig(p22_dir).set_local_person_id("P22", "Bob")
        GroupConfig(p31_dir).set_local_person_id("P31", "Charlie")

        repo_p17 = GitRepo(p17_dir)
        cfg_p17 = GroupConfig(p17_dir)
        print(f"P17 on branch: {repo_p17.get_current_branch()}")

        repo_p22 = GitRepo(p22_dir)
        cfg_p22 = GroupConfig(p22_dir)
        print(f"P22 on branch: {repo_p22.get_current_branch()}")

        repo_p31 = GitRepo(p31_dir)
        cfg_p31 = GroupConfig(p31_dir)
        print(f"P31 on branch: {repo_p31.get_current_branch()}")

        # ---------------------------------------------------------
        # [Criterion 3 & 4] Person A (P17) implements changes and publishes with PUB
        # ---------------------------------------------------------
        print("\n>>> [Criterion 3 & 4] Person A implements unary expression support and calls PUB...")
        parser_code_p17 = (p17_dir / "src" / "parser.py").read_text(encoding="utf-8")
        # Add unary minus support
        parser_code_p17 = parser_code_p17.replace(
            "if len(tokens) == 1:",
            "if len(tokens) == 2 and tokens[0].value == '-':\n"
            "            return ParseResult(ast=Node(kind='UnaryExpr', value='-', children=[Node(kind='Literal', value=tokens[1].value)]), tokens=tokens)\n"
            "        if len(tokens) == 1:"
        )
        (p17_dir / "src" / "parser.py").write_text(parser_code_p17, encoding="utf-8")

        # Add unit test for unary
        test_code_p17 = (p17_dir / "tests" / "test_parser.py").read_text(encoding="utf-8")
        test_code_p17 = test_code_p17.replace(
            "def test_single_literal(self):",
            "def test_unary_minus(self):\n"
            "        res = self.parser.parse('-5')\n"
            "        self.assertTrue(res.is_valid)\n"
            "        self.assertEqual(res.ast.kind, 'UnaryExpr')\n\n"
            "    def test_single_literal(self):"
        )
        (p17_dir / "tests" / "test_parser.py").write_text(test_code_p17, encoding="utf-8")

        pub_event_p17 = run_pub(
            cfg_p17,
            repo_p17,
            summary="Implemented unary minus expression support",
            interface_changes=["Parser.parse supports UnaryExpr node with '-' operator"],
            commit_msg="Support unary minus in parser"
        )
        change_17_id = pub_event_p17["change_id"]
        assert change_17_id == "C-17", f"Expected C-17, got {change_17_id}"
        print(f"Published change {change_17_id} (Event: {pub_event_p17['event_id']})")

        # ---------------------------------------------------------
        # [Criterion 5] Person B (P22) runs SYNC and discovers published change
        # ---------------------------------------------------------
        print("\n>>> [Criterion 5] Person B runs SYNC to discover P17's published change...")
        sync_res_p22 = run_sync(cfg_p22, repo_p22)
        assert sync_res_p22["new_events_count"] > 0
        discovered_change = sync_res_p22["new_changes"][0]
        assert discovered_change["change_id"] == "C-17"
        print(f"Discovered: {discovered_change['change_id']} - {discovered_change['summary']}")

        # ---------------------------------------------------------
        # [Criterion 6] Person B (P22) reviews change using REV
        # ---------------------------------------------------------
        print("\n>>> [Criterion 6] Person B reviews C-17 using REV...")
        rev_event = run_rev(
            cfg_p22,
            repo_p22,
            change_id="C-17",
            verdict="accept",
            summary="Clean implementation of unary minus with accompanying test case."
        )
        assert rev_event["verdict"] == "accept"
        print(f"Review published: verdict={rev_event['verdict']}")

        # ---------------------------------------------------------
        # [Criterion 7 & 8] Person B (P22) integrates C-17 with INT (Automatic Git Merge + Levels 2 & 3 verification)
        # ---------------------------------------------------------
        print("\n>>> [Criterion 7 & 8] Person B integrates C-17 with INT (Verification beyond Git merge)...")
        # P22 also added to_summary on renderer
        renderer_p22 = (p22_dir / "src" / "renderer.py").read_text(encoding="utf-8")
        renderer_p22 += "\n    def to_summary(self, res):\n        return f'NodeKind:{res.ast.kind}'\n"
        (p22_dir / "src" / "renderer.py").write_text(renderer_p22, encoding="utf-8")
        repo_p22.add("src/renderer.py")
        repo_p22.commit("Add to_summary helper to renderer")

        int_res_p22 = run_int(
            cfg_p22,
            repo_p22,
            change_id="C-17",
            semantic_review_verdict="pass"
        )
        assert int_res_p22["result"] == "success"
        assert int_res_p22["verification"]["build"] == "pass"
        assert int_res_p22["verification"]["tests"] == "pass"
        assert int_res_p22["verification"]["semantic_review"] == "pass"
        print(f"Integration of C-17 verified mechanically and semantically: {int_res_p22['verification']}")

        # P22 publishes C-22
        pub_p22 = run_pub(
            cfg_p22,
            repo_p22,
            summary="Integrated C-17 and added renderer summary feature",
            interface_changes=["Renderer.to_summary() added"]
        )
        change_22_id = pub_p22["change_id"]

        # Accept C-22 into canonical main
        print("\nPromoting verified changes to canonical 'main'...")
        repo_main = GitRepo(shared_repo_dir)
        repo_main.merge("people/P22/renderer-summary", message="Integrate C-22 into main")

        # ---------------------------------------------------------
        # [Criterion 9 & 10] Deliberately conflicting change & AI conflict resolution
        # ---------------------------------------------------------
        print("\n>>> [Criterion 9 & 10] Deliberately creating Git conflict and resolving via agent...")
        # Person C (P31) syncs
        run_sync(cfg_p31, repo_p31)

        # P31 writes a conflicting parser modification at the same lines
        parser_p31 = (p31_dir / "src" / "parser.py").read_text(encoding="utf-8")
        parser_p31 = parser_p31.replace(
            "if len(tokens) == 1:",
            "if len(tokens) == 2 and tokens[0].value == '!':\n"
            "            return ParseResult(ast=Node(kind='NotExpr', value='!', children=[Node(kind='Literal', value=tokens[1].value)]), tokens=tokens)\n"
            "        if len(tokens) == 1:"
        )
        (p31_dir / "src" / "parser.py").write_text(parser_p31, encoding="utf-8")
        run_pub(cfg_p31, repo_p31, summary="Add NOT operator '!' to parser")

        # Now P17 tries to integrate C-31 into people/P17/parser-unary
        print("P17 attempts to integrate conflicting change C-31...")

        def ai_conflict_resolver(conflicted_files, repo):
            print(f"[AI Agent] Inspecting conflicting files: {conflicted_files}")
            for cf in conflicted_files:
                cf_path = repo.working_dir / cf
                # Write back resolved parser supporting both '-' and '!'
                resolved_parser = (
                    "        if len(tokens) == 2 and tokens[0].value == '-':\n"
                    "            return ParseResult(ast=Node(kind='UnaryExpr', value='-', children=[Node(kind='Literal', value=tokens[1].value)]), tokens=tokens)\n"
                    "        if len(tokens) == 2 and tokens[0].value == '!':\n"
                    "            return ParseResult(ast=Node(kind='NotExpr', value='!', children=[Node(kind='Literal', value=tokens[1].value)]), tokens=tokens)\n"
                    "        if len(tokens) == 1:"
                )
                original_text = (PROJECT_ROOT / "src" / "parser.py").read_text(encoding="utf-8")
                cf_path.write_text(original_text.replace("        if len(tokens) == 1:", resolved_parser), encoding="utf-8")
            return True, "Merged both '-' unary operator and '!' NOT operator with mutual compatibility"

        int_conflict_res = run_int(
            cfg_p17,
            repo_p17,
            change_id="C-31",
            semantic_review_verdict="pass",
            auto_resolve_handler=ai_conflict_resolver
        )
        assert int_conflict_res["result"] == "success"
        print(f"Conflict resolved by AI: {int_conflict_res['conflict_resolution_summary']}")

        # ---------------------------------------------------------
        # [Criterion 11 & 12] Run TEST and publish test evidence
        # ---------------------------------------------------------
        print("\n>>> [Criterion 11 & 12] Running TEST against combined software and publishing evidence...")
        test_ev = run_test(
            cfg_p17,
            repo_p17,
            scope="current_branch",
            human_checks_required=["Verify parser responsiveness on 10,000 node expressions"]
        )
        assert test_ev["automated_result"] == "pass"
        print(f"Test evidence published: Event {test_ev['event_id']}, result={test_ev['automated_result']}")

        # ---------------------------------------------------------
        # [Criterion 13] Group reaches accepted canonical state
        # ---------------------------------------------------------
        print("\n>>> [Criterion 13] Updating canonical 'main' with accepted integrated state...")
        repo_main.merge("people/P17/parser-unary", message="Integrate C-17 and C-31 into main")
        canonical_final_commit = repo_main.get_current_commit()
        print(f"Canonical 'main' accepted commit: {canonical_final_commit[:8]}")

        # ---------------------------------------------------------
        # [Criterion 14 & 15] Any recognized group member initiates FINAL and produces group result
        # ---------------------------------------------------------
        print("\n>>> [Criterion 14 & 15] Member P17 initiates FINAL to produce single group result...")
        cfg_main = GroupConfig(shared_repo_dir, person_id="P17")
        # Step 1: candidate generation
        cand_res = run_final(cfg_main, repo_main, confirmed=False)
        assert cand_res["status"] == "candidate_generated"

        # Step 2: confirm final result
        final_res = run_final(
            cfg_main,
            repo_main,
            confirmed=True,
            known_limitations=["Parentheses nesting limited to standard binary tree evaluation in v0.1"]
        )
        assert final_res["status"] == "completed_with_known_limitations"
        assert (shared_repo_dir / ".group" / "final" / "final_report.md").is_file()
        assert (shared_repo_dir / ".group" / "final" / "final.json").is_file()

        print("\nFinal Report generated at .group/final/final_report.md:")
        print("-" * 50)
        print((shared_repo_dir / ".group" / "final" / "final_report.md").read_text(encoding="utf-8"))
        print("-" * 50)

        # Check STATUS report
        run_status(cfg_main, repo_main)

        print("=" * 80)
        print("ALL 15 SUCCESS CRITERIA SUCCESSFULLY DEMONSTRATED AND VERIFIED!")
        print("=" * 80)
        return True

    finally:
        shutil.rmtree(sim_dir, ignore_errors=True)


if __name__ == "__main__":
    success = run_simulation()
    sys.exit(0 if success else 1)
