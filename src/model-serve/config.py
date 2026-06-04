from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MODEL_PATH: str = "/src/model-serve/models/resnet18.pth"
    MODEL_VERSION: str = "1.0.0"
    
    class Config:
        env_file = ".env"

settings = Settings()