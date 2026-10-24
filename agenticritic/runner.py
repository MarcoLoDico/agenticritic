"""Orchestrates a full simulation run and persists everything under runs/<run_id>/."""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from . import config
from .aggregate import aggregate
from .agent import run_session
from .browser import Browser
from .evaluate import evaluate
from .models import Persona, ProductBrief, Session


def _write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    elif isinstance(obj, list):
        obj = [o.model_dump() if hasattr(o, "model_dump") else o for o in obj]
    path.write_text(json.dumps(obj, indent=2))


async def run_simulation(
    brief: ProductBrief,
    personas: list[Persona],
    runs_per_persona: int = 1,
    url: str | None = None,
    log=print,
) -> Path:
    url = url or brief.url
    slug = brief.name.lower().replace(" ", "-")
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{slug}"
    run_dir = config.RUNS_DIR / run_id
    shots = run_dir / "shots"
    shots.mkdir(parents=True)
    started = time.time()

    _write(run_dir / "brief.json", brief)
    _write(run_dir / "personas.json", personas)
    meta = {"run_id": run_id, "url": url, "status": "running", "started": datetime.now().isoformat(),
            "agent_model": config.AGENT_MODEL, "analysis_model": config.ANALYSIS_MODEL,
            "max_steps": config.MAX_STEPS}
    _write(run_dir / "meta.json", meta)

    jobs = [(f"s{idx:02d}-{p.id}"[:60], p) for idx, p in enumerate(
        [p for p in personas for _ in range(runs_per_persona)])]
    log(f"Run {run_id}: {len(jobs)} sessions against {url}")

    sem = asyncio.Semaphore(config.CONCURRENCY)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=config.HEADLESS)

        async def one(session_id: str, persona: Persona) -> Session:
            async with sem:
                # A fresh context per agent: no shared cookies/state, so agents can't influence each other.
                ctx = await browser.new_context(viewport={"width": 1280, "height": 860})
                try:
                    s = await run_session(session_id, persona, brief, Browser(ctx, url, shots, brief.blocked_labels), log=log)
                finally:
                    await ctx.close()
                _write(run_dir / "sessions" / f"{session_id}.json", s)
                log(f"Session {session_id} finished: {s.status}, {len(s.steps)} steps")
                return s

        sessions = await asyncio.gather(*(one(sid, p) for sid, p in jobs))
        await browser.close()

    await analyze_run(run_dir, brief, sessions, log=log)
    meta.update(status="done", duration_s=round(time.time() - started),
                sessions=len(sessions))
    meta["findings"] = len(json.loads((run_dir / "findings.json").read_text()))
    _write(run_dir / "meta.json", meta)
    log(f"Done → {run_dir}")
    return run_dir


async def analyze_run(run_dir: Path, brief: ProductBrief, sessions: list[Session], log=print):
    """Aggregate sessions into findings and score them; safe to re-run on a finished run."""
    log("Aggregating findings…")
    findings = await aggregate(brief, sessions)
    _write(run_dir / "findings.json", findings)

    if brief.ground_truth:
        gt = Path(brief.ground_truth)
        if not gt.is_absolute():
            gt = config.ROOT / gt
        log("Evaluating against ground truth…")
        result = await evaluate(findings, gt)
        _write(run_dir / "eval.json", result)
        log(f"Recall {result.recall:.0%}  Precision {result.precision:.0%}")
