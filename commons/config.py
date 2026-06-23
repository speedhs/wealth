import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Kalpi Trade Execution Engine"
    
    # Postgres configuration
    DB_HOST: str = "db"
    DB_PORT: int = 5432
    DB_USER: str = "kalpi_user"
    DB_PASSWORD: str = "kalpi_password"
    DB_NAME: str = "kalpi_wealth"
    
    # RabbitMQ configuration
    RABBITMQ_HOST: str = "rabbitmq"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASSWORD: str = "guest"
    
    # Queues
    QUEUE_EXECUTION_REQUESTS: str = "portfolio_execution_requests"
    QUEUE_BROKER_TRADES: str = "broker_trades"
    QUEUE_ORDER_UPDATES: str = "order_updates"
    
    # Mock Broker Configurations
    MOCK_BROKER_LATENCY_MIN_MS: int = 100
    MOCK_BROKER_LATENCY_MAX_MS: int = 500
    MOCK_BROKER_FAILURE_RATE: float = 0.05  # 5% random failure rate for testing
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
