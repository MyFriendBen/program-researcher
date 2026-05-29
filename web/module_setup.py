"""
Set up the 'program_research_agent' module alias.

The repo directory may not be named 'program_research_agent', but all
internal imports use that name. This module creates the alias so imports
like `from program_research_agent.graph import run_research` work
regardless of the directory name.

Import this module before importing anything from program_research_agent.
"""

import sys
import types
from pathlib import Path

# The repo root is one level up from this file (web/module_setup.py -> repo root)
repo_dir = Path(__file__).parent.parent.resolve()

if "program_research_agent" not in sys.modules:
    actual_name = repo_dir.name
    if actual_name != "program_research_agent":
        sys.path.insert(0, str(repo_dir.parent))
        mod = types.ModuleType("program_research_agent")
        mod.__path__ = [str(repo_dir)]
        mod.__file__ = str(repo_dir / "__init__.py")
        sys.modules["program_research_agent"] = mod
