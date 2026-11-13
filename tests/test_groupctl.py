"""Unit tests for groupctl core logic."""
import unittest
import tempfile
import json
from pathlib import Path
from groupctl.config import GroupConfig
from groupctl.events import EventManager, generate_event_id
from groupctl.validation import Validator


class TestGroupctl(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        # Create .group structure
        group_dir = self.root / ".group"
        group_dir.mkdir(parents=True)
        (group_dir / "events").mkdir()
        (group_dir / "members").mkdir()
        (group_dir / "final").mkdir()
        (group_dir / "local").mkdir()

        group_json = {
            "protocol_version": "0.1",
            "group_id": "G-TEST",
            "canonical_branch": "main",
            "assignment_file": ".group/assignment/assignment.md"
        }
        with open(group_dir / "group.json", "w") as f:
            json.dump(group_json, f)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_event_creation_and_listing(self):
        cfg = GroupConfig(self.root, person_id="P17")
        em = EventManager(cfg)

        ev = em.create_event(
            event_type="change_published",
            specific_data={"change_id": "C-17", "summary": "Test change", "branch": "people/P17/feat"},
            person_id="P17"
        )
        self.assertEqual(ev["event_type"], "change_published")
        self.assertEqual(ev["person_id"], "P17")
        self.assertTrue(ev["event_id"].startswith("E-"))

        all_events = em.list_events()
        self.assertEqual(len(all_events), 1)
        self.assertEqual(all_events[0]["change_id"], "C-17")

        found = em.find_change_event("C-17")
        self.assertIsNotNone(found)
        self.assertEqual(found["event_id"], ev["event_id"])

    def test_validator_detects_conflict_markers(self):
        conflict_file = self.root / "bad_file.py"
        conflict_file.write_text("<<<<<<< HEAD\nprint('hello')\n=======\nprint('world')\n>>>>>>> feat\n")
        val = Validator(self.root)
        markers = val.check_conflict_markers()
        self.assertTrue(len(markers) > 0)


if __name__ == "__main__":
    unittest.main()
