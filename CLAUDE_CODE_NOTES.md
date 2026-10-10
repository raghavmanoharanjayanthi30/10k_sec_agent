# Claude Code Notes

This document describes how AI assistance (Claude) was used to build this project.

## Development Workflow

### 1. Planning Phase

**AI Contribution:**
- Analyzed the take-home requirements and identified key deliverables
- Proposed the multi-agent architecture (Planner → Researcher → Synthesizer)
- Designed the state schema (`ResearchState`) to track data flow between agents
- Mapped 10-K items to research question types
- Identified relevant MCP tools from the sec-edgar-mcp server (22 tools total)

**Human Decisions:**
- Chose to use a single Researcher agent with smart routing instead of multiple specialized researchers
- Selected Claude Sonnet 5.5 as the LLM for agents
- Decided on max 2 iterations for the research loop

### 2. Architecture Design

**AI Contribution:**
- Created the LangGraph state graph with conditional edges
- Designed the routing logic:
  - After Planner: route to Researcher or Cannot Answer
  - After Synthesizer: route to Done or loop back to Planner
- Structured the FastAPI endpoints for async job handling
- Defined Pydantic models for type-safe API contracts

### 3. Implementation & Debugging Journey

This section documents the iterative debugging process:

#### Issue 1: Model Name Not Found
**Error:** `model: claude-sonnet-4-20250514 not found`
**Fix:** Updated to `claude-sonnet-5-5` (current model name)

#### Issue 2: Temperature Deprecated
**Error:** `temperature is deprecated for this model`
**Fix:** Removed `temperature=0` parameter from LLM initialization

#### Issue 3: Response Content is List
**Error:** `'list' object has no attribute 'strip'`
**Cause:** Newer LangChain versions return `response.content` as a list of content blocks
**Fix:** Added handling for list content:
```python
if isinstance(content, list):
    text_parts = []
    for block in content:
        if isinstance(block, dict) and "text" in block:
            text_parts.append(block["text"])
    content = "".join(text_parts)
```

#### Issue 4: MCP Package Requires Python 3.10+
**Error:** `No matching distribution found for mcp>=1.0.0`
**Cause:** System Python was 3.9, MCP requires 3.10+
**Fix:** Installed Python 3.11 via Homebrew: `brew install python@3.11`

#### Issue 5: SEC_EDGAR_USER_AGENT Not Set
**Error:** `SEC_EDGAR_USER_AGENT environment variable is not set`
**Cause:** MCP tools initialized at import time before .env was loaded
**Fix:** Added `load_dotenv()` at top of researcher.py and lazy-loaded tools:
```python
from dotenv import load_dotenv
load_dotenv()

_filings_tools = None
def get_filings_tools():
    global _filings_tools
    if _filings_tools is None:
        from sec_edgar_mcp.tools import FilingsTools
        _filings_tools = FilingsTools()
    return _filings_tools
```

#### Issue 6: Citation URL is None
**Error:** `Input should be a valid string, input_value=None`
**Fix:** Used `or ""` fallback: `url=c.get("url") or ""`

#### Issue 7: Sections Nested Under 'sections' Key
**Symptom:** Risk factors text not being extracted despite MCP working
**Cause:** MCP returns `{"success": True, "sections": {"risk_factors": "..."}}`
**Fix:** Added nested lookup:
```python
sections_data = sections_result.get("sections", sections_result)
if "risk_factors" in sections_data:
    content = sections_data["risk_factors"]
```

#### Issue 8: JSON Parsing Failures on Long Responses
**Error:** `Unterminated string starting at: line 37 column 5`
**Cause:** LLM response truncated mid-JSON
**Fix:** Added JSON repair logic to close unclosed brackets/braces

### 4. Key Design Decisions

#### Why Single Researcher Agent?
Initially considered multiple specialized Researcher agents (one per 10-K item group). Decided against this because:
1. Adds complexity without clear benefit
2. MCP tools already handle item-specific fetching
3. Single agent with smart routing is simpler to debug
4. Can always split later if needed

#### Why Max 2 Iterations?
The Synthesizer can request more data by setting `is_complete=False`. Limited to 2 iterations to:
1. Prevent infinite loops
2. Keep latency reasonable
3. Most questions can be answered in 1-2 passes

#### Why Background Tasks?
Research can take 10-30 seconds. Using FastAPI background tasks:
1. Returns immediately with job_id
2. Client polls for completion
3. Scales better than blocking requests

#### Why Direct MCP Tool Calls?
Initially tried:
1. Docker subprocess (failed - Docker not installed)
2. HTTP SSE transport (complex setup)
3. **Direct Python import** (worked!) - since sec-edgar-mcp is a Python package, we can import and call the tools directly

