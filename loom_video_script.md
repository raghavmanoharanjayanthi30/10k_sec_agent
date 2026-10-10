Loom Video Script (10-30 minutes)
Section 1: Problem Framing (2-3 min)
What to show: README.md open, or just talk to camera

Script:

"The problem I'm solving: A 500-person professional services firm has analysts spending 4 hours a day on early-stage research — pulling background on companies from SEC filings. Senior partners want this automated.

What I built: A multi-agent system that takes a natural language question about a company, fetches the relevant SEC 10-K filing sections, and returns a grounded report with citations.

Who uses it: Internal analysts who need quick answers like 'What are Apple's risk factors?' or 'What's Microsoft's cloud revenue?'

What I cut for scope: I focused on 10-K filings only — no 10-Q quarterly reports, no 8-K event filings. I also used in-memory storage instead of Redis, which means jobs don't survive server restarts. That's a production TODO."

Section 2: Architecture Defense (8-12 min)
What to show: README.md Mermaid diagram, then agents/graph.py

2a. Walk the State Graph
"Let me walk through the architecture. [Show Mermaid diagram]

User question comes in → goes to the Planner
Planner identifies the company ticker (like AAPL) and which 10-K items we need (Item 1A for risk factors, Item 7 for financials, etc.)
First conditional edge: If Planner can't identify a company or relevant items → route to 'Cannot Answer' and exit. Otherwise → route to Researcher
Researcher calls the MCP tools to fetch the actual filing data from SEC EDGAR
Synthesizer combines the raw data into a structured report with citations
Second conditional edge: If Synthesizer says the answer is complete → END. If it needs more data → loop back to Planner. I cap this at 2 iterations to prevent infinite loops."
Show code: Open agents/graph.py lines 11-47 (the routing functions)

"Here's the actual routing logic. route_after_planner checks if items_needed is empty — if so, we can't answer. route_after_synthesizer checks is_complete and the iteration count."

2b. Defend Orchestration Pattern
"I used a supervisor-like sequential pattern — Planner delegates to Researcher, Researcher hands off to Synthesizer.

Why not hierarchical? I only have 3 agents, not enough complexity to need multiple levels of supervisors.

Why not swarm? The workflow is predictable — plan, research, synthesize. Agents don't need to negotiate with each other dynamically."

2c. Defend Sync vs Async
"The /research endpoint is async with background tasks. When you POST a question, it immediately returns a job_id and runs the research in the background. You poll /jobs/{job_id} to get results.

Why? Research takes 10-30 seconds. If I blocked the request, the client would timeout and I'd tie up a worker thread. With background tasks, the server stays responsive and can handle many concurrent users."

2d. Defend MCP Choice
"I used sec-edgar-mcp for fetching SEC filings.

Why MCP instead of direct API calls? MCP gives me a standardized interface — I can swap out the data source later without rewriting my agent logic. Plus the MCP server handles rate limiting and pagination for me.

One limitation I hit: The MCP tool only extracts 3 sections (business, risk factors, MD&A) with 10k character limits. So I built a custom section_extractor.py that fetches the full filing and parses all 16 standard 10-K items."

Section 3: Live Demo (8-12 min)
What to show: Terminal + browser

3a. Run a Fresh Question
"Let me run a question that's NOT in my golden set."

cd /Users/raghavraahul/Downloads/10k_filing_agentic_system
source venv/bin/activate
uvicorn app.main:app --reload --port 8080
Then in another terminal or browser (Swagger UI at http://localhost:8080/docs):

curl -X POST http://localhost:8080/research \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Nvidia'\''s revenue breakdown by segment?"}'
"I get back a job_id. Now I poll for results..."

curl http://localhost:8080/jobs/<job_id>
"And here's the structured report with citations to the 10-K filing."

3b. Show LangSmith Trace
"Let me show you the LangSmith trace for this run."

Open LangSmith in browser (or show your screenshots in /traces/)

"You can see the full execution: Planner ran first, identified NVDA and Item 7. Then Researcher made 3 MCP tool calls. Then Synthesizer produced the final report. Total latency was about 15 seconds — most of that is the LLM calls and SEC API fetches.

Latency hotspot: The Researcher's get_filing_content call is the slowest because 10-K filings can be 300k+ characters. I added parallel chunk fetching to speed this up."

3c. Run Eval
python eval/run_eval.py
"This runs my 5 golden tasks and checks if the responses contain the expected facts. I'm using an LLM-as-judge to score quality.

What it measures: Does the response mention the required facts? Is it grounded in the actual filing? Did it cite sources?

Results: 5/5 passing, average judge score 4.2/5."

Section 4: Tradeoffs & What's Next (3-5 min)
What to show: Talk to camera or README production section

4a. What's Not Production-Ready
"The biggest gap is persistence. Right now jobs and cache are in-memory — if the server restarts, everything is lost. For production, I'd add Redis for the job store and cache.

Also, no authentication by default. I added optional API key auth, but it's off in dev mode. Production would need proper auth and rate limiting per user, not just per IP."

4b. Why LangGraph Over Alternatives
"I considered CrewAI — it's great for role-based agents, but I didn't need the 'backstory' and 'goal' abstractions. My agents are more functional than persona-based.

I considered LlamaIndex — it's excellent for RAG, but I'm not doing vector search over documents. I'm fetching specific filing sections by item number.

LangGraph was the right fit because I needed explicit state management and conditional routing. The StateGraph abstraction maps directly to my workflow."

4c. What Claude Code Got Wrong
"The biggest issue was assuming the MCP response structure. Claude generated code that looked for sections_result['risk_factors'], but the actual response was nested: sections_result['sections']['risk_factors']. The code silently failed — no error, just empty data.

Lesson: Always inspect actual API responses. Don't trust the AI's assumptions about data structures."

Section 5: Failure Mode Walk-Through (2-3 min)
What to show: Terminal

Option A: Send a Bad Question
curl -X POST http://localhost:8080/research \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the weather today?"}'
"This question has nothing to do with SEC filings. Watch what happens...

The Planner can't identify a company or relevant 10-K items, so it routes to 'Cannot Answer'. The user gets back a clear error: 'This question cannot be answered using SEC 10-K filings.'

What logs: The job status shows 'failed' with the error message. In production, I'd also log the question for analysis — maybe we're getting a lot of off-topic queries."

Option B: Send Malformed Input
curl -X POST http://localhost:8080/research \
  -H "Content-Type: application/json" \
  -d '{"question": ""}'
"Empty question. Pydantic validation catches this and returns a 400 Bad Request with a clear error message. The request never even reaches the agent."

Option C: (If you can) Kill the MCP Server
"If the SEC API is down or rate-limited, the Researcher catches the exception, logs it, and the job fails gracefully with an error message rather than crashing the whole system."

Closing (30 sec)
"That's the 10-K Filing Agent. It's a working v1 that passes all golden tasks. For production, I'd add Redis persistence, better monitoring, and expand to other SEC form types. Thanks for watching."

Quick Checklist Before Recording
Server runs: uvicorn app.main:app --reload --port 8080
Have a fresh question ready (not in golden set): "What is Nvidia's revenue breakdown?"
LangSmith traces visible (or have screenshots ready)
Eval script runs: python eval/run_eval.py
Know where graph.py is to show routing functions
