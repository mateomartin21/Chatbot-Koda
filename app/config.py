from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Aplicacion
    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    # Seguridad
    jwt_secret: str
    jwt_expire_days: int = 30
    magic_link_ttl_minutes: int = 15

    # Seleccion de proveedor
    provider_stt: str = "aws"
    provider_llm: str = "aws"
    provider_tts: str = "aws"
    provider_email: str = "aws"

    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    bedrock_model_id: str | None = None
    bedrock_model_id_barato: str | None = None
    bedrock_max_tool_iterations: int = 3

    transcribe_language: str = "es-MX"

    polly_voice_id: str = "Mia"
    polly_engine: str = "generative"
    polly_output_format: str = "mp3"

    ses_from_email: str | None = None
    ses_from_name: str = "Koda"
    ses_configuration_set: str | None = None

    s3_bucket: str | None = None
    s3_signed_url_ttl_seconds: int = 600

    # SMTP (PROVIDER_EMAIL=smtp). El plan B del correo mientras SES siga en sandbox:
    # en sandbox SES solo entrega a direcciones verificadas a mano, y eso deja fuera a
    # cualquiera que no conozcas de antemano. Ver docs/adr/ADR-022.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    # Plan B (solo si PROVIDER_* = fallback)
    groq_api_key: str | None = None
    groq_stt_model: str = "whisper-large-v3-turbo"
    # Verificar contra console.groq.com/docs/models antes de confiar en este default —
    # Groq deprecia modelos con relativa frecuencia.
    groq_llm_model: str = "openai/gpt-oss-120b"
    gemini_api_key: str | None = None
    resend_api_key: str | None = None

    # Base de datos
    database_url: str = "postgresql+asyncpg://koda:koda@localhost:5432/koda"

    # Limites
    max_audio_seconds: int = 60
    max_audio_mb: int = 10
    max_text_chars: int = 2000
    max_images_per_message: int = 3
    max_image_mb: int = 8
    max_video_seconds: int = 10
    max_video_mb: int = 25
    video_keyframes: int = 6
    rate_limit_messages_per_hour: int = 30
    rate_limit_magic_links_per_hour: int = 5
    rate_limit_magic_links_per_hour_ip: int = 20

    # Recordatorios
    reminder_morning_hour: int = 6
    reminder_evening_hour: int = 20
    reminder_weekly_day: int = 6
    reminder_weekly_hour: int = 19
    reminder_inactive_days: int = 30


def get_settings() -> Settings:
    return Settings()
