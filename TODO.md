# agenticritic — TODO

> A synthetic customer panel that continuously uses your product.
>
> **Understand Product → Generate Personas → Give Persona a Goal → Agent Uses Product → Record Experience → Produce Feedback → Aggregate Across Personas**

Decisions (from kickoff):
- Python + Playwright (async), LLM calls via **OpenRouter** (OpenAI-compatible API, `OPENROUTER_API_KEY`).
- Default models: agent loop `anthropic/claude-haiku-5.5` (cheap, many steps), analysis `anthropic/claude-sonnet-5.5` (personas, debriefs, aggregation, eval). Both overridable via env.
- Targets: a bundled demo app with **planted** UX issues (for validation) **and** any URL.
- Output: local web dashboard (FastAPI + Jinja), plus JSON on disk under `runs/`.

---

## MVP (v0.1)

### 0. Scaffolding
- [x] Repo layout, `requirements.txt`, `.env.example`, `README.md`
- [x] Config loader (`.env`, model names, concurrency, step budget)
- [x] OpenRouter client with JSON-output helper + retry

### 1. Understand product
- [x] Project brief file (`projects/*.json`): name, URL, description, target users, primary jobs
- [ ] (later) Auto-crawl the app to draft the brief

### 2. Personas
- [x] Persona schema built on **behavior**, not demographics: goal(s), knowledge, constraints, preferences, patience, risk tolerance, product expectations
- [x] Behavior knobs that change how the agent acts: exploration style (careful / skimmer / advanced-seeker / literal), patience → max failed attempts before abandoning, terminology rigidity, tech savviness
- [x] `generate-personas` command: brief → N diverse personas → `personas.json` the startup can edit
- [ ] Persona editor in dashboard

### 3. Agent uses product
- [x] Playwright wrapper: fresh isolated browser context per agent (no shared state between agents)
- [x] Observation = URL + title + visible text + indexed list of interactive elements (DOM/accessibility based)
- [x] Actions: click, type, select, navigate, back, scroll, done, give_up
- [x] Screenshot every step (for replay)
- [x] Each step recorded as **Goal → Action → Expectation → Result → Friction**
- [x] Persona-driven abandonment (patience budget, step budget)
- [ ] (later) Optional vision mode: send screenshots to the model
- [ ] (later) Auth: login with test credentials per project

### 4. Session feedback (debrief)
- [x] Per-session debrief: goal outcomes, top frictions (tied to steps), missing features, would-continue + reason, score
- [x] Feedback must cite specific steps — no vague "make it more intuitive"

### 5. Aggregate
- [x] Cluster frictions / requests across sessions into findings: "7/10 first-time users struggled to find team invitations"
- [x] Each finding links to evidence (session + step) for replay
- [x] Categories: usability, missing feature, bug, pricing/trust, positive

### 6. Validation (the core question: does synthetic feedback predict real feedback?)
- [x] Demo app ("Ledgerly", expense management) with planted issues + `ground_truth.json`
- [x] `evaluate`: LLM judge matches findings ↔ known issues → **recall** (known issue → found independently?) and **precision** (agent complaints real users also care about)
- [x] Agents never see ground truth
- [ ] (later) Import real historical customer feedback (CSV/Intercom/etc.) as ground truth for real startups

### 7. Dashboard
- [x] Runs list
- [x] Run page: findings (counts, severity, personas affected), eval scores, personas
- [x] Session replay: step-by-step trace with screenshots
- [ ] Launch a run from the UI
- [x] Static export (`cli export`): self-contained folder, works offline

---

## After MVP
- [ ] Re-run on every build (CI hook / webhook) and diff findings between builds
- [ ] Diversity guardrails: detect personas converging on identical opinions
- [ ] Calibrate "human-ness": impatience, misreads, random abandonment
- [ ] Coverage map: which pages/flows were never explored
- [ ] Safety: domain allowlist, block destructive actions (delete, pay, send email) on real apps
- [ ] Cost tracking per run (tokens → $)
- [ ] Multi-tenant / hosted version

## Status log
- 2026-10-23 — MVP built. Pipeline verified end-to-end against Ledgerly with a scripted stand-in LLM (real browser, real dashboard). **Not yet run with a real model**: needs `OPENROUTER_API_KEY` in `.env`.
- 2026-10-23 — First real runs (6 personas, haiku-5.5 agents / sonnet-5.5 analysis, ~3 min each):
  - Run 1: recall 40%, but invalid. Harness bugs: bracketed ids ("[0]") broke actions, and truncated JSON dropped 3/6 sessions.
  - Run 2: recall 70% after fixes, but a regression (id 0 treated as missing) killed the expense-submitter session.
  - Run 3 (`runs/20261023-223949-ledgerly`): **recall 80% (8/10)**, precision 38%. Missed GT8 (bulk actions) and GT9 (CSV export). Most unmatched findings are real Ledgerly flaws I didn't plant (unlabelled demo data, roles never explained, no receipt upload), so precision is a lower bound.
- Next:
  - [ ] Run `--repeat 3` and report recall as mean ± spread (one run is noisy: run 2 found GT9, run 3 didn't)
  - [ ] Extend ground truth with the legitimate unplanted issues, or have a human label unmatched findings as real/false
  - [ ] Agents never browse the expense list as power users → coverage gap for bulk actions (GT8)
- 2026-10-23 — First real-site run: Cookd (`runs/20261023-224941-cookd`), 4 logged-out personas, 15 steps. 13 findings; spot-checking showed 3 were harness artifacts:
  - Agents snapshot client-rendered pages before data arrives (leaderboard "empty", search "irrelevant"). Fix: wait until "Loading…/Searching…" text is gone, or the DOM stops changing.
  - Agents are text-only, so they reported "no photos". Fix: list `<img>` alt text in the observation, or turn on vision mode.
  - [x] Both fixed: observations now wait for the page to settle (no loading text, text unchanged for 1s, 10s cap) and report load time, and they list images with alt text. Verified on Cookd without LLM calls (leaderboard shows rows, 'chicken and rice' search shows 25 filtered results, photos listed).
