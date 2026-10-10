"""Evaluation script for the 10-K research agent with fact-checking and LLM-as-judge."""

import asyncio
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import research
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage


def load_golden_tasks() -> list[dict]:
    """Load golden tasks from JSON file."""
    tasks_path = Path(__file__).parent / "golden_tasks.json"
    with open(tasks_path) as f:
        return json.load(f)


def check_facts(result: dict, task: dict) -> dict:
    """
    Check if required facts are present in the response.
    
    Returns detailed verification results.
    """
    verification = task.get("verification", {})
    report = result.get("report", {})
    
    # Combine all text for searching
    summary = report.get("summary", "").lower()
    findings_text = " ".join(
        f.get("content", "") for f in report.get("findings", [])
    ).lower()
    full_text = f"{summary} {findings_text}"
    
    checks = {
        "has_report": bool(report),
        "has_summary": bool(report.get("summary")),
        "has_findings": len(report.get("findings", [])) > 0,
        "has_citations": len(result.get("citations", [])) > 0,
        "no_error": result.get("error") is None,
    }
    
    # Check required facts
    required_facts = verification.get("required_facts", [])
    facts_found = []
    for fact in required_facts:
        # Handle OR conditions
        if " OR " in fact:
            alternatives = [f.strip().lower() for f in fact.split(" OR ")]
            if any(alt in full_text for alt in alternatives):
                facts_found.append(fact)
        elif fact.lower() in full_text:
            facts_found.append(fact)
    
    min_facts = verification.get("min_facts_required", len(required_facts) // 2)
    checks["facts_found"] = len(facts_found)
    checks["facts_required"] = len(required_facts)
    checks["facts_pass"] = len(facts_found) >= min_facts
    checks["facts_details"] = facts_found
    
    # Check required products (for Tesla)
    required_products = verification.get("required_products", [])
    if required_products:
        products_found = [p for p in required_products if p.lower() in full_text]
        min_products = verification.get("min_products_required", 3)
        checks["products_found"] = len(products_found)
        checks["products_required"] = len(required_products)
        checks["products_pass"] = len(products_found) >= min_products
        checks["products_details"] = products_found
    
    # Check legal keywords (for Amazon)
    legal_keywords = verification.get("legal_keywords", [])
    if legal_keywords:
        legal_found = [k for k in legal_keywords if k.lower() in full_text]
        min_legal = verification.get("min_legal_keywords", 2)
        checks["legal_found"] = len(legal_found)
        checks["legal_pass"] = len(legal_found) >= min_legal
        checks["legal_details"] = legal_found
    
    # Check numeric patterns
    numeric_checks = verification.get("numeric_checks", [])
    for nc in numeric_checks:
        pattern = nc.get("pattern", "")
        if pattern:
            matches = re.findall(pattern, full_text, re.I)
            checks[f"numeric_{nc['description'][:20]}"] = len(matches) > 0
    
    # Overall fact check pass
    checks["fact_check_passed"] = all([
        checks["has_report"],
        checks["has_summary"],
        checks["no_error"],
        checks.get("facts_pass", True),
        checks.get("products_pass", True) if required_products else True,
        checks.get("legal_pass", True) if legal_keywords else True,
    ])
    
    return checks


async def llm_judge(result: dict, task: dict) -> dict:
    """
    Use LLM as a judge to evaluate the response quality.
    
    Returns a score (1-5) and explanation.
    """
    verification = task.get("verification", {})
    criteria = verification.get("llm_judge_criteria", "")
    
    if not criteria:
        return {"score": None, "explanation": "No LLM judge criteria provided"}
    
    report = result.get("report", {})
    summary = report.get("summary", "")
    findings = report.get("findings", [])
    
    # Format the response for judging
    response_text = f"""
Summary: {summary}

Findings:
"""
    for f in findings:
        response_text += f"- {f.get('topic', '')}: {f.get('content', '')}\n"
    
    judge_prompt = f"""You are evaluating a research agent's response to a question about SEC 10-K filings.

Question: {task['question']}

Agent's Response:
{response_text}

Evaluation Criteria:
{criteria}

Score the response from 1-5:
1 = Completely wrong or missing key information
2 = Partially correct but missing important facts
3 = Acceptable - covers main points but lacks detail
4 = Good - accurate and well-sourced
5 = Excellent - comprehensive, accurate, and well-cited

Respond in JSON format:
{{"score": <1-5>, "explanation": "<brief explanation>"}}
"""
    
    try:
        llm = ChatAnthropic(model="claude-sonnet-5-5", max_tokens=500)
        response = await llm.ainvoke([HumanMessage(content=judge_prompt)])
        
        content = response.content
        if isinstance(content, list):
            content = content[0].get("text", "") if content else ""
        
        # Parse JSON response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        judge_result = json.loads(content.strip())
        return judge_result
        
    except Exception as e:
        return {"score": None, "explanation": f"LLM judge error: {str(e)}"}


async def run_evaluation(use_llm_judge: bool = True):
    """Run evaluation on all golden tasks."""
    tasks = load_golden_tasks()
    results = []
    
    print(f"\n{'='*60}")
    print(f"10-K Research Agent Evaluation")
    print(f"{'='*60}")
    print(f"Running {len(tasks)} golden tasks...")
    print(f"LLM Judge: {'Enabled' if use_llm_judge else 'Disabled'}\n")
    
    for task in tasks:
        print(f"Task {task['id']}: {task['question'][:50]}...")
        
        try:
            # Run research
            start_time = datetime.now()
            result = await research(task["question"])
            elapsed = (datetime.now() - start_time).total_seconds()
            
            # Fact check verification
            fact_checks = check_facts(result, task)
            
            # LLM judge (optional)
            judge_result = {"score": None, "explanation": "Skipped"}
            if use_llm_judge:
                judge_result = await llm_judge(result, task)
            
            # Determine pass/fail
            passed = fact_checks["fact_check_passed"]
            if use_llm_judge and judge_result.get("score"):
                passed = passed and judge_result["score"] >= 3
            
            # Store result
            task_result = {
                "task_id": task["id"],
                "question": task["question"],
                "company": task["company"],
                "elapsed_seconds": elapsed,
                "fact_checks": fact_checks,
                "llm_judge": judge_result,
                "passed": passed,
                "summary": result.get("report", {}).get("summary", ""),
                "error": result.get("error"),
            }
            results.append(task_result)
            
            # Print status
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status} ({elapsed:.1f}s)")
            print(f"    Facts: {fact_checks['facts_found']}/{fact_checks['facts_required']}")
            if use_llm_judge and judge_result.get("score"):
                print(f"    LLM Judge: {judge_result['score']}/5 - {judge_result['explanation'][:60]}...")
            
            if not passed:
                if result.get("error"):
                    print(f"    Error: {result['error'][:80]}")
                if not fact_checks.get("facts_pass", True):
                    print(f"    Missing facts: {set(task['verification'].get('required_facts', [])) - set(fact_checks.get('facts_details', []))}")
            
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results.append({
                "task_id": task["id"],
                "question": task["question"],
                "error": str(e),
                "passed": False,
            })
    
    # Summary
    passed = sum(1 for r in results if r.get("passed", False))
    total = len(results)
    
    # Calculate average LLM judge score
    judge_scores = [r["llm_judge"]["score"] for r in results if r.get("llm_judge", {}).get("score")]
    avg_score = sum(judge_scores) / len(judge_scores) if judge_scores else 0
    
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed ({100*passed/total:.0f}%)")
    if judge_scores:
        print(f"Average LLM Judge Score: {avg_score:.1f}/5")
    print(f"{'='*60}\n")
    
    # Save results
    output_path = Path(__file__).parent / "eval_results.json"
    with open(output_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": passed / total,
                "avg_llm_score": avg_score if judge_scores else None,
            },
            "results": results,
        }, f, indent=2)
    
    print(f"Results saved to {output_path}")
    
    return results


if __name__ == "__main__":
    # Check for --no-judge flag
    use_judge = "--no-judge" not in sys.argv
    asyncio.run(run_evaluation(use_llm_judge=use_judge))
