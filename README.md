# Group Collaboration Software System (`groupctl`)
Version 0.1

This repository contains the complete implementation of the **Group Collaboration Software System** (`groupctl`), built to enable multiple human + AI pairs to collaborate effectively on a shared programming repository without requiring a centralized Dispatcher.

---

## 1. System Architecture & Core Principles

```text
                    GROUP ASSIGNMENT
                           |
                  shared GitHub repository
                           |
        +------------------+------------------+
        |                  |                  |
   Student A          Student B          Student C
      <->                <->                <->
   local AI           local AI           local AI
        |                  |                  |
        +--------- publish / review / --------+
                   integrate / test
                           |
                    accepted group state
                           |
                    ONE GROUP RESULT
```

### Mechanical Tasks vs. AI Engineering Judgment
- **`groupctl` & Git**: Handle mechanical facts (tracking commits, checking dirty worktrees, creating immutable structured events, running test suites, detecting conflict markers).
- **AI Agent**: Supplies engineering judgment (resolving code conflicts with mutual semantic compatibility, verifying API contracts, assessing test completeness, and summarizing impacts for human teammates).

### Prompt Shorthand Commands
Instead of writing long paragraphs, human students interact with their agents using concise prompt shorthand:
- **`SYNC`**: Pull remote events, check canonical updates, and summarize new changes and interface impacts.
- **`PUB`**: Run pre-publish checks, commit work branch, push, and broadcast a structured `change_published` event (`C-<id>`).
- **`INT <change_id>`**: Inspect diff & interfaces, merge change into current branch, resolve conflicts if safe, run build & tests, and publish an `integration_result`.
- **`REV <change_id>`**: Inspect diff, surrounding code, and interfaces; run tests and publish a structured `review` event (`accept`, `accept_with_changes`, `reject`, `needs_more_evidence`).
- **`TEST [scope]`**: Execute automated test suites, record pass/fail evidence, document required manual human checks, and publish a `test_result` event.
- **`STATUS`**: Display current branch, commit, relation to canonical state (ahead/behind), active blockers, and recommended next steps.
- **`FINAL`**: Run validation, draft `.group/final/candidate.md`, request human confirmation, and generate `.group/final/final_report.md`, `.group/final/final.json`, and a `final_result` event.

---

## 2. Repository Layout & Contracts

```text
group_A/
├── .group/
│   ├── group.json                    # Group protocol configuration
│   ├── assignment/
│   │   └── assignment.md             # Group assignment specification
│   ├── members/                      # Registered member descriptors
│   │   ├── P17.json                  # Student A (Susan)
│   │   ├── P22.json                  # Student B (Bob)
│   │   └── P31.json                  # Student C (Charlie)
│   ├── events/                       # Immutable collaboration event files
│   │   └── E-<timestamp>-<person>-<uuid>.json
│   ├── final/                        # Group finalization records
│   │   ├── candidate.md              # Proposed final candidate report
│   │   ├── final_report.md           # Authoritative substantive final report
│   │   └── final.json                # Machine-readable finalization envelope
│   └── local/                        # Local configuration & sync pointers (ignored by git)
│
├── groupctl/                         # Core Python collaboration engine
│   ├── __init__.py
│   ├── cli.py                        # CLI entry point
│   ├── config.py                     # .group resolution & config management
│   ├── repo.py                       # Safe Git operations wrapper
│   ├── events.py                     # Event I/O & multi-branch event discovery
│   ├── validation.py                 # Multi-level build, test, and marker checking
│   └── commands/                     # Implementation of all standard procedures
│       ├── sync_cmd.py
│       ├── pub_cmd.py
│       ├── int_cmd.py
│       ├── rev_cmd.py
│       ├── test_cmd.py
│       ├── status_cmd.py
│       ├── final_cmd.py
│       └── init_cmd.py
│
├── AGENT_SKILL.md                    # Portable AI agent skill / instruction file
├── groupctl.py                       # Executable entrypoint
├── groupctl.bat                      # Windows launcher
├── src/                              # Sample domain model (parser & renderer)
│   ├── model.py
│   ├── parser.py
│   └── renderer.py
├── tests/                            # Unit tests for domain logic and groupctl
│   ├── test_parser.py
│   └── test_groupctl.py
├── docs/                             # Authoritative protocol specifications
│   ├── 00_assignment.md
│   ├── 01_architecture_and_workflow.md
│   ├── 02_repository_contract.md
│   ├── 03_event_format_contract.md
│   ├── 04_command_reference.md
│   ├── 05_command_procedures.md
│   ├── 06_agent_behavior_specification.md
│   └── 07_testing_and_finalization.md
└── demo_collaboration.py             # 15-step multi-agent end-to-end verification
```

---

## 3. How to Run & Verify

### Running Unit Tests
```bash
python -m unittest discover -s tests
```

### Running the End-to-End Multi-Agent Demonstration
The demonstration script (`demo_collaboration.py`) verifies all 15 success criteria from Section 7 of the specification:
```bash
python demo_collaboration.py
```
This simulation automatically executes:
1. Multi-member shared repository setup (P17, P22, P31).
2. Independent personal work branches (`people/P17/...`, `people/P22/...`, `people/P31/...`).
3. Independent feature implementation and publication via `groupctl pub` (`C-17`).
4. Event discovery via `groupctl sync`.
5. Peer review via `groupctl rev` (`verdict=accept`).
6. Clean automated integration and 3-level verification via `groupctl int` (Level 1 Git, Level 2 Mechanical, Level 3 Semantic).
7. Publication of integrated change `C-22`.
8. Generation and detection of a deliberate merge conflict from `C-31`.
9. AI-guided conflict resolution preserving both feature intents and verifying test suites.
10. Execution and broadcast of test evidence via `groupctl test`.
11. Update of canonical branch `main`.
12. Group finalization via `groupctl final`, generating `candidate.md`, `final_report.md`, and `final.json`.
