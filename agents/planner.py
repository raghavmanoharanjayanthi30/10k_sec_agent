"""Planner agent - parses questions and determines what data to fetch."""

import json
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from .state import ResearchState


# Common company ticker mappings
COMPANY_TICKERS = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "tesla": "TSLA",
    "meta": "META",
    "facebook": "META",
    "nvidia": "NVDA",
    "netflix": "NFLX",
    "jpmorgan": "JPM",
    "walmart": "WMT",
    "disney": "DIS",
    "coca-cola": "KO",
    "pepsi": "PEP",
    "intel": "INTC",
    "amd": "AMD",
    "salesforce": "CRM",
    "oracle": "ORCL",
    "ibm": "IBM",
}

# 10-K item descriptions for the LLM
ITEM_DESCRIPTIONS = """
10-K Items Reference (use these item numbers in your response):

PART I:
- Item 1: Business - Company overview, products, services, strategy, employees, executive officers
- Item 1A: Risk Factors - Key risks facing the company
- Item 1B: Unresolved Staff Comments - SEC comment letters
- Item 1C: Cybersecurity - Cybersecurity risks, incidents, governance
- Item 2: Properties - Physical locations, facilities, real estate
- Item 3: Legal Proceedings - Lawsuits, litigation, regulatory actions
- Item 4: Mine Safety Disclosures

PART II:
- Item 5: Market for Common Equity - Stock info, dividends, repurchases
- Item 6: [Reserved]
- Item 7: MD&A - Management Discussion & Analysis, revenue trends, strategy, outlook
- Item 7A: Market Risk - Interest rate, currency, commodity price risks
- Item 8: Financial Statements - Balance sheet, income statement, cash flow, notes
- Item 9: Changes in Accountants
- Item 9A: Controls and Procedures - Internal controls, SOX compliance
- Item 9B: Other Information
- Item 9C: Foreign Jurisdiction Disclosures

PART III:
- Item 10: Directors & Executive Officers - Board members, executives, corporate governance
- Item 11: Executive Compensation - Pay packages, bonuses, equity awards
- Item 12: Security Ownership - Major shareholders, insider ownership
- Item 13: Related Party Transactions
- Item 14: Principal Accountant Fees

PART IV:
- Item 15: Exhibits and Schedules
- Item 16: Form 10-K Summary

Common question-to-item mappings:
- "executive officers" or "management team" or "who runs" → Item 1 or Item 10
- "risk factors" or "risks" → Item 1A
- "legal" or "lawsuits" or "litigation" → Item 3
- "revenue" or "financial performance" or "earnings" → Item 7, Item 8
- "cybersecurity" → Item 1C
- "properties" or "facilities" or "locations" → Item 2
- "compensation" or "pay" or "salary" → Item 11
- "shareholders" or "ownership" → Item 12
- "business model" or "what does X do" → Item 1
"""

PLANNER_SYSTEM_PROMPT = f"""You are a research planner for SEC 10-K filing analysis.

Your job is to:
1. Identify the company being asked about (extract ticker symbol)
2. Determine which 10-K items are needed to answer the question
3. Identify any specific subsections needed (e.g., "executive_officers" within Item 1)
4. Break down the question into specific research sub-questions

{ITEM_DESCRIPTIONS}

Respond in JSON format:
{{
    "company": "TICKER",
    "company_name": "Full Company Name",
    "items_needed": ["1", "1A", "7"],
    "subsections_needed": ["executive_officers"],
    "research_questions": ["What are the main risk factors?", "What is the revenue trend?"],
    "reasoning": "Brief explanation of why these items are needed"
}}

Important:
- For questions about executives/officers/management, include BOTH Item 1 AND Item 10
- For questions about legal matters, include Item 3
- For financial questions, include both Item 7 (MD&A) and Item 8 (Financial Statements)
- Use the exact item numbers (e.g., "1A" not "1a", "7A" not "7a")

If you cannot identify a company or the question is not about SEC filings, respond:
{{
    "company": null,
    "company_name": null,
    "items_needed": [],
    "subsections_needed": [],
    "research_questions": [],
    "reasoning": "Explanation of why this cannot be answered"
}}
"""


def create_planner():
    """Create the planner LLM."""
    return ChatAnthropic(
        model="claude-sonnet-5-5",
        max_tokens=1024,
    )


async def run_planner(state: ResearchState) -> ResearchState:
    """
    Parse the user's question and create a research plan.
    
    Updates state with:
    - company: ticker symbol
    - company_name: full company name
    - items_needed: list of 10-K items to fetch
    - subsections_needed: specific subsections to extract
    - research_questions: sub-questions to answer
    """
    llm = create_planner()
    
    # Check if this is a re-plan (iteration > 0)
    context = ""
    if state.get("iteration", 0) > 0:
        context = f"""
Previous attempt found this data but it was incomplete:
- Items fetched: {list(state.get('raw_data', {}).keys())}
- Missing info: {state.get('missing_info', [])}

Please identify additional items needed to complete the answer.
"""
    
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=f"Question: {state['question']}\n{context}")
    ]
    
    response = await llm.ainvoke(messages)
    
    # Parse JSON response
    try:
        # Extract JSON from response (handle markdown code blocks)
        content = response.content
        # Handle case where content is a list (newer LangChain versions)
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
                elif hasattr(block, "text"):
                    text_parts.append(block.text)
            content = "".join(text_parts)
        
        if not content:
            return {
                **state,
                "company": "",
                "company_name": "",
                "items_needed": [],
                "subsections_needed": [],
                "research_questions": [],
                "error": f"Empty response from planner. Raw: {response}",
            }
        
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        plan = json.loads(content.strip())
        
        # Normalize ticker if company name was given
        company = plan.get("company")
        if company:
            company = company.upper()
        elif plan.get("company_name"):
            # Try to look up ticker from company name
            name_lower = plan["company_name"].lower()
            for name, ticker in COMPANY_TICKERS.items():
                if name in name_lower:
                    company = ticker
                    break
        
        # Normalize item numbers (ensure uppercase for letters)
        items_needed = []
        for item in plan.get("items_needed", []):
            items_needed.append(str(item).upper())
        
        return {
            **state,
            "company": company or "",
            "company_name": plan.get("company_name", ""),
            "items_needed": items_needed,
            "subsections_needed": plan.get("subsections_needed", []),
            "research_questions": plan.get("research_questions", []),
            "iteration": state.get("iteration", 0),
        }
        
    except json.JSONDecodeError as e:
        return {
            **state,
            "company": "",
            "company_name": "",
            "items_needed": [],
            "subsections_needed": [],
            "research_questions": [],
            "error": f"Failed to parse planner response: {e}",
        }
