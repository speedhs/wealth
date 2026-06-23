import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from app.api import schemas
from app.rms.validator import validate_portfolio_execution, get_current_holdings
from commons.queue import publish_message
from commons.config import settings
from commons.db import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post(
    "/portfolio/execute",
    response_model=schemas.ExecuteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute a portfolio trade or rebalance batch"
)
def execute_portfolio(request: schemas.PortfolioExecuteRequest):
    """
    Submits a list of trades/adjustments for execution.
    1. Validates the request (RMS validation) and checks for active execution to prevent double execution.
    2. Enqueues the execution request onto the RabbitMQ ingest queue.
    3. Returns immediate acceptance with a tracking ID.
    """
    # Convert trades list to standard dictionaries
    trade_dicts = [trade.model_dump() for trade in request.trades]
    
    # Run RMS & Validation checks
    validation = validate_portfolio_execution(
        portfolio_id=str(request.portfolio_id),
        broker=request.broker,
        action_type=request.action_type,
        trades=trade_dicts
    )
    
    if not validation["valid"]:
        logger.warning(f"API: Execution rejected by RMS: {validation['error_message']}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation["error_message"]
        )
        
    if validation["already_matched"]:
        logger.info(f"API: Portfolio '{request.portfolio_id}' is already in desired state. Skipping order placement.")
        execution_id = uuid.uuid4()
        now = datetime.utcnow()
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO portfolio_executions (id, portfolio_id, status, total_orders, completed_orders, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """,
                    (str(execution_id), str(request.portfolio_id), "COMPLETED", 0, 0, now, now)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"API: Failed to save empty execution job: {e}")
        finally:
            conn.close()

        return schemas.ExecuteResponse(
            portfolio_execution_id=execution_id,
            status="COMPLETED",
            message="Portfolio is already in the desired state. No trades executed."
        )
        
    # Generate unique Execution ID
    execution_id = uuid.uuid4()
    
    # Payload to send to Subprocess 1 (Ingest Worker)
    payload = {
        "portfolio_execution_id": str(execution_id),
        "portfolio_id": str(request.portfolio_id),
        "broker": request.broker.lower().strip(),
        "action_type": request.action_type.upper().strip(),
        "trades": validation["parsed_trades"]  # normalized trades
    }
    
    try:
        # Publish message to queue
        publish_message(settings.QUEUE_EXECUTION_REQUESTS, payload)
        logger.info(f"API: Portfolio execution {execution_id} accepted and queued.")
        
        return schemas.ExecuteResponse(
            portfolio_execution_id=execution_id,
            status="PENDING",
            message="Portfolio execution request received and enqueued."
        )
    except Exception as e:
        logger.critical(f"API: Failed to enqueue execution job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to publish execution job. Message broker might be unavailable."
        )

@router.get(
    "/portfolio/execution/{execution_id}",
    response_model=schemas.ExecutionStatusResponse,
    summary="Get status of a specific execution job and its child orders"
)
def get_execution_status(execution_id: str):
    """
    Retrieves the current execution job details and the state of its sub-orders.
    Uses raw SQL with explicit columns.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Query portfolio execution status
            cursor.execute(
                """
                SELECT id, portfolio_id, status, total_orders, completed_orders, created_at, updated_at 
                FROM portfolio_executions 
                WHERE id = %s;
                """,
                (execution_id,)
            )
            job = cursor.fetchone()
            
            if not job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Execution job '{execution_id}' not found."
                )
                
            # Query child orders
            cursor.execute(
                """
                SELECT id, portfolio_execution_id, ticker, action, quantity, status, error_message, broker_order_id, created_at, updated_at 
                FROM orders 
                WHERE portfolio_execution_id = %s;
                """,
                (execution_id,)
            )
            db_orders = cursor.fetchall()
            
            # Format and return response
            orders_response = []
            for o in db_orders:
                orders_response.append(schemas.OrderStatusResponse(
                    id=o["id"],
                    ticker=o["ticker"],
                    action=o["action"],
                    quantity=o["quantity"],
                    status=o["status"],
                    error_message=o["error_message"],
                    broker_order_id=o["broker_order_id"]
                ))
                
            return schemas.ExecutionStatusResponse(
                id=job["id"],
                portfolio_id=job["portfolio_id"],
                status=job["status"],
                total_orders=job["total_orders"],
                completed_orders=job["completed_orders"],
                created_at=job["created_at"].isoformat(),
                updated_at=job["updated_at"].isoformat(),
                orders=orders_response
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error reading execution status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database read failure."
        )
    finally:
        conn.close()

@router.get(
    "/portfolios",
    response_model=list,
    summary="Get all portfolios registered in the system"
)
def get_portfolios():
    """
    Returns lists of all portfolios. Uses raw SQL with explicit columns.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, broker, created_at, updated_at FROM portfolios;")
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"API: Error listing portfolios: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database read failure."
        )
    finally:
        conn.close()
        
@router.get(
    "/portfolio/executions",
    response_model=list,
    summary="Get all historical execution jobs"
)
def get_all_executions():
    """
    Returns list of all executions. Uses raw SQL with explicit columns.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, portfolio_id, status, total_orders, completed_orders, created_at, updated_at 
                FROM portfolio_executions 
                ORDER BY created_at DESC;
                """
            )
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"API: Error listing executions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database read failure."
        )
    finally:
        conn.close()

@router.get(
    "/portfolio/{portfolio_id}/holdings",
    response_model=schemas.HoldingsResponse,
    summary="Get current net holdings for a portfolio"
)
def get_portfolio_holdings(portfolio_id: str):
    """
    Computes current net holdings for a portfolio by aggregating
    all successfully executed orders in the database.
    """
    try:
        # Validate that portfolio_id is a valid UUID
        uuid.UUID(portfolio_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid portfolio ID format. Must be a valid UUID."
        )

    # Check if portfolio exists
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM portfolios WHERE id = %s;", (portfolio_id,))
            portfolio = cursor.fetchone()
            # If portfolio doesn't exist, it means there are no executions, so holdings are empty.
            if not portfolio:
                return {
                    "portfolio_id": portfolio_id,
                    "holdings": {}
                }
    except Exception as e:
        logger.error(f"API: Error checking portfolio {portfolio_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database query failure."
        )
    finally:
        conn.close()

    holdings = get_current_holdings(portfolio_id)
    return {
        "portfolio_id": portfolio_id,
        "holdings": holdings
    }
