# Autonomous Research Agent

A multi-agent system that takes a natural-language research question, autonomously
plans how to answer it, decides which sources to query, searches them in parallel,
extracts and deduplicates findings, scores them for relevance/credibility/freshness,
and synthesizes a professional Markdown + PDF research report — with zero hardcoded
topic-to-source mappings and zero canned responses.

## Project Overview

Each stage — planning, source selection, searching, extracting, scoring, and
writing the report — is its own agent, wired together as a
[LangGraph](https://langchain-ai.github.io/langgraph/) state graph. The LLM does
the real reasoning at every step: what to search for, which sources fit the
query, and how relevant/credible/fresh each finding is. Nothing is hardcoded —
no fixed topic→source table, no credibility allowlist, no canned report
template. The only non-LLM code is mechanical bookkeeping (URL dedup, JSON
parsing, file I/O) that never touches what the research actually finds or
concludes.

A small web UI (`app/static/`, served at `/`) lets you run a query, watch the
agent reason live, and read the finished report — plain HTML/CSS/JS, no
framework, no build step.

## Architecture Diagram

```
                         User query
                             |
                             v
                     +---------------+
                     |    Planner    |  LLM: research goal, information needs,
                     |     Agent     |  candidate source TYPES
                     +---------------+
                             |
                             v
                     +---------------+
                     |    Source     |  LLM: concrete (source, query) tasks
                     |   Selector    |  per information need
                     +---------------+
                             |
              +--------------+--------------+
              |  fan-out (LangGraph Send)    |
              v              v               v
        +-----------+  +-----------+   +-----------+
        |  Search   |  |  Search   |   |  Search   |   <- run concurrently,
        |  Worker   |  |  Worker   |   |  Worker   |      each scrapes its own
        | (Tavily)  |  |  (Wiki)   |   |  (arXiv)  |      top results too
        +-----------+  +-----------+   +-----------+
              |              |               |
              +--------------+--------------+
                             v
                     +---------------+
                     |   Extractor   |  LLM: title, main idea, facts,
                     |     Agent     |  stats, dates, names, confidence
                     +---------------+
                             v
                     +---------------+
                     | Deduplicator  |  URL dedup + near-duplicate
                     |     Agent     |  text merge (difflib)
                     +---------------+
                             v
                     +---------------+
                     |   Relevance   |  LLM judges relevance, credibility,
                     |    Scorer     |  freshness, and completeness
                     +---------------+
                             v
                     +---------------+
                     | Summarizer    |  LLM: executive summary, key findings,
                     |    Agent      |  analysis, stats, risks, insights
                     +---------------+
                             v
                     +---------------+
                     |    Report     |  Markdown -> .md + professionally
                     |   Generator   |  formatted .pdf
                     +---------------+
                             v
                     +---------------+
                     |    Memory     |  SQLite: query, timestamp, summary,
                     |    Storage    |  sources, report paths
                     +---------------+
                             v
                       Final Response
```

## Features

- **Autonomous planning** — the LLM decomposes the query into prioritized information needs.
- **Dynamic source selection** — source types are chosen per-query, not hardcoded.
- **Parallel search** — every (source, query) task runs as its own LangGraph branch (`Send` fan-out), and page scraping within a branch is concurrent (`asyncio.gather`).
- **Streaming responses** — `POST /api/research/stream` emits each agent's reasoning log via Server-Sent Events as the graph executes.
- **Memory** — every session (query, timestamp, summary, sources, report paths) is persisted to SQLite; `GET /api/history/similar` lets you reuse a past run instead of re-searching.
- **Markdown + PDF export** — every report is written to disk in both formats; the PDF has cover-page styling, section headings, and pagination.
- **Confidence & credibility scoring** — findings carry an extraction confidence, plus relevance/credibility/freshness/completeness scores that gate what reaches the final report.
- **Search caching** — identical (source, query) pairs are served from an in-process TTL cache.
- **Retry & error isolation** — network and LLM calls retry with backoff (`tenacity`); a failed source/finding is dropped, not fatal to the run.
- **Reasoning logs** — every node appends a human-readable log line describing its decision, returned in both the sync and streaming APIs.
- **Async throughout** — FastAPI + LangGraph async nodes + async HTTP clients end to end.

## Installation

Requires Python 3.12+.

```bash
git clone <this-repo>
cd Autonomous_Research_Agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Setup

```bash
cp .env.example .env
```

Then edit `.env` and set at least one LLM provider key.

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `LLM_PROVIDER` | `openai`, `anthropic`, or `mistral` | `openai` |
| `OPENAI_API_KEY` | OpenAI API key (if `LLM_PROVIDER=openai`) | — |
| `OPENAI_MODEL` | OpenAI model id | `gpt-4.1` |
| `ANTHROPIC_API_KEY` | Anthropic API key (if `LLM_PROVIDER=anthropic`) | — |
| `ANTHROPIC_MODEL` | Anthropic model id | `claude-sonnet-4-5` |
| `MISTRAL_API_KEY` | Mistral API key (if `LLM_PROVIDER=mistral`) | — |
| `MISTRAL_MODEL` | Mistral model id | `mistral-large-latest` |
| `LLM_MIN_INTERVAL_SECONDS` | Minimum gap between LLM calls, enforced process-wide | `1.0` |
| `TAVILY_API_KEY` | Optional; enables the high-quality `tavily` source | — |
| `MAX_SEARCH_RESULTS_PER_SOURCE` | Results fetched per search task | `5` |
| `MAX_PAGES_TO_SCRAPE` | Reserved cap on full-page scrapes | `8` |
| `SEARCH_CACHE_TTL_SECONDS` | TTL for the in-process search cache | `3600` |
| `RELEVANCE_SCORE_THRESHOLD` | Minimum combined score to keep a finding | `0.45` |
| `HTTP_TIMEOUT_SECONDS` | Timeout for scraping/search HTTP calls | `20` |
| `DATABASE_PATH` | SQLite file path | `data/db/research_agent.sqlite3` |
| `REPORTS_DIR` | Where `.md`/`.pdf` reports are written | `data/reports` |

DuckDuckGo, Wikipedia, and arXiv require no API key and work out of the box;
Tavily is optional but recommended for higher-quality web results.

**Switching LLM providers is a one-line env change** — `app/tools/llm_client.py`
branches on `LLM_PROVIDER` and instantiates the matching official SDK
(`openai`, `anthropic`, or `mistralai`); every agent calls the same
`complete()`/`complete_json()` interface regardless of provider.

> **Note on rate limits**: free/trial-tier LLM keys (Mistral's included) often
> cap requests per second quite low. A shared rate limiter in
> `app/tools/llm_client.py` enforces a minimum gap (`LLM_MIN_INTERVAL_SECONDS`)
> between *every* outbound LLM call, process-wide — this is what actually
> prevents 429 storms, not the extractor's concurrency setting (which only
> bounds how much work is queued at once, not how fast it's sent). If you still
> see repeated "429 Rate limit exceeded" in the logs, raise this value; lower it
> if your key has more headroom. Every LLM-calling agent past the initial
> planning step (extractor, relevance scorer, summarizer) degrades to a
> heuristic/mechanical fallback instead of crashing the run if its call fails
> after retries — you'll see it noted in the report
> and in the `reasoning_log`.

## Running the Application

```bash
uvicorn app.main:app --reload
```

The API is served at `http://127.0.0.1:8000`; interactive docs at `/docs`.

A minimal web UI is served at `http://127.0.0.1:8000/` (plain HTML/CSS/JS, no
build step, no framework — `app/static/`). Type a query, watch the agent's
reasoning stream in live as a terminal-style trace, then read the finished
report and download it as Markdown or PDF. Past sessions are listed below and
clickable to reload without re-running the pipeline.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/api/research` | Run the full pipeline, return the final report |
| `POST` | `/api/research/stream` | Same, streamed as SSE reasoning logs + final report |
| `GET` | `/api/history?limit=50` | List past research sessions |
| `GET` | `/api/history/similar?query=...` | Find past sessions similar enough to reuse |
| `GET` | `/api/history/{session_id}` | Get a past session's record + Markdown |
| `GET` | `/api/history/{session_id}/report.md` | Download that session's Markdown report |
| `GET` | `/api/history/{session_id}/report.pdf` | Download that session's PDF report |

## Example Requests

```bash
curl -X POST http://127.0.0.1:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the latest breakthroughs in solid-state batteries?"}'
```

Streaming (SSE):

```bash
curl -N -X POST http://127.0.0.1:8000/api/research/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "How is the EU regulating generative AI in 2026?"}'
```

Reuse past research:

```bash
curl "http://127.0.0.1:8000/api/history/similar?query=solid-state+battery+breakthroughs"
```

## Example Outputs

`POST /api/research` response shape:

```json
{
  "session_id": "b6f1...e2",
  "query": "What are the latest breakthroughs in solid-state batteries?",
  "markdown": "# Research Summary\n\n**Query:** ...\n\n## Executive Summary\n...",
  "summary": {
    "executive_summary": "...",
    "key_findings": ["..."],
    "detailed_analysis": "...",
    "important_statistics": ["..."],
    "risks_and_limitations": ["..."],
    "actionable_insights": ["..."]
  },
  "references": ["https://...", "https://..."],
  "markdown_path": "data/reports/b6f1...e2.md",
  "pdf_path": "data/reports/b6f1...e2.pdf",
  "reasoning_log": [
    "Planner: goal='...' | sources=['tavily', 'arxiv']",
    "Source Selector: 4 search tasks across ['arxiv', 'tavily']",
    "Researcher[tavily]: '...' -> 5 results",
    "Extractor: 7 structured findings from 9 raw results",
    "Deduplicator: 7 -> 5 unique findings",
    "Relevance Scorer: 4/5 findings kept (threshold 0.45)",
    "Summarizer: synthesized 4 findings into report summary",
    "Report Generator: exported data/reports/....md and data/reports/....pdf",
    "Memory: session ... saved"
  ]
}
```

The generated Markdown report follows this structure:

```markdown
# Research Summary

## Executive Summary
## Key Findings
## Detailed Analysis
## Important Statistics
## Risks / Limitations
## Actionable Insights
## References
```

## Folder Structure

```
Autonomous_Research_Agent/
├── README.md
├── requirements.txt
├── pytest.ini
├── .env.example
├── app/
│   ├── main.py                  # FastAPI app + endpoints
│   ├── graph.py                 # LangGraph wiring
│   ├── agents/
│   │   ├── state.py             # shared graph state (TypedDict)
│   │   ├── planner.py
│   │   ├── source_selector.py
│   │   ├── researcher.py        # parallel search workers (Send fan-out)
│   │   ├── extractor.py
│   │   ├── deduplicator.py
│   │   ├── relevance_scorer.py
│   │   ├── summarizer.py
│   │   ├── report_generator.py
│   │   └── memory.py
│   ├── tools/
│   │   ├── llm_client.py        # OpenAI/Anthropic abstraction
│   │   ├── search.py            # Tavily/DuckDuckGo/Wikipedia/arXiv
│   │   ├── web_scraper.py       # httpx + trafilatura extraction
│   │   ├── markdown_export.py
│   │   └── pdf_export.py        # fpdf2-based professional PDF
│   ├── utils/
│   │   ├── config.py            # pydantic-settings
│   │   └── logger.py
│   └── models/
│       ├── schemas.py           # Pydantic models for the whole pipeline
│       └── database.py          # SQLite session memory
├── tests/
└── data/
    ├── db/                      # SQLite file (gitignored)
    └── reports/                 # generated .md/.pdf reports (gitignored)
```

## Design Notes / Deliberate Simplifications

- **All research reasoning is LLM-driven, not rule-based.** Planning, source
  selection, content extraction, and relevance/credibility/freshness/completeness
  scoring are each a model call reasoning over the actual query/content in front
  of it — there is no hardcoded topic→source table, no domain allowlist for
  credibility, and no fixed synthesis template with blanks filled in. The only
  non-LLM logic in the pipeline is mechanical bookkeeping that never touches
  content interpretation: exact-URL dedup, near-duplicate text merging (string
  similarity, not semantic judgment), JSON parsing/repair, and file I/O. A
  neutral-score fallback exists solely for the LLM-unavailable error path (e.g.
  a provider outage or rate limit) so one failed call can't discard an entire
  run's collected research — it is never the primary decision path.
- **Vector memory** is implemented as difflib similarity over past queries rather
  than a FAISS/Chroma embedding index — the history table is small and exact-ish
  phrasing match is enough for "did I already research this." This only affects
  *retrieving a past report to reuse*, not the research reasoning itself. Swap in
  a real embedding index (`app/models/database.find_similar`) if history grows large.

## Future Improvements

- Swap the difflib-based session similarity search for real embeddings (FAISS/Chroma) once history grows large.
- Add authenticated multi-user sessions (currently a single shared SQLite store).
- Add more source tools behind the same `SourceType` enum (e.g. SEC EDGAR, GitHub, Yahoo Finance) — the planner/selector need no changes to start using them.
- Persist and replay the full `ResearchState` per session (currently only the final report + summary are stored) for deeper audit/debugging.

## Testing

```bash
pytest -q
```

Tests cover the deterministic logic (deduplication, Markdown rendering, PDF export,
SQLite session storage, LLM JSON-repair parsing) plus the LLM-driven agents
(planner, source selector, relevance scorer, summarizer, and the full FastAPI app
including the SSE streaming endpoint) with the LLM/search calls mocked, so the
whole suite runs without API keys or network access. Exercising the pipeline
against real providers/search engines (as opposed to mocks) requires actual keys.
