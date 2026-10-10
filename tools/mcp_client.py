"""MCP client wrapper for SEC EDGAR tools."""

import json
import subprocess
from typing import Any, Optional


class MCPClient:
    """
    Client for interacting with the sec-edgar-mcp server.
    
    The MCP server runs as a Docker container and communicates via stdio.
    """
    
    def __init__(self, user_agent: str):
        """
        Initialize the MCP client.
        
        Args:
            user_agent: SEC EDGAR user agent string (required by SEC)
                       Format: "Your Name (your@email.com)"
        """
        self.user_agent = user_agent
        self._docker_image = "stefanoamorelli/sec-edgar-mcp:latest"
    
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        """
        Call an MCP tool and return the result.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool result as a dictionary
        """
        # Build the MCP request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        # Run the Docker container with the request
        try:
            result = subprocess.run(
                [
                    "docker", "run", "-i", "--rm",
                    "-e", f"SEC_EDGAR_USER_AGENT={self.user_agent}",
                    self._docker_image
                ],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                return {"error": f"Docker error: {result.stderr}"}
            
            # Parse the response
            response = json.loads(result.stdout)
            
            if "error" in response:
                return {"error": response["error"]}
            
            return response.get("result", {})
            
        except subprocess.TimeoutExpired:
            return {"error": "MCP call timed out"}
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse MCP response: {e}"}
        except Exception as e:
            return {"error": f"MCP call failed: {e}"}
    
    # Convenience methods for common tools
    
    async def get_recent_filings(
        self,
        identifier: str,
        form_type: str = "10-K",
        days: int = 365,
        limit: int = 5
    ) -> dict:
        """Get recent filings for a company."""
        return await self.call_tool("get_recent_filings", {
            "identifier": identifier,
            "form_type": form_type,
            "days": days,
            "limit": limit
        })
    
    async def get_filing_sections(
        self,
        identifier: str,
        accession_number: str,
        form_type: str = "10-K"
    ) -> dict:
        """Get sections from a filing (business, risk_factors, mda)."""
        return await self.call_tool("get_filing_sections", {
            "identifier": identifier,
            "accession_number": accession_number,
            "form_type": form_type
        })
    
    async def get_financials(
        self,
        identifier: str,
        statement_type: str = "all",
        form_type: str = "10-K"
    ) -> dict:
        """Get financial statements (income, balance sheet, cash flow)."""
        return await self.call_tool("get_financials", {
            "identifier": identifier,
            "statement_type": statement_type,
            "form_type": form_type
        })
    
    async def get_segment_data(
        self,
        identifier: str,
        segment_type: str = "business"
    ) -> dict:
        """Get revenue breakdown by segment or geography."""
        return await self.call_tool("get_segment_data", {
            "identifier": identifier,
            "segment_type": segment_type
        })
    
    async def compare_periods(
        self,
        identifier: str,
        metric: str,
        start_year: int,
        end_year: int
    ) -> dict:
        """Compare a metric year-over-year."""
        return await self.call_tool("compare_periods", {
            "identifier": identifier,
            "metric": metric,
            "start_year": start_year,
            "end_year": end_year
        })
    
    async def get_company_info(self, identifier: str) -> dict:
        """Get company information (name, CIK, SIC, exchange)."""
        return await self.call_tool("get_company_info", {
            "identifier": identifier
        })
