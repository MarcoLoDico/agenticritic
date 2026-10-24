"""Generate behaviorally diverse personas from a product brief."""

import json
import re

from . import config
from .llm import chat_json
from .models import Persona, ProductBrief

_SYSTEM = """You design synthetic user panels for product testing.
Personas must be defined by BEHAVIOR, not demographics: what they are trying to get done,
what they already know, constraints, preferences, patience, risk tolerance and what they
expect the product to do. Make the panel diverse: first-timers and experts, buyers and
daily users, skeptics and enthusiasts, careful explorers and impatient skimmers.
Goals must be concrete tasks someone could attempt in the product within a few minutes,
phrased the way THIS persona would think about them (their own words, not the product's)."""

_SCHEMA = """Return JSON: {"personas": [{
  "name": str, "role": str, "summary": str (1-2 sentences, second person: "You ..."),
  "goals": [str, 2-3 concrete tasks],
  "knowledge": str, "constraints": str, "preferences": str, "expectations": str,
  "behavior": {
    "exploration": "careful" | "skimmer" | "advanced_seeker" | "literal",
    "patience": 1-5, "tech_savviness": 1-5, "terminology_rigidity": 1-5, "risk_tolerance": 1-5
  }
}]}"""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


async def generate_personas(brief: ProductBrief, n: int = 6) -> list[Persona]:
    brief_json = brief.model_dump(exclude={"ground_truth", "url", "blocked_labels"})
    data = await chat_json(
        [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": f"Product brief:\n{json.dumps(brief_json, indent=2)}\n\n"
                f"Create {n} personas. Vary exploration styles and patience levels "
                f"across the panel (at least one with patience <= 2).\n\n{_SCHEMA}",
            },
        ],
        model=config.ANALYSIS_MODEL,
        temperature=0.9,
        max_tokens=6000,
    )
    personas = []
    seen: set[str] = set()
    for raw in data["personas"]:
        pid = _slug(f"{raw['role']}-{raw['name']}")
        while pid in seen:
            pid += "-x"
        seen.add(pid)
        personas.append(Persona(id=pid, **raw))
    return personas
