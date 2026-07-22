from typing import TypedDict

class ResearchPilotState(TypedDict):
    query: str
    sub_questions: list[str]
    findings: list[dict[str, str]]
    draft_report: str
    critic_score: int
    revision_count: int
    verified: bool
    stale: bool
    approval_status: str
    watchlist_entity: str
