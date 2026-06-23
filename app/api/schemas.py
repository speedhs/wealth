from typing import List, Optional
from pydantic import BaseModel, Field, UUID4

class TradeSchema(BaseModel):
    ticker: str = Field(..., description="Stock symbol (e.g. INFY, RELIANCE, TCS)")
    action: str = Field(..., description="Trade action: 'BUY', 'SELL', or 'REBALANCE'")
    quantity: int = Field(..., description="Quantity of shares. Can be positive or negative for REBALANCE.")

class PortfolioExecuteRequest(BaseModel):
    portfolio_id: UUID4 = Field(..., description="Unique UUID identifier of the portfolio")
    broker: str = Field(..., description="Broker key: 'zerodha', 'fyers', 'angelone', 'groww', 'upstox', or 'mock'")
    action_type: str = Field(..., description="Execution mode: 'FIRST_TIME' or 'REBALANCE'")
    trades: List[TradeSchema] = Field(..., description="List of target trades to perform")

class ExecuteResponse(BaseModel):
    portfolio_execution_id: UUID4 = Field(..., description="ID representing this execution task")
    status: str = Field(..., description="Initial execution state (e.g. PENDING)")
    message: str = Field(..., description="Details of acceptance")

# Schemas for checking status in the UI
class OrderStatusResponse(BaseModel):
    id: UUID4
    ticker: str
    action: str
    quantity: int
    status: str
    error_message: Optional[str] = None
    broker_order_id: Optional[str] = None

class ExecutionStatusResponse(BaseModel):
    id: UUID4
    portfolio_id: UUID4
    status: str
    total_orders: int
    completed_orders: int
    created_at: str
    updated_at: str
    orders: List[OrderStatusResponse]
