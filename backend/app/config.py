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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
