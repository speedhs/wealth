from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

class TradeSchema(BaseModel):
    ticker: str = Field(..., description="Stock symbol (e.g. INFY, RELIANCE, TCS)")
    quantity: int = Field(..., description="Target quantity (FIRST_TIME) or signed adjustment (REBALANCE). Positive = buy, negative = sell.")
    action: Optional[str] = Field(None, description="Optional. Resolved automatically by the engine based on execution mode.")

class PortfolioExecuteRequest(BaseModel):
    portfolio_id: UUID = Field(..., description="Unique UUID identifier of the portfolio")
    broker: str = Field(..., description="Broker key: 'zerodha', 'fyers', 'angelone', 'groww', 'upstox', or 'mock'")
    action_type: str = Field(..., description="Execution mode: 'FIRST_TIME' or 'REBALANCE'")
    trades: List[TradeSchema] = Field(..., description="List of target trades to perform")

class ExecuteResponse(BaseModel):
    portfolio_execution_id: UUID = Field(..., description="ID representing this execution task")
    status: str = Field(..., description="Initial execution state (e.g. PENDING)")
    message: str = Field(..., description="Details of acceptance")

# Schemas for checking status in the UI
class OrderStatusResponse(BaseModel):
    id: UUID
    ticker: str
    action: str
    quantity: int
    status: str
    error_message: Optional[str] = None
    broker_order_id: Optional[str] = None

class ExecutionStatusResponse(BaseModel):
    id: UUID
    portfolio_id: UUID
    status: str
    total_orders: int
    completed_orders: int
    created_at: str
    updated_at: str
    orders: List[OrderStatusResponse]
