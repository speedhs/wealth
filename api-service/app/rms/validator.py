import logging
import re
from datetime import datetime
from commons.db import get_db_connection

logger = logging.getLogger(__name__)

# Tickers that are restricted from trading
RESTRICTED_TICKERS = {"RESTR", "BLOCK", "SUSPENDED"}

# Maximum single order quantity
MAX_ORDER_QTY = 100000


def get_current_holdings(portfolio_id: str) -> dict:
    """
    Computes current net holdings for a portfolio by aggregating
    all successfully executed orders in the database.

    Returns:
        dict: Mapping of ticker -> net quantity held.
    """
    holdings = {}
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT o.ticker, o.action, o.quantity
                FROM orders o
                JOIN portfolio_executions pe ON o.portfolio_execution_id = pe.id
                WHERE pe.portfolio_id = %s AND o.status = 'EXECUTED';
                """,
                (portfolio_id,),
            )
            for row in cursor.fetchall():
                ticker = row["ticker"].upper()
                qty = row["quantity"]
                if row["action"] == "BUY":
                    holdings[ticker] = holdings.get(ticker, 0) + qty
                elif row["action"] == "SELL":
                    holdings[ticker] = holdings.get(ticker, 0) - qty

            # Drop tickers with zero or negative net holdings
            holdings = {t: q for t, q in holdings.items() if q > 0}
    except Exception as e:
        logger.error(f"RMS: Error computing holdings for {portfolio_id}: {e}")
    finally:
        conn.close()
    return holdings


def _validate_ticker(ticker: str, index: int) -> dict | None:
    """Returns an error dict if the ticker is invalid, else None."""
    if not ticker:
        return _err(f"Trade at index {index} has an empty ticker.")
    if ticker in RESTRICTED_TICKERS:
        return _err(f"Ticker '{ticker}' is in the restricted list.")
    if not re.match(r"^[A-Z0-9\-\.&]+$", ticker):
        return _err(f"Ticker '{ticker}' contains invalid characters.")
    return None


def _err(msg: str) -> dict:
    return {"valid": False, "error_message": msg, "parsed_trades": [], "already_matched": False}


def validate_portfolio_execution(
    portfolio_id: str, broker: str, action_type: str, trades: list
) -> dict:
    """
    Validates a portfolio execution request.

    FIRST_TIME mode:
        Treats each trade as a desired end-state (ticker + target qty).
        Computes delta against current holdings. Only the difference is traded.
        Stocks held but not in target are fully exited.
        If holdings already match, returns already_matched=True.

    REBALANCE mode:
        Each trade specifies its own action:
          - BUY: direct purchase of specified quantity
          - SELL: direct sale of specified quantity
          - REBALANCE: quantity is the TARGET holding; system computes
            the delta vs current holdings and generates BUY/SELL accordingly.
            If already at target, the stock is skipped (HOLD).

    Returns dict with keys: valid, error_message, parsed_trades, already_matched.
    """
    if not trades:
        return _err("Trades list cannot be empty.")

    # --- Database-level checks ---
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Check / auto-create portfolio
            cursor.execute(
                "SELECT id, name, broker, created_at, updated_at FROM portfolios WHERE id = %s;",
                (portfolio_id,),
            )
            portfolio = cursor.fetchone()

            if not portfolio:
                logger.info(f"RMS: Portfolio '{portfolio_id}' not found. Auto-creating.")
                now = datetime.utcnow()
                cursor.execute(
                    """
                    INSERT INTO portfolios (id, name, broker, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (portfolio_id, f"Portfolio {portfolio_id[:8]}", broker, now, now),
                )
                conn.commit()
            else:
                if portfolio["broker"].lower() != broker.lower():
                    return _err(
                        f"Broker mismatch: portfolio registered with '{portfolio['broker']}', "
                        f"request specifies '{broker}'."
                    )

            # 2. Prevent double execution
            cursor.execute(
                """
                SELECT id, status
                FROM portfolio_executions
                WHERE portfolio_id = %s AND status IN ('PENDING', 'PROCESSING');
                """,
                (portfolio_id,),
            )
            active = cursor.fetchone()
            if active:
                return _err(
                    f"Double execution prevented: active job '{active['id']}' "
                    f"in status '{active['status']}'."
                )

    except Exception as e:
        logger.error(f"RMS: Database validation error: {e}")
        return _err(f"Database validation error: {e}")
    finally:
        conn.close()

    # --- Field-level validation ---
    validated = []
    for idx, trade in enumerate(trades):
        ticker = trade.get("ticker", "").strip().upper()
        err = _validate_ticker(ticker, idx)
        if err:
            return err

        raw_qty = trade.get("quantity")
        if raw_qty is None:
            return _err(f"Trade for '{ticker}' is missing quantity.")
        try:
            qty = int(raw_qty)
        except (ValueError, TypeError):
            return _err(f"Quantity for '{ticker}' must be an integer.")

        action = trade.get("action")
        if action:
            action = action.strip().upper()

        validated.append({"ticker": ticker, "quantity": qty, "action": action})

    # --- Fetch current holdings (needed by both modes) ---
    current_holdings = get_current_holdings(portfolio_id)
    logger.info(f"RMS: Current holdings for {portfolio_id}: {current_holdings}")

    # --- Mode-specific resolution ---
    parsed_trades = []
    mode = action_type.strip().upper()

    if mode == "FIRST_TIME":
        # Build desired target state from all trades
        target_state = {}
        for t in validated:
            if t["quantity"] < 0:
                return _err(f"Target quantity for '{t['ticker']}' cannot be negative in FIRST_TIME mode.")
            target_state[t["ticker"]] = t["quantity"]

        logger.info(f"RMS: Target state: {target_state}")

        # Stocks in target: compute delta
        for ticker, target_qty in target_state.items():
            current_qty = current_holdings.get(ticker, 0)
            delta = target_qty - current_qty
            if delta > 0:
                parsed_trades.append({"ticker": ticker, "action": "BUY", "quantity": delta})
            elif delta < 0:
                parsed_trades.append({"ticker": ticker, "action": "SELL", "quantity": abs(delta)})
            # delta == 0 → HOLD, skip

        # Stocks held but NOT in target: exit fully
        for ticker, current_qty in current_holdings.items():
            if ticker not in target_state:
                parsed_trades.append({"ticker": ticker, "action": "SELL", "quantity": current_qty})

    elif mode == "REBALANCE":
        # Per-trade action handling
        for t in validated:
            ticker = t["ticker"]
            qty = t["quantity"]
            action = t.get("action") or "REBALANCE"

            if action == "BUY":
                # Direct buy: quantity = shares to purchase
                if qty <= 0:
                    return _err(f"BUY quantity for '{ticker}' must be positive.")
                parsed_trades.append({"ticker": ticker, "action": "BUY", "quantity": qty})

            elif action == "SELL":
                # Direct sell: quantity = shares to exit
                if qty <= 0:
                    return _err(f"SELL quantity for '{ticker}' must be positive.")
                current = current_holdings.get(ticker, 0)
                if current < qty:
                    return _err(
                        f"Cannot sell {qty} shares of '{ticker}'. "
                        f"Current holding is only {current}."
                    )
                parsed_trades.append({"ticker": ticker, "action": "SELL", "quantity": qty})

            elif action == "REBALANCE":
                # Target-based: quantity = desired total holding
                if qty < 0:
                    return _err(f"REBALANCE target for '{ticker}' cannot be negative.")
                current = current_holdings.get(ticker, 0)
                delta = qty - current
                if delta > 0:
                    parsed_trades.append({"ticker": ticker, "action": "BUY", "quantity": delta})
                elif delta < 0:
                    parsed_trades.append({"ticker": ticker, "action": "SELL", "quantity": abs(delta)})
                else:
                    logger.info(f"RMS: '{ticker}' already at target ({qty}). HOLD — no action needed.")
            else:
                return _err(
                    f"Invalid action '{action}' for '{ticker}'. "
                    f"Must be BUY, SELL, or REBALANCE."
                )
    else:
        return _err(f"Invalid action_type '{action_type}'. Must be 'FIRST_TIME' or 'REBALANCE'.")

    # --- Final safety limits ---
    for pt in parsed_trades:
        if pt["quantity"] > MAX_ORDER_QTY:
            return _err(
                f"RMS limit: resolved quantity for {pt['ticker']} ({pt['quantity']}) "
                f"exceeds max single order size ({MAX_ORDER_QTY:,})."
            )

    # --- Portfolio already at target ---
    if not parsed_trades:
        logger.info(f"RMS: Portfolio '{portfolio_id}' already matches desired state. No trades needed.")
        return {
            "valid": True,
            "error_message": None,
            "parsed_trades": [],
            "already_matched": True,
        }

    logger.info(f"RMS: Resolved {len(parsed_trades)} trades: {parsed_trades}")
    return {"valid": True, "error_message": None, "parsed_trades": parsed_trades, "already_matched": False}
