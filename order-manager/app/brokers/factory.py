import logging
from app.brokers.zerodha import ZerodhaAdapter
from app.brokers.fyers import FyersAdapter
from app.brokers.angelone import AngelOneAdapter
from app.brokers.groww import GrowwAdapter
from app.brokers.upstox import UpstoxAdapter
from app.brokers.mock_broker import MockBrokerAdapter

logger = logging.getLogger(__name__)

# Map broker identifiers to their corresponding adapter classes
BROKER_MAP = {
    "zerodha": ZerodhaAdapter,
    "fyers": FyersAdapter,
    "angelone": AngelOneAdapter,
    "groww": GrowwAdapter,
    "upstox": UpstoxAdapter,
    "mock": MockBrokerAdapter
}

def get_broker_adapter(broker_name: str):
    """
    Factory function to get a broker adapter instance.
    
    Args:
        broker_name (str): The name of the broker (case-insensitive).
        
    Returns:
        BrokerAdapter: An instance of the requested broker adapter.
        
    Raises:
        ValueError: If the broker is unsupported.
    """
    normalized_name = broker_name.lower().strip()
    if normalized_name not in BROKER_MAP:
        raise ValueError(
            f"Unsupported broker: '{broker_name}'. "
            f"Supported brokers are: {list(BROKER_MAP.keys())}"
        )
    
    adapter_class = BROKER_MAP[normalized_name]
    logger.debug(f"Instantiated broker adapter for '{normalized_name}' using {adapter_class.__name__}")
    return adapter_class()
