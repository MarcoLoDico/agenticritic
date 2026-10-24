"""Read-only dashboard over runs/.  Run:  uvicorn dashboard.server:app --port 8000"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from agenticritic import config

from .views import ServerUrls, list_runs, render, run_context, session_context

app = FastAPI()
URLS = ServerUrls()


def _run_dir(run_id: str) -> Path:
    d = (config.RUNS_DIR / run_id).resolve()
    if config.RUNS_DIR.resolve() not in d.parents or not d.is_dir():
        raise HTTPException(404)
    return d


@app.get("/", response_class=HTMLResponse)
def index():
    return render("index.html", URLS, runs=list_runs(config.RUNS_DIR))


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run(run_id: str):
    return render("run.html", URLS, **run_context(_run_dir(run_id)))


@app.get("/runs/{run_id}/sessions/{session_id}", response_class=HTMLResponse)
def session(run_id: str, session_id: str):
    ctx = session_context(_run_dir(run_id), session_id)
    if not ctx:
        raise HTTPException(404)
    return render("session.html", URLS, **ctx)


@app.get("/runs/{run_id}/shots/{name}")
def shot(run_id: str, name: str):
    p = _run_dir(run_id) / "shots" / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)
