# Group Collaboration Software Assignment
Version 0.1

## 1. Assignment
Build the first working layer of a future multi-agent programming system:
> Several human + AI pairs must be able to work together as one group on one programming assignment, using a shared GitHub repository, without requiring a Dispatcher.

## 2. Core Principle
Git provides source control and history.
The collaboration software (`groupctl`) adds a small layer above Git so that humans and AI agents can perform standard group operations reliably and consistently.
Command vocabulary: `SYNC`, `PUB`, `INT`, `REV`, `TEST`, `STATUS`, `FINAL`.

## 3. What Must Be Built
1. A local collaboration tool (`groupctl`).
2. A portable agent instruction/skill file (`AGENT_SKILL.md`).
3. A shared repository convention (`.group/`).
4. A structured event/change format (`.group/events/`).
5. A safe Git workflow based on individual work branches (`people/<person_id>/<topic>`) and canonical branch (`main`).
6. Testing and verification behavior beyond Git merge.
7. A group finalization procedure (`FINAL`).

## 4. Scope Limits
Version 0.1 does NOT need: Dispatcher, automatic task allocation, vendor-specific AI integration, extra servers, or autonomous project planning.
