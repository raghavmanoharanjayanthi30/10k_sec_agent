# Technical Exam Answers

**Time spent:** 2 hours  
**Date:** 10/9/2026

---

## Section A: Agent Foundations

### Q1 (2 pts)
**In one paragraph, define the difference between an LLM chain and an agent. Use the system you just built as an example. What in your system makes it an agent rather than a chain?**

_Your answer here..._
LLM chain is usually a fixed sequence of steps, decided at design time, each step's output feeds into the next and it is deterministic. agent is more dynamic, has access to tools it can choose to invoke (or not). 10-K system is an agent because planner decides which 10-K items are needed. Researcher chooses which MCP tools to call based on the plan and there is conditional routing.

### Q2 (3 pts)
**Name three concrete failure modes that get worse as you scale an agentic system from a single agent to multiple agents. For each, name the mitigation pattern.**

1. **Failure mode:** Sub agents doing duplicating work or fight over tasks
   **Mitigation:** Have an orchestrator or supervisor that delegates tasks and ensures no sub agent does overlapping tasks

2. **Failure mode:** Agents have different version of the state, make contradictory changes
   **Mitigation:** A shared state everyone checks before acting

3. **Failure mode:** Difficulty diagnosing root cause of unexpected behavior. Agent C fails, but the real bug was in Agent A three steps ago. 
   **Mitigation:** Keep a log/trail of what each agent did and why

---

## Section B: LangChain & LangGraph

### Q3 (4 pts)
**In LangGraph, what is the difference between a regular edge and a conditional edge, and what is the State object actually doing under the hood? Answer with reference to the StateGraph you wrote in your build.**

_Your answer here..._
Regular: A->B (fixed)
conditional edge, if condition 1 A->C else, A-> D
Internally, shared dict passed through graph (state with fields); nodes are functions with read/update the state; routing functions are used in conditional edges to decide flow

### Q4 (4 pts)
**Compare the supervisor pattern vs. the hierarchical pattern vs. the swarm pattern for multi-agent orchestration in LangGraph. Give one scenario where each is the right answer.**

**Supervisor pattern:**
- Description: Orchestrator - receives main tasks - creates and delegates sub tasks for the worker agents
- Best scenario: When tasks are relatively independent and you need clear routing

**Hierarchical pattern:**
- Description: supervisors at multiple levels like a company org chart
- Best scenario: When one supervisor can't handle the complexity alone and we need multiple. Example: if you're building a system that needs to do research, write code, AND review it, maybe you need a "research lead" and a "engineering lead" who each manage their own sub-agents

**Swarm pattern:**
- Description: decentralized, no central router; flat structure, agents communicate with each other
- Best scenario: When agents should collaborate fluidly and workflow is dynamic/unpredictable

---

