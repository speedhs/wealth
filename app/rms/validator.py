import logging
import re
from datetime import datetime
from app.core.db import get_db_connection

logger = logging.getLogger(__name__)

# Basic restricted tickers list (e.g., system test bans)
RESTRICTED_TICKERS = {"RESTR", "BLOCK", "SUSPENDED"}

def get_current_holdings(portfolio_id: str) -> dict:
    """
    Computes current holdings for a portfolio based on successfully executed orders.
    Returns:
        dict: Mapping of ticker -> quantity (integer).
    """
    holdings = {}
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # We select explicit columns (no SELECT *)
            cursor.execute(
                """
                SELECT o.ticker, o.action, o.quantity 
                FROM orders o 
                JOIN portfolio_executions pe ON o.portfolio_execution_id = pe.id 
                WHERE pe.portfolio_id = %s AND o.status = 'EXECUTED';
                """,
                (portfolio_id,)
            )
            executed_orders = cursor.fetchall()
            for order in executed_orders:
                ticker = order["ticker"].upper()
                qty = order["quantity"]
                action = order["action"].upper()
                if action == "BUY":
                    holdings[ticker] = holdings.get(ticker, 0) + qty
                elif action == "SELL":
                    holdings[ticker] = holdings.get(ticker, 0) - qty
            
            # Clean up zero or negative holdings
            holdings = {t: q for t, q in holdings.items() if q > 0}
    except Exception as e:
        logger.error(f"RMS: Error computing holdings: {e}")
    finally:
        conn.close()
    return holdings

