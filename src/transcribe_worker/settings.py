from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="worker_")

    DEVICE: str = "cpu"
    HF_TOKEN: str = ""
    MODEL: str = "medium"
    LANGUAGE: str = "Russian"
    DIARIZE_MIN_SPEAKERS: int = 2
    DIARIZE_MAX_SPEAKERS: int = 5


settings = WorkerSettings()
