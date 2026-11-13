"""End-to-End Version 0.1 Success Demonstration for groupctl.

Demonstrates all 15 requirements from 00_group_collaboration_assignment.md Section 7:
1. Three people (P17 Susan, P22 Bob, P31 Carol) use the same shared Git repository.
2. Each person has a separate work branch (people/P17/parser, people/P22/renderer, people/P31/tests).
3. Independently implement different changes.
4. Person A (P17) publishes a completed change (C-17) using PUB.
5. Person B (P22) runs SYNC and discovers P17's published change.
6. Person B reviews (REV C-17) and integrates (INT C-17) P17's change.
7. Git automatically merges C-17 cleanly.
8. System verifies Level 1 (Git), Level 2 (Build & pytest), and Level 3 (Semantic review).
9. A deliberately conflicting change (C-31 vs C-22 in src/model.py) produces a Git conflict.
10. The AI agent is guided through resolving the conflict, followed by 3-level verification.
11. A group member (P31) runs TEST against the combined software.
12. Test results are published as a test_result event so all group members can see them.
13. The group reaches an accepted canonical state on main.
14. A recognized group member (P17) initiates FINAL (prepare candidate -> human confirm).
15. FINAL produces one canonical group result (.group/final/final_report.md, final.json, final_result event).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from groupctl.core import GroupRepo, find_git_executable


def _handle_remove_readonly(func, path, exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _git(cwd: Path, args: list[str]) -> str:
    res = subprocess.run(
        [find_git_executable()] + args,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    return res.stdout.strip()


def run_demonstration(workspace_dir: Path | None = None) -> dict:
    base_dir = (workspace_dir or (ROOT / "demo" / "workspace")).resolve()
    if base_dir.exists():
        shutil.rmtree(base_dir, onerror=_handle_remove_readonly)
    base_dir.mkdir(parents=True, exist_ok=True)

    remote_path = base_dir / "remote.git"
    p17_dir = base_dir / "P17_clone"
    p22_dir = base_dir / "P22_clone"
    p31_dir = base_dir / "P31_clone"

    print("======================================================================")
    print("Group Collaboration Software v0.1 - 15-Step Success Demonstration")
    print("======================================================================")

    # 0. Create shared bare remote repository (simulating shared GitHub repo)
    _git(base_dir, ["init", "--bare", str(remote_path)])

    # 1. Initialize repository in P17's clone and register all 3 group members
    p17_dir.mkdir(parents=True, exist_ok=True)
    repo_p17 = GroupRepo(p17_dir)
    repo_p17.init_repo(
        group_id="G-12",
        canonical_branch="main",
        assignment_text=(
            "# Group Assignment: State-Machine Parser & Renderer\n\n"
            "Build a structured block parser and HTML/text renderer with source-position tracking.\n"
        ),
        commit_initial=False,
    )

    # Create initial starter codebase on main
    (p17_dir / "src").mkdir(exist_ok=True)
    (p17_dir / "tests").mkdir(exist_ok=True)
    (p17_dir / "src" / "__init__.py").write_text("", encoding="utf-8")

    (p17_dir / "src" / "model.py").write_text(
        '''"""Shared AST data model for the Group G-12 parser and renderer."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class BlockNode:
    name: str
    transitions: List[str] = field(default_factory=list)
    line: int = 1
    end_column: int = 1


@dataclass
class ParseResult:
    nodes: List[BlockNode]
    source_name: str = "<memory>"
''',
        encoding="utf-8",
    )

    (p17_dir / "src" / "parser.py").write_text(
        '''"""Parser module."""

from .model import BlockNode, ParseResult


class Parser:
    def parse(self, text: str, source_name: str = "<memory>") -> ParseResult:
        nodes = []
        for idx, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            nodes.append(BlockNode(name=line, transitions=[], line=idx, end_column=len(raw_line)))
        return ParseResult(nodes=nodes, source_name=source_name)
''',
        encoding="utf-8",
    )

    (p17_dir / "src" / "renderer.py").write_text(
        '''"""Renderer module."""

from .model import ParseResult


class Renderer:
    def render(self, result: ParseResult) -> str:
        lines = [f"Document({result.source_name}):"]
        for node in result.nodes:
            lines.append(f"  - {node.name} (line {node.line})")
        return "\\n".join(lines)
''',
        encoding="utf-8",
    )

    (p17_dir / "tests" / "test_project.py").write_text(
        '''"""Automated unit and integration tests for Group G-12."""

