#!/usr/bin/env python3
"""
Convenience script to run the Program Research Agent CLI.

This script can be run from the repo directory regardless of what
the repo directory is named locally.

Usage:
    python run.py research --program CSFP --state il --white-label il --source-url https://...
    python run.py graph
    python run.py --help
"""

import sys
from pathlib import Path

# Add the repo's parent directory to Python path, with the repo aliased as 'program_research_agent'
repo_dir = Path(__file__).parent.resolve()
parent_dir = repo_dir.parent

# Create a symlink or use sys.modules trick to make the import work
# We'll add the parent to the path and create a module alias
sys.path.insert(0, str(parent_dir))

# Create an alias so 'program_research_agent' imports from this directory
import importlib
import types

# Get the actual directory name
actual_name = repo_dir.name

# If the directory isn't named 'program_research_agent', create an alias
if actual_name != 'program_research_agent':
    # Import the package under its actual name first by adding repo to path
    sys.path.insert(0, str(repo_dir.parent))

    # Create a fake module that points to our directory
    program_research_agent = types.ModuleType('program_research_agent')
    program_research_agent.__path__ = [str(repo_dir)]
    program_research_agent.__file__ = str(repo_dir / '__init__.py')
    sys.modules['program_research_agent'] = program_research_agent

# Now import and run the CLI
from program_research_agent.cli import cli

if __name__ == "__main__":
    cli()
