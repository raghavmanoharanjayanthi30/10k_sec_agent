"""Configuration settings."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    
    # API Keys
    anthropic_api_key: str = ""
    langchain_api_key: str = ""
    
    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_project: str = "10k-filing-agent"
    
    # SEC EDGAR
    sec_edgar_user_agent: str = "Research Agent (research@example.com)"
    
    # MCP Server
    mcp_server_url: str = "http://localhost:8000"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
