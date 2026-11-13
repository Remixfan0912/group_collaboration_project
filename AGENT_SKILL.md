# Group Collaboration Agent Skill Specification
Version 0.1

This skill document defines the behavior of an AI coding agent collaborating with human students and other AI agents on a shared repository.

## 1. Core Principle: Human Shorthand & AI Judgment
When the student provides a shorthand prompt command (`SYNC`, `PUB`, `INT`, `REV`, `TEST`, `STATUS`, `FINAL`), the agent executes the corresponding procedure:
- **Mechanical tasks**: delegated to Git and `groupctl`.
- **Engineering judgment**: supplied by the AI agent (conflict resolution, semantic compatibility, API consistency, test sufficiency).

## 2. Command Mappings

### `SYNC`
- **Goal**: Bring working context up to date with the group without blindly merging unfinished branches.
- **Agent Action**:
  1. Run `python groupctl.py sync`
  2. Inspect new events output: changes (`change_published`), reviews, blockers, or test results.
  3. Check if any new change invalidates current assumptions or modifies shared interfaces.
  4. Summarize for the human teammate what was incorporated and any potential impacts.

### `PUB`
- **Goal**: Publish coherent completed work for teammates to discover.
- **Agent Action**:
  1. Verify working code with mechanical check and unit tests.
  2. Ensure changes are properly documented (interface modifications, known issues).
  3. Execute `python groupctl.py pub -m "<concise summary>" --interfaces "<interface changes>"`.
  4. Inform human of the newly minted `change_id` (e.g. `C-17`).

### `INT <change_id>`
- **Goal**: Integrate a teammate's published change into the local branch and verify.
- **Agent Action**:
  1. Run `python groupctl.py int <change_id>`.
  2. If Git reports conflicts:
     - Inspect the conflict markers and understand the intent of both sides.
     - Carefully resolve conflicts preserving both features.
     - Run tests and static checks.
     - Never silently discard teammate work or corrupt shared state.
  3. Perform semantic review: verify whether the merged code functions correctly end-to-end.

### `REV <change_id>`
- **Goal**: Review a teammate's change without merging.
- **Agent Action**:
  1. Run `python groupctl.py rev <change_id> --verdict <verdict> -m "<review notes>"`.
  2. Allowed verdicts: `accept`, `accept_with_changes`, `reject`, `needs_more_evidence`.
  3. Distinguish definite defects from style preferences or risks.

### `TEST [scope]`
- **Goal**: Test software and publish transparent evidence.
- **Agent Action**:
  1. Run `python groupctl.py test [scope]`.
  2. Note automated pass/fail results.
  3. Document any required manual human checks with specific steps.

### `STATUS`
- **Goal**: Explain current situation relative to canonical branch and group.
- **Agent Action**:
  1. Run `python groupctl.py status`.
  2. Report branch, ahead/behind status, uncommitted files, blockers, and recommend the immediate next step.

### `FINAL`
- **Goal**: Formulate the canonical group submission.
- **Agent Action**:
  1. Run `python groupctl.py final`.
  2. Verify that `.group/final/candidate.md` correctly represents group work, canonical commit, and validation evidence.
  3. Present the candidate report to the student for confirmation.
  4. After confirmation, run `python groupctl.py final --confirm` to generate `.group/final/final_report.md` and `final.json`.

## 3. Two Contexts
- **Private/Local**: Agent reasoning, temporary edits, scratch files.
- **Public/Shared**: Published commits, events under `.group/events/`, reviews, test records.
Never broadcast raw conversational chat logs to the shared repository. Always use structured events.
