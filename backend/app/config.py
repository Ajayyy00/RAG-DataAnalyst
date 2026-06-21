"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    app_name: str = "Healthcare Copilot API"
    app_env: str = Field(
        default="development", pattern="^(development|staging|production)$"
    )
    app_debug: bool = False
    api_prefix: str = "/api/v1"
    secret_key: str = "supersecretkey-change-in-production"
    # Comma-separated list of allowed browser origins in non-debug mode, e.g.
    # "https://app.healthcopilot.com,https://admin.healthcopilot.com".
    cors_allowed_origins: str = ""

    # ── PostgreSQL ────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "healthcopilot"
    postgres_user: str = "hc_user"
    postgres_password: str = "changeme"

    # Dedicated least-privilege role used ONLY to execute analyst-generated SQL.
    # Leave blank to fall back to the main credentials (no isolation). In
    # production this MUST point at a role with SELECT-only grants on the
    # clinical tables and no access to `users` / `audit_logs`.
    # Host/port/db default to the primary cluster so only user/password need to
    # be supplied for same-cluster least-privilege roles, but a fully separate
    # read replica can be configured by overriding all five values.
    readonly_postgres_host: Optional[str] = None
    readonly_postgres_port: Optional[int] = None
    readonly_postgres_db: Optional[str] = None
    readonly_postgres_user: Optional[str] = None
    readonly_postgres_password: Optional[str] = None

    # Require a *distinct* read-only role in production (fail closed at startup).
    require_readonly_role: bool = False

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"
    session_ttl_seconds: int = 86400  # 24 hours

    # ── ChromaDB ──────────────────────────────────────────────
    chromadb_host: str = "localhost"
    chromadb_port: int = 8000
    chromadb_collection: str = "healthcare_schema"
    # "http" uses ChromaDB server; "ephemeral" uses in-process client (local dev without Docker)
    chromadb_mode: str = Field(default="http", pattern="^(http|ephemeral|persistent)$")

    # ── LLM ───────────────────────────────────────────────────
    llm_base_url: str = "http://localhost:8080/v1"
    llm_model: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    llm_api_key: str = "not-needed-for-local"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.1
    llm_timeout_seconds: int = 60

    # ── JWT ───────────────────────────────────────────────────
    jwt_secret_key: str = "jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # ── Auth cookies (HttpOnly, browser auth) ─────────────────
    cookie_access_name: str = "access_token"
    cookie_refresh_name: str = "refresh_token"
    # If None, Secure is enabled automatically in production (see cookie_secure_effective).
    cookie_secure: Optional[bool] = None
    cookie_samesite: str = Field(default="lax", pattern="^(lax|strict|none)$")
    cookie_domain: Optional[str] = None

    # ── PHI encryption at rest (Fernet) ───────────────────────
    # urlsafe base64 32-byte key(s). The FIRST key encrypts; all are tried for
    # decryption to support zero-downtime key rotation. Generate with:
    #   python -m app.scripts.generate_encryption_key
    phi_encryption_keys: Optional[str] = None

    # ── Query Execution ───────────────────────────────────────
    query_timeout_seconds: int = 30
    max_rows: int = 10000

    # ── Logging ───────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Embeddings / RAG ─────────────────────────────────────
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_top_k: int = 5

    # ── Kafka ────────────────────────────────────────────────────
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_events_topic: str = "clinical_events"

    # ── Neo4j Knowledge Graph ────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "changeme"
    kg_sync_interval_minutes: int = 60

    # ── Computed Properties ──────────────────────────────────
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def has_dedicated_readonly_role(self) -> bool:
        """True when a separate read-only DB user is configured."""
        return bool(
            self.readonly_postgres_user
            and self.readonly_postgres_user != self.postgres_user
        )

    @property
    def readonly_database_url(self) -> str:
        """Async URL for the read-only executor role.

        Each component independently falls back to the primary cluster so a
        same-cluster least-privilege role only needs USER/PASSWORD, while a
        fully separate replica can override host/port/db too. When nothing is
        configured this falls back to the main credentials (no isolation) — the
        startup validator warns/fails depending on `require_readonly_role`.
        """
        host = self.readonly_postgres_host or self.postgres_host
        port = self.readonly_postgres_port or self.postgres_port
        db = self.readonly_postgres_db or self.postgres_db
        user = self.readonly_postgres_user or self.postgres_user
        password = self.readonly_postgres_password or self.postgres_password
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parsed list of allowed CORS origins (empty in debug → regex localhost)."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def cookie_secure_effective(self) -> bool:
        """Secure cookies: explicit override, else on in production."""
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production

    @field_validator("secret_key", "postgres_password", "jwt_secret_key")
    @classmethod
    def check_secure_secrets(cls, v: str, info) -> str:
        # Pydantic v2 requires info.data to access other fields, but we can't reliably read app_env if it hasn't parsed yet.
        # So we just do a basic check here or we could check it inside __init__.
        # Actually a simple check against known weak passwords is fine.
        weak_passwords = [
            "changeme",
            "supersecretkey-change-in-production",
            "jwt-secret-key-change-in-production",
        ]
        if v in weak_passwords and "production" in str(info.data.get("app_env", "")):
            raise ValueError(
                f"Cannot use default/weak secret for {info.field_name} in production!"
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
