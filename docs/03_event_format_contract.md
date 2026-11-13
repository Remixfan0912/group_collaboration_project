# Collaboration Event Format Contract
Version 0.1

## Common Envelope
```json
{
  "protocol_version": "0.1",
  "event_id": "E-20261016T021530Z-P17-a91f",
  "event_type": "change_published",
  "group_id": "G-12",
  "person_id": "P17",
  "created_at": "2026-10-16T02:15:30Z",
  "related_events": []
}
```

## Supported Types
- `change_published`: contains `change_id`, `branch`, `commit`, `summary`, `files_changed`, `interface_changes`, `tests_run`, `known_issues`, `proposed_for_integration`.
- `finding`: contains `summary`, `evidence`.
- `question`: contains `question_id`, `text`, `blocking`.
- `answer`: contains `question_id`, `text`.
- `review`: contains `change_id`, `verdict` (`accept`, `accept_with_changes`, `reject`, `needs_more_evidence`), `summary`, `issues`, `tests_run`.
- `test_result`: contains `scope`, `commit`, `commands`, `automated_result` (`pass`, `fail`, `partial`, `not_available`), `passed`, `failed`, `skipped`, `human_checks_required`, `summary`.
- `integration_result`: contains `change_id`, `target_branch`, `result` (`success`, `failed`, `needs_human`), `merge_commit`, `conflicts`, `conflict_resolution_summary`, `verification` (`build`, `tests`, `semantic_review`), `summary`.
- `blocker`: contains `summary`, `blocking_change_id`, `requested_action`.
- `final_candidate`: contains `canonical_commit`, `candidate_report_path`, `tests_considered`, `known_issues`.
- `final_result`: contains `canonical_commit`, `final_report_path`, `test_evidence`, `known_limitations`, `initiated_by`.
