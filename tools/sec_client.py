"""Direct SEC EDGAR API client (no MCP/Docker dependency)."""

import httpx
from typing import Any, Optional


class SECEdgarClient:
    """
    Direct client for SEC EDGAR API.
    
    This bypasses MCP and calls SEC EDGAR directly for simpler testing.
    """
    
    def __init__(self, user_agent: str):
        """
        Initialize the SEC EDGAR client.
        
        Args:
            user_agent: SEC EDGAR user agent string (required by SEC)
                       Format: "Your Name (your@email.com)"
        """
        self.user_agent = user_agent
        self.base_url = "https://data.sec.gov"
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }
    
    async def get_company_cik(self, ticker: str) -> Optional[str]:
        """Get CIK for a ticker symbol."""
        async with httpx.AsyncClient() as client:
            # Get company tickers mapping
            resp = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=self.headers,
                timeout=30,
            )
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            ticker_upper = ticker.upper()
            
            for entry in data.values():
                if entry.get("ticker") == ticker_upper:
                    # CIK needs to be zero-padded to 10 digits
                    return str(entry.get("cik_str", "")).zfill(10)
            
            return None
    
    async def get_recent_filings(
        self,
        identifier: str,
        form_type: str = "10-K",
        limit: int = 5
    ) -> dict:
        """Get recent filings for a company."""
        # First get CIK
        cik = await self.get_company_cik(identifier)
        if not cik:
            return {"error": f"Could not find CIK for {identifier}"}
        
        async with httpx.AsyncClient() as client:
            # Get company submissions
            resp = await client.get(
                f"{self.base_url}/submissions/CIK{cik}.json",
                headers=self.headers,
                timeout=30,
            )
            
            if resp.status_code != 200:
                return {"error": f"Failed to get filings: HTTP {resp.status_code}"}
            
            data = resp.json()
            filings = []
            
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            accessions = recent.get("accessionNumber", [])
            dates = recent.get("filingDate", [])
            
            for i, form in enumerate(forms):
                if form == form_type and len(filings) < limit:
                    acc_num = accessions[i]
                    acc_formatted = acc_num.replace("-", "")
                    filings.append({
                        "accession_number": acc_num,
                        "filing_date": dates[i],
                        "form_type": form,
                        "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_formatted}/{acc_num}-index.htm",
                    })
            
            return {
                "filings": filings,
                "company_name": data.get("name", ""),
                "cik": cik,
            }
    
    async def get_filing_sections(
        self,
        identifier: str,
        accession_number: str,
        form_type: str = "10-K"
    ) -> dict:
        """
        Get sections from a filing by parsing the actual 10-K HTML.
        
        Extracts Item 1 (Business), Item 1A (Risk Factors), and Item 7 (MD&A).
        """
        cik = await self.get_company_cik(identifier)
        if not cik:
            return {"error": f"Could not find CIK for {identifier}"}
        
        acc_formatted = accession_number.replace("-", "")
        
        async with httpx.AsyncClient() as client:
            # First, get the filing index to find the 10-K document
            index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_formatted}/{accession_number}-index.json"
            
            resp = await client.get(index_url, headers=self.headers, timeout=30)
            
            if resp.status_code != 200:
                # Try alternative: get the directory listing
                return await self._get_sections_from_filing_direct(client, cik, acc_formatted, accession_number)
            
            index_data = resp.json()
            
            # Find the main 10-K document (usually .htm file)
            doc_url = None
            for item in index_data.get("directory", {}).get("item", []):
                name = item.get("name", "")
                if name.endswith(".htm") and "10-k" in name.lower():
                    doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_formatted}/{name}"
                    break
            
            if not doc_url:
                # Try to find any .htm file
                for item in index_data.get("directory", {}).get("item", []):
                    name = item.get("name", "")
                    if name.endswith(".htm") and not name.endswith("-index.htm"):
                        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_formatted}/{name}"
                        break
            
            if not doc_url:
                return await self._get_sections_from_filing_direct(client, cik, acc_formatted, accession_number)
            
            return await self._parse_10k_document(client, doc_url)
    
    async def _get_sections_from_filing_direct(
        self, 
        client: httpx.AsyncClient, 
        cik: str, 
        acc_formatted: str,
        accession_number: str
    ) -> dict:
        """Try to get sections by directly accessing the filing directory."""
        # Try common 10-K filename patterns
        base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_formatted}"
        
        # Get directory listing
        dir_resp = await client.get(f"{base_url}/", headers=self.headers, timeout=30)
        
        if dir_resp.status_code == 200:
            # Parse HTML to find .htm files
            import re
            htm_files = re.findall(r'href="([^"]+\.htm)"', dir_resp.text, re.IGNORECASE)
            
            for htm_file in htm_files:
                if "10-k" in htm_file.lower() or "10k" in htm_file.lower():
                    doc_url = f"{base_url}/{htm_file}"
                    return await self._parse_10k_document(client, doc_url)
            
            # If no 10-k specific file, try the first large htm file
            for htm_file in htm_files:
                if not htm_file.endswith("-index.htm") and "ex" not in htm_file.lower():
                    doc_url = f"{base_url}/{htm_file}"
                    return await self._parse_10k_document(client, doc_url)
        
        return {
            "error": "Could not find 10-K document",
            "filing_url": base_url,
        }
    
    async def _parse_10k_document(self, client: httpx.AsyncClient, doc_url: str) -> dict:
        """Parse a 10-K HTML document to extract sections."""
        import re
        
        resp = await client.get(doc_url, headers=self.headers, timeout=60)
        
        if resp.status_code != 200:
            return {"error": f"Failed to fetch document: HTTP {resp.status_code}"}
        
        html = resp.text
        
        # Remove HTML tags but keep text
        def strip_html(text: str) -> str:
            # Remove script and style elements
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text)
            # Decode HTML entities
            text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            return text.strip()
        
        sections = {
            "filing_url": doc_url,
        }
        
        # Try to extract Item 1A - Risk Factors
        # Common patterns in 10-K filings
        risk_patterns = [
            r'(?:ITEM\s*1A[.\s]*[-–—]?\s*RISK\s*FACTORS)(.*?)(?:ITEM\s*1B|ITEM\s*2\b)',
            r'(?:Item\s*1A[.\s]*[-–—]?\s*Risk\s*Factors)(.*?)(?:Item\s*1B|Item\s*2\b)',
            r'(?:RISK\s*FACTORS)(.*?)(?:UNRESOLVED\s*STAFF|ITEM\s*1B|ITEM\s*2\b)',
        ]
        
        for pattern in risk_patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                risk_text = strip_html(match.group(1))
                # Limit to first 15000 chars to avoid overwhelming the LLM
                if len(risk_text) > 15000:
                    risk_text = risk_text[:15000] + "... [truncated]"
                sections["risk_factors"] = risk_text
                break
        
        if "risk_factors" not in sections:
            sections["risk_factors"] = "[Risk factors section could not be extracted from the filing]"
        
        # Try to extract Item 1 - Business
        business_patterns = [
            r'(?:ITEM\s*1[.\s]*[-–—]?\s*BUSINESS)(.*?)(?:ITEM\s*1A|ITEM\s*1B)',
            r'(?:Item\s*1[.\s]*[-–—]?\s*Business)(.*?)(?:Item\s*1A|Item\s*1B)',
        ]
        
        for pattern in business_patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                business_text = strip_html(match.group(1))
                if len(business_text) > 10000:
                    business_text = business_text[:10000] + "... [truncated]"
                sections["business"] = business_text
                break
        
        if "business" not in sections:
            sections["business"] = "[Business section could not be extracted from the filing]"
        
        # Try to extract Item 7 - MD&A
        mda_patterns = [
            r'(?:ITEM\s*7[.\s]*[-–—]?\s*MANAGEMENT.S\s*DISCUSSION)(.*?)(?:ITEM\s*7A|ITEM\s*8\b)',
            r'(?:Item\s*7[.\s]*[-–—]?\s*Management.s\s*Discussion)(.*?)(?:Item\s*7A|Item\s*8\b)',
            r'(?:MANAGEMENT.S\s*DISCUSSION\s*AND\s*ANALYSIS)(.*?)(?:QUANTITATIVE|ITEM\s*7A|ITEM\s*8\b)',
        ]
        
        for pattern in mda_patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                mda_text = strip_html(match.group(1))
                if len(mda_text) > 12000:
                    mda_text = mda_text[:12000] + "... [truncated]"
                sections["mda"] = mda_text
                break
        
        if "mda" not in sections:
            sections["mda"] = "[MD&A section could not be extracted from the filing]"
        
        return sections
    
    async def get_financials(
        self,
        identifier: str,
        statement_type: str = "all",
        form_type: str = "10-K"
    ) -> dict:
        """Get financial data from company facts."""
        cik = await self.get_company_cik(identifier)
        if not cik:
            return {"error": f"Could not find CIK for {identifier}"}
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/xbrl/companyfacts/CIK{cik}.json",
                headers=self.headers,
                timeout=30,
            )
            
            if resp.status_code != 200:
                return {"error": f"Failed to get financials: HTTP {resp.status_code}"}
            
            data = resp.json()
            
            # Extract key financial metrics
            facts = data.get("facts", {})
            us_gaap = facts.get("us-gaap", {})
            
            financials = {
                "company": data.get("entityName", identifier),
                "cik": cik,
            }
            
            # Try to get revenue
            for revenue_key in ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]:
                if revenue_key in us_gaap:
                    units = us_gaap[revenue_key].get("units", {})
                    usd = units.get("USD", [])
                    if usd:
                        # Get most recent annual values
                        annual = [u for u in usd if u.get("form") == "10-K"]
                        if annual:
                            recent = sorted(annual, key=lambda x: x.get("end", ""), reverse=True)[:3]
                            financials["revenue"] = [
                                {"period": r.get("end"), "value": r.get("val"), "form": r.get("form")}
                                for r in recent
                            ]
                            break
            
            # Try to get net income
            for income_key in ["NetIncomeLoss", "ProfitLoss"]:
                if income_key in us_gaap:
                    units = us_gaap[income_key].get("units", {})
                    usd = units.get("USD", [])
                    if usd:
                        annual = [u for u in usd if u.get("form") == "10-K"]
                        if annual:
                            recent = sorted(annual, key=lambda x: x.get("end", ""), reverse=True)[:3]
                            financials["net_income"] = [
                                {"period": r.get("end"), "value": r.get("val"), "form": r.get("form")}
                                for r in recent
                            ]
                            break
            
            # Try to get total assets
            if "Assets" in us_gaap:
                units = us_gaap["Assets"].get("units", {})
                usd = units.get("USD", [])
                if usd:
                    annual = [u for u in usd if u.get("form") == "10-K"]
                    if annual:
                        recent = sorted(annual, key=lambda x: x.get("end", ""), reverse=True)[:3]
                        financials["total_assets"] = [
                            {"period": r.get("end"), "value": r.get("val"), "form": r.get("form")}
                            for r in recent
                        ]
            
            return financials
    
    async def get_segment_data(
        self,
        identifier: str,
        segment_type: str = "business"
    ) -> dict:
        """Get segment data (placeholder - requires deeper XBRL parsing)."""
        return {
            "note": "Segment data extraction requires detailed XBRL parsing",
            "identifier": identifier,
        }
