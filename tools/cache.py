"""Caching utilities for SEC filing data."""

import time
import hashlib
from typing import Any, Optional, Dict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class CacheEntry:
    """A cached item with TTL."""
    value: Any
    expires_at: float
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class FilingCache:
    """
    Thread-safe in-memory cache for SEC filing data.
    
    Caches:
    - Filing metadata (company filings list)
    - Filing sections (extracted content)
    - Full filing content
    
    Uses TTL-based expiration to ensure data freshness.
    """
    
    def __init__(self, default_ttl: int = 3600):
        """
        Initialize cache.
        
        Args:
            default_ttl: Default time-to-live in seconds (default: 1 hour)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
        self.default_ttl = default_ttl
        self.stats = {"hits": 0, "misses": 0}
    
    def _make_key(self, prefix: str, *args) -> str:
        """Create a cache key from prefix and arguments."""
        key_parts = [prefix] + [str(a) for a in args]
        key_str = ":".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if it exists and hasn't expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self.stats["misses"] += 1
                return None
            
            if entry.is_expired():
                del self._cache[key]
                self.stats["misses"] += 1
                return None
            
            self.stats["hits"] += 1
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in cache with optional custom TTL."""
        ttl = ttl or self.default_ttl
        expires_at = time.time() + ttl
        
        with self._lock:
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
    
    def delete(self, key: str) -> bool:
        """Delete a key from cache. Returns True if key existed."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> int:
        """Clear all cache entries. Returns number of entries cleared."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns number of entries removed."""
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() if v.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total = self.stats["hits"] + self.stats["misses"]
            hit_rate = self.stats["hits"] / total if total > 0 else 0
            return {
                "hits": self.stats["hits"],
                "misses": self.stats["misses"],
                "hit_rate": f"{hit_rate:.2%}",
                "size": len(self._cache),
            }
    
    # Convenience methods for specific data types
    
    def get_filings(self, company: str, form_type: str) -> Optional[dict]:
        """Get cached filings list for a company."""
        key = self._make_key("filings", company, form_type)
        return self.get(key)
    
    def set_filings(self, company: str, form_type: str, data: dict, ttl: int = 3600) -> None:
        """Cache filings list for a company."""
        key = self._make_key("filings", company, form_type)
        self.set(key, data, ttl)
    
    def get_sections(self, company: str, accession: str) -> Optional[dict]:
        """Get cached sections for a filing."""
        key = self._make_key("sections", company, accession)
        return self.get(key)
    
    def set_sections(self, company: str, accession: str, data: dict, ttl: int = 7200) -> None:
        """Cache sections for a filing (longer TTL since filings don't change)."""
        key = self._make_key("sections", company, accession)
        self.set(key, data, ttl)
    
    def get_full_content(self, company: str, accession: str) -> Optional[str]:
        """Get cached full filing content."""
        key = self._make_key("content", company, accession)
        return self.get(key)
    
    def set_full_content(self, company: str, accession: str, content: str, ttl: int = 7200) -> None:
        """Cache full filing content."""
        key = self._make_key("content", company, accession)
        self.set(key, content, ttl)
    
    def get_financials(self, company: str) -> Optional[dict]:
        """Get cached financial data for a company."""
        key = self._make_key("financials", company)
        return self.get(key)
    
    def set_financials(self, company: str, data: dict, ttl: int = 3600) -> None:
        """Cache financial data for a company."""
        key = self._make_key("financials", company)
        self.set(key, data, ttl)


# Global cache instance
_cache: Optional[FilingCache] = None


def get_cache() -> FilingCache:
    """Get the global cache instance (lazy initialization)."""
    global _cache
    if _cache is None:
        _cache = FilingCache(default_ttl=3600)  # 1 hour default
    return _cache
