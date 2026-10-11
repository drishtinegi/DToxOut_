"""
Application configuration module.

Loads all settings from environment variables using pydantic-settings.
A single ``settings`` instance is exported for use throughout the app:

    from app.core.config import settings
    print(settings.JWT_SECRET_KEY)
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration class.

    Each field maps to an environment variable of the SAME NAME.
    Values are loaded from ``.env`` at module-import time.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ---- Application ----
    APP_NAME: str = "DToxOut"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # ---- Server ----
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ---- Database ----
    DATABASE_URL: str = ""

    # ---- JWT / Authentication ----
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---- Logging ----
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "keyvalue"

    # ---- CORS Configuration ----
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:8000,http://127.0.0.1:8000"
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "*"
    CORS_ALLOW_HEADERS: str = "*"

    # ---- Reverse proxy / API docs ----
    # Number of trusted reverse proxies in front of the app (nginx, Azure
    # Container Apps ingress, ...). 0 = ignore X-Forwarded-For entirely.
    TRUSTED_PROXY_COUNT: int = 1
    # Expose /docs, /redoc and /openapi.json. Disabled automatically in production
    # unless explicitly enabled.
    ENABLE_API_DOCS: Optional[bool] = None
    # HSTS max-age (seconds) sent in production. 0 disables the header.
    HSTS_MAX_AGE: int = 31536000

    # ---- Rate Limiting ----
    RATE_LIMIT_DEFAULT: str = "60/minute"
    RATE_LIMIT_AUTH: str = "5/minute"
    RATE_LIMIT_SCAN: str = "10/minute"
    RATE_LIMIT_SEARCH: str = "30/minute"

    # ---- Image Upload & OCR ----
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB
    ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/webp"
    DELETE_TEMP_UPLOADS: bool = True
    RETAIN_UPLOADS: bool = False
    UPLOAD_RETENTION_HOURS: int = 24

    # ---- OCR Engine Configuration ----
    OCR_PROVIDER: str = "tesseract"  # mock | tesseract | paddle
    OCR_LANGUAGE: str = "eng"
    OCR_TIMEOUT_SECONDS: float = 10.0
    OCR_MIN_CONFIDENCE: float = 0.60

    # ---- Image Preprocessing Limits ----
    MAX_IMAGE_WIDTH: int = 4096
    MAX_IMAGE_HEIGHT: int = 4096
    MAX_IMAGE_PIXELS: int = 16_000_000

    # ---- External Object Storage ----
    STORAGE_PROVIDER: str = "local"  # local | azure | s3
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = None
    AZURE_STORAGE_CONTAINER_NAME: str = "dtoxout-uploads"
    S3_BUCKET_NAME: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS_ORIGINS into a cleaned list.

        Returns:
            List of allowed origin URLs with whitespace stripped.
        """
        if not self.CORS_ORIGINS:
            return []
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def is_production(self) -> bool:
        """Check if the application is running in production mode."""
        return self.APP_ENV.lower() == "production"

    @property
    def api_docs_enabled(self) -> bool:
        """Interactive API docs are on in dev/test, off in production by default."""
        if self.ENABLE_API_DOCS is not None:
            return self.ENABLE_API_DOCS
        return not self.is_production

    @property
    def log_level_int(self) -> int:
        """Parse LOG_LEVEL string into a Python logging integer level.

        Falls back to INFO if the value is unrecognized.
        """
        import logging

        return getattr(logging, self.LOG_LEVEL.upper(), logging.INFO)

    def validate_production_config(self) -> None:
        """Validate production configuration settings.

        Raises:
            ValueError: If required secrets or settings are missing/insecure in production.
        """
        if not self.is_production:
            return

        insecure_keys = {"", "default-insecure-key", "change-me", "dev-secret", "secret"}
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY.lower().strip() in insecure_keys:
            raise ValueError(
                "Production configuration error: JWT_SECRET_KEY must be configured with a secure secret in production mode."
            )

        if not self.DATABASE_URL or not self.DATABASE_URL.strip():
            raise ValueError(
                "Production configuration error: DATABASE_URL must be explicitly configured in production mode."
            )

        if len(self.JWT_SECRET_KEY) < 32:
            raise ValueError(
                "Production configuration error: JWT_SECRET_KEY must be at least 32 characters."
            )

        if self.CORS_ALLOW_CREDENTIALS and "*" in self.cors_origin_list:
            raise ValueError(
                "Production configuration error: Wildcard '*' CORS origin is prohibited when CORS_ALLOW_CREDENTIALS is True."
            )

        if self.DEBUG:
            raise ValueError(
                "Production configuration error: DEBUG must be false in production mode."
            )


# Singleton settings instance — import this everywhere.
settings = Settings()

