"""Init command for groupctl."""
from pathlib import Path
from datetime import datetime, timezone
import json
from groupctl.config import GroupConfig, PROTOCOL_VERSION


def run_init(
    root_dir: Path,
    group_id: str = "G-01",
    canonical_branch: str = "main",
    person_id: str = "P01",
    display_name: str = "Student 1"
):
    group_dir = root_dir / ".group"
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / "assignment").mkdir(parents=True, exist_ok=True)
    (group_dir / "members").mkdir(parents=True, exist_ok=True)
    (group_dir / "events").mkdir(parents=True, exist_ok=True)
    (group_dir / "final").mkdir(parents=True, exist_ok=True)
    (group_dir / "local").mkdir(parents=True, exist_ok=True)

    # .gitkeep files
    for sub in ["events", "final", "local"]:
        gitkeep = group_dir / sub / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    # group.json
    group_json_path = group_dir / "group.json"
    if not group_json_path.exists():
        data = {
            "protocol_version": PROTOCOL_VERSION,
            "group_id": group_id,
            "canonical_branch": canonical_branch,
            "assignment_file": ".group/assignment/assignment.md"
        }
        with open(group_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # default assignment file
    assign_path = group_dir / "assignment" / "assignment.md"
    if not assign_path.exists():
        with open(assign_path, "w", encoding="utf-8") as f:
            f.write("# Group Project Assignment\n\nCollaborative programming project.\n")

    # member file
    now_iso = datetime.now(timezone.utc).isoformat()
    member_path = group_dir / "members" / f"{person_id}.json"
    if not member_path.exists():
        member_data = {
            "protocol_version": PROTOCOL_VERSION,
            "person_id": person_id,
            "display_name": display_name,
            "joined_at": now_iso
        }
        with open(member_path, "w", encoding="utf-8") as f:
            json.dump(member_data, f, indent=2)

    # local config
    local_cfg = group_dir / "local" / "config.json"
    with open(local_cfg, "w", encoding="utf-8") as f:
        json.dump({"person_id": person_id}, f, indent=2)

    print(f"Initialized group repository structure in {group_dir}")
    print(f"Group: {group_id}, Canonical branch: {canonical_branch}, Person: {person_id} ({display_name})")
