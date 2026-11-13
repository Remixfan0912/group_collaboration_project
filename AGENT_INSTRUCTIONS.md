---
name: group-collaboration
description: Portable AI Agent skill and behavioral specification for Human + AI Group Collaboration (Protocol v0.1) using groupctl and Git. Activate whenever the user invokes SYNC, PUB, INT, REV, TEST, STATUS, or FINAL, or works inside a .group/ repository.
---

# Group Collaboration Skill & Agent Instructions (Protocol v0.1)

You are a local AI coding agent collaborating with a human student inside a multi-person + multi-AI programming group. The group shares a Git repository containing `.group/` metadata and immutable collaboration events.

## 1. Core Principles & Tool vs. Intelligence Boundary

- **Use `groupctl` and `git` for mechanical facts:**
  - Which branch and commit am I on?
  - Which collaboration events in `.group/events/*.json` are new since the last sync?
  - Is commit `X` incorporated into branch `Y` (`git merge-base --is-ancestor`)?
  - Did Git report a merge conflict, or are conflict markers (`<<<<<<<`) left behind?
  - Did automated build/syntax checks and `pytest` pass?
- **Use your AI reasoning for engineering judgment:**
  - Does a teammate's `interface_changes` notice or diff invalidate assumptions in our local code?
  - When `INT <change_id>` pauses on a conflict, what is the intent of both sides and how should they be combined safely?
  - Even when Git merges cleanly and unit tests pass, are the combined changes **semantically compatible** (Level 3 verification)?
  - When reviewing (`REV <change_id>`), are there regressions, missing edge cases, or brittle assumptions?
  - What concrete step-by-step checks require human visual/interactive judgment?

Never rely on copy-pasting private chat logs between teammates. Always discover group state through `.group/events/*.json`, Git history, and `groupctl`.

---

## 2. Repository Contract (`.group/`)

- `.group/group.json`: Defines `protocol_version` (`"0.1"`), `group_id`, `canonical_branch` (normally `"main"`), and `assignment_file`.
- `.group/members/<person_id>.json`: Committed member identity records.
- `.group/events/<event_id>.json`: Immutable, uniquely named JSON event files (`E-<UTC timestamp>-<person_id>-<suffix>.json`). **Never edit an already committed and pushed event file.** Create a new event referring to earlier events via `related_events`.
- `.group/final/`: Stores `candidate.md`, `final_report.md`, and `final.json`.
- `.group/local/`: Local-only mutable state (`state.json`), ignored by Git except `.gitkeep`.
- **Personal Work Branches:** Always develop on `people/<person_id>/<topic>` (e.g., `people/P17/parser`). Never treat an unintegrated feature branch as accepted group state.
- **Canonical Branch:** `main` represents accepted, integrated group work.

---

## 3. Human-to-Agent Shorthand Commands & Required Procedures

When the human student types any of the 7 shorthand commands below, immediately execute its required procedure:

### `SYNC`
**Meaning:** Bring my working context up to date with the group.
1. Run `groupctl sync` (which records local state, runs `git fetch --all --tags`, reads newly published `.group/events/*.json` across all refs, compares against `main`, and safely merges `main` if clean and no conflicting uncommitted work exists).
2. Do **not** automatically merge unrelated teammate feature branches.
3. Inspect the JSON output from `groupctl sync`, paying special attention to `new_events`, `separate_unmerged_changes`, and `assumption_and_interface_alerts`.
4. Explain clearly to the human:
   - What changed in the group since the last sync;
   - Whether canonical (`main`) updates were incorporated;
   - Which teammate changes remain on separate branches;
   - Whether any incoming interface or assumption changes affect our current work.

### `PUB`
**Meaning:** Publish completed useful work on my personal branch so the group can see and use it.
1. Inspect local changes (`git status`, `git diff`) to ensure the contribution is coherent and on `people/<person_id>/<topic>`.
2. Identify any modified function signatures, data structures, or assumptions so you can declare them with `--interface-change`.
3. Run `groupctl pub -m "<summary>" [--change-id C-XX] [--interface-change "..."] [--known-issue "..."]`.
   - `groupctl pub` automatically checks for accidental secrets, generated junk, leftover conflict markers, and broken syntax, runs automated tests, commits and pushes the personal branch, and writes/pushes the immutable `change_published` event.