from src.parser import Parser
from src.renderer import Renderer


def test_basic_parse_and_render():
    p = Parser()
    r = Renderer()
    res = p.parse("Idle\\nRunning", source_name="demo.sm")
    out = r.render(res)
    assert "Document(demo.sm):" in out
    assert "- Idle (line 1)" in out
    assert "- Running (line 2)" in out
''',
        encoding="utf-8",
    )

    repo_p17.add_member("P17", "Susan", set_active=True, commit=False)
    repo_p17.add_member("P22", "Bob", set_active=False, commit=False)
    repo_p17.add_member("P31", "Carol", set_active=False, commit=False)
    repo_p17.use_member("P17", display_name="Susan")

    repo_p17.git(["add", "-A"])
    repo_p17.git(["commit", "-m", "Initial Group G-12 project skeleton and member records"])
    repo_p17.git(["remote", "add", "origin", str(remote_path)])
    repo_p17.push_current_branch()
    _git(remote_path, ["symbolic-ref", "HEAD", "refs/heads/main"])

    # Clone for P22 (Bob) and P31 (Carol)
    _git(base_dir, ["clone", str(remote_path), str(p22_dir)])
    _git(base_dir, ["clone", str(remote_path), str(p31_dir)])

    repo_p22 = GroupRepo(p22_dir)
    repo_p22.use_member("P22", display_name="Bob")

    repo_p31 = GroupRepo(p31_dir)
    repo_p31.use_member("P31", display_name="Carol")

    print("[Step 1-2] Created shared remote and 3 separate clones & personal branches:")
    b17 = repo_p17.start_personal_branch("parser")
    b22 = repo_p22.start_personal_branch("renderer")
    b31 = repo_p31.start_personal_branch("tests")
    print(f"  - P17 (Susan): {b17}")
    print(f"  - P22 (Bob):   {b22}")
    print(f"  - P31 (Carol): {b31}")

    # Step 3 & 4: P17 implements nested transition parsing and publishes C-17 via PUB
    (p17_dir / "src" / "parser.py").write_text(
        '''"""Parser module with transition arrow support."""

from .model import BlockNode, ParseResult


class Parser:
    def parse(self, text: str, source_name: str = "<memory>") -> ParseResult:
        nodes = []
        for idx, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "->" in line:
                name_part, trans_part = line.split("->", 1)
                name = name_part.strip()
                transitions = [t.strip() for t in trans_part.split(",") if t.strip()]
            else:
                name = line
                transitions = []
            nodes.append(
                BlockNode(
                    name=name,
                    transitions=transitions,
                    line=idx,
                    end_column=len(raw_line),
                )
            )
        return ParseResult(nodes=nodes, source_name=source_name)
''',
        encoding="utf-8",
    )

    (p17_dir / "tests" / "test_parser_transitions.py").write_text(
        '''"""Tests for P17 parser transitions."""

from src.parser import Parser


def test_parse_transitions_and_columns():
    p = Parser()
    res = p.parse("Idle -> Running, Error\\nRunning -> Done")
    assert len(res.nodes) == 2
    assert res.nodes[0].name == "Idle"
    assert res.nodes[0].transitions == ["Running", "Error"]
    assert res.nodes[0].end_column == len("Idle -> Running, Error")
''',
        encoding="utf-8",
    )

    pub_c17 = repo_p17.cmd_pub(
        summary="Implemented transition arrow parsing ('->') and preserved source end_column.",
        change_id="C-17",
        interface_changes=[
            "BlockNode.transitions now populated from 'State -> Next1, Next2' syntax.",
            "Parser.parse returns ParseResult with accurate line and end_column.",
        ],
    )
    print(f"[Step 3-4] P17 ran PUB -> published {pub_c17['change_id']} (event {pub_c17['event_id']})")

    # Meanwhile P22 (Bob) independently enhances Renderer on people/P22/renderer
    (p22_dir / "src" / "renderer.py").write_text(
        '''"""Renderer module with transition formatting."""

from .model import ParseResult


class Renderer:
    def render(self, result: ParseResult) -> str:
        lines = [f"Document({result.source_name}):"]
        for node in result.nodes:
            trans_str = f" -> {', '.join(node.transitions)}" if node.transitions else ""
            lines.append(f"  - {node.name}{trans_str} (line {node.line}) [col {node.end_column}]")
        return "\\n".join(lines)
