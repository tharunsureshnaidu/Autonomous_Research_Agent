"""Planner Agent: turns a raw user query into a structured research plan.

The LLM reasons about the research goal, breaks it into concrete
information needs, and proposes candidate source *types* (not fixed by us —
see the SourceType enum for the universe it can choose from). No mapping
from "topic keyword" to "source" is hardcoded anywhere in this file.
"""
from __future__ import annotations

from app.agents.state import ResearchState
from app.models.schemas import ResearchPlan, SourceType
from app.tools.llm_client import get_llm_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM = """You are the Planning Agent of an autonomous research system.
Given a user's research query, decide:
1. The overall research goal (one sentence).
2. 3-6 specific information needs (sub-questions) that must be answered, each with a priority 1(highest)-5(lowest).
3. Which source TYPES are likely to contain useful information. Choose only from this exact set:
   - "tavily": general-purpose high quality web search (good default for almost anything)
   - "web": broad web search via DuckDuckGo
   - "news": recent news articles
   - "wikipedia": encyclopedic background/definitions
   - "arxiv": academic papers (only for scientific/technical/AI/ML/research queries)
   Pick only the types that genuinely fit this query's nature - do not include all of them by default.
4. A one-sentence description of what the final report should deliver.

Respond as JSON matching exactly:
{
  "research_goal": "...",
  "information_needed": [{"topic": "...", "reasoning": "...", "priority": 1}],
  "candidate_sources": ["tavily", "wikipedia", ...],
  "expected_output": "..."
}
"""


async def plan_node(state: ResearchState) -> dict:
    query = state["query"]
    logger.info("planning research for query=%r", query)

    client = get_llm_client()
    raw = await client.complete_json(_SYSTEM, f"Research query: {query}")
    plan = ResearchPlan.model_validate(raw)

    # Guard against a model hallucinating an unknown source type.
    plan.candidate_sources = [s for s in plan.candidate_sources if s in set(SourceType)] or [SourceType.TAVILY]

    logger.info(
        "plan ready: goal=%r needs=%d sources=%s",
        plan.research_goal,
        len(plan.information_needed),
        [s.value for s in plan.candidate_sources],
    )
    return {
        "plan": plan.model_dump(mode="json"),
        "logs": [f"Planner: goal='{plan.research_goal}' | sources={[s.value for s in plan.candidate_sources]}"],
    }
