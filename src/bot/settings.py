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


class LoggerConfig(BaseSettings):
    LOG_LEVEL: str = "DEBUG"


class Settings(BaseSettings):

    webhook: WebhookSettings = WebhookSettings()
    bot: BotConfig = BotConfig()
    logger_config: LoggerConfig = LoggerConfig()
    app_settings: AppSettings = AppSettings()
    transcribe: TranscribeSettings = TranscribeSettings()


settings = Settings()
