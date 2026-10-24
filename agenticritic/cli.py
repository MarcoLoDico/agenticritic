"""Command line entry point.

  python -m agenticritic.cli personas projects/ledgerly.json -n 6
  python -m agenticritic.cli run projects/ledgerly.json [--url http://...] [--repeat 2]
  python -m agenticritic.cli analyze runs/<run_id>    # re-aggregate + evaluate existing sessions
  python -m agenticritic.cli evaluate runs/<run_id>
  python -m agenticritic.cli export [run_id ...] [--out export]   # static dashboard, no server needed
"""

import argparse
import asyncio
import json
from pathlib import Path

from .evaluate import evaluate
from .models import Finding, Persona, ProductBrief, Session
from .personas import generate_personas
from .runner import analyze_run, run_simulation


def _personas_path(project: Path) -> Path:
    return project.with_name(project.stem + ".personas.json")


def load_brief(project: Path) -> ProductBrief:
    return ProductBrief.model_validate_json(project.read_text())


async def cmd_personas(args):
    project = Path(args.project)
    personas = await generate_personas(load_brief(project), n=args.n)
    out = _personas_path(project)
    out.write_text(json.dumps([p.model_dump() for p in personas], indent=2))
    for p in personas:
        print(f"- {p.id}: {p.role} ({p.behavior.exploration}, patience {p.behavior.patience})")
    print(f"Wrote {out} — edit it freely before running.")


async def cmd_run(args):
    project = Path(args.project)
    brief = load_brief(project)
    ppath = _personas_path(project)
    if not ppath.exists():
        print(f"No personas at {ppath}; generating {args.n}…")
        personas = await generate_personas(brief, n=args.n)
        ppath.write_text(json.dumps([p.model_dump() for p in personas], indent=2))
    personas = [Persona.model_validate(p) for p in json.loads(ppath.read_text())]
    if args.only:
        personas = [p for p in personas if p.id in args.only.split(",")]
    await run_simulation(brief, personas, runs_per_persona=args.repeat, url=args.url)


async def cmd_analyze(args):
    run_dir = Path(args.run_dir)
    brief = ProductBrief.model_validate_json((run_dir / "brief.json").read_text())
    sessions = [Session.model_validate_json(p.read_text()) for p in sorted((run_dir / "sessions").glob("*.json"))]
    await analyze_run(run_dir, brief, sessions)
    meta = json.loads((run_dir / "meta.json").read_text())
    meta.update(status="done", sessions=len(sessions),
                findings=len(json.loads((run_dir / "findings.json").read_text())))
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))


async def cmd_evaluate(args):
    run_dir = Path(args.run_dir)
    brief = ProductBrief.model_validate_json((run_dir / "brief.json").read_text())
    gt = args.ground_truth or brief.ground_truth
    if not gt:
        raise SystemExit("No ground truth: pass --ground-truth")
    findings = [Finding.model_validate(f) for f in json.loads((run_dir / "findings.json").read_text())]
    result = await evaluate(findings, gt)
    (run_dir / "eval.json").write_text(result.model_dump_json(indent=2))
    print(f"Recall {result.recall:.0%}  Precision {result.precision:.0%}")
    for m in result.matches:
        print(f"  {'✓' if m['found'] else '✗'} {m['issue_id']} {m['title']} {m['finding_ids']}")


async def cmd_export(args):
    from dashboard.export import export_dashboard

    from . import config

    index = export_dashboard(config.RUNS_DIR, Path(args.out), [Path(r).name for r in args.run_ids] or None)
    print(f"Wrote {index.resolve()}")


def main():
    ap = argparse.ArgumentParser(prog="agenticritic")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("personas", help="generate personas from a project brief")
    p.add_argument("project")
    p.add_argument("-n", type=int, default=6)

    r = sub.add_parser("run", help="run synthetic users against the product")
    r.add_argument("project")
    r.add_argument("--url", help="override the brief's URL")
    r.add_argument("--repeat", type=int, default=1, help="sessions per persona")
    r.add_argument("--only", help="comma-separated persona ids")
    r.add_argument("-n", type=int, default=6, help="personas to generate if none exist")

    a = sub.add_parser("analyze", help="re-aggregate and evaluate an existing run's sessions")
    a.add_argument("run_dir")

    e = sub.add_parser("evaluate", help="score a run's findings against known issues")
    e.add_argument("run_dir")
    e.add_argument("--ground-truth")

    x = sub.add_parser("export", help="write the dashboard as a static folder you can open or share")
    x.add_argument("run_ids", nargs="*", help="runs to include (default: all)")
    x.add_argument("--out", default="export")

    args = ap.parse_args()
    asyncio.run({"personas": cmd_personas, "run": cmd_run, "analyze": cmd_analyze, "evaluate": cmd_evaluate,
                 "export": cmd_export}[args.cmd](args))


if __name__ == "__main__":
    main()
