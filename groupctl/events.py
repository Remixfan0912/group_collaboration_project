"""Event creation, reading, and management for groupctl."""
import json
import uuid
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from groupctl.config import GroupConfig


def generate_event_id(person_id: str) -> str:
    """Generate E-<UTC timestamp>-<person_id>-<short unique suffix>."""
    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:4]
    return f"E-{now_str}-{person_id}-{suffix}"


def get_iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class EventManager:
    def __init__(self, config: GroupConfig):
        self.config = config
        self.events_dir = config.events_dir
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def sync_events_from_repo(self, repo) -> List[str]:
        """Discover and pull event files from all Git branches into local .group/events/."""
        # Find all event files committed across all branches/refs
        code, out, _ = repo.run("log", "--all", "--name-only", "--format=", "--", ".group/events/*.json")
        if code != 0 or not out.strip():
            return []

        imported = []
        found_paths = set(line.strip().replace("\\", "/") for line in out.strip().splitlines() if line.strip().endswith(".json"))
        
        for rel_path in found_paths:
            filename = Path(rel_path).name
            target_file = self.events_dir / filename
            if not target_file.exists():
                # Read content from git object
                c, content, _ = repo.run("show", f"HEAD:{rel_path}")
                if c != 0 or not content.strip():
                    # Try from any branch containing it
                    c, content, _ = repo.run("show", f":{rel_path}")
                if c != 0 or not content.strip():
                    # Fallback: get commit hash that touched it
                    c_rev, commit_hash, _ = repo.run("log", "--all", "-n", "1", "--format=%H", "--", rel_path)
                    if c_rev == 0 and commit_hash.strip():
                        c, content, _ = repo.run("show", f"{commit_hash.strip()}:{rel_path}")

                if c == 0 and content.strip():
                    try:
                        # Verify valid JSON before saving
                        json.loads(content)
                        with open(target_file, "w", encoding="utf-8") as f:
                            f.write(content)
                        imported.append(filename)
                    except Exception:
                        pass
        return imported

    def create_event(
        self,
        event_type: str,
        specific_data: Dict[str, Any],
        related_events: Optional[List[str]] = None,
        person_id: Optional[str] = None
    ) -> Dict[str, Any]:
        p_id = person_id or self.config.person_id or "unknown"
        event_id = generate_event_id(p_id)
        
        envelope = {
            "protocol_version": self.config.protocol_version,
            "event_id": event_id,
            "event_type": event_type,
            "group_id": self.config.group_id,
            "person_id": p_id,
            "created_at": get_iso_now(),
            "related_events": related_events or []
        }
        envelope.update(specific_data)

        event_file = self.events_dir / f"{event_id}.json"
        with open(event_file, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)

        return envelope

    def list_events(self) -> List[Dict[str, Any]]:
        """List all events sorted by timestamp and filename."""
        events = []
        if not self.events_dir.exists():
            return events

        for p in sorted(self.events_dir.glob("*.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    events.append(data)
            except Exception:
                continue

        events.sort(key=lambda x: (x.get("created_at", ""), x.get("event_id", "")))
        return events

    def get_events_after(self, last_known_event_id: Optional[str]) -> List[Dict[str, Any]]:
        all_events = self.list_events()
        if not last_known_event_id:
            return all_events
        idx = -1
        for i, ev in enumerate(all_events):
            if ev.get("event_id") == last_known_event_id:
                idx = i
                break
        if idx != -1:
            return all_events[idx + 1:]
        return all_events

    def find_change_event(self, change_id: str) -> Optional[Dict[str, Any]]:
        for ev in reversed(self.list_events()):
            if ev.get("event_type") == "change_published" and ev.get("change_id") == change_id:
                return ev
        return None

    def get_last_sync_event_id(self) -> Optional[str]:
        sync_file = self.config.local_dir / "last_sync.json"
        if sync_file.is_file():
            try:
                with open(sync_file, "r", encoding="utf-8") as f:
                    return json.load(f).get("last_event_id")
            except Exception:
                pass
        return None

    def set_last_sync_event_id(self, event_id: str):
        self.config.local_dir.mkdir(parents=True, exist_ok=True)
        sync_file = self.config.local_dir / "last_sync.json"
        with open(sync_file, "w", encoding="utf-8") as f:
            json.dump({"last_event_id": event_id, "updated_at": get_iso_now()}, f, indent=2)
