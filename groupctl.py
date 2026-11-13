#!/usr/bin/env python
"""groupctl executable entrypoint."""
import sys
from pathlib import Path

# Add current directory to sys.path so groupctl package can be imported directly
root = Path(__file__).parent.resolve()
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from groupctl.cli import main

if __name__ == "__main__":
    main()
