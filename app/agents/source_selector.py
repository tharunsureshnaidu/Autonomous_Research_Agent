"""Source Selection Agent: turns the plan's information needs into concrete search tasks.

For every information need, the LLM decides which of the plan's candidate
source types actually apply and writes an effective search query for each -
still no hardcoded topic-to-source table.
"""
from __future__ import annotations

from app.agents.state import ResearchState
from app.models.schemas import SearchTask, SourceSelectionPlan
from app.tools.llm_client import get_llm_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM = """You are the Source Selection Agent of an autonomous research system.
You are given a research plan: a goal, a list of information needs, and a list of
allowed source types. For EACH information need, decide which allowed source
type(s) are actually worth querying (not necessarily all of them), and write an
effective, specific search query string for each one.

Respond as JSON matching exactly:
{"tasks": [{"source": "tavily", "query": "...", "information_need": "...", "priority": 1}]}

Rules:
- "source" must be one of the allowed source types given to you.
- "information_need" must exactly match one of the given topics.
- Keep queries concise and search-engine friendly, not full sentences.
- Produce at most 2 tasks per information need.
"""


async def select_sources_node(state: ResearchState) -> dict:
    plan = state["plan"]
    client = get_llm_client()

    user = (
        f"Research goal: {plan['research_goal']}\n"
        f"Allowed source types: {plan['candidate_sources']}\n"
        f"Information needs:\n"
        + "\n".join(f"- {n['topic']} (priority {n['priority']})" for n in plan["information_needed"])
    )
    raw = await client.complete_json(_SYSTEM, user)
    selection = SourceSelectionPlan.model_validate(raw)

    allowed = set(plan["candidate_sources"])
    tasks = [t for t in selection.tasks if t.source.value in allowed]
    if not tasks:
        # Fallback so the pipeline never stalls on a malformed selection.
        tasks = [
            SearchTask(source=plan["candidate_sources"][0], query=plan["research_goal"], information_need=n["topic"], priority=n["priority"])
            for n in plan["information_needed"]
        ]

    logger.info("source selection produced %d search tasks", len(tasks))
    return {
        "search_tasks": [t.model_dump(mode="json") for t in tasks],
        "logs": [f"Source Selector: {len(tasks)} search tasks across {sorted({t.source.value for t in tasks})}"],
    }
