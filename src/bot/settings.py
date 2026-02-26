from pydantic_settings import BaseSettings, SettingsConfigDict


class BotConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="bot_")

    TOKEN: str = ""
    NAME: str = ""


class WebhookSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="webhook_")

    USE_WEBHOOK: bool = False
    BASE_URL: str = "https://xxx.ngrok-free.app"
    PATH: str = "/webhook"
    SECRET: str = ""
    HOST: str = "localhost"
    PORT: int = 8080

    @property
    def webhook_url(self) -> str:
        return f"{self.BASE_URL}{self.PATH}"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="app_")
    BASE_URL: str = ""


class TranscribeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="transcribe_")

    ENABLE_ON_STARTUP: bool = False
    AUDIO_FILE_PATH: str = "src/bot/audio/privet-druzya.mp3"
    MODEL: str = "medium"
    LANGUAGE: str = "Russian"
    DEVICE: str = "cpu"  # "cpu" или "cuda"
    HF_TOKEN: str = ""  # HuggingFace токен для диаризации (pyannote)
    DIARIZE_BY_DEFAULT: bool = True  # диаризация по умолчанию при транскрибации
    DIARIZE_MIN_SPEAKERS: int = 2
    DIARIZE_MAX_SPEAKERS: int = 5


class SummarySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="summary_")

    BASE_URL: str = "http://localhost:11434/v1"  # Ollama (OpenAI-совместимый API)
    MODEL: str = "llama3.2"  # Ollama: llama3.2, qwen2.5, mistral
    MAX_RETRIES: int = 3  # Количество повторов при ошибке
    REQUEST_TIMEOUT: int = 120  # Таймаут запроса в секундах
    ENABLE_AFTER_TRANSCRIBE: bool = True  # Генерировать summary после транскрибации в боте


class LoggerConfig(BaseSettings):
    LOG_LEVEL: str = "DEBUG"


class Settings(BaseSettings):

    webhook: WebhookSettings = WebhookSettings()
    bot: BotConfig = BotConfig()
    logger_config: LoggerConfig = LoggerConfig()
    app_settings: AppSettings = AppSettings()
    transcribe: TranscribeSettings = TranscribeSettings()
    summary: SummarySettings = SummarySettings()


settings = Settings()
