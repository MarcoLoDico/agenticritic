import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Cheap/fast model drives the step-by-step browser loop; a stronger one does analysis.
AGENT_MODEL = os.getenv("AGENT_MODEL", "anthropic/claude-haiku-5.5")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "anthropic/claude-sonnet-5.5")

MAX_STEPS = int(os.getenv("MAX_STEPS", "25"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "4"))
HEADLESS = os.getenv("HEADLESS", "1") != "0"

RUNS_DIR = ROOT / "runs"
PROJECTS_DIR = ROOT / "projects"
