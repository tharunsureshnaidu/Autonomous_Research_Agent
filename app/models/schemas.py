"""Pydantic models shared across the pipeline: plan, search, extraction, scoring, report, API I/O."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """The universe of search tools the agent may choose from. The LLM decides which apply."""

    TAVILY = "tavily"
    WEB = "web"  # DuckDuckGo general web search
    NEWS = "news"  # DuckDuckGo news search
    WIKIPEDIA = "wikipedia"
    ARXIV = "arxiv"


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


class InformationNeed(BaseModel):
    topic: str = Field(..., description="A specific sub-question the research must answer")
    reasoning: str = Field(..., description="Why this sub-question matters for the goal")
    priority: int = Field(..., ge=1, le=5, description="1 = highest priority")


class ResearchPlan(BaseModel):
    research_goal: str
    information_needed: list[InformationNeed]
    candidate_sources: list[SourceType] = Field(
        default_factory=list, description="Source types the planner believes are relevant"
    )
    expected_output: str = Field(..., description="What the final report should deliver")


class SearchTask(BaseModel):
    source: SourceType
    query: str
    information_need: str = Field(..., description="Which information need this task serves")
    priority: int = Field(default=3, ge=1, le=5)


class SourceSelectionPlan(BaseModel):
    tasks: list[SearchTask]


# ---------------------------------------------------------------------------
# Search / extraction
# ---------------------------------------------------------------------------


class RawResult(BaseModel):
    source: SourceType
    url: str
    title: str
    snippet: str = ""
    content: str = ""
    published_date: Optional[str] = None


class ExtractedFinding(BaseModel):
    title: str
    main_idea: str
    facts: list[str] = Field(default_factory=list)
    statistics: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    source: SourceType
    url: str
    confidence: float = Field(ge=0.0, le=1.0)


class ScoredFinding(BaseModel):
    finding: ExtractedFinding
    relevance: float = Field(ge=0.0, le=1.0)
    credibility: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    completeness: float = Field(ge=0.0, le=1.0)

    @property
    def total_score(self) -> float:
        return round(
            0.4 * self.relevance + 0.3 * self.credibility + 0.15 * self.freshness + 0.15 * self.completeness,
            4,
        )


# ---------------------------------------------------------------------------
# Summary / report
# ---------------------------------------------------------------------------


class ResearchSummary(BaseModel):
    executive_summary: str
    key_findings: list[str]
    detailed_analysis: str
    important_statistics: list[str]
    risks_and_limitations: list[str]
    actionable_insights: list[str]


class ResearchReport(BaseModel):
    session_id: str
    query: str
    markdown: str
    summary: ResearchSummary
    references: list[str]
    created_at: str


# ---------------------------------------------------------------------------
# API I/O
# ---------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Natural-language research question")


class SessionRecord(BaseModel):
    session_id: str
    query: str
    timestamp: str
    executive_summary: str
    sources: list[str]
    markdown_path: str
    pdf_path: Optional[str] = None
