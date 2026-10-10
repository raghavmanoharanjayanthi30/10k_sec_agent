"""Researcher agent - fetches data from SEC EDGAR via MCP tools."""

import asyncio
import logging
import os
import time
from typing import Any, Optional, List, Callable, TypeVar
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

# Load .env at module import time
load_dotenv()

from .state import ResearchState
from tools.section_extractor import extract_sections_from_filing, get_section_for_topic, extract_executive_officers
from tools.cache import get_cache

logger = logging.getLogger(__name__)

# Type variable for retry decorator
T = TypeVar('T')


# =============================================================================
# Retry Configuration
# =============================================================================

class RetryConfig:
    """Configuration for retry behavior."""
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # seconds
    MAX_DELAY = 10.0  # seconds
    EXPONENTIAL_BASE = 2
    
    # SEC EDGAR rate limit: 10 requests per second
    SEC_RATE_LIMIT_DELAY = 0.1  # 100ms between requests


def retry_with_backoff(
    max_retries: int = RetryConfig.MAX_RETRIES,
    base_delay: float = RetryConfig.BASE_DELAY,
    max_delay: float = RetryConfig.MAX_DELAY,
    exponential_base: float = RetryConfig.EXPONENTIAL_BASE,
    retryable_exceptions: tuple = (Exception,),
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff calculation
        retryable_exceptions: Tuple of exceptions that should trigger a retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    # Add rate limiting delay for SEC API
                    if attempt > 0:
                        delay = min(
                            base_delay * (exponential_base ** (attempt - 1)),
                            max_delay
                        )
                        logger.info(f"Retry attempt {attempt}/{max_retries} for {func.__name__}, waiting {delay:.1f}s")
                        time.sleep(delay)
                    
                    return func(*args, **kwargs)
                    
                except retryable_exceptions as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {e}")
                    
                    if attempt == max_retries:
                        logger.error(f"All {max_retries + 1} attempts failed for {func.__name__}")
                        raise
            
            # Should not reach here, but just in case
            raise last_exception
        
        return wrapper
    return decorator


# =============================================================================
# MCP Tool Configuration
# =============================================================================

# Map 10-K items to section names returned by MCP
# MCP only supports these 3 sections natively
MCP_SUPPORTED_SECTIONS = {
    "1": "business",
    "1A": "risk_factors",
    "7": "mda",
}

# All 10-K items we can extract with our custom extractor
ALL_ITEMS = [
    "1", "1A", "1B", "1C", "2", "3", "4",
    "5", "6", "7", "7A", "8", "9", "9A", "9B", "9C",
    "10", "11", "12", "13", "14", "15", "16"
]

# Thread pool for parallel API calls
_executor: Optional[ThreadPoolExecutor] = None

def get_executor() -> ThreadPoolExecutor:
    """Get thread pool executor for parallel fetching."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4)
    return _executor


# Lazy-loaded tool instances
_filings_tools: Optional[Any] = None
_financial_tools: Optional[Any] = None


def get_filings_tools():
    """Lazy-load FilingsTools to ensure env vars are set."""
    global _filings_tools
    if _filings_tools is None:
        from sec_edgar_mcp.tools import FilingsTools
        _filings_tools = FilingsTools()
    return _filings_tools


def get_financial_tools():
    """Lazy-load FinancialTools to ensure env vars are set."""
    global _financial_tools
    if _financial_tools is None:
        from sec_edgar_mcp.tools import FinancialTools
        _financial_tools = FinancialTools()
    return _financial_tools


# =============================================================================
# SEC API Wrapper Functions with Retry
# =============================================================================

@retry_with_backoff(max_retries=3)
def get_recent_filings_with_retry(company: str, form_type: str, days: int, limit: int) -> dict:
    """Get recent filings with retry logic."""
    time.sleep(RetryConfig.SEC_RATE_LIMIT_DELAY)  # Rate limiting
    filings_tools = get_filings_tools()
    return filings_tools.get_recent_filings(
        identifier=company,
        form_type=form_type,
        days=days,
        limit=limit
    )


@retry_with_backoff(max_retries=3)
def get_filing_sections_with_retry(company: str, accession: str, form_type: str) -> dict:
    """Get filing sections with retry logic."""
    time.sleep(RetryConfig.SEC_RATE_LIMIT_DELAY)  # Rate limiting
    filings_tools = get_filings_tools()
    return filings_tools.get_filing_sections(
        identifier=company,
        accession_number=accession,
        form_type=form_type
    )


@retry_with_backoff(max_retries=3)
def get_filing_content_with_retry(company: str, accession: str, offset: int, max_chars: int) -> dict:
    """Get filing content chunk with retry logic."""
    time.sleep(RetryConfig.SEC_RATE_LIMIT_DELAY)  # Rate limiting
    filings_tools = get_filings_tools()
    return filings_tools.get_filing_content(
        identifier=company,
        accession_number=accession,
        offset=offset,
        max_chars=max_chars
    )


@retry_with_backoff(max_retries=3)
def get_financials_with_retry(company: str, statement_type: str) -> dict:
    """Get financial data with retry logic."""
    time.sleep(RetryConfig.SEC_RATE_LIMIT_DELAY)  # Rate limiting
    financial_tools = get_financial_tools()
    return financial_tools.get_financials(
        identifier=company,
        statement_type=statement_type
    )


# =============================================================================
# Content Validation
# =============================================================================

def _is_content_truncated_or_incomplete(content: str, item: str) -> bool:
    """Check if MCP-returned content appears truncated or incomplete."""
    if not content:
        return True
    
    # Check for truncation markers
    if "[truncated]" in content.lower():
        return True
    
    # Check if content is suspiciously short for certain items
    min_expected_lengths = {
        "1": 5000,   # Business section should be substantial
        "1A": 3000,  # Risk factors usually long
        "7": 5000,   # MD&A is typically very long
        "10": 2000,  # Directors/officers section
    }
    
    min_len = min_expected_lengths.get(item, 1000)
    if len(content) < min_len:
        return True
    
    # Check if it looks like just a table of contents
    toc_indicators = [
        "page",
        "see item",
        "incorporated by reference",
        "begins on page",
    ]
    content_lower = content.lower()
    toc_count = sum(1 for ind in toc_indicators if ind in content_lower)
    if toc_count >= 2 and len(content) < 3000:
        return True
    
    return False


# =============================================================================
# Parallel Content Fetching
# =============================================================================

def _fetch_content_chunk(company: str, accession: str, offset: int, max_chars: int) -> dict:
    """Fetch a single chunk of filing content (for parallel execution)."""
    return get_filing_content_with_retry(company, accession, offset, max_chars)


async def fetch_full_content_parallel(company: str, accession: str, chunk_size: int = 100000) -> str:
    """
    Fetch full filing content using parallel chunk fetching.
    
    First fetches initial chunk to get total size, then fetches
    remaining chunks in parallel for faster retrieval.
    """
    cache = get_cache()
    
    # Check cache first
    cached_content = cache.get_full_content(company, accession)
    if cached_content:
        logger.info(f"Cache hit for full content: {company}/{accession}")
        return cached_content
    
    # First call to get total_chars
    first_result = get_filing_content_with_retry(company, accession, 0, chunk_size)
    
    if not first_result.get("success"):
        logger.error(f"Failed to fetch initial content chunk: {first_result.get('error')}")
        return ""
    
    full_content = first_result.get("content", "")
    total_chars = first_result.get("total_chars", 0)
    
    # If we got everything in first chunk, return
    if first_result.get("next_offset") is None:
        cache.set_full_content(company, accession, full_content)
        return full_content
    
    # Calculate remaining offsets
    offsets = list(range(chunk_size, total_chars, chunk_size))
    
    if offsets:
        logger.info(f"Fetching {len(offsets)} additional chunks in parallel for {company}/{accession}")
        
        # Fetch remaining chunks in parallel using thread pool
        loop = asyncio.get_event_loop()
        executor = get_executor()
        
        tasks = [
            loop.run_in_executor(
                executor,
                _fetch_content_chunk,
                company, accession, offset, chunk_size
            )
            for offset in offsets
        ]
        
        # Wait for all chunks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results in order
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Chunk {i} failed: {result}")
            elif isinstance(result, dict) and result.get("success"):
                full_content += result.get("content", "")
    
    # Cache the full content
    cache.set_full_content(company, accession, full_content)
    logger.info(f"Cached full content for {company}/{accession}: {len(full_content)} chars")
    
    return full_content


# =============================================================================
# Main Researcher Function
# =============================================================================

async def run_researcher(state: ResearchState) -> ResearchState:
    """
    Fetch data from SEC EDGAR based on the planner's output.
    
    Uses sec-edgar-mcp tools for initial fetch, then falls back to
    custom section extractor for complete content when needed.
    
    Features:
    - Caching of filing data to avoid repeated fetches
    - Parallel chunk fetching for full filing content
    - Retry with exponential backoff for API failures
    - SEC API rate limiting (10 req/sec)
    
    Updates state with:
    - raw_data: text content from filing sections
    - subsection_data: specific subsections (e.g., executive officers)
    - financial_data: structured financial data
    - filing_info: metadata about the filing
    """
    company = state.get("company", "")
    items_needed = state.get("items_needed", [])
    subsections_needed = state.get("subsections_needed", [])
    
    if not company:
        return {
            **state,
            "error": "No company specified",
        }
    
    cache = get_cache()
    
    try:
        # Step 1: Get the latest 10-K filing using MCP tool (with caching)
        cached_filings = cache.get_filings(company, "10-K")
        if cached_filings:
            logger.info(f"Cache hit for filings: {company}")
            filings_result = cached_filings
        else:
            filings_result = get_recent_filings_with_retry(company, "10-K", 365, 1)
            if filings_result.get("success"):
                cache.set_filings(company, "10-K", filings_result)
        
        if not filings_result.get("success"):
            return {
                **state,
                "error": f"Failed to get filings: {filings_result.get('error', 'Unknown error')}",
            }
        
        filings = filings_result.get("filings", [])
        if not filings:
            return {
                **state,
                "error": f"No 10-K filings found for {company}",
            }
        
        filing = filings[0]
        
        # Get URL or construct it from accession number
        filing_url = filing.get("url") or filing.get("filing_url")
        accession_number = filing.get("accession_number")
        cik = filing.get("cik", "").lstrip("0")
        
        if not filing_url and accession_number:
            # Construct SEC URL from accession number
            acc_formatted = accession_number.replace("-", "")
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_formatted}/{accession_number}-index.htm"
        
        filing_info = {
            "accession_number": accession_number,
            "filing_date": filing.get("filing_date"),
            "url": filing_url or "",
            "company_name": filings_result.get("company_name", company),
            "cik": cik,
        }
        
        company_name = state.get("company_name") or filings_result.get("company_name", "")
        
        # Step 2: Try MCP sections first for supported items (with caching)
        raw_data = state.get("raw_data", {}) or {}
        mcp_items = [item for item in items_needed if item in MCP_SUPPORTED_SECTIONS]
        items_needing_full_extraction = []
        
        if mcp_items and filing_info.get("accession_number"):
            # Check cache for sections
            cached_sections = cache.get_sections(company, accession_number)
            
            if cached_sections:
                logger.info(f"Cache hit for sections: {company}/{accession_number}")
                sections_result = cached_sections
            else:
                sections_result = get_filing_sections_with_retry(
                    company, accession_number, "10-K"
                )
                if sections_result.get("success"):
                    cache.set_sections(company, accession_number, sections_result)
            
            if sections_result.get("success"):
                sections_data = sections_result.get("sections", sections_result)
                
                for item in mcp_items:
                    section_name = MCP_SUPPORTED_SECTIONS[item]
                    if section_name in sections_data:
                        content = sections_data[section_name]
                        
                        # Check if content is complete
                        if _is_content_truncated_or_incomplete(content, item):
                            items_needing_full_extraction.append(item)
                        else:
                            # Truncate if too long for context
                            if isinstance(content, str) and len(content) > 30000:
                                content = content[:30000] + "\n\n... [truncated for context limit]"
                            raw_data[item] = content
                    else:
                        items_needing_full_extraction.append(item)
        
        # Step 3: Use full extraction for items not in MCP or incomplete
        non_mcp_items = [item for item in items_needed if item not in MCP_SUPPORTED_SECTIONS]
        items_to_extract = list(set(items_needing_full_extraction + non_mcp_items))
        
        subsection_data = state.get("subsection_data", {}) or {}
        
        if items_to_extract or subsections_needed:
            # Fetch full filing content using parallel fetching
            full_content = await fetch_full_content_parallel(
                company, 
                filing_info["accession_number"]
            )
            
            if full_content:
                # Extract sections using our custom extractor
                extraction_result = extract_sections_from_filing(
                    filing_text=full_content,
                    items=items_to_extract,
                    include_subsections=bool(subsections_needed),
                    max_chars_per_section=30000
                )
                
                # Add extracted sections to raw_data
                for item, content in extraction_result.get("sections", {}).items():
                    if item not in raw_data or _is_content_truncated_or_incomplete(raw_data.get(item, ""), item):
                        raw_data[item] = content
                
                # Add subsections
                for subsec_key, content in extraction_result.get("subsections", {}).items():
                    subsection_data[subsec_key] = content
                
                # If specific subsections were requested, try to find them
                for subsec in subsections_needed:
                    if subsec == "executive_officers":
                        # Use direct extraction for executive officers
                        exec_content = extract_executive_officers(full_content)
                        if exec_content:
                            subsection_data["executive_officers"] = exec_content
                        else:
                            # Fallback: search in Items 1 and 10
                            for item in ["1", "10"]:
                                key = f"{item}_executive_officers"
                                if key not in subsection_data:
                                    topic_results = get_section_for_topic(full_content, "executive officers")
                                    if topic_results:
                                        subsection_data.update(topic_results)
        
        # Step 4: Fetch financial data if items 7 or 8 are needed (with caching)
        financial_data = state.get("financial_data", {}) or {}
        
        if "7" in items_needed or "8" in items_needed:
            cached_financials = cache.get_financials(company)
            
            if cached_financials:
                logger.info(f"Cache hit for financials: {company}")
                financial_data["financials"] = cached_financials
            else:
                financials_result = get_financials_with_retry(company, "all")
                
                if financials_result.get("success"):
                    financial_data["financials"] = financials_result
                    cache.set_financials(company, financials_result)
        
        return {
            **state,
            "company_name": company_name,
            "raw_data": raw_data,
            "subsection_data": subsection_data,
            "financial_data": financial_data,
            "filing_info": filing_info,
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Researcher error: {e}\n{traceback.format_exc()}")
        return {
            **state,
            "error": f"Researcher error: {str(e)}",
        }