### Q5 (3 pts)
**You have a text-to-SQL agent backed by LangGraph and MongoDB (as in Unit 2.2's text-to-query course). A user asks a question that requires data from two collections. Walk through the failure modes you'd expect, and how you would harden the system against each.**

_Your answer here..._
when user asks something needing two collections, things can break: agent might not realize it needs both tables, might not know how to join them, casing issues like "Prague" vs "prague", wrong date formats, syntax errors, or query runs fine but gives wrong answer. also output could be huge.

fixes: give llm schema context — column descriptions, sample rows, label primary key or foreign key so it knows how to join. use lower() for casing. have executor catch syntax errors and retry with error feedback. for semantically wrong but syntactically correct queries, have agent explain its logic first. for huge output, enforce LIMIT.

---

## Section C: Multi-Framework Agent Literacy

### Q6 (5 pts)
**You have four agentic projects on your plate. For each, pick one of CrewAI, LlamaIndex, smolagents, or Haystack and defend the choice in 2–3 sentences. You may reuse a framework across projects only if you can defend why.**

1. **A tightly orchestrated sales-research crew with clearly defined roles**
   - Framework: CrewAI
   - Defense: Designed to work in case where multiple agents, each with a specific role and backstory work together

2. **A heavy-document RAG-plus-agent system**
   - Framework: Llamaindex
   - Defense: Built for indexing and querying large document sets. It also supports agents that can reason over multiple data sources and has native text to sql

3. **A Hugging Face open-source-only deployment for a privacy-sensitive client**
   - Framework: smolagents
   - Defense: Made by hugging face; smolagents is fully open source, works with open-source models; can run everything locally with HF model

4. **A healthcare research agent that must compose Haystack pipelines**
   - Framework: Haystack
   - Defense: When you need a full pipeline and want something battle-tested for production

---

### Q7 (4 pts)
**Explain MCP in one paragraph as if you were explaining it to a senior backend engineer who has never heard of it. Then, in a second paragraph, explain why an AI engineer should care about MCP specifically — what does it solve that bespoke tool plumbing does not?**

_Your answer here..._
**Paragraph 1 (for backend engineer):**
It's a standardized protocol; Uses client-server model;  MCP server exposes tools, your app is the client. It's like REST APIs but specifically for AI tool calling. For example, a Yahoo Finance MCP server might expose tools like get_stock_price(ticker) and get_financials(ticker) any AI app can connect and use them without custom integration code.

**Paragraph 2 (why AI engineers should care):**
Same tool can work across different frameworks like Langchain, llamaindex etc
tool implementation can be separated from agent logic
its an ecosystem and there are many pre built servers ex for github, slack etc
agents can dynamically discover available tools at runtime instead of engineers having to hardcode the tools

## Section D: FastAPI for AI Workloads

### Q8 (3 pts)
**Why is async FastAPI especially relevant for LLM-backed services compared to sync FastAPI? Give a concrete example from your own build where async handling matters or would matter at scale.**

_Your answer here..._
In my 10K filing system, when a user asks a question, the agent might need to retrieve documents, generate a query, and call the LLM, each taking seconds. With sync FastAPI, each request blocks a worker thread while waiting. With async, the thread is freed during those waits, so the server can handle many concurrent users without needing tons of workers. At scale, this is the difference between needing 4 workers vs 40.

### Q9 (3 pts)
**Your /research endpoint hits an LLM provider that randomly returns 500s ~2% of the time. Sketch (in code or pseudocode) the retry, timeout, and circuit-breaker pattern you would apply, and explain what you'd log so a teammate could debug a regression next week.**

```python
for attempt in range(max_retries + 1):
  response = await asyncio.wait_for(
                llm_client.call(prompt),
                timeout=timeout_seconds
            )
   
   if attempt < max_retries:
            backoff = 2 ** attempt
            logger.info(f"Retrying in {backoff}s...")
            await asyncio.sleep(backoff)

# after all failied retries
failure_count += 1
last_failure_time = time.time()

if failure_count >= FAILURE_THRESHOLD:
   circuit_state = "open"
   logger.error(f"Circuit opened after {failure_count} failures")
```

**What to log:**
_Your answer here..._
Retry: max 2 retries with exponential backoff (1s, 2s)
Timeout: 60s per attempt
Circuit breaker: after 5 consecutive failures, stop calling for 30s
Logging: request_id, attempt #, error type, latency, circuit state — so teammate can filter by request_id and see exactly what happened

## Section E: AI-Assisted Development

### Q10 (3 pts)
**Compare Cursor, Claude Code, and GitHub Copilot in terms of where each is the right tool. Give one task per tool where it is clearly the strongest choice, and one task where it is clearly not.**

| Tool | Best for | Not good for |
|------|----------|--------------|
| Github Copilot | Quick inline code completions by suggesting next lines of code | agentic planning, multi-file refactoring |
| Claude Code | Terminal/CLI workflows | harder to see file changes |
| Cursor | Large codebase refactors, changing many files | can't work from CLI |

Copilot = autocomplete
Cursor = AI-native IDE
Claude Code = AI-native terminal
---

### Q11 (3 pts)
**Open your CLAUDE_CODE_NOTES.md. Pick one prompt or workflow you used during this build that worked well, and one that failed. For each, explain in 3–4 sentences why it worked or failed, and what you'd change. Paste the prompts verbatim.**

**Prompt that worked well:**
```
Search for actual content patterns, not TOC entries:
content_patterns = [
    r"OUR EXECUTIVE OFFICERS AS OF[^.]{0,50}WERE AS FOLLOWS",
    r"NAME\s+AGE\s+POSITION WITH THE COMPANY",
]
```
Why it worked: 
This prompt/approach worked because it was specific about what to look for, actual content patterns vs table of contents entries. The regex patterns target real executive officer sections rather than just matching "Executive Officers" which appears in both TOC and content. Being explicit about the distinction solved the problem of extracting wrong dat

**Prompt that failed:**
```
sections_result = get_filing_sections(company, accession)
if "risk_factors" in sections_result:
    content = sections_result["risk_factors"]
```
Why it failed: Why it failed: I assumed the MCP tool returned sections at the top level of the response, but it actually nested them under a "sections" key: {"success": True, "sections": {"risk_factors": "..."}}. The code silently failed to find risk_factors because it was looking in the wrong place.
What you'd change: What you'd change: Always inspect the actual response structure first — print it out or check the docs. The fix was adding sections_data = sections_result.get("sections", sections_result) to handle both cases. I'd also add better error logging when expected keys aren't found so failures are obvious, not silent.

---

## Section F: Synthesis

### Q12 (8 pts)
**Imagine you are 90 days into a new AI engineer role. The team owns a customer-support agent that is in production and unreliable: ~12% of conversations end in a state the team cannot explain, latency p95 is 18 seconds, and there is no eval harness. You have one quarter to fix it.**

**Write a one-page plan covering:**

**(a) What you would instrument first and why:**

_Your answer here..._
logging: for each query log which nodes got hit, state changes, timestamps at each step, and what the final outcome was. also categorize queries so i can see if certain types fail more or take longer. right now 12% of convos end in unexplainable states which means theres basically no visibility. cant fix what i cant see.

**(b) The eval harness you would stand up and how you would seed it:**

_Your answer here..._
build an eval harness that runs test queries and checks if it answered correctly, reached a valid end state, and how long it took. to seed it id pull real convos from prod logs: especially the ones that failed plus some successful ones. manually label like 30-50 as golden test cases with expected outcomes. store as json in the repo so its versioned.

**(c) Which architectural change you would prioritize first and what you would defer:**

_Your answer here..._
first id map out the whole agent flow: every step, every llm call, every tool call. look for unnecessary steps or redundant calls or stuff that could run in parallel but doesnt. 18s p95 is brutal so probably too many sequential llm calls or slow tools. id prioritize cutting steps and parallelizing. defer big rewrites or switching frameworks until i actually understand whats breaking through the logging.

**(d) One bet you would resist making no matter how loud the pressure to make it:**

_Your answer here..._
id resist doing a full rewrite or switching frameworks. when stuff is broken its tempting to just say screw it lets rebuild from scratch but thats a multi-month thing that might not even fix the real problems. plus you lose all the edge case handling the current system figured out. better to fix what you have, understand why its failing, then make targeted changes
---

## Submission Checklist

- [X] All questions answered
- [X] No LLM-generated answers
- [X] Time spent recorded at top
- [X] Reviewed for clarity
