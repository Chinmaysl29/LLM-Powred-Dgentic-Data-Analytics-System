"""Strongly typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime settings shared by all infrastructure adapters and services."""

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_name: str = "Enterprise AI Data Analyst OS"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"
    cors_origins: str | list[str] = ""

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai_analyst"
    postgres_user: str = "postgres"
    postgres_password: SecretStr = SecretStr("postgres")
    database_url: str | None = None
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: SecretStr | None = None
    redis_db: int = 0
    redis_url: str = "redis://localhost:6379/0"
    default_tenant_id: str = "system"

    # ------------------------------------------------------------------
    # ChromaDB
    # ------------------------------------------------------------------
    chroma_host: str = "localhost"
    chroma_port: int = Field(default=8001, ge=1, le=65535)
    chroma_persist_dir: str = "/chroma"

    # ------------------------------------------------------------------
    # LLM Providers
    # ------------------------------------------------------------------
    groq_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    default_llm: str = "llama-3.3-70b-versatile"
    default_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ------------------------------------------------------------------
    # HuggingFace
    # ------------------------------------------------------------------
    huggingface_api_key: SecretStr | None = None

    # ------------------------------------------------------------------
    # LangChain / LangSmith
    # ------------------------------------------------------------------
    langchain_tracing_v2: bool = False
    langchain_project: str = "AI-Data-Analyst-OS"
    langsmith_api_key: SecretStr | None = None

    # ------------------------------------------------------------------
    # JWT Authentication
    # ------------------------------------------------------------------
    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # ------------------------------------------------------------------
    # Supabase Integration
    # ------------------------------------------------------------------
    supabase_url: str = "https://pmmlieqibfgbxtjdkbnl.supabase.co"
    supabase_publishable_key: SecretStr | None = None
    supabase_jwt_aud: str = "authenticated"

    # ------------------------------------------------------------------
    # Financial Data APIs
    # ------------------------------------------------------------------
    alpha_vantage_api_key: str | None = None
    finnhub_api_key: str | None = None

    # ------------------------------------------------------------------
    # News & Sentiment
    # ------------------------------------------------------------------
    news_api_key: str | None = None

    # ------------------------------------------------------------------
    # Forecasting
    # ------------------------------------------------------------------
    forecast_horizon_days: int = 30
    default_time_series_model: str = "prophet"

    # ------------------------------------------------------------------
    # RAG Configuration
    # ------------------------------------------------------------------
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 200
    top_k_documents: int = 5
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ------------------------------------------------------------------
    # SQL Agent
    # ------------------------------------------------------------------
    sql_agent_max_iterations: int = 10
    sql_agent_timeout: int = 60

    # ------------------------------------------------------------------
    # File Uploads
    # ------------------------------------------------------------------
    max_file_size_mb: int = 100
    allowed_file_types: str = "csv,xlsx,xls,json,parquet,pdf"
    upload_dir: str = "storage"

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------
    default_chart_engine: str = "plotly"

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------
    enable_metrics: bool = True
    enable_audit_logs: bool = True

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        """Restrict application mode to known deployment environments."""
        normalized = value.lower()
        if normalized == "testing":
            normalized = "test"
        if normalized not in {"development", "test", "staging", "production"}:
            raise ValueError("ENVIRONMENT must be development, test, staging, or production")
        return normalized

    @model_validator(mode="after")
    def assemble_redis_configuration(self) -> "Settings":
        """Normalize Redis URL with URL-encoded credentials and enforce production authentication."""
        raw_pw: str | None = None
        if self.redis_password and self.redis_password.get_secret_value():
            raw_pw = self.redis_password.get_secret_value()

        parsed = urlsplit(self.redis_url) if self.redis_url else None
        parsed_pw = parsed.password if parsed else None

        if parsed_pw and not raw_pw:
            raw_pw = unquote(parsed_pw)
            self.redis_password = SecretStr(raw_pw)

        if self.environment == "production" and not raw_pw and not parsed_pw:
            raise ValueError(
                "Production environment requires Redis authentication credentials "
                "(REDIS_PASSWORD or authenticated REDIS_URL)"
            )

        if raw_pw and parsed:
            quoted_pw = quote(raw_pw, safe="")
            username = parsed.username or ""
            user_prefix = f"{quote(username, safe='')}:{quoted_pw}@" if username else f":{quoted_pw}@"
            host = parsed.hostname or self.redis_host
            port = f":{parsed.port}" if parsed.port is not None else (f":{self.redis_port}" if self.redis_port else "")
            netloc = f"{user_prefix}{host}{port}"
            path = parsed.path if parsed.path and parsed.path != "/" else f"/{self.redis_db}"
            self.redis_url = urlunsplit((
                parsed.scheme or "redis",
                netloc,
                path,
                parsed.query,
                parsed.fragment,
            ))
        elif not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

        return self

    @property
    def masked_redis_url(self) -> str:
        """Return Redis URL with credentials redacted for safe logging."""
        if not self.redis_url:
            return ""
        parsed = urlsplit(self.redis_url)
        if not parsed.password:
            return self.redis_url
        user_prefix = f"{parsed.username}:****@" if parsed.username else ":****@"
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        return urlunsplit((
            parsed.scheme,
            f"{user_prefix}{host}{port}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        ))

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Return the normalized, deduplicated list of permitted CORS origins."""
        raw_origins: list[str] = []

        if isinstance(self.cors_origins, str):
            if self.cors_origins.strip():
                raw_origins.extend(part.strip() for part in self.cors_origins.split(",") if part.strip())
        elif isinstance(self.cors_origins, (list, tuple, set)):
            raw_origins.extend(str(item).strip() for item in self.cors_origins if str(item).strip())

        if self.frontend_url and self.frontend_url.strip():
            raw_origins.append(self.frontend_url.strip())

        if self.environment in {"development", "test"}:
            raw_origins.extend([
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:80",
                "http://127.0.0.1:80",
            ])

        normalized: list[str] = []
        seen: set[str] = set()

        for origin in raw_origins:
            cleaned = origin.rstrip("/")
            if not cleaned or cleaned == "*" or cleaned.startswith("http://*") or cleaned.startswith("https://*"):
                continue
            if cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)

        return normalized

    @property
    def postgres_dsn(self) -> str:
        """Return the SQLAlchemy-compatible PostgreSQL connection URL."""
        if self.database_url:
            return self.database_url
        password = self.postgres_password.get_secret_value()
        return (
            "postgresql+psycopg://"
            f"{self.postgres_user}:{password}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def allowed_extension_set(self) -> set[str]:
        """Return normalized set of allowed file upload extensions."""
        return {
            f".{ext.strip().lower().lstrip('.')}"
            for ext in self.allowed_file_types.split(",")
            if ext.strip()
        }

    @property
    def upload_path(self) -> Path:
        """Return the resolved upload directory, creating it if needed."""
        path = PROJECT_ROOT / self.upload_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    """Create one immutable settings instance per process."""
    return Settings()
