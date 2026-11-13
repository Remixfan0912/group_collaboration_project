# Architecture and Workflow
Version 0.1

## 1. Components
The system has four conceptual components:
1. **Human**: The student steers local AI, makes decisions, invokes commands.
2. **Local AI Agent**: Edits code, uses Git, reasons about changes, resolves conflicts, performs semantic reviews, creates collaboration events.
3. **`groupctl`**: Deterministic collaboration helper for identity, synchronization, publishing, event I/O, validation bookkeeping.
4. **GitHub Repository**: Shared persistent substrate storing code, branches, tests, events, and final records.

## 2. Canonical State vs. Personal Work
- Canonical state: `main` (accepted group work).
- Personal work: `people/<person_id>/<topic>` (unfinished/experimental work).

## 3. Parallel Work & Publish Before Integrate
- Completed work is published with Git commits + pushed branch + `change_published` event.
- Other agents inspect actual diff; the change description is context, not proof.

## 4. Integration Levels
- Level 1: Git integration (commits incorporated).
- Level 2: Mechanical validation (build, automated tests pass, no conflict markers).
- Level 3: Semantic review (combined changes make sense, assumptions preserved).

## 5. Conflict Handling
Identify conflicting files, inspect intent of both sides, resolve deliberately, build & test, review semantic compatibility, publish `integration_result`.