### 5. Files Created/Modified

| File | Purpose | AI Contribution |
|------|---------|-----------------|
| `PLANNING.md` | Architecture documentation | 100% AI-generated |
| `agents/state.py` | State definition | 100% AI-generated |
| `agents/planner.py` | Planner agent | 100% AI-generated, debugged |
| `agents/researcher.py` | Researcher agent | 100% AI-generated, heavily debugged |
| `agents/synthesizer.py` | Synthesizer agent | 100% AI-generated, debugged |
| `agents/graph.py` | LangGraph state graph | 100% AI-generated |
| `tools/sec_client.py` | Direct SEC API fallback | 100% AI-generated |
| `tools/section_extractor.py` | Full 10-K section parser | 100% AI-generated |
| `tools/cache.py` | In-memory TTL cache | 100% AI-generated |
| `app/main.py` | FastAPI application | 100% AI-generated, debugged |
| `app/models.py` | Pydantic schemas | 100% AI-generated |
| `eval/golden_tasks.json` | Test questions | 100% AI-generated |
| `eval/run_eval.py` | Evaluation script | 100% AI-generated |
| `Dockerfile` | Container config | 100% AI-generated |
| `README.md` | Documentation | 100% AI-generated |

### 6. Prompts Used

#### Planner System Prompt
The planner uses a structured prompt that:
1. Provides 10-K item reference (what each item contains)
2. Asks for JSON output with company, items_needed, research_questions
3. Handles edge cases (unknown company, non-SEC questions)

#### Synthesizer System Prompt
The synthesizer prompt:
1. Instructs to combine raw data into structured findings
2. Requires citations to source items
3. Asks for completeness assessment
4. Enforces factual accuracy (only use provided data)

### 7. Iteration Log

1. **Initial scaffold** - Created project structure, basic agents
2. **Model fixes** - Updated model name, removed temperature
3. **Content parsing** - Fixed list content handling
4. **Python upgrade** - Installed Python 3.11 for MCP
5. **Env loading** - Fixed environment variable loading order
6. **URL handling** - Fixed None URL validation errors
7. **Nested data** - Fixed sections data structure lookup
8. **JSON repair** - Added truncated JSON handling
9. **Documentation** - README, this file
10. **Section extraction** - Added custom extractor for all 10-K items
11. **Production hardening** - Added auth, retry, rate limiting, caching

### 8. Evaluation Results

Initial run: 3/5 passed (60%)
- Task 1 (Apple risks): JSON parsing issue → Fixed
- Task 2 (Microsoft cloud): ✓ PASS
- Task 3 (Tesla business): JSON parsing issue → Fixed
- Task 4 (Amazon legal): ✓ PASS
- Task 5 (Apple revenue YoY): ✓ PASS

After fixes: 5/5 passed (100%)

**Improved Evaluation (with fact-checking and LLM-as-judge):**
- Pass rate: 5/5 (100%)
- Average LLM Judge Score: 4.2/5

### 9. Section Extraction Enhancement

#### Problem: MCP Tool Limitations
The sec-edgar-mcp tool's `get_filing_sections()` only extracts 3 sections:
- `business` (Item 1) - truncated to 10,000 chars
- `risk_factors` (Item 1A)
- `mda` (Item 7)

This caused issues with questions about:
- Executive officers (subsection within Item 1, often truncated)
- Legal proceedings (Item 3 - not extracted)
- Properties (Item 2 - not extracted)

#### Solution: Custom Section Extractor
Created `tools/section_extractor.py` that:
1. Fetches full filing content via MCP's `get_filing_content()`
2. Parses all 16 standard 10-K items using regex patterns
3. Extracts subsections (e.g., "Executive Officers" within Item 1)
4. Skips TOC entries to find actual content

**Key technique for executive officers:**
```python
# Search for actual content patterns, not TOC entries
content_patterns = [
    r"OUR EXECUTIVE OFFICERS AS OF[^.]{0,50}WERE AS FOLLOWS",
    r"NAME\s+AGE\s+POSITION WITH THE COMPANY",
]
```

#### Result
Query: "Who are the executive officers at Microsoft?"

**Before:** "The provided data does not name any executive officers..."

**After:** "As of July 29, 2026, Microsoft's executive officers were Satya Nadella (Chairman and CEO), Judson B. Althoff (CEO, Microsoft Commercial Business), Amy L. Coleman (EVP and Chief Human Resources Officer)..."

### 10. Production Hardening (Latest Updates)

#### API Key Authentication
Added optional API key authentication to protect endpoints:

