from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://support:support@localhost:5433/support_assistant"
    openai_api_key: str = ""
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    # The transaction-resolve step (deciding which transaction(s) a customer means,
    # including status-aware language like "my last purchase"/"how much did I pay")
    # measurably needs a stronger model than chat_model: gpt-4o-mini confidently picked
    # a PENDING transaction for a "how much did I pay" question, ignoring an explicit
    # instruction that PENDING/FAILED != paid; gpt-5.6-sol got it right on the same
    # prompt. reasoning_effort="none" is required for this model to support tool
    # calls on the Chat Completions API at all - see docs/judgment-model-comparison.md.
    resolve_model: str = "gpt-5.6-sol"
    resolve_reasoning_effort: str | None = "none"
    # Conversation titles are generated from the first user message via a plain,
    # cheap content-generation call - gpt-4o-mini is already priced in pricing.py
    # and is more than capable of a short summarizing title.
    title_model: str = "gpt-4o-mini"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120
    kb_min_similarity: float = 0.30
    cors_origins: str = "http://localhost:3000"
    support_contact_email: str = "support@example.com"
    escalation_decline_threshold: int = 2

    # Redemption order tracking - Redis is a pure cache (no persistence needed,
    # see docker-compose.yml), separate port from a dev machine's own default
    # Redis to avoid local collisions, same reasoning as Postgres's 5433 remap.
    redis_url: str = "redis://localhost:6380/0"
    ongoing_redemptions_cache_ttl_seconds: int = 45
    ongoing_redemptions_negative_cache_ttl_seconds: int = 20
    tracking_cache_ttl_seconds: int = 90
    tracking_stale_cache_ttl_seconds: int = 86400
    tracking_lock_ttl_seconds: int = 8
    internal_tracking_base_url: str = "http://localhost:8000"
    tracking_timeout_seconds: float = 3.0
    tracking_max_retries: int = 2
    tracking_retry_backoff_seconds: float = 0.3
    tracking_circuit_breaker_threshold: int = 3
    tracking_circuit_breaker_cooldown_seconds: float = 30.0
    customer_display_timezone: str = "Asia/Kolkata"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
