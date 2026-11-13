"""Configuration and directory resolution for groupctl."""
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

PROTOCOL_VERSION = "0.1"


def find_group_root(start_path: Optional[Path] = None) -> Path:
    """Find the root directory containing the .group folder."""
    curr = (start_path or Path.cwd()).resolve()
    while True:
        group_dir = curr / ".group"
        if group_dir.is_dir() and (group_dir / "group.json").is_file():
            return curr
        if curr.parent == curr:
            break
        curr = curr.parent
    # Fallback to current directory
    return (start_path or Path.cwd()).resolve()


class GroupConfig:
    def __init__(self, root_dir: Optional[Path] = None, person_id: Optional[str] = None):
        self.root_dir = find_group_root(root_dir)
        self.group_dir = self.root_dir / ".group"
        self.events_dir = self.group_dir / "events"
        self.members_dir = self.group_dir / "members"
        self.final_dir = self.group_dir / "final"
        self.local_dir = self.group_dir / "local"

        self.group_data = self._load_group_json()
        self.protocol_version = self.group_data.get("protocol_version", PROTOCOL_VERSION)
        self.group_id = self.group_data.get("group_id", "G-01")
        self.canonical_branch = self.group_data.get("canonical_branch", "main")
        self.assignment_file = self.group_data.get("assignment_file", ".group/assignment/assignment.md")

        self.person_id = person_id or os.getenv("GROUPCTL_PERSON_ID") or self._load_local_person_id()

    def _load_group_json(self) -> Dict[str, Any]:
        p = self.group_dir / "group.json"
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _load_local_person_id(self) -> Optional[str]:
        p = self.local_dir / "config.json"
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("person_id")
            except Exception:
                pass
        return None

    def set_local_person_id(self, person_id: str, display_name: Optional[str] = None):
        self.person_id = person_id
        self.local_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.local_dir / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"person_id": person_id}, f, indent=2)

        # Register member file if not already present
        member_file = self.members_dir / f"{person_id}.json"
        if not member_file.exists():
            self.members_dir.mkdir(parents=True, exist_ok=True)
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()
            member_data = {
                "protocol_version": self.protocol_version,
                "person_id": person_id,
                "display_name": display_name or person_id,
                "joined_at": now_iso
            }
            with open(member_file, "w", encoding="utf-8") as f:
                json.dump(member_data, f, indent=2)
