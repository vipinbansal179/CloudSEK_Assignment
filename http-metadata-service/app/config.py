"""
Application configuration management.

Uses pydantic-settings to load configuration from environment variables,
providing type safety and validation for all external resource identifiers.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Attributes:
        app_name: Display name for the API service.
        app_version: Current version of the application.
        debug: Enable debug mode for development.
        mongo_url: MongoDB connection string.
        mongo_db_name: Name of the MongoDB database.
        http_request_timeout: Timeout (seconds) for outbound HTTP requests.
        http_max_redirects: Maximum number of HTTP redirects to follow.
        http_user_agent: User-Agent header for outbound HTTP requests.
    """

    # Application settings
    app_name: str = Field(
        default="HTTP Metadata Inventory Service",
        description="Display name for the API service",
    )
    app_version: str = Field(
        default="1.0.0",
        description="Current version of the application",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )

    # MongoDB settings
    mongo_url: str = Field(
        default="mongodb://mongodb:27017",
        description="MongoDB connection string",
    )
    mongo_db_name: str = Field(
        default="metadata_inventory",
        description="Name of the MongoDB database",
    )

    # HTTP client settings
    http_request_timeout: float = Field(
        default=30.0,
        description="Timeout in seconds for outbound HTTP requests",
    )
    http_max_redirects: int = Field(
        default=10,
        description="Maximum number of HTTP redirects to follow",
    )
    http_user_agent: str = Field(
        default="HTTPMetadataInventoryService/1.0",
        description="User-Agent header for outbound requests",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """
    Factory function to create and return a Settings instance.
    
    This function can be used as a FastAPI dependency for 
    injecting configuration throughout the application.
    
    Returns:
        Settings: Validated application settings.
    """
    return Settings()