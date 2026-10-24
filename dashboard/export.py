"""Write the dashboard as a self-contained static folder (open index.html, no server needed)."""

import shutil
from pathlib import Path

from .views import StaticUrls, list_runs, render, run_context, session_context


def export_dashboard(runs_dir: Path, out: Path, run_ids: list[str] | None = None) -> Path:
    runs = list_runs(runs_dir)
    if run_ids:
        missing = set(run_ids) - {r["meta"]["run_id"] for r in runs}
        if missing:
            raise SystemExit(f"Unknown run(s): {', '.join(sorted(missing))}")
        runs = [r for r in runs if r["meta"]["run_id"] in run_ids]

    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render("index.html", StaticUrls(0), runs=runs))

    for r in runs:
        run_id = r["meta"]["run_id"]
        src, dst = runs_dir / run_id, out / "runs" / run_id
        ctx = run_context(src)
        (dst / "sessions").mkdir(parents=True, exist_ok=True)
        (dst / "index.html").write_text(render("run.html", StaticUrls(2), **ctx))
        for s in ctx["sessions"]:
            page = render("session.html", StaticUrls(3), **session_context(src, s["id"]))
            (dst / "sessions" / f"{s['id']}.html").write_text(page)
        if (src / "shots").exists():
            shutil.copytree(src / "shots", dst / "shots", dirs_exist_ok=True)
    return out / "index.html"
