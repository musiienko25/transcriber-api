"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Transcriber API"
    app_version: str = "1.0.0"
    debug: bool = False
    dev_mode: bool = Field(default=False, description="Enable dev mode (bypass auth)")
    environment: Literal["development", "staging", "production"] = "development"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    # API Keys (comma-separated list of valid API keys)
    api_keys: str = Field(default="", description="Comma-separated list of valid API keys")

    # Rate Limiting
    rate_limit_requests: int = Field(default=100, description="Requests per window")
    rate_limit_window: int = Field(default=60, description="Window in seconds")

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_job_ttl: int = Field(default=86400, description="Job TTL in seconds (24h)")

    # Whisper Model
    whisper_model: str = Field(default="base", description="Whisper model size")
    whisper_device: str = Field(default="auto", description="Device: auto, cpu, cuda")
    whisper_compute_type: str = Field(default="auto", description="Compute type for faster-whisper")

    # ASR Settings
    asr_sync_max_duration: int = Field(
        default=600, description="Max duration (sec) for sync ASR response"
    )
    asr_provider: Literal["local", "openai", "deepgram", "assemblyai"] = "local"

    # External ASR API Keys (for hosted providers)
    openai_api_key: str | None = None
    deepgram_api_key: str | None = None
    assemblyai_api_key: str | None = None

    # Runpod
    runpod_api_key: str | None = None
    runpod_endpoint_id: str | None = None
    runpod_webhook_secret: str | None = None

    # S3/R2 Storage
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "transcriber-media"
    s3_region: str = "auto"

    # File Upload
    max_upload_size_mb: int = Field(default=500, description="Max upload size in MB")
    allowed_audio_extensions: str = ".mp3,.wav,.m4a,.flac,.ogg,.wma,.aac"
    allowed_video_extensions: str = ".mp4,.mkv,.webm,.avi,.mov,.wmv"

    # Temp Storage
    temp_dir: str = "/tmp/transcriber"

    @field_validator("api_keys")
    @classmethod
    def parse_api_keys(cls, v: str) -> str:
        """Validate API keys format."""
        return v

    def get_api_keys_list(self) -> list[str]:
        """Get API keys as a list."""
        if not self.api_keys:
            return []
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    def get_allowed_extensions(self) -> set[str]:
        """Get all allowed file extensions."""
        audio = set(self.allowed_audio_extensions.split(","))
        video = set(self.allowed_video_extensions.split(","))
        return audio | video


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
