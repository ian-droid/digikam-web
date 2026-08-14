"""Application configuration loaded from the app's own database / environment."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

from app.paths import default_data_dir


class Settings(BaseSettings):
    # Path to the app's own SQLite database (created by `init`)
    # When frozen, defaults next to the executable under data/
    app_db_path: Path = default_data_dir() / "app.db"

    # Session secret (set during init or via env)
    secret_key: str = "change-me-in-production-please-use-a-long-random-string"

    # Cookie settings
    session_cookie_name: str = "digikam_web_session"
    session_max_age: int = 60 * 60 * 24 * 7  # 7 days

    # Server
    host: str = "0.0.0.0"
    port: int = 8443

    # TLS (must be provided by operator)
    tls_cert: Optional[Path] = None
    tls_key: Optional[Path] = None

    class Config:
        env_prefix = "DIGIKAM_WEB_"
        env_file = ".env"


settings = Settings()
