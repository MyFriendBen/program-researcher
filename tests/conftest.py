"""pytest configuration for program_research_agent tests."""

import sys
import types
from pathlib import Path

# Set up module aliasing so 'program_research_agent' imports work
# regardless of what the repo directory is named locally
repo_dir = Path(__file__).parent.parent.resolve()
actual_name = repo_dir.name

if actual_name != "program_research_agent":
    # Create a module alias
    sys.path.insert(0, str(repo_dir.parent))

    program_research_agent = types.ModuleType("program_research_agent")
    program_research_agent.__path__ = [str(repo_dir)]
    program_research_agent.__file__ = str(repo_dir / "__init__.py")
    sys.modules["program_research_agent"] = program_research_agent
