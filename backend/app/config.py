from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Academic Lesson Plan System"
    app_version: str = "1.0.0"

    mongodb_uri: str
    database_name: str = "academic_lesson_plan"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    class Config:
        env_file = ".env"


settings = Settings()