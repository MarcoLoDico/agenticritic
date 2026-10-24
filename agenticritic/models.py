from typing import Literal

from pydantic import BaseModel, Field


class ProductBrief(BaseModel):
    name: str
    url: str
    description: str
    target_users: list[str]
    primary_jobs: list[str]
    notes: str = ""
    blocked_labels: list[str] = []  # controls agents must not use on a live app (e.g. "Delete", "Feedback")
    ground_truth: str | None = None  # path to known issues, used only by `evaluate`


class Behavior(BaseModel):
    exploration: Literal["careful", "skimmer", "advanced_seeker", "literal"] = "careful"
    patience: int = Field(3, ge=1, le=5, description="1 = abandons fast, 5 = very persistent")
    tech_savviness: int = Field(3, ge=1, le=5)
    terminology_rigidity: int = Field(3, ge=1, le=5, description="5 = only uses words they already know")
    risk_tolerance: int = Field(3, ge=1, le=5)


class Persona(BaseModel):
    id: str
    name: str
    role: str
    summary: str
    goals: list[str]
    knowledge: str
    constraints: str
    preferences: str
    expectations: str
    behavior: Behavior = Behavior()

    @property
    def max_failed_attempts(self) -> int:
        return self.behavior.patience + 1


class Step(BaseModel):
    index: int
    goal: str
    url: str
    thought: str = ""
    action: dict
    expectation: str = ""
    result: str = ""  # filled in from the agent's reflection on the next step
    friction: str | None = None
    friction_severity: int | None = None  # 1-5
    screenshot: str | None = None
    error: str | None = None


class GoalOutcome(BaseModel):
    goal: str
    status: Literal["completed", "partial", "failed", "abandoned"]
    notes: str = ""


class Debrief(BaseModel):
    goal_outcomes: list[GoalOutcome] = []
    frictions: list[dict] = []  # {step, description, expected, happened, why_it_matters}
    missing_features: list[dict] = []  # {feature, why, step}
    liked: list[str] = []
    would_continue: bool = False
    would_continue_reason: str = ""
    score: int = 0  # 0-10 likelihood to recommend


class Session(BaseModel):
    id: str
    persona: Persona
    status: Literal["completed", "abandoned", "out_of_steps", "error"] = "completed"
    steps: list[Step] = []
    debrief: Debrief | None = None
    error: str | None = None


class Evidence(BaseModel):
    session_id: str
    step: int | None = None
    quote: str = ""


class Finding(BaseModel):
    id: str
    title: str
    category: Literal["usability", "missing_feature", "bug", "pricing_trust", "positive"]
    description: str
    severity: int = 3
    persona_ids: list[str] = []
    evidence: list[Evidence] = []
    recommendation: str = ""


class EvalResult(BaseModel):
    recall: float
    precision: float
    matches: list[dict]  # {issue_id, finding_ids, found}
    unmatched_findings: list[str]
