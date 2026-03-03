"""Root conftest.py — sets up the program_research_agent module alias.

This must live at the repo root (program-researcher/) so pytest loads it
before any test collection or Package.setup() calls attempt to import
__init__.py by file path.
"""

import sys
import types
from pathlib import Path

repo_dir = Path(__file__).parent.resolve()
actual_name = repo_dir.name  # "program-researcher"

if actual_name != "program_research_agent":
    sys.path.insert(0, str(repo_dir.parent))

    program_research_agent = types.ModuleType("program_research_agent")
    program_research_agent.__path__ = [str(repo_dir)]
    program_research_agent.__file__ = str(repo_dir / "__init__.py")
    program_research_agent.__package__ = "program_research_agent"

    # Register under the canonical name used by test imports
    sys.modules["program_research_agent"] = program_research_agent
    # Register under the directory name so pytest's import_path finds it in
    # sys.modules (avoiding the hyphen-in-module-name error)
    sys.modules[actual_name] = program_research_agent
