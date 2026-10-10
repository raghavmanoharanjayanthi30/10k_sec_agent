"""Synthesizer agent - combines data into a structured report with citations."""

import json
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from .state import ResearchState


SYNTHESIZER_SYSTEM_PROMPT = """You are a research synthesizer for SEC 10-K filing analysis.

Your job is to:
1. Combine raw data from SEC filings into a clear, structured answer
2. Add proper citations to the source filing
3. Determine if the answer is complete or if more data is needed

You will receive:
- The original question
- Raw text from 10-K sections (risk factors, MD&A, etc.)
- Financial data (if available)
- Filing metadata (accession number, date, URL)

Respond in JSON format:
{
    "summary": "A concise 2-3 sentence answer to the question",
    "findings": [
        {
            "topic": "Topic name",
            "content": "Detailed finding",
            "source_item": "1A"
        }
    ],
    "is_complete": true,
    "missing_info": [],
    "reasoning": "Why the answer is complete or what's missing"
}

If the data is insufficient, set is_complete to false and list what's missing.

IMPORTANT:
- Always cite the specific 10-K item where information came from
- Use exact numbers from financial data when available
- Be factual - only include information that's in the provided data
"""


def create_synthesizer():
    """Create the synthesizer LLM."""
    return ChatAnthropic(
        model="claude-sonnet-5-5",
        max_tokens=2048,
    )


async def run_synthesizer(state: ResearchState) -> ResearchState:
    """
    Synthesize raw data into a structured report with citations.
    
    Updates state with:
    - report: structured report with summary and findings
    - citations: list of citations to source filings
    - is_complete: whether the answer is complete
    - missing_info: what additional data is needed (if incomplete)
    """
    llm = create_synthesizer()
    
    # Build context from state
    context_parts = [
        f"Question: {state['question']}",
        f"Company: {state.get('company_name', state.get('company', 'Unknown'))} ({state.get('company', '')})",
    ]
    
    # Add filing info
    filing_info = state.get("filing_info", {})
    if filing_info:
        context_parts.append(f"\nFiling Info:")
        context_parts.append(f"- Accession Number: {filing_info.get('accession_number', 'N/A')}")
        context_parts.append(f"- Filing Date: {filing_info.get('filing_date', 'N/A')}")
        context_parts.append(f"- URL: {filing_info.get('url', 'N/A')}")
    
    # Add raw data from sections
    raw_data = state.get("raw_data", {})
    if raw_data:
        context_parts.append("\n10-K Section Data:")
        for item, content in raw_data.items():
            # Truncate very long sections
            truncated = content[:8000] if len(content) > 8000 else content
            context_parts.append(f"\n--- Item {item} ---\n{truncated}")
    
    # Add subsection data (e.g., executive officers)
    subsection_data = state.get("subsection_data", {})
    if subsection_data:
        context_parts.append("\n10-K Subsection Data:")
        for subsec_key, content in subsection_data.items():
            # Truncate very long subsections
            truncated = content[:6000] if len(content) > 6000 else content
            context_parts.append(f"\n--- Subsection: {subsec_key} ---\n{truncated}")
    
    # Add financial data
    financial_data = state.get("financial_data", {})
    if financial_data:
        context_parts.append("\nFinancial Data:")
        context_parts.append(json.dumps(financial_data, indent=2, default=str)[:4000])
    
    context = "\n".join(context_parts)
    
    messages = [
        SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
        HumanMessage(content=context)
    ]
    
    response = await llm.ainvoke(messages)
    
    # Parse JSON response
    try:
        content = response.content
        # Handle case where content is a list (newer LangChain versions)
        if isinstance(content, list):
            # Extract text from content blocks
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
                "error": f"Empty response from synthesizer. Raw response: {response}",
                "is_complete": True,
                "iteration": state.get("iteration", 0) + 1,
            }
        
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        # Try to fix common JSON issues
        content = content.strip()
        
        # Try to parse, with fallback for truncated JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Try to fix truncated JSON by closing brackets
            fixed = content
            # Count open/close brackets
            open_braces = fixed.count('{') - fixed.count('}')
            open_brackets = fixed.count('[') - fixed.count(']')
            
            # Close any unclosed strings (find last quote)
            if fixed.count('"') % 2 == 1:
                fixed = fixed + '"'
            
            # Close brackets and braces
            fixed = fixed + ']' * open_brackets + '}' * open_braces
            
            try:
                result = json.loads(fixed)
            except json.JSONDecodeError:
                # Last resort: try to extract key fields using regex
                import re
                
                # Try to extract summary
                summary_match = re.search(r'"summary"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', content)
                summary = summary_match.group(1) if summary_match else "Synthesis incomplete - see raw data"
                
                # Try to extract findings
                findings = []
                finding_pattern = r'"topic"\s*:\s*"([^"]*)"[^}]*"content"\s*:\s*"([^"]*(?:\\.[^"]*)*)"[^}]*"source_item"\s*:\s*"([^"]*)"'
                for match in re.finditer(finding_pattern, content):
                    findings.append({
                        "topic": match.group(1),
                        "content": match.group(2)[:500],  # Truncate long content
                        "source_item": match.group(3)
                    })
                
                # If we found something, use it
                if summary or findings:
                    result = {
                        "summary": summary.replace('\\"', '"').replace('\\n', ' '),
                        "findings": findings,
                        "is_complete": True,
                        "missing_info": []
                    }
                else:
                    result = {
                        "summary": "Response parsing failed. The filing was retrieved but the synthesis was incomplete.",
                        "findings": [],
                        "is_complete": True,
                        "missing_info": ["Full synthesis failed due to response truncation"]
                    }
        
        # Build citations
        citations = []
        for finding in result.get("findings", []):
            citations.append({
                "source": f"10-K Item {finding.get('source_item', 'Unknown')}",
                "url": filing_info.get("url", ""),
                "item": finding.get("source_item", ""),
                "excerpt": finding.get("content", "")[:200],
            })
        
        # Build report
        report = {
            "question": state["question"],
            "company": state.get("company", ""),
            "company_name": state.get("company_name", ""),
            "summary": result.get("summary", ""),
            "findings": result.get("findings", []),
            "filing_date": filing_info.get("filing_date", ""),
            "filing_url": filing_info.get("url", ""),
        }
        
        return {
            **state,
            "report": report,
            "citations": citations,
            "is_complete": result.get("is_complete", True),
            "missing_info": result.get("missing_info", []),
            "iteration": state.get("iteration", 0) + 1,
        }
        
    except json.JSONDecodeError as e:
        return {
            **state,
            "error": f"Failed to parse synthesizer response: {e}",
            "is_complete": True,  # Don't loop on parse errors
            "iteration": state.get("iteration", 0) + 1,
        }
