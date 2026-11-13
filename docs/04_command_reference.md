# Human-to-Agent Collaboration Command Reference & Procedures
Version 0.1

## Commands
1. **`SYNC`**: Fetch remote state, inspect new events, update from canonical branch safely, report changes and assumptions.
2. **`PUB`**: Review local changes, run quick checks, commit & push branch, create & push `change_published` event with `change_id`.
3. **`INT <change_id>`**: Locate change, inspect diff & event, merge into current branch, resolve conflicts if safe, verify (build/test/semantic), publish `integration_result`.
4. **`REV <change_id>`**: Inspect diff & code, check assumptions, run tests, formulate verdict, publish `review` event.
5. **`TEST [scope]`**: Run build/tests/static checks, publish `test_result` event with pass/fail counts.
6. **`STATUS`**: Report identity, branch, commits, ahead/behind, new events, test status, blockers.
7. **`FINAL`**: Check canonical state, verify unresolved work, run validation, generate candidate report, obtain human confirmation, publish `final_report.md`, `final.json`, and `final_result` event.