''',
        encoding="utf-8",
    )
    repo_p22.git(["add", "src/renderer.py"])
    repo_p22.git(["commit", "-m", "Format transitions and source positions in Renderer"])

    # Step 5: P22 runs SYNC and discovers P17's C-17
    sync_p22 = repo_p22.cmd_sync()
    print(
        f"[Step 5]   P22 ran SYNC -> discovered {sync_p22['new_events_count']} new event(s): "
        f"{[e['change_id'] for e in sync_p22['new_events'] if e.get('change_id')]}"
    )

    # Step 6: P22 reviews C-17 using REV C-17, then integrates C-17 using INT C-17
    rev_c17 = repo_p22.cmd_rev(
        change_id="C-17",
        verdict="accept",
        summary="Reviewed C-17 diff and tests. Transition parsing and end_column tracking match Renderer expectations.",
    )
    print(f"[Step 6a]  P22 ran REV C-17 -> verdict='{rev_c17['verdict']}' (event {rev_c17['review_event_id']})")

    # Step 7 & 8: Clean Git merge + 3-level verification (Git + Build/Tests + Semantic review)
    int_c17 = repo_p22.cmd_int(
        change_id="C-17",
        semantic_review="pass",
        semantic_notes="Verified Parser.parse transitions list and end_column integrate cleanly with Renderer.render.",
    )
    print(
        f"[Step 6b-8] P22 ran INT C-17 -> status='{int_c17['status']}', "
        f"verification={int_c17['verification']['level_2_tests']}, semantic={int_c17['verification']['level_3_semantic_review']}"
    )

    # P22 also modifies src/model.py to add a helper method and publishes C-22
    (p22_dir / "src" / "model.py").write_text(
        '''"""Shared AST data model for the Group G-12 parser and renderer."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class BlockNode:
    name: str
    transitions: List[str] = field(default_factory=list)
    line: int = 1
    end_column: int = 1

    def has_transitions(self) -> bool:
        """Return True when this block transitions to at least one target state."""
        return len(self.transitions) > 0


@dataclass
class ParseResult:
    nodes: List[BlockNode]
    source_name: str = "<memory>"

    def summary_label(self) -> str:
        return f"{self.source_name} ({len(self.nodes)} blocks)"
''',
        encoding="utf-8",
    )
    pub_c22 = repo_p22.cmd_pub(
        summary="Integrated C-17, enhanced Renderer transition output, and added model summary helpers.",
        change_id="C-22",
        interface_changes=["Added BlockNode.has_transitions() and ParseResult.summary_label()."],
    )
    print(f"[Step 8b]  P22 ran PUB -> published {pub_c22['change_id']} (event {pub_c22['event_id']})")

    # Step 9: P31 (Carol) creates a deliberately conflicting modification in src/model.py on people/P31/tests
    (p31_dir / "src" / "model.py").write_text(
        '''"""Shared AST data model for the Group G-12 parser and renderer."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class BlockNode:
    name: str
    transitions: List[str] = field(default_factory=list)
    line: int = 1
    end_column: int = 1

    def is_terminal(self) -> bool:
        """Return True when this block has no outgoing transitions."""
        return len(self.transitions) == 0


@dataclass
class ParseResult:
    nodes: List[BlockNode]
    source_name: str = "<memory>"

    def node_names(self) -> List[str]:
        return [n.name for n in self.nodes]
