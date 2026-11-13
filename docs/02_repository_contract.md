# Shared Repository Contract
Version 0.1

## Layout
```text
repository/
├── .group/
│   ├── group.json
│   ├── assignment/
│   │   └── assignment.md
│   ├── members/
│   │   └── <person_id>.json
│   ├── events/
│   │   └── <event_id>.json
│   ├── final/
│   │   ├── candidate.md
│   │   ├── final_report.md
│   │   └── final.json
│   └── local/
│       └── .gitkeep
```

## `group.json`
```json
{
  "protocol_version": "0.1",
  "group_id": "G-12",
  "canonical_branch": "main",
  "assignment_file": ".group/assignment/assignment.md"
}
```

## Personal Branches
Format: `people/<person_id>/<topic>`

## Events
- Path: `.group/events/<event_id>.json`
- ID format: `E-<UTC timestamp>-<person_id>-<short unique suffix>`
- Immutable once pushed.
