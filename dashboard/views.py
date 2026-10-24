"""Page contexts and link builders shared by the live server and the static exporter."""

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


class ServerUrls:
    """Absolute URLs served by dashboard/server.py."""

    def index(self):
        return "/"

    def run(self, run_id):
        return f"/runs/{run_id}"

    def session(self, run_id, session_id):
        return f"/runs/{run_id}/sessions/{session_id}"

    def shot(self, run_id, name):
        return f"/runs/{run_id}/shots/{name}"


class StaticUrls:
    """Relative file links for the exported folder, from a page `depth` directories below the root.

    Layout: index.html, runs/<id>/index.html, runs/<id>/sessions/<sid>.html, runs/<id>/shots/*.png
    """

    def __init__(self, depth: int):
        self.up = "../" * depth

    def index(self):
        return f"{self.up}index.html"

    def run(self, run_id):
        return f"{self.up}runs/{run_id}/index.html"

    def session(self, run_id, session_id):
        return f"{self.up}runs/{run_id}/sessions/{session_id}.html"

    def shot(self, run_id, name):
        return f"{self.up}runs/{run_id}/shots/{name}"


def _load(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def list_runs(runs_dir: Path) -> list[dict]:
    runs = []
    if runs_dir.exists():
        for d in sorted(runs_dir.iterdir(), reverse=True):
            if d.is_dir() and (d / "meta.json").exists():
                runs.append({"meta": _load(d / "meta.json"), "eval": _load(d / "eval.json")})
    return runs


def load_sessions(run_dir: Path) -> list[dict]:
    return [_load(p) for p in sorted((run_dir / "sessions").glob("*.json"))] if (run_dir / "sessions").exists() else []


def run_context(run_dir: Path) -> dict:
    sessions = load_sessions(run_dir)
    personas = _load(run_dir / "personas.json", [])
    return {
        "meta": _load(run_dir / "meta.json"),
        "brief": _load(run_dir / "brief.json"),
        "personas": personas,
        "persona_by_id": {p["id"]: p for p in personas},
        "findings": _load(run_dir / "findings.json", []),
        "sessions": sessions,
        "eval": _load(run_dir / "eval.json"),
        "n_personas": len({s["persona"]["id"] for s in sessions}) or len(personas),
    }


def session_context(run_dir: Path, session_id: str) -> dict | None:
    s = _load(run_dir / "sessions" / f"{Path(session_id).name}.json")
    return {"meta": _load(run_dir / "meta.json"), "s": s} if s else None


def render(template: str, urls, **ctx) -> str:
    return env.get_template(template).render(urls=urls, **ctx)
