"""Validation, build, testing, and semantic verification helper."""
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple


class Validator:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir

    def run_tests(self, scope: str = "all") -> Dict[str, Any]:
        """Run project tests (pytest or python unittest) and collect results."""
        commands = []
        tests_dir = self.root_dir / "tests"
        if not tests_dir.is_dir():
            return {
                "commands": ["none"],
                "automated_result": "not_available",
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "summary": "No tests directory found."
            }

        # Check if pytest is available, otherwise use unittest
        test_cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
        cmd_str = f"python -m unittest discover -s tests"
        commands.append(cmd_str)

        proc = subprocess.run(
            test_cmd,
            cwd=str(self.root_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        output = proc.stdout + "\n" + proc.stderr
        passed = 0
        failed = 0
        skipped = 0

        # Parse unittest output format e.g. "Ran 5 tests in 0.01s\n\nOK" or "FAILED (failures=1, errors=1)"
        if "Ran " in output:
            try:
                for line in output.splitlines():
                    if line.startswith("Ran "):
                        parts = line.split()
                        total = int(parts[1])
                        if "OK" in output:
                            passed = total
                            failed = 0
                        else:
                            # Parse failures / errors
                            fail_count = 0
                            if "failures=" in output:
                                fail_count += int(output.split("failures=")[1].split(",")[0].split(")")[0])
                            if "errors=" in output:
                                fail_count += int(output.split("errors=")[1].split(",")[0].split(")")[0])
                            failed = fail_count
                            passed = max(0, total - failed)
            except Exception:
                pass

        auto_result = "pass" if proc.returncode == 0 else "fail"
        summary = f"Automated tests: {passed} passed, {failed} failed." if proc.returncode == 0 else f"Automated test run failed:\n{output[-300:]}"

        return {
            "commands": commands,
            "automated_result": auto_result,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "summary": summary,
            "raw_output": output
        }

    def check_conflict_markers(self) -> List[str]:
        """Scan source files for git conflict markers."""
        markers = []
        for ext in ["*.py", "*.md", "*.json", "*.txt"]:
            for f in self.root_dir.rglob(ext):
                # Skip .git and .group/local
                if ".git" in f.parts or ("local" in f.parts and ".group" in f.parts):
                    continue
                try:
                    with open(f, "r", encoding="utf-8", errors="ignore") as file:
                        for line_idx, line in enumerate(file, start=1):
                            if line.startswith("<<<<<<<") or line.startswith("=======") or line.startswith(">>>>>>>"):
                                markers.append(f"{f.relative_to(self.root_dir)}:{line_idx}")
                except Exception:
                    pass
        return markers

    def mechanical_check(self) -> Tuple[bool, List[str]]:
        """Verify no conflict markers and code syntax is clean."""
        issues = []
        markers = self.check_conflict_markers()
        if markers:
            issues.append(f"Leftover conflict markers detected in: {', '.join(markers)}")

        # Check Python compilation syntax
        for py_file in self.root_dir.rglob("*.py"):
            if ".git" in py_file.parts or ".group" in py_file.parts:
                continue
            proc = subprocess.run(
                [sys.executable, "-m", "py_compile", str(py_file)],
                capture_output=True,
                text=True
            )
            if proc.returncode != 0:
                issues.append(f"Syntax error in {py_file.name}: {proc.stderr.strip()}")

        return (len(issues) == 0), issues
