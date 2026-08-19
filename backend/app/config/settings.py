from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str
    APP_VERSION: str

    MONGODB_URI: str
    DATABASE_NAME: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    GROQ_API_KEY: str
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # --- CORS ---
    # Comma-separated list of allowed frontend origins. Defaults to the
    # local Next.js dev server. Override in production via the environment
    # (e.g. FRONTEND_ORIGINS="https://app.example.com").
    FRONTEND_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Uploads ---
    # Maximum accepted upload size in megabytes (development default: 10 MB).
    MAX_UPLOAD_SIZE_MB: int = 10

    # --- OCR (scanned PDF handling) ---
    # Minimum count of alphanumeric characters for a PDF's native text layer
    # to be considered "meaningful". Below this, the PDF is treated as scanned
    # and routed through OCR. All OCR settings have safe defaults and are
    # optional in the environment.
    OCR_MIN_MEANINGFUL_CHARS: int = 20

    # Rasterisation zoom used when rendering scanned PDF pages to images for
    # OCR. 2.0 (~144 DPI) balances recognition quality against memory/CPU.
    OCR_RENDER_ZOOM: float = 2.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    @property
    def frontend_origins_list(self) -> list[str]:
        """Parse FRONTEND_ORIGINS into a clean list of explicit origins."""
        return [
            origin.strip()
            for origin in self.FRONTEND_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def max_upload_size_bytes(self) -> int:
        """Maximum accepted upload size expressed in bytes."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


settings = Settings()