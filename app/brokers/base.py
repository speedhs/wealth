from abc import ABC, abstractmethod

class BrokerAdapter(ABC):
    """
    Abstract Base Class for Broker Integrations.
    All broker adapters (Zerodha, Fyers, AngelOne, etc.) must implement this interface
    to ensure seamless modular hot-swapping.
    """
    
    @abstractmethod
    def authenticate(self, credentials: dict) -> bool:
        """
        Authenticate with the broker's API.
        
        Args:
            credentials (dict): A dictionary containing credentials (API keys, tokens, passwords).
            
        Returns:
            bool: True if authentication is successful, False otherwise.
        """
        pass

    @abstractmethod
    def place_order(self, ticker: str, action: str, quantity: int) -> dict:
        """
        Place an order to buy or sell a specific ticker.
        
        Args:
            ticker (str): The ticker symbol (e.g. "RELIANCE", "TCS").
            action (str): The order action ("BUY" or "SELL").
            quantity (int): The number of shares.
            
        Returns:
            dict: A dictionary containing:
                - "broker_order_id": The unique order reference from the broker.
                - "status": The order status (e.g. "EXECUTED").
                
        Raises:
            Exception: If order placement fails due to API rejection, balance issues, etc.
        """
        pass
