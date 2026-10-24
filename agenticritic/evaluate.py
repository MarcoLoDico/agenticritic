"""Score findings against known (historical / planted) customer issues.

recall    = share of known issues that agents independently discovered
precision = share of agent findings (excluding positives) that match a known issue.
            When ground truth is incomplete this is a lower bound: agents may find real
            problems nobody recorded.
"""

import json
from pathlib import Path

from . import config
from .llm import chat_json
from .models import EvalResult, Finding

_SYSTEM = """You are a strict evaluator. Decide which synthetic-user findings describe the same
underlying problem as each known customer issue. A match requires the same root problem
(same feature/flow and same kind of failure), not just the same general area."""


async def evaluate(findings: list[Finding], ground_truth_path: str | Path) -> EvalResult:
    issues = json.loads(Path(ground_truth_path).read_text())["issues"]
    scored = [f for f in findings if f.category != "positive"]
    data = await chat_json(
        [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": "KNOWN ISSUES:\n"
                + json.dumps([{"id": i["id"], "title": i["title"], "description": i["description"]} for i in issues], indent=1)
                + "\n\nFINDINGS:\n"
                + json.dumps([{"id": f.id, "title": f.title, "description": f.description} for f in scored], indent=1)
                + '\n\nReturn JSON: {"matches": [{"issue_id": str, "finding_ids": [str], "reason": str}]} '
                "with one entry per known issue (empty finding_ids if not found).",
            },
        ],
        model=config.ANALYSIS_MODEL,
        temperature=0,
        max_tokens=3000,
    )
    valid = {f.id for f in scored}
    matches = []
    matched_findings: set[str] = set()
    by_id = {m["issue_id"]: m for m in data.get("matches", [])}
    for issue in issues:
        m = by_id.get(issue["id"], {})
        fids = [f for f in m.get("finding_ids", []) if f in valid]
        matched_findings.update(fids)
        matches.append({"issue_id": issue["id"], "title": issue["title"], "finding_ids": fids,
                        "found": bool(fids), "reason": m.get("reason", "")})
    recall = sum(m["found"] for m in matches) / len(issues) if issues else 0.0
    precision = len(matched_findings) / len(scored) if scored else 0.0
    return EvalResult(
        recall=round(recall, 3),
        precision=round(precision, 3),
        matches=matches,
        unmatched_findings=sorted(valid - matched_findings, key=lambda x: int(x[1:])),
    )
