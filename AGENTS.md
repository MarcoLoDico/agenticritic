# AGENTS.md

Guidance for coding agents (and humans) working in this repo. Read [README.md](README.md) for the product pitch and [TODO.md](TODO.md) for the roadmap and status log.

## What this is

agenticritic is a synthetic customer panel. LLM personas drive a real browser (Playwright) through a web app, record every step as **Goal → Action → Expectation → Result → Friction**, debrief in character, and the debriefs are clustered into findings ("4/6 personas couldn't find team invites"). Findings can be scored against known issues for **recall** and **precision**; that score is the core research question.

## Layout

```
agenticritic/          the pipeline (Python package)
  config.py            env/.env settings: models, MAX_STEPS, CONCURRENCY, HEADLESS, paths
  llm.py               OpenRouter client (OpenAI SDK) + chat_json(): JSON-only replies, retries, truncation check
  models.py            pydantic models: ProductBrief, Persona/Behavior, Step, Session, Debrief, Finding, EvalResult
  personas.py          brief → behaviorally diverse personas
  browser.py           Playwright wrapper: settle-wait, text observation, action execution, safety guards
  agent.py             per-persona loop + debrief prompt; trace_text()
  aggregate.py         sessions → findings with evidence (session + step)
  evaluate.py          findings vs ground truth → recall / precision
  runner.py            run_simulation() and analyze_run(); writes runs/<run_id>/
  cli.py               personas | run | analyze | evaluate | export
dashboard/
  views.py             page contexts + link builders shared by server and export (ServerUrls / StaticUrls)
  server.py            FastAPI viewer over runs/
  export.py            static, offline copy of the dashboard
  templates/           Jinja templates; every link goes through `urls.*`, never a hard-coded path
demo_app/              Ledgerly: fake expense SaaS with 10 planted issues (ground_truth.json)
projects/              product briefs (<name>.json) and generated personas (<name>.personas.json)
selected-exports/      static dashboard snapshots committed on purpose
tests/smoke_fake_llm.py end-to-end check with a scripted fake LLM
```

Gitignored, local only: `.env` (API key), `/runs/` (raw run output), `/export/` (scratch exports), `.venv/`.

## Setup and commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env            # OPENROUTER_API_KEY=...

.venv/bin/python tests/smoke_fake_llm.py                      # free; run after any pipeline change
.venv/bin/uvicorn demo_app.app:app --port 8100                # Ledgerly
.venv/bin/uvicorn dashboard.server:app --port 8000            # dashboard
.venv/bin/python -m agenticritic.cli personas projects/<p>.json -n 6
.venv/bin/python -m agenticritic.cli run projects/<p>.json [--url URL] [--only id,id] [--repeat N]
.venv/bin/python -m agenticritic.cli analyze runs/<run_id>    # re-aggregate + re-score existing sessions
.venv/bin/python -m agenticritic.cli export [run_id ...] [--out DIR]
```

Python 3.14, no build step, no lint config. Match the existing style: type hints, small modules, comments only where the reason isn't obvious.

## Cost rules (real money)

- `personas`, `run`, `analyze` and `evaluate` call paid models through OpenRouter on the owner's key. **Never start them without the user's explicit go-ahead**, and say roughly what it will cost first. Reference point: one 6-persona Ledgerly run cost about $0.45, mostly the analysis model (debriefs and aggregation), not the agent steps.
- Verify code changes with `tests/smoke_fake_llm.py`, or by exercising `Browser` directly against a page. Neither calls an LLM.
- If aggregation or evaluation fails after sessions finished, use `cli analyze runs/<id>` instead of re-running the sessions.
- Small panels for real sites: `MAX_STEPS=15` and 4 personas is the usual cheap configuration.

## Safety rules for live sites

- Agents click and submit real forms. Point them at demo, staging or sandbox environments. A production site is only OK logged out and with guards on.
- `ProductBrief.blocked_labels` lists controls agents may not use (substring match on text or aria-label, e.g. `"feedback"`, `"delete"`, `"log in"`). The browser also refuses off-site navigation and sends the agent back if a click leaves the host. Keep both when changing `browser.py`.
- Never commit `.env`, and never print the key.
- Run output contains third-party page content (other users' names and posts). Raw `runs/` stays local; anything copied into `selected-exports/` is published, so check with the user first.

## How the harness can lie (read before trusting findings)

Several "findings" in early runs were harness artifacts. When a finding looks surprising, check the session replay and the page itself before reporting it.

- **Client-rendered pages:** `Browser.settle()` waits until there is no "Loading…/Searching…" text and the page text has been unchanged for 1s (10s cap). Without it, agents report empty tables and irrelevant search results.
- **Text-only agents:** they see images only through the `--- IMAGES ---` list (alt text). Don't treat "no photos" or purely visual complaints as real unless vision is added.
- **Element ids:** models send targets as `3`, `"3"`, `"[3]"` or `"#3"`. `act()` normalises these. Watch for falsy ids: `0` is valid.
- **Errors become findings:** whatever `act()` raises is shown to the agent, and agents report it as an app bug. Raise plain-language messages (`there is no element [12] on this page`), never Python internals.
- **Truncation:** `chat_json` treats `finish_reason == "length"` as a failure and retries. Give prompts that return big JSON enough `max_tokens`.
- **Partial sessions still count:** a session that errors keeps its steps, still gets a debrief, and is aggregated (`aggregate` uses `if s.steps`).

## Conventions

- **Independence:** each persona gets its own browser context and its own LLM conversation. Never share state between sessions, so agents can't converge on each other's opinions.
- **Specific feedback:** frictions must cite a step and say what was expected, what happened and why it matters. Keep prompts strict about this. Vague UX advice is a bug.
- **Ground truth stays hidden:** agents and personas must never see ground truth. It's only read by `evaluate.py`. `personas.py` excludes `ground_truth`, `url` and `blocked_labels` from the brief it sends.
- **Agent context:** only the current page is sent in full. Older observations are reduced to their URL line to control cost. If you add sections to the observation, keep `URL:` as the first line and `TITLE:` as the second.
- **Run layout:** `runs/<run_id>/` contains `meta.json`, `brief.json`, `personas.json`, `sessions/*.json`, `shots/*.png`, `findings.json` and `eval.json` (eval only when the brief has `ground_truth`). The dashboard, `analyze` and `export` all read this layout, so change it everywhere or not at all.
- **Dashboard links:** templates build every link with `urls.index()`, `urls.run()`, `urls.session()` and `urls.shot()` so one set of templates serves both the server and the static export. Step deep links use `#step-N`.
- **Default models:** `anthropic/claude-haiku-5.5` for the agent loop, `anthropic/claude-sonnet-5.5` for analysis, both overridable with `AGENT_MODEL` and `ANALYSIS_MODEL`.

## Adding things

- **A new product:** add `projects/<name>.json` (copy `ledgerly.json`), optionally a ground-truth file shaped like `demo_app/ground_truth.json`, and `blocked_labels` for live sites.
- **A planted issue in Ledgerly:** change `demo_app/app.py` and add the issue to `demo_app/ground_truth.json` in the same change.
- **A new agent action:** add it to the prompt schema in `agent.py` and the dispatch in `Browser.act()`, then cover it in the smoke test.
- **When you finish meaningful work:** add a line to the status log at the bottom of `TODO.md`.
