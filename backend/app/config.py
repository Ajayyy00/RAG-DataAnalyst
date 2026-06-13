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
    app_env: str = Field(default="development", pattern="^(development|staging|production)$")
    app_debug: bool = False
    api_prefix: str = "/api/v1"
    secret_key: str = "supersecretkey-change-in-production"

    # ── PostgreSQL ────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "healthcopilot"
    postgres_user: str = "hc_user"
    postgres_password: str = "changeme"

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
    def is_production(self) -> bool:
        return self.app_env == "production"

    @field_validator("secret_key", "postgres_password", "jwt_secret_key")
    @classmethod
    def check_secure_secrets(cls, v: str, info) -> str:
        # Pydantic v2 requires info.data to access other fields, but we can't reliably read app_env if it hasn't parsed yet.
        # So we just do a basic check here or we could check it inside __init__.
        # Actually a simple check against known weak passwords is fine.
        weak_passwords = ["changeme", "supersecretkey-change-in-production", "jwt-secret-key-change-in-production"]
        if v in weak_passwords and "production" in str(info.data.get("app_env", "")):
            raise ValueError(f"Cannot use default/weak secret for {info.field_name} in production!")
        return v

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