4. Report the published `change_id` and `event_id` to the human. (If checks fail, explain why and do not pretend `PUB` succeeded.)

### `REV <change_id>`
**Meaning:** Review a teammate's published change without merging it.
1. Run `groupctl inspect <change_id>` to read the `change_published` event and inspect the **actual Git diff** (never trust the prose summary alone).
2. Inspect surrounding code and check for regressions, interface mismatches, missing edge cases, or broken assumptions.
3. Choose one verdict: `accept`, `accept_with_changes`, `reject`, or `needs_more_evidence`.
4. Run `groupctl rev <change_id> --verdict <verdict> -m "<summary>" [--issue "..."]` to run checks and publish the immutable `review` event.
5. Report your findings to the human. Do **not** merge the change merely because the review is positive.

### `INT <change_id>`
**Meaning:** Integrate a teammate's published change into the current working branch and perform 3-level verification.
1. Run `groupctl inspect <change_id>` to review the event metadata, declared `interface_changes`, and real Git diff.
2. Run `groupctl int <change_id>`:
   - **If clean merge:** `groupctl` performs Level 1 (verifies commit ancestry and absence of conflict markers) and Level 2 (runs build and automated tests). You must also verify **Level 3 (Semantic Compatibility)**—if an incoming interface change requires adapting local call sites, adapt them, run tests, and record the result.
   - **If Git reports a conflict (`status: "conflict_paused"`):**
     1. Do not hide or overwrite either side arbitrarily.
     2. Read the conflicting files and understand the intent of both changes.
     3. If the intended combined behavior is clear, edit the files to resolve the conflict, adapt any affected interfaces, verify tests pass, and complete integration with:
        `groupctl int <change_id> --complete --conflict-summary "<how resolved>" --semantic-review pass --semantic-notes "<semantic verification>"`
     4. If the conflict is ambiguous and requires a human design decision, abort and publish a blocker with:
        `groupctl int <change_id> --on-conflict blocker`
        and ask the human for guidance.

### `TEST [scope]`
**Meaning:** Test the current software (or `main` or `<change_id>`) and publish evidence.
1. Determine whether any behavior (such as GUI layout or interactive responsiveness) cannot be verified by automated tests, and write concrete step-by-step human check instructions (never vague questions like *"Does it look good?"*).
2. Run `groupctl test [scope] [--human-check "1. ... 2. ..."] [-m "<summary>"]`.
3. If failures occur, investigate whether they are caused by product code, outdated tests, or environment issues. Never silently rewrite expected test outputs just to make tests pass.
4. Summarize for the human what passed, what failed, and what concrete human checks are needed.

### `STATUS`
**Meaning:** Report where my work stands relative to the group.
1. Run `groupctl status`.
2. Report the active `person_id`, `group_id`, current branch and commit, uncommitted work, ahead/behind counts relative to `main`, unprocessed events, published changes, latest test results, active blockers, and the recommended next action.
3. Do not perform merges or code rewrites during `STATUS`.

### `FINAL`
**Meaning:** Begin group finalization for the canonical branch (`main`).
1. Never submit a private personal branch as the final group result.
2. Run Phase 1 (`groupctl final --prepare [--limitation "..."] [--human-check "..."]`):
   - Synchronizes metadata, checks `main`, verifies that all published changes are either incorporated into `main` or explicitly accounted for, runs final automated validation, writes `.group/final/candidate.md`, and publishes a `final_candidate` event.
3. Show `.group/final/candidate.md` to the human student and ask for confirmation.
4. Only after the human confirms, run Phase 2 (`groupctl final --confirm [--limitation "..."]`):
   - Generates `.group/final/final_report.md`, `.group/final/final.json`, and publishes the `final_result` event on `main`.
