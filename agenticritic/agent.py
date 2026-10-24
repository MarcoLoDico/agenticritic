"""A single simulated user working through their goals in a real browser."""

import json

from . import config
from .browser import Browser
from .llm import chat_json
from .models import Debrief, Persona, ProductBrief, Session, Step

_STYLE = {
    "careful": "You read pages fully before acting and explore menus methodically.",
    "skimmer": "You skim. You read headings and button labels only, and click the first thing that looks plausible.",
    "advanced_seeker": "You actively look for advanced features, settings, shortcuts, integrations and bulk actions.",
    "literal": "You only recognise the words you already use for things. If a label uses unfamiliar jargon you assume it is not what you want.",
}


def persona_prompt(p: Persona, brief: ProductBrief) -> str:
    b = p.behavior
    return f"""You are role-playing a real person trying out a product called "{brief.name}".
Stay fully in character. You are NOT a QA tester and NOT an AI assistant: you are this person,
with their knowledge, impatience and blind spots.

WHO YOU ARE: {p.name}, {p.role}. {p.summary}
WHAT YOU KNOW: {p.knowledge}
CONSTRAINTS: {p.constraints}
PREFERENCES: {p.preferences}
WHAT YOU EXPECT FROM A PRODUCT LIKE THIS: {p.expectations}
HOW YOU BROWSE: {_STYLE[b.exploration]}
Patience {b.patience}/5, tech savviness {b.tech_savviness}/5, sticks to own terminology {b.terminology_rigidity}/5, risk tolerance {b.risk_tolerance}/5.
You give up on a goal after about {p.max_failed_attempts} failed or confusing attempts. Do not
behave more patiently or rationally than this person would.

YOUR GOALS (in your own words):
{chr(10).join(f"{i + 1}. {g}" for i, g in enumerate(p.goals))}

Each turn you see the current page: a LOAD line (how long content took to appear; react to
slowness as this person would), the visible text, the IMAGES on the page (you see photos only
through their descriptions; a photo with no description is still a photo a person would see),
and the interactive elements with [id]s.
Respond with JSON:
{{
  "current_goal": str,                 // which goal you are working on
  "last_result": str,                  // what actually happened after your previous action (empty on first turn)
  "friction": str | null,              // if the last result or this page confused, annoyed or blocked you: what you expected vs what happened and why it matters to YOU. null if fine.
  "friction_severity": 1-5 | null,
  "thought": str,                      // short, in character
  "action": {{"type": "click"|"type"|"select"|"navigate"|"back"|"scroll"|"goal_done"|"give_up_goal"|"finish",
             "target": element id (for click/type/select), "text": str (for type/select), "submit": bool, "url": str (navigate only, a path on this site)}},
  "expectation": str                   // what you expect to happen after this action
}}
Use "goal_done" when the current goal is achieved, "give_up_goal" when you'd realistically give up on it,
and "finish" when you are done with all goals or would stop using the product entirely.
Only fill one field per "type" action; you'll see the page again after each action."""


_DEBRIEF = """The session is over. Step out of the browser but stay in character and give product feedback.
Every friction must reference the step number where it happened and say what you expected,
what happened instead, and why it matters for someone like you. No vague advice like
"make it more intuitive". Return JSON:
{
  "goal_outcomes": [{"goal": str, "status": "completed"|"partial"|"failed"|"abandoned", "notes": str}],
  "frictions": [{"step": int, "description": str, "expected": str, "happened": str, "why_it_matters": str}],
  "missing_features": [{"feature": str, "why": str, "step": int | null}],
  "liked": [str],
  "would_continue": bool,
  "would_continue_reason": str,
  "score": 0-10
}"""


def trace_text(session: Session) -> str:
    lines = []
    for s in session.steps:
        a = s.action
        what = a.get("type", "")
        if a.get("target") is not None:
            what += f" #{a['target']}"
        if a.get("text"):
            what += f' "{a["text"]}"'
        if a.get("url"):
            what += f" {a['url']}"
        lines.append(
            f"STEP {s.index} on {s.url} | goal: {s.goal} | action: {what} | expected: {s.expectation} "
            f"| result: {s.error or s.result} | friction: {s.friction or '-'}"
        )
    return "\n".join(lines)


