import time
import random
import uuid
import logging
from app.brokers.base import BrokerAdapter
from commons.config import settings

logger = logging.getLogger(__name__)

class MockBrokerAdapter(BrokerAdapter):
    """
    Simulated Broker Adapter for testing.
    Mocks network latency, API rate limits, and random order rejections.
    """
    
    def __init__(self):
        self.latency_min = settings.MOCK_BROKER_LATENCY_MIN_MS
        self.latency_max = settings.MOCK_BROKER_LATENCY_MAX_MS
        self.failure_rate = settings.MOCK_BROKER_FAILURE_RATE

    def authenticate(self, credentials: dict) -> bool:
        """Simulates authentication with broker."""
        logger.info("MockBroker: Authenticating with credentials...")
        # Simulate network roundtrip
        time.sleep(random.randint(self.latency_min, self.latency_max) / 1000.0)
        return True

    def place_order(self, ticker: str, action: str, quantity: int) -> dict:
        """Simulates order execution with random latency and failure rates."""
        logger.info(f"MockBroker: Placing {action} order for {quantity} shares of {ticker}...")
        
        # 1. Simulate network latency
        sleep_time = random.randint(self.latency_min, self.latency_max) / 1000.0
        time.sleep(sleep_time)
        
        # 2. Input validation
        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}. Must be greater than 0.")
            
        if action not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid action: {action}. Must be BUY or SELL.")
            
        # 3. Simulate failure conditions
        if ticker.upper() == "FAIL":
            raise Exception("Broker API simulation error: Stock is not liquid or suspended.")
            
        if random.random() < self.failure_rate:
            raise Exception("Broker API simulation error: Internal Gateway Error (502).")
            
        # 4. Generate mock success response
        broker_order_id = f"mock_ord_{uuid.uuid4().hex[:12]}"
        logger.info(f"MockBroker: Order {broker_order_id} placed successfully for {ticker}.")
        
        return {
            "broker_order_id": broker_order_id,
            "status": "EXECUTED"
        }
