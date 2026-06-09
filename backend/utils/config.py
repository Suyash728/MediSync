"""
Application settings loaded from environment variables / .env file.
Using pydantic-settings means every variable is type-checked at startup —
a missing required env var raises a clear error rather than a silent None.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Supabase — used server-side to make privileged DB calls with the service key
    supabase_url: str
    supabase_service_key: str          # Service role key — NEVER sent to browser
    supabase_anon_key: str             # Anon key — used to verify user JWTs

    # LLM keys — server-side only
    groq_api_key: str
    gemini_api_key: str = ""           # Optional fallback

    # ABDM (optional for Phase 5)
    abdm_client_id: str = ""
    abdm_client_secret: str = ""
    abdm_base_url: str = "https://sandbox.abdm.gov.in"

    # App config
    environment: str = "development"
    allowed_origins: list[str] = ["http://localhost:3000"]
    jwt_secret: str = ""               # Used to verify Supabase JWTs

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Module-level singleton — import this everywhere instead of re-constructing
settings = Settings()  # type: ignore[call-arg]
