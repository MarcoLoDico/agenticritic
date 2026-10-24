# agenticritic

A synthetic customer panel that uses your product. It sends persona-driven browser agents through a web app, records each step as **Goal → Action → Expectation → Result → Friction**, and aggregates the feedback into findings like "4/6 personas couldn't find team invitations". Each finding links back to the sessions that produced it, so you can replay them.

The goal is to need constant customer testing less, not to replace real customers. `evaluate` measures how well the synthetic findings match real or known issues.

See [TODO.md](TODO.md) for the roadmap.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env   # then add your OPENROUTER_API_KEY
```

## Try it on the bundled demo app

Ledgerly is a fake expense-management SaaS with 10 planted product issues, listed in `demo_app/ground_truth.json`. The agents never see that file.

```bash
.venv/bin/uvicorn demo_app.app:app --port 8100          # terminal 1
.venv/bin/python -m agenticritic.cli personas projects/ledgerly.json -n 6
.venv/bin/python -m agenticritic.cli run projects/ledgerly.json
.venv/bin/uvicorn dashboard.server:app --port 8000      # then open http://localhost:8000
```

## Use it on your own app

Copy `projects/ledgerly.json` and change `name`, `url`, `description`, `target_users` and `primary_jobs`. Then:

```bash
.venv/bin/python -m agenticritic.cli personas projects/myapp.json -n 8
# edit projects/myapp.personas.json however you like
.venv/bin/python -m agenticritic.cli run projects/myapp.json --repeat 2
```

`--url` overrides the URL in the brief, for example to point at a staging build. If you have historical customer feedback, put it in a file with the same shape as `ground_truth.json` and set `"ground_truth"` in the brief. Each run is then scored automatically. You can also re-score an existing run with `cli evaluate runs/<id>`.

## Save or share results

Runs are stored under `runs/<run_id>/` (JSON + screenshots); the dashboard only reads them, so nothing is lost when servers stop. To get a folder you can open or send without running anything:

```bash
.venv/bin/python -m agenticritic.cli export                        # all runs → export/index.html
.venv/bin/python -m agenticritic.cli export 20261023-224941-cookd --out cookd-report
```

Open `index.html` in any browser. Zip the folder to share it. Screenshots make it large (about 25 MB for a 4-persona run).

## How it works

| Stage | Module |
|---|---|
| Product brief | `projects/*.json` |
| Personas based on behavior, not demographics: goals, knowledge, constraints, patience, exploration style, how strictly they stick to their own terminology | `agenticritic/personas.py` |
| One isolated browser context per agent, so agents can't influence each other. The agent sees visible text plus indexed interactive elements and takes a screenshot at every step | `agenticritic/browser.py` |
| Agent loop: stays in character, gives up based on patience, records friction against the step where it happened | `agenticritic/agent.py` |
| Per-session debrief: every friction cites a step and states expected vs. what happened | `agenticritic/agent.py` |
| Clustering into findings with evidence | `agenticritic/aggregate.py` |
| Recall and precision against known issues | `agenticritic/evaluate.py` |
| Dashboard | `dashboard/` |

Models are called through OpenRouter. The defaults are `anthropic/claude-haiku-5.5` for the step loop and `anthropic/claude-sonnet-5.5` for analysis. Override them with `AGENT_MODEL` and `ANALYSIS_MODEL` in `.env`.

> **Safety:** agents click on and submit real forms. Point them only at demo, staging or sandbox environments, never at production data.
