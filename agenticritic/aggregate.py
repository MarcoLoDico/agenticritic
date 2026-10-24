"""Cluster per-session feedback into population-level findings."""

import json

from . import config
from .llm import chat_json
from .models import Finding, ProductBrief, Session

_SYSTEM = """You are a senior product researcher synthesising a synthetic user study.
You receive feedback from independent simulated users (each with a persona) who used the product.
Cluster their feedback into distinct, specific findings. Merge duplicates that describe the same
underlying problem even if worded differently. Each finding must be concrete and actionable
(e.g. "Team invitations are hidden under 'Workspace Administration'; small-business users look
for 'Team' or 'Members'"), never generic ("improve UX"). Only cite evidence that exists in the input."""

_SCHEMA = """Return JSON: {"findings": [{
  "title": str,                       // headline, e.g. "First-time users can't find team invitations"
  "category": "usability" | "missing_feature" | "bug" | "pricing_trust" | "positive",
  "description": str,                 // what happened, what users expected, why it matters
  "severity": 1-5,
  "persona_ids": [str],               // every persona that hit this
  "evidence": [{"session_id": str, "step": int | null, "quote": str (max 20 words, no double quotes inside)}],
  "recommendation": str
}]}
Order by (number of personas affected x severity), most important first."""


def _session_digest(s: Session) -> dict:
    d = s.debrief
    return {
        "session_id": s.id,
        "persona_id": s.persona.id,
        "persona": f"{s.persona.role}: {s.persona.summary}",
        "status": s.status,
        "step_frictions": [
            {"step": st.index, "url": st.url, "goal": st.goal, "expected": st.expectation, "friction": st.friction}
            for st in s.steps
            if st.friction
        ],
        "debrief": d.model_dump() if d else None,
    }


async def aggregate(brief: ProductBrief, sessions: list[Session]) -> list[Finding]:
    usable = [s for s in sessions if s.steps]  # partial sessions still carry evidence
    if not usable:
        return []
    digest = [_session_digest(s) for s in usable]
    data = await chat_json(
        [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": f"Product: {brief.name} — {brief.description}\n\n"
                f"Session feedback ({len(usable)} sessions):\n{json.dumps(digest, indent=1)}\n\n{_SCHEMA}",
            },
        ],
        model=config.ANALYSIS_MODEL,
        temperature=0.2,
        max_tokens=16000,
    )
    valid_personas = {s.persona.id for s in usable}
    valid_sessions = {s.id for s in usable}
    findings = []
    for i, raw in enumerate(data.get("findings", [])):
        raw["persona_ids"] = [p for p in raw.get("persona_ids", []) if p in valid_personas]
        raw["evidence"] = [e for e in raw.get("evidence", []) if e.get("session_id") in valid_sessions]
        findings.append(Finding(id=f"F{i + 1}", **raw))
    return findings