```python
# app/main.py
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        return "dev-mode"  # No auth in development
    if not api_key or api_key != expected_key:
        raise HTTPException(status_code=401/403, ...)
```

**Usage:**
- Set `API_KEY` in `.env` to enable authentication
- Include `X-API-Key: your-key` header in requests
- Health check (`/healthz`) remains unauthenticated

#### Retry with Exponential Backoff
Added retry logic for all SEC EDGAR API calls:

```python
# agents/researcher.py
@retry_with_backoff(max_retries=3)
def get_recent_filings_with_retry(company: str, form_type: str, days: int, limit: int) -> dict:
    time.sleep(RetryConfig.SEC_RATE_LIMIT_DELAY)  # 100ms rate limiting
    filings_tools = get_filings_tools()
    return filings_tools.get_recent_filings(...)
```

**Configuration:**
- Max retries: 3
- Base delay: 1 second
- Max delay: 10 seconds
- Exponential base: 2 (delays: 1s, 2s, 4s)

#### SEC API Rate Limiting
Added 100ms delay between SEC API calls to respect their 10 req/sec limit:

```python
class RetryConfig:
    SEC_RATE_LIMIT_DELAY = 0.1  # 100ms between requests
```

#### Input Validation
Enhanced Pydantic models with security validators:

```python
# app/models.py
@field_validator("question")
@classmethod
def validate_question(cls, v: str) -> str:
    if len(v) > 1000:
        raise ValueError("Question too long")
    # Check for SQL injection, prompt injection, etc.
    blocked_patterns = [r";\s*DROP", r"UNION\s+SELECT", ...]
    for pattern in blocked_patterns:
        if re.search(pattern, v, re.IGNORECASE):
            raise ValueError("Invalid characters in question")
    return v
```

#### In-Memory Caching
Added TTL-based caching for SEC data:

```python
# tools/cache.py
class FilingCache:
    def __init__(self, default_ttl: int = 3600):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
    
    def get_filings(self, company: str, form_type: str) -> Optional[dict]:
        return self._get(f"filings:{company}:{form_type}")
    
    def set_filings(self, company: str, form_type: str, data: dict):
        self._set(f"filings:{company}:{form_type}", data)
```

**Cache types:**
- Filing metadata (1 hour TTL)
- Section content (1 hour TTL)
- Full filing content (1 hour TTL)
- Financial data (1 hour TTL)

#### Parallel Content Fetching
Large filings are now fetched in parallel chunks:

```python
# agents/researcher.py
async def fetch_full_content_parallel(company: str, accession: str, chunk_size: int = 100000) -> str:
    # First call to get total_chars
    first_result = get_filing_content_with_retry(company, accession, 0, chunk_size)
    
    # Calculate remaining offsets
    offsets = list(range(chunk_size, total_chars, chunk_size))
    
    # Fetch remaining chunks in parallel
    tasks = [loop.run_in_executor(executor, _fetch_content_chunk, ...) for offset in offsets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
```

### 11. Lessons Learned

1. **Test incrementally** - Each component should be tested before integration
2. **Check data structures** - API responses often have nested structures
3. **Handle edge cases** - LLM responses can be truncated, malformed, or in unexpected formats
4. **Environment matters** - Python version, env vars, and import order all matter
5. **Lazy loading** - Initialize resources when needed, not at import time
6. **MCP limitations** - Third-party MCP tools may have extraction limits; build fallbacks
7. **Rate limiting is essential** - Both for protecting your API and respecting external APIs
8. **Caching saves time** - Repeated queries for the same company benefit greatly from caching

### 12. Known Limitations

1. **Filing text has no structure** - MCP's `get_filing_content()` returns raw text without newlines, making section parsing challenging
2. **TOC vs Content** - Section headers appear in both TOC and actual content; must distinguish between them
3. **Item 3 (Legal Proceedings)** - Not extracted by MCP; requires full content fetch
4. **Large filings** - Some 10-Ks are 300k+ chars; fetching full content takes multiple API calls
5. **In-memory storage** - Jobs and cache are lost on server restart (see production guide for Redis)

### 13. Future Improvements

See README.md "Production Readiness Guide" for detailed recommendations:

1. **Redis for persistence** - Replace in-memory job store and cache
2. **Database for history** - Store job history for audit trails
3. **Secrets management** - Use AWS Secrets Manager, etc.
4. **Structured logging** - Replace print with structlog
5. **Metrics** - Add Prometheus metrics
6. **Distributed tracing** - OpenTelemetry integration
7. **Streaming** - Stream partial results as they're generated
8. **Better JSON handling** - Use structured output or retry on parse failures