def _temperature(p: Persona) -> float:
    # Less patient / skimming personas act more erratically.
    base = {"careful": 0.4, "literal": 0.5, "advanced_seeker": 0.6, "skimmer": 0.9}[p.behavior.exploration]
    return min(1.0, base + (3 - p.behavior.patience) * 0.05)


async def run_session(
    session_id: str, persona: Persona, brief: ProductBrief, browser: Browser, log=print
) -> Session:
    session = Session(id=session_id, persona=persona)
    messages: list[dict] = [{"role": "system", "content": persona_prompt(persona, brief)}]
    failures_on_goal = 0
    current_goal = persona.goals[0] if persona.goals else ""
    goals_resolved = 0

    try:
        await browser.start()
        last_outcome = ""
        for i in range(config.MAX_STEPS):
            obs = await browser.observe()
            shot = await browser.screenshot(f"{session_id}-{i:02d}")
            # Only the current page is sent in full; older observations shrink to their URL line
            # (the agent's own JSON replies still carry its memory of what it saw and did).
            for m in messages[1:]:
                if m["role"] == "user" and "--- VISIBLE TEXT ---" in m["content"]:
                    m["content"] = m["content"].split("\nTITLE:")[0] + "\n(page content omitted)"
            messages.append({"role": "user", "content": f"{last_outcome}STEP {i}\n{obs}"})
            # Keep the context bounded: system prompt + the last few user/assistant turns.
            if len(messages) > 12:
                messages = [messages[0]] + messages[-11:]

            decision = await chat_json(messages, model=config.AGENT_MODEL, temperature=_temperature(persona), max_tokens=1500)
            messages.append({"role": "assistant", "content": json.dumps(decision)})

            current_goal = decision.get("current_goal") or current_goal
            action = decision.get("action") or {"type": "finish"}
            step = Step(
                index=i,
                goal=current_goal,
                url=browser.page.url,
                thought=decision.get("thought", ""),
                action=action,
                expectation=decision.get("expectation", ""),
                screenshot=shot,
            )
            if session.steps and decision.get("last_result"):
                session.steps[-1].result = decision["last_result"]
            if decision.get("friction"):
                # Friction is about the outcome of the previous action (or the landing page on step 0).
                target = session.steps[-1] if session.steps else step
                target.friction = decision["friction"]
                target.friction_severity = decision.get("friction_severity")
            session.steps.append(step)
            log(f"  [{persona.id}] {i:02d} {action.get('type')} {action.get('target', action.get('url', ''))} — {step.thought[:80]}")

            kind = action.get("type")
            if kind == "finish":
                break
            if kind in ("goal_done", "give_up_goal"):
                goals_resolved += 1
                failures_on_goal = 0
                step.result = "goal marked done" if kind == "goal_done" else "gave up on goal"
                last_outcome = ""
                if goals_resolved >= len(persona.goals):
                    break
                continue

            try:
                step.result = await browser.act(action)  # refined by the agent's own reflection next turn
                last_outcome = f"(system) action executed: {step.result}\n\n"
            except Exception as e:  # noqa: BLE001 - a click on a stale/missing element etc.
                step.error = str(e).splitlines()[0][:200]
                failures_on_goal += 1
                last_outcome = f"(system) action failed: {step.error}\n\n"
            if failures_on_goal > persona.max_failed_attempts + 2:
                session.status = "abandoned"
                break
        else:
            session.status = "out_of_steps"

        if any(s.action.get("type") == "give_up_goal" for s in session.steps) and session.status == "completed":
            session.status = "abandoned"

    except Exception as e:  # noqa: BLE001
        session.status = "error"
        session.error = f"{type(e).__name__}: {e}"
        log(f"  [{persona.id}] ERROR {session.error}")

    # Debrief even after an error: the steps and frictions recorded so far are still evidence.
    if session.steps:
        try:
            # The rolling context was trimmed, so debrief from the full structured trace instead.
            debrief = await chat_json(
                [
                    messages[0],
                    {"role": "user", "content": f"Your full session trace:\n{trace_text(session)}\n\n{_DEBRIEF}"},
                ],
                model=config.ANALYSIS_MODEL,
                temperature=0.4,
                max_tokens=5000,
            )
            session.debrief = Debrief.model_validate(debrief)
        except Exception as e:  # noqa: BLE001
            session.error = (session.error or "") + f" | debrief failed: {e}"
            log(f"  [{persona.id}] DEBRIEF FAILED {e}")
    return session
