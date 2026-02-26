"""
Configuration for the Program Research Agent.

Loads settings from environment variables and provides defaults.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Load .env file if present
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # ----- API Keys -----
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude",
    )
    linear_api_key: str = Field(
        default="",
        description="Linear API key for ticket creation",
    )

    # ----- Model Configuration -----
    researcher_model: str = Field(
        default="claude-sonnet-4-5-20250929",
        description="Model to use for researcher agent (extraction, generation)",
    )
    qa_model: str = Field(
        default="claude-opus-4-6",
        description="Model to use for QA agent (validation, error detection)",
    )
    model_temperature: float = Field(
        default=0.1,
        description="Temperature for model responses (lower = more deterministic)",
    )
    model_max_tokens: int = Field(
        default=8192,
        description="Maximum tokens for model responses",
    )
    model_max_retries: int = Field(
        default=5,
        description="Maximum retries for API calls (handles transient 500 errors)",
    )

    # ----- Workflow Configuration -----
    max_qa_iterations: int = Field(
        default=3,
        description="Maximum QA loop iterations before proceeding",
    )
    max_links_per_source: int = Field(
        default=50,
        description="Maximum links to extract from a single source",
    )
    web_request_timeout: int = Field(
        default=60,
        description="Timeout in seconds for web requests",
    )

    # ----- Paths -----
    project_root: Path = Field(
        default=Path(__file__).parent.parent,
        description="Root directory of the MFB project",
    )
    output_dir: Path = Field(
        default=Path(__file__).parent / "output",
        description="Directory for output files",
    )
    schemas_dir: Path = Field(
        default=Path(__file__).parent.parent / "mfb_pre_validation_json_schemas",
        description="Directory containing JSON schemas",
    )

    # ----- Backend Paths (for reading screener fields) -----
    backend_models_path: Path = Field(
        default=Path(__file__).parent.parent / "benefits-api" / "screener" / "models.py",
        description="Path to Django screener models",
    )
    frontend_types_path: Path = Field(
        default=Path(__file__).parent.parent / "benefits-calculator" / "src" / "Types" / "FormData.ts",
        description="Path to frontend type definitions",
    )

    # ----- Linear Configuration -----
    linear_team_id: str = Field(
        default="",
        description="Linear team ID for ticket creation",
    )
    linear_project_id: str = Field(
        default="",
        description="Linear project ID for new programs",
    )

    class Config:
        env_prefix = "RESEARCH_AGENT_"
        env_file = ".env"
        extra = "ignore"


# Global settings instance
settings = Settings()


def get_schema_path(schema_name: str) -> Path:
    """Get the full path to a JSON schema file."""
    return settings.schemas_dir / schema_name


def get_output_path(filename: str) -> Path:
    """Get the full path to an output file, creating the directory if needed."""
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    return settings.output_dir / filename


def validate_settings() -> list[str]:
    """Validate that required settings are configured. Returns list of errors."""
    errors = []

    if not settings.anthropic_api_key:
        errors.append("RESEARCH_AGENT_ANTHROPIC_API_KEY is required")

    if not settings.backend_models_path.exists():
        errors.append(f"Backend models not found at {settings.backend_models_path}")

    if not settings.schemas_dir.exists():
        errors.append(f"Schemas directory not found at {settings.schemas_dir}")

    return errors
