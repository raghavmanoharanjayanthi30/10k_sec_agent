"""State definition for the 10-K filing research agent."""

from typing import TypedDict, Optional


class ResearchState(TypedDict):
    """State passed between agents in the research graph."""
    
    # Input
    question: str                      # User's original question
    
    # Planner outputs
    company: str                       # Extracted company ticker (AAPL, MSFT)
    company_name: str                  # Full company name
    items_needed: list[str]            # ["1A", "7", "8"] - 10-K items to fetch
    subsections_needed: list[str]      # ["executive_officers"] - specific subsections
    research_questions: list[str]      # Sub-questions to answer
    
    # Researcher outputs
    raw_data: dict[str, str]           # {"1A": "risk factors text...", "7": "MD&A text..."}
    subsection_data: dict[str, str]    # {"1_executive_officers": "exec info..."}
    financial_data: dict               # Structured financial data from XBRL
    filing_info: dict                  # {accession_number, filing_date, url}
    
    # Synthesizer outputs
    report: dict                       # Final structured report
    citations: list[dict]              # [{source, url, item, excerpt}]
    is_complete: bool                  # Whether answer is complete
    missing_info: list[str]            # What's still needed (if incomplete)
    
    # Control flow
    iteration: int                     # Track loops (max 2)
    error: Optional[str]               # Any errors encountered
