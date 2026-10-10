"""LangGraph state graph for the 10-K research agent."""

from langgraph.graph import StateGraph, END

from .state import ResearchState
from .planner import run_planner
from .researcher import run_researcher
from .synthesizer import run_synthesizer


def route_after_planner(state: ResearchState) -> str:
    """
    Conditional edge after planner.
    
    Routes to:
    - "researcher" if items are needed
    - "cannot_answer" if no items identified (question can't be answered)
    """
    items_needed = state.get("items_needed", [])
    
    if not items_needed or len(items_needed) == 0:
        return "cannot_answer"
    
    return "researcher"


def route_after_synthesizer(state: ResearchState) -> str:
    """
    Conditional edge after synthesizer.
    
    Routes to:
    - "done" if answer is complete
    - "done" if max iterations reached (return partial answer)
    - "planner" if more data is needed (loop back)
    """
    is_complete = state.get("is_complete", True)
    iteration = state.get("iteration", 0)
    
    if is_complete:
        return "done"
    
    if iteration >= 2:
        # Max iterations reached, return what we have
        return "done"
    
    # Loop back to planner for more data
    return "planner"


async def cannot_answer_node(state: ResearchState) -> ResearchState:
    """Handle questions that cannot be answered."""
    return {
        **state,
        "error": "Unable to answer this question. Could not identify a company or relevant 10-K items.",
        "is_complete": True,
        "report": {
            "question": state["question"],
            "summary": "This question cannot be answered using SEC 10-K filings.",
            "findings": [],
            "error": "No company or relevant filing items identified",
        },
    }


def build_graph() -> StateGraph:
    """
    Build the LangGraph state graph for 10-K research.
    
    Graph structure:
    
    START -> planner -> [conditional] -> researcher -> synthesizer -> [conditional] -> END
                     |                                             |
                     -> cannot_answer -> END                       -> planner (loop)
    """
    # Create the graph
    graph = StateGraph(ResearchState)
    
    # Add nodes
    graph.add_node("planner", run_planner)
    graph.add_node("researcher", run_researcher)
    graph.add_node("synthesizer", run_synthesizer)
    graph.add_node("cannot_answer", cannot_answer_node)
    
    # Set entry point
    graph.set_entry_point("planner")
    
    # Add conditional edge after planner
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "researcher": "researcher",
            "cannot_answer": "cannot_answer",
        }
    )
    
    # Add edge from researcher to synthesizer
    graph.add_edge("researcher", "synthesizer")
    
    # Add conditional edge after synthesizer
    graph.add_conditional_edges(
        "synthesizer",
        route_after_synthesizer,
        {
            "done": END,
            "planner": "planner",
        }
    )
    
    # Add edge from cannot_answer to END
    graph.add_edge("cannot_answer", END)
    
    return graph


def create_research_agent():
    """Create and compile the research agent graph."""
    graph = build_graph()
    return graph.compile()


# Convenience function for running research
async def research(question: str) -> ResearchState:
    """
    Run a research query through the agent.
    
    Args:
        question: The research question about SEC filings
        
    Returns:
        Final state with report and citations
    """
    agent = create_research_agent()
    
    initial_state: ResearchState = {
        "question": question,
        "company": "",
        "company_name": "",
        "items_needed": [],
        "research_questions": [],
        "raw_data": {},
        "financial_data": {},
        "filing_info": {},
        "report": {},
        "citations": [],
        "is_complete": False,
        "missing_info": [],
        "iteration": 0,
        "error": None,
    }
    
    final_state = await agent.ainvoke(initial_state)
    return final_state
