"""End-to-end smoke test with a scripted fake LLM: costs nothing, needs no API key.

Starts the Ledgerly demo app on a spare port, runs two scripted sessions through the real
browser/agent/runner/aggregate/evaluate pipeline into a temp dir, and checks the output.

  .venv/bin/python tests/smoke_fake_llm.py
"""

import asyncio
import json
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from agenticritic import agent, aggregate, config, evaluate, runner  # noqa: E402
from agenticritic.models import Persona, ProductBrief  # noqa: E402

PORT = 8199


def find_id(obs: str, pattern: str) -> str | None:
    m = re.search(r"\[(\d+)\][^\n]*" + pattern, obs)
    return m.group(1) if m else None


async def fake_chat_json(messages, model, **kw):
    """Plays a founder who onboards, skips the integration, and goes looking for team invites."""
    last = messages[-1]["content"]
    if "STEP" in last and "INTERACTIVE ELEMENTS" in last:
        obs, url = last, re.search(r"URL: (\S+)", last).group(1)
        if "Company name" in obs:
            line = next(ln for ln in obs.splitlines() if 'label="Company name' in ln)
            if "value=" not in line:
                return {"current_goal": "set up", "thought": "name", "expectation": "name entered",
                        "action": {"type": "type", "target": find_id(obs, 'label="Company name'), "text": "Acme"}}
            # Bracketed id on purpose: the harness must accept "[2]" as well as 2.
            return {"current_goal": "set up", "thought": "continue", "expectation": "next step",
                    "action": {"type": "click", "target": f"[{find_id(obs, '\"Continue\"')}]"}}
        if "remind me later" in obs:
            return {"current_goal": "set up", "friction": "Forced to connect QuickBooks; skip link is tiny",
                    "friction_severity": 4, "thought": "skip", "expectation": "dashboard",
                    "action": {"type": "click", "target": find_id(obs, "remind me later")}}
        if url.endswith("/dashboard"):
            return {"current_goal": "invite", "thought": "settings", "expectation": "Team tab",
                    "action": {"type": "click", "target": find_id(obs, '"Settings"')}}
        if url.endswith("/settings"):
            return {"current_goal": "invite", "friction": "No Team tab", "friction_severity": 3,
                    "thought": "hmm", "expectation": "members",
                    "action": {"type": "click", "target": find_id(obs, "Workspace Administration")}}
        return {"current_goal": "invite", "thought": "done", "expectation": "", "action": {"type": "finish"}}
    if "session trace" in last:
        return {"goal_outcomes": [{"goal": "invite", "status": "failed", "notes": "jargon"}],
                "frictions": [{"step": 2, "description": "forced integration", "expected": "skip",
                               "happened": "tiny link", "why_it_matters": "blocked"}],
                "missing_features": [{"feature": "approval rules", "why": "control", "step": None}],
                "liked": ["clean"], "would_continue": False, "would_continue_reason": "confusing", "score": 4}
    if "Cluster" in messages[0]["content"]:
        sid = re.search(r'"session_id": "([^"]+)"', last).group(1)
        pid = re.search(r'"persona_id": "([^"]+)"', last).group(1)
        return {"findings": [
            {"title": "Onboarding forces accounting integration", "category": "usability", "description": "d",
             "severity": 4, "persona_ids": [pid, "not-a-persona"], "recommendation": "r",
             "evidence": [{"session_id": sid, "step": 2, "quote": "tiny"}]},
            {"title": "No approval rules", "category": "missing_feature", "description": "d", "severity": 3,
             "persona_ids": [pid], "evidence": [], "recommendation": "r"}]}
    if "KNOWN ISSUES" in last:
        return {"matches": [{"issue_id": "GT2", "finding_ids": ["F1"], "reason": "same"},
                            {"issue_id": "GT7", "finding_ids": ["F2"], "reason": "same"}]}
    raise AssertionError("unexpected prompt: " + last[:200])


def start_demo_app():
    server = uvicorn.Server(uvicorn.Config("demo_app.app:app", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return server


def main():
    for mod in (agent, aggregate, evaluate):
        mod.chat_json = fake_chat_json
    config.MAX_STEPS = 12
    config.RUNS_DIR = Path(tempfile.mkdtemp())
    server = start_demo_app()

    brief = ProductBrief.model_validate_json((ROOT / "projects/ledgerly.json").read_text())
    brief.url = f"http://127.0.0.1:{PORT}/"
    brief.ground_truth = str(ROOT / "demo_app/ground_truth.json")
    p = Persona(id="founder-a", name="Test", role="Founder", summary="You run a 5-person startup.",
                goals=["set up", "invite a teammate"], knowledge="k", constraints="c", preferences="p", expectations="e")
    run_dir = asyncio.run(runner.run_simulation(brief, [p, p.model_copy(update={"id": "founder-b"})], log=lambda *_: None))
    server.should_exit = True

    sessions = [json.loads(f.read_text()) for f in sorted((run_dir / "sessions").glob("*.json"))]
    findings = json.loads((run_dir / "findings.json").read_text())
    ev = json.loads((run_dir / "eval.json").read_text())

    assert len(sessions) == 2, sessions
    for s in sessions:
        assert s["status"] == "completed", (s["id"], s["status"], s.get("error"))
        assert not any(st["error"] for st in s["steps"]), [st["error"] for st in s["steps"]]
        urls = [st["url"] for st in s["steps"]]
        assert any(u.endswith("/settings/workspace") for u in urls), urls
        assert s["debrief"]["score"] == 4
        assert all((run_dir / "shots" / st["screenshot"]).exists() for st in s["steps"])
    assert "not-a-persona" not in findings[0]["persona_ids"], "aggregate must drop unknown persona ids"
    assert ev["recall"] == 0.2 and ev["precision"] == 1.0, ev
    print(f"OK: 2 sessions, {len(findings)} findings, recall {ev['recall']:.0%} ({run_dir})")


if __name__ == "__main__":
    main()