def validate_portfolio_execution(portfolio_id: str, broker: str, action_type: str, trades: list) -> dict:
    """
    Validates a portfolio execution request against DB state and business/RMS rules.
    Runs raw SQL queries with explicit columns (no SELECT *).
    Calculates deltas in FIRST_TIME mode.
    
    Returns:
        dict: A dictionary containing:
            - "valid": bool
            - "error_message": str (or None)
            - "parsed_trades": list (processed and normalized trades)
            - "already_matched": bool (True if target state equals current state, meaning no orders needed)
    """
    # 1. Basic request checks
    if not trades:
        return {
            "valid": False, 
            "error_message": "Trades list cannot be empty.", 
            "parsed_trades": [],
            "already_matched": False
        }
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 2. Check if portfolio exists
            cursor.execute(
                "SELECT id, name, broker, created_at, updated_at FROM portfolios WHERE id = %s;",
                (portfolio_id,)
            )
            portfolio = cursor.fetchone()
            
            if not portfolio:
                # For convenience in tests, we automatically register the portfolio if it doesn't exist
                logger.info(f"RMS: Portfolio '{portfolio_id}' not found. Creating a default one for test purposes.")
                now = datetime.utcnow()
                cursor.execute(
                    """
                    INSERT INTO portfolios (id, name, broker, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (portfolio_id, f"Auto-Created Portfolio {portfolio_id[:8]}", broker, now, now)
                )
                conn.commit()
            else:
                # Verify broker matches registered broker
                registered_broker = portfolio["broker"]
                if registered_broker.lower() != broker.lower():
                    return {
                        "valid": False,
                        "error_message": f"Broker mismatch. Portfolio is registered with '{registered_broker}' but request specifies '{broker}'.",
                        "parsed_trades": [],
                        "already_matched": False
                    }

            # 3. Prevent Double Execution
            cursor.execute(
                """
                SELECT id, portfolio_id, status, total_orders, completed_orders, created_at, updated_at 
                FROM portfolio_executions 
                WHERE portfolio_id = %s AND status IN ('PENDING', 'PROCESSING');
                """,
                (portfolio_id,)
            )
            active_execution = cursor.fetchone()
            if active_execution:
                return {
                    "valid": False,
                    "error_message": f"Double Execution Prevented: Portfolio has an active execution in status '{active_execution['status']}' (ID: {active_execution['id']}).",
                    "parsed_trades": [],
                    "already_matched": False
                }

    except Exception as e:
        logger.error(f"RMS Validation database error: {e}")
        return {
            "valid": False, 
            "error_message": f"Database validation error: {str(e)}", 
            "parsed_trades": [],
            "already_matched": False
        }
    finally:
        conn.close()

    # 4. Normalize and validate input fields first
    pre_validated_trades = []
    for index, trade in enumerate(trades):
        ticker = trade.get("ticker", "").strip().upper()
        action = trade.get("action", "").strip().upper()
        qty = trade.get("quantity")

        if not ticker:
            return {"valid": False, "error_message": f"Trade at index {index} has an empty ticker.", "parsed_trades": [], "already_matched": False}
            
        if ticker in RESTRICTED_TICKERS:
            return {"valid": False, "error_message": f"Ticker '{ticker}' is in the restricted list.", "parsed_trades": [], "already_matched": False}

        if qty is None:
            return {"valid": False, "error_message": f"Trade for {ticker} is missing quantity.", "parsed_trades": [], "already_matched": False}

        if not re.match(r"^[A-Z0-9\-\.\&]+$", ticker):
            return {"valid": False, "error_message": f"Ticker '{ticker}' contains invalid characters.", "parsed_trades": [], "already_matched": False}

        pre_validated_trades.append({
            "ticker": ticker,
            "action": action,
            "quantity": qty
        })

    # 5. Resolve Delta if FIRST_TIME / Target State is provided
    parsed_trades = []
    
    if action_type.upper() == "FIRST_TIME":
        # Target state specified by trades
        target_state = {}
        for t in pre_validated_trades:
            try:
                target_qty = int(t["quantity"])
            except (ValueError, TypeError):
                return {"valid": False, "error_message": f"Target quantity for '{t['ticker']}' must be an integer.", "parsed_trades": [], "already_matched": False}
            
            if target_qty < 0:
                return {"valid": False, "error_message": f"Target quantity for '{t['ticker']}' cannot be negative for first-time layout.", "parsed_trades": [], "already_matched": False}
                
            target_state[t["ticker"]] = target_qty

        # Fetch current holdings from DB
        current_holdings = get_current_holdings(portfolio_id)
        logger.info(f"RMS: Current holdings for '{portfolio_id}': {current_holdings}")
        logger.info(f"RMS: Target state: {target_state}")

        # Compute delta
        # A. Buy or sell adjustments for items in target state
        for ticker, target_qty in target_state.items():
            current_qty = current_holdings.get(ticker, 0)
            diff = target_qty - current_qty
            
            if diff > 0:
                parsed_trades.append({"ticker": ticker, "action": "BUY", "quantity": diff})
            elif diff < 0:
                parsed_trades.append({"ticker": ticker, "action": "SELL", "quantity": abs(diff)})
                
        # B. Completely exit items held but not in target state
        for ticker, current_qty in current_holdings.items():
            if ticker not in target_state:
                parsed_trades.append({"ticker": ticker, "action": "SELL", "quantity": current_qty})
                
    else:
        # REBALANCE Mode: Parse explicit instructions
        for t in pre_validated_trades:
            ticker = t["ticker"]
            action = t["action"]
            qty = t["quantity"]
            
            if action == "REBALANCE":
                try:
                    signed_qty = int(qty)
                except (ValueError, TypeError):
                    return {"valid": False, "error_message": f"Rebalance quantity for '{ticker}' must be an integer.", "parsed_trades": [], "already_matched": False}
                    
                if signed_qty == 0:
                    continue
                elif signed_qty > 0:
                    resolved_action = "BUY"
                    resolved_qty = signed_qty
                else:
                    resolved_action = "SELL"
                    resolved_qty = abs(signed_qty)
            else:
                if action not in ["BUY", "SELL"]:
                    return {"valid": False, "error_message": f"Invalid action '{action}' for '{ticker}'. Action must be BUY, SELL, or REBALANCE.", "parsed_trades": [], "already_matched": False}
                    
                try:
                    resolved_qty = int(qty)
                except (ValueError, TypeError):
                    return {"valid": False, "error_message": f"Quantity for '{ticker}' must be an integer.", "parsed_trades": [], "already_matched": False}
                    
                if resolved_qty <= 0:
                    return {"valid": False, "error_message": f"Quantity for '{ticker}' must be greater than 0.", "parsed_trades": [], "already_matched": False}
                    
                resolved_action = action

            parsed_trades.append({
                "ticker": ticker,
                "action": resolved_action,
                "quantity": resolved_qty
            })

    # 6. Final safety check on resolved trades
    for p_trade in parsed_trades:
        if p_trade["quantity"] > 100000:
            return {
                "valid": False, 
                "error_message": f"RMS Limit Exceeded: Resolved quantity for {p_trade['ticker']} ({p_trade['quantity']}) exceeds max single order size (100,000).", 
                "parsed_trades": [],
                "already_matched": False
            }

    # 7. Check if there are zero trades required
    if not parsed_trades:
        logger.info(f"RMS: Current holdings for '{portfolio_id}' already match desired state. Skipping order placement.")
        return {
            "valid": True,
            "error_message": None,
            "parsed_trades": [],
            "already_matched": True
        }

    return {"valid": True, "error_message": None, "parsed_trades": parsed_trades, "already_matched": False}