''',
        encoding="utf-8",
    )
    pub_c31 = repo_p31.cmd_pub(
        summary="Added BlockNode.is_terminal() and ParseResult.node_names() helpers in model.py.",
        change_id="C-31",
        interface_changes=["Added BlockNode.is_terminal() and ParseResult.node_names()."],
    )
    print(f"[Step 9a]  P31 ran PUB -> published conflicting change {pub_c31['change_id']} (event {pub_c31['event_id']})")

    # P22 attempts to integrate C-31 -> triggers a Git conflict in src/model.py!
    int_c31_conflict = repo_p22.cmd_int("C-31")
    assert int_c31_conflict["status"] == "conflict_paused", f"Expected conflict_paused, got {int_c31_conflict}"
    print(
        f"[Step 9b]  P22 ran INT C-31 -> Git conflict detected and paused in {int_c31_conflict['conflicts']}"
    )

    # Step 10: AI agent inspects both intents and resolves the conflict in src/model.py by preserving both helpers
    (p22_dir / "src" / "model.py").write_text(
        '''"""Shared AST data model for the Group G-12 parser and renderer."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class BlockNode:
    name: str
    transitions: List[str] = field(default_factory=list)
    line: int = 1
    end_column: int = 1

    def has_transitions(self) -> bool:
        """Return True when this block transitions to at least one target state."""
        return len(self.transitions) > 0

    def is_terminal(self) -> bool:
        """Return True when this block has no outgoing transitions."""
        return len(self.transitions) == 0


@dataclass
class ParseResult:
    nodes: List[BlockNode]
    source_name: str = "<memory>"

    def summary_label(self) -> str:
        return f"{self.source_name} ({len(self.nodes)} blocks)"

    def node_names(self) -> List[str]:
        return [n.name for n in self.nodes]
''',
        encoding="utf-8",
    )

    # Add comprehensive test covering both P22 and P31 model methods
    (p22_dir / "tests" / "test_combined_model.py").write_text(
        '''"""Combined tests verifying conflict resolution between C-22 and C-31."""

from src.parser import Parser
from src.renderer import Renderer


def test_combined_helpers_and_rendering():
    parser = Parser()
    renderer = Renderer()
    result = parser.parse("Start -> Finish\\nFinish", source_name="workflow.sm")
    assert result.summary_label() == "workflow.sm (2 blocks)"
    assert result.node_names() == ["Start", "Finish"]
    assert result.nodes[0].has_transitions() is True
    assert result.nodes[0].is_terminal() is False
    assert result.nodes[1].has_transitions() is False
    assert result.nodes[1].is_terminal() is True
    rendered = renderer.render(result)
    assert "Start -> Finish (line 1) [col 15]" in rendered
''',
        encoding="utf-8",
    )

    int_c31_done = repo_p22.cmd_int(
        change_id="C-31",
        complete_resolved=True,
        conflict_resolution_summary=(
            "Combined P22's has_transitions()/summary_label() and P31's is_terminal()/node_names() in src/model.py."
        ),
        semantic_review="pass",
        semantic_notes="Both helper sets are complementary and pass combined unit & integration tests.",
    )
    print(
        f"[Step 10]  P22 resolved conflict & ran INT C-31 --complete -> status='{int_c31_done['status']}', "
        f"merge_commit={int_c31_done['merge_commit']}"
    )

    # Step 13 (promote to canonical main) & Step 11-12 (P31 runs TEST and publishes test_result)
    promote_out = repo_p22.promote_to_canonical(source_branch="people/P22/renderer")
    print(
        f"[Step 13]  Promoted verified integrated work to canonical branch '{promote_out['canonical_branch']}' "
        f"@ {promote_out['canonical_commit'][:7]}"
    )

    # P31 syncs with canonical main and runs TEST main
    repo_p31.git(["checkout", "main"])
    repo_p31.git(["pull", "origin", "main"])
    repo_p31.cmd_sync()
    test_out = repo_p31.cmd_test(
        scope="main",
        human_checks_required=[
            "1. Open rendered output for 'workflow.sm'. 2. Verify 'Start -> Finish' indentation and line:column numbers are visually aligned."
        ],
    )
    print(
        f"[Step 11-12] P31 ran TEST main -> result='{test_out['automated_result']}' "
        f"({test_out['passed']} passed, {test_out['failed']} failed), published event {test_out['test_event_id']}"
    )

    # Step 14 & 15: Recognized member P17 runs FINAL (prepare candidate -> confirm final result)
    repo_p17.git(["checkout", "main"])
    repo_p17.git(["pull", "origin", "main"])
    repo_p17.cmd_sync()

    cand_out = repo_p17.cmd_final_prepare(
        known_limitations=["Interactive GUI preview is not included; output is formatted text."],
    )
    print(
        f"[Step 14]  P17 initiated FINAL (--prepare) -> generated {cand_out['candidate_report_path']} "
        f"(event {cand_out['candidate_event_id']})"
    )

    final_out = repo_p17.cmd_final_confirm(
        known_limitations=["Interactive GUI preview is not included; output is formatted text."],
    )
    print(
        f"[Step 15]  P17 confirmed FINAL (--confirm) -> status='{final_out['status']}', "
        f"canonical_commit={final_out['canonical_commit'][:7]}, report={final_out['report_file']}, "
        f"event={final_out['final_event_id']}"
    )
    print("======================================================================")
    print(f"Demonstration workspace saved at: {base_dir}")
    print("======================================================================")

    return {
        "workspace": str(base_dir),
        "remote": str(remote_path),
        "clones": {"P17": str(p17_dir), "P22": str(p22_dir), "P31": str(p31_dir)},
        "final": final_out,
    }


if __name__ == "__main__":
    run_demonstration()
