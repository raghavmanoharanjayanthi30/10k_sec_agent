"""
Full 10-K Section Extractor

Extracts complete sections from SEC 10-K filings, including subsections.
Uses MCP's get_filing_content() to fetch full text, then parses sections.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class Section:
    """Represents a 10-K section."""
    item: str
    title: str
    content: str
    start_pos: int
    end_pos: int
    subsections: Dict[str, str]


# Standard 10-K item patterns (SEC mandated structure)
ITEM_PATTERNS = {
    "1": r"ITEM\s*1\.?\s*[-–—]?\s*BUSINESS",
    "1A": r"ITEM\s*1A\.?\s*[-–—]?\s*RISK\s*FACTORS",
    "1B": r"ITEM\s*1B\.?\s*[-–—]?\s*UNRESOLVED\s*STAFF\s*COMMENTS",
    "1C": r"ITEM\s*1C\.?\s*[-–—]?\s*CYBERSECURITY",
    "2": r"ITEM\s*2\.?\s*[-–—]?\s*PROPERTIES",
    "3": r"ITEM\s*3\.?\s*[-–—]?\s*LEGAL\s*PROCEEDINGS",
    "4": r"ITEM\s*4\.?\s*[-–—]?\s*MINE\s*SAFETY",
    "5": r"ITEM\s*5\.?\s*[-–—]?\s*MARKET\s*FOR",
    "6": r"ITEM\s*6\.?\s*[-–—]?\s*(\[RESERVED\]|RESERVED|SELECTED)",
    "7": r"ITEM\s*7\.?\s*[-–—]?\s*MANAGEMENT",
    "7A": r"ITEM\s*7A\.?\s*[-–—]?\s*QUANTITATIVE",
    "8": r"ITEM\s*8\.?\s*[-–—]?\s*FINANCIAL\s*STATEMENTS",
    "9": r"ITEM\s*9\.?\s*[-–—]?\s*CHANGES\s*IN\s*AND\s*DISAGREEMENTS",
    "9A": r"ITEM\s*9A\.?\s*[-–—]?\s*CONTROLS",
    "9B": r"ITEM\s*9B\.?\s*[-–—]?\s*OTHER\s*INFORMATION",
    "9C": r"ITEM\s*9C\.?\s*[-–—]?\s*DISCLOSURE\s*REGARDING",
    "10": r"ITEM\s*10\.?\s*[-–—]?\s*DIRECTORS",
    "11": r"ITEM\s*11\.?\s*[-–—]?\s*EXECUTIVE\s*COMPENSATION",
    "12": r"ITEM\s*12\.?\s*[-–—]?\s*SECURITY\s*OWNERSHIP",
    "13": r"ITEM\s*13\.?\s*[-–—]?\s*CERTAIN\s*RELATIONSHIPS",
    "14": r"ITEM\s*14\.?\s*[-–—]?\s*PRINCIPAL\s*ACCOUNTANT",
    "15": r"ITEM\s*15\.?\s*[-–—]?\s*(EXHIBITS|EXHIBIT)",
    "16": r"ITEM\s*16\.?\s*[-–—]?\s*FORM\s*10-K\s*SUMMARY",
}

# Common subsection patterns within items
SUBSECTION_PATTERNS = {
    "executive_officers": [
        r"INFORMATION\s*ABOUT\s*(OUR\s*)?EXECUTIVE\s*OFFICERS",
        r"EXECUTIVE\s*OFFICERS\s*OF\s*THE\s*(REGISTRANT|COMPANY)",
        r"EXECUTIVE\s*OFFICERS",
        r"OUR\s*EXECUTIVE\s*OFFICERS",
    ],
    "products_services": [
        r"PRODUCTS\s*AND\s*SERVICES",
        r"OUR\s*PRODUCTS",
        r"PRODUCTS",
    ],
    "competition": [
        r"COMPETITION",
        r"COMPETITIVE\s*ENVIRONMENT",
    ],
    "employees": [
        r"HUMAN\s*CAPITAL",
        r"EMPLOYEES",
        r"OUR\s*PEOPLE",
    ],
    "intellectual_property": [
        r"INTELLECTUAL\s*PROPERTY",
        r"PATENTS\s*AND\s*TRADEMARKS",
    ],
    "government_regulation": [
        r"GOVERNMENT\s*REGULATION",
        r"REGULATORY\s*ENVIRONMENT",
        r"REGULATION",
    ],
}

# Item titles for reference
ITEM_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "[Reserved]",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions",
    "10": "Directors, Executive Officers, and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits, Financial Statement Schedules",
    "16": "Form 10-K Summary",
}


class SectionExtractor:
    """Extracts sections and subsections from 10-K filing text."""
    
    def __init__(self, filing_text: str):
        """Initialize with full filing text."""
        self.text = filing_text
        self.text_upper = filing_text.upper()
        self._section_positions: Dict[str, Tuple[int, int]] = {}
        self._find_all_sections()
    
    def _find_all_sections(self):
        """Find start positions of all sections."""
        positions = []
        
        for item, pattern in ITEM_PATTERNS.items():
            matches = list(re.finditer(pattern, self.text_upper))
            
            if len(matches) == 1:
                # Only one match - use it
                positions.append((matches[0].start(), item, matches[0].group()))
            elif len(matches) > 1:
                # Multiple matches - try to find the actual content (not TOC)
                # The actual section usually has more content after it
                best_match = None
                best_score = -1
                
                for match in matches:
                    pos = match.start()
                    # Look at content after this match
                    after_content = self.text[pos:pos + 2000]
                    
                    # Score based on content length and indicators
                    score = 0
                    
                    # Penalize if it looks like TOC (short with page numbers nearby)
                    if re.search(r'^\s*\d+\s*$', after_content[:100], re.MULTILINE):
                        score -= 10
                    
                    # Bonus if there's substantial text content
                    words_after = len(after_content.split())
                    score += min(words_after, 100)
                    
                    # Bonus if it contains typical section content
                    if item == "1" and "BUSINESS" in after_content.upper()[:500]:
                        if any(word in after_content.upper() for word in ["PRODUCTS", "SERVICES", "OPERATIONS", "EMPLOYEES"]):
                            score += 50
                    
                    if score > best_score:
                        best_score = score
                        best_match = match
                
                if best_match:
                    positions.append((best_match.start(), item, best_match.group()))
        
        # Sort by position
        positions.sort(key=lambda x: x[0])
        
        # Calculate end positions (start of next section)
        for i, (start, item, _) in enumerate(positions):
            if i + 1 < len(positions):
                end = positions[i + 1][0]
            else:
                end = len(self.text)
            
            # Only keep first occurrence of each item
            if item not in self._section_positions:
                self._section_positions[item] = (start, end)
    
    def get_section(self, item: str, max_chars: Optional[int] = None) -> Optional[str]:
        """
        Get the full content of a section.
        
        Args:
            item: Item number (e.g., "1", "1A", "7")
            max_chars: Optional limit on characters returned
            
        Returns:
            Section content or None if not found
        """
        if item not in self._section_positions:
            return None
        
        start, end = self._section_positions[item]
        content = self.text[start:end].strip()
        
        if max_chars and len(content) > max_chars:
            content = content[:max_chars] + "\n\n... [truncated]"
        
        return content
    
    def get_subsection(self, item: str, subsection_name: str, max_chars: Optional[int] = None) -> Optional[str]:
        """
        Get a specific subsection within an item.
        
        Args:
            item: Item number (e.g., "1", "10")
            subsection_name: Name of subsection (e.g., "executive_officers")
            max_chars: Optional limit on characters returned
            
        Returns:
            Subsection content or None if not found
        """
        section_content = self.get_section(item)
        if not section_content:
            return None
        
        patterns = SUBSECTION_PATTERNS.get(subsection_name, [])
        if not patterns:
            # Try using the name directly as a pattern
            patterns = [subsection_name.upper().replace("_", r"\s*")]
        
        section_upper = section_content.upper()
        
        for pattern in patterns:
            match = re.search(pattern, section_upper)
            if match:
                # Find the start of this subsection
                start = match.start()
                
                # Find the end (next major heading or end of section)
                # Look for next all-caps heading or next Item
                end_pattern = r'\n\s*[A-Z][A-Z\s]{10,}\n|\nITEM\s*\d'
                end_match = re.search(end_pattern, section_upper[start + len(match.group()):])
                
                if end_match:
                    end = start + len(match.group()) + end_match.start()
                else:
                    end = len(section_content)
                
                content = section_content[start:end].strip()
                
                if max_chars and len(content) > max_chars:
                    content = content[:max_chars] + "\n\n... [truncated]"
                
                return content
        
        return None
    
    def get_available_sections(self) -> List[str]:
        """Get list of available section items."""
        return list(self._section_positions.keys())
    
    def search_for_topic(self, topic: str, max_chars: int = 10000) -> Optional[Dict[str, str]]:
        """
        Search for a topic across all sections.
        
        Args:
            topic: Topic to search for (e.g., "executive officers")
            max_chars: Max chars per result
            
        Returns:
            Dict mapping item numbers to relevant content
        """
        results = {}
        topic_pattern = topic.upper().replace(" ", r"\s*")
        
        for item in self._section_positions:
            content = self.get_section(item)
            if content and re.search(topic_pattern, content.upper()):
                # Extract surrounding context
                match = re.search(topic_pattern, content.upper())
                if match:
                    # Get content from match position
                    start = max(0, match.start() - 200)
                    end = min(len(content), match.start() + max_chars)
                    results[item] = content[start:end]
        
        return results if results else None


def extract_sections_from_filing(
    filing_text: str,
    items: List[str],
    include_subsections: bool = True,
    max_chars_per_section: int = 50000
) -> Dict[str, Any]:
    """
    Extract specified sections from a 10-K filing.
    
    Args:
        filing_text: Full text of the 10-K filing
        items: List of items to extract (e.g., ["1", "1A", "7"])
        include_subsections: Whether to extract known subsections
        max_chars_per_section: Max characters per section
        
    Returns:
        Dict with sections and metadata
    """
    extractor = SectionExtractor(filing_text)
    
    result = {
        "success": True,
        "sections": {},
        "subsections": {},
        "available_sections": extractor.get_available_sections(),
    }
    
    for item in items:
        content = extractor.get_section(item, max_chars=max_chars_per_section)
        if content:
            result["sections"][item] = content
            
            # Extract known subsections for this item
            if include_subsections:
                if item in ["1", "10"]:  # Items that commonly have executive officers
                    exec_content = extractor.get_subsection(item, "executive_officers")
                    if exec_content:
                        result["subsections"][f"{item}_executive_officers"] = exec_content
                
                if item == "1":  # Business section subsections
                    for subsec in ["products_services", "competition", "employees"]:
                        subsec_content = extractor.get_subsection(item, subsec)
                        if subsec_content:
                            result["subsections"][f"{item}_{subsec}"] = subsec_content
    
    return result


def extract_executive_officers(filing_text: str, max_chars: int = 10000) -> Optional[str]:
    """
    Directly extract executive officers information from filing text.
    
    This function searches for common patterns that indicate executive officer
    information, regardless of section structure.
    
    Args:
        filing_text: Full text of the 10-K filing
        max_chars: Maximum characters to return
        
    Returns:
        Executive officers content or None if not found
    """
    text_upper = filing_text.upper()
    
    # First, try to find the actual executive officers table/list
    # Look for patterns that indicate actual content (not TOC)
    content_patterns = [
        # Table header patterns with names
        r"OUR EXECUTIVE OFFICERS AS OF[^.]{0,50}WERE AS FOLLOWS",
        r"EXECUTIVE OFFICERS[^.]{0,30}NAME\s+AGE",
        r"NAME\s+AGE\s+POSITION WITH THE COMPANY",
        r"EXECUTIVE OFFICERS OF THE REGISTRANT",
    ]
    
    for pattern in content_patterns:
        match = re.search(pattern, text_upper)
        if match:
            start = match.start()
            # Find a reasonable end point
            end_patterns = [
                r"ITEM\s*1A",
                r"ITEM\s*2\.",
                r"RISK\s*FACTORS",
                r"AVAILABLE\s*INFORMATION",
                r"PART\s*II",
            ]
            
            end = start + max_chars
            for end_pattern in end_patterns:
                end_match = re.search(end_pattern, text_upper[start + 100:start + max_chars])
                if end_match:
                    end = min(end, start + 100 + end_match.start())
                    break
            
            content = filing_text[start:end]
            # Verify this has actual names (not just TOC)
            if re.search(r'(CEO|Chief Executive|Chairman|President|Officer)', content, re.I):
                return content
    
    # Second approach: find by looking for the actual officer names/titles pattern
    # This pattern matches the typical format: "Name Age Title"
    officer_table_pattern = r"(Satya|Tim|Sundar|Andy|Jensen|Lisa)[^.]{0,50}(Chairman|Chief Executive|CEO|President)"
    match = re.search(officer_table_pattern, filing_text, re.I)
    if match:
        # Expand backwards to find section header
        start = max(0, match.start() - 500)
        # Look for section header
        header_match = re.search(r"EXECUTIVE OFFICERS|INFORMATION ABOUT", filing_text[start:match.start()].upper())
        if header_match:
            start = start + header_match.start()
        
        # Find end
        end = min(len(filing_text), match.start() + max_chars)
        end_patterns = [r"ITEM\s*1A", r"ITEM\s*2\.", r"RISK\s*FACTORS", r"PART\s*II"]
        for end_pattern in end_patterns:
            end_match = re.search(end_pattern, text_upper[match.start():match.start() + max_chars])
            if end_match:
                end = min(end, match.start() + end_match.start())
                break
        
        return filing_text[start:end]
    
    # Third approach: search for "INFORMATION ABOUT OUR EXECUTIVE OFFICERS" but skip TOC
    header_pattern = r"INFORMATION ABOUT OUR EXECUTIVE OFFICERS"
    matches = list(re.finditer(header_pattern, text_upper))
    
    for match in matches:
        start = match.start()
        # Check if this is TOC (followed by page number pattern)
        after_text = filing_text[start:start + 200]
        # TOC entries are short and followed by page numbers
        if re.match(r"[^\d]{0,50}\d+\s*(Item|ITEM|PART)", after_text):
            continue  # Skip TOC entry
        
        # This looks like actual content
        end = start + max_chars
        for end_pattern in [r"ITEM\s*1A", r"RISK\s*FACTORS", r"PART\s*II"]:
            end_match = re.search(end_pattern, text_upper[start + 100:start + max_chars])
            if end_match:
                end = min(end, start + 100 + end_match.start())
                break
        
        content = filing_text[start:end]
        # Verify this has actual names
        if re.search(r'(CEO|Chief Executive|Chairman|President|Officer)', content, re.I):
            return content
    
    return None


def get_section_for_topic(filing_text: str, topic: str) -> Optional[Dict[str, str]]:
    """
    Find sections relevant to a specific topic.
    
    Args:
        filing_text: Full text of the 10-K filing
        topic: Topic to search for
        
    Returns:
        Dict mapping item numbers to relevant content
    """
    # Special handling for executive officers
    if "executive" in topic.lower() or "officer" in topic.lower():
        exec_content = extract_executive_officers(filing_text)
        if exec_content:
            return {"executive_officers": exec_content}
    
    extractor = SectionExtractor(filing_text)
    return extractor.search_for_topic(topic)
