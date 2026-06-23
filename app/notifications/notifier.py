import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Configure a dedicated logger for notifications to make it stand out
notification_logger = logging.getLogger("kalpi.notifications")

def trigger_execution_notification(execution_id: str, portfolio_id: str, total_orders: int, orders: list):
    """
    Triggers a notification summarizing the executed trades and any failed orders.
    As per specifications, this prints a clear summary block to the log files/console.
    
    Args:
        execution_id (str): The ID of the portfolio execution job.
        portfolio_id (str): The ID of the portfolio.
        total_orders (int): The count of total orders.
        orders (list): List of order dictionaries containing ticker, action, quantity, status, error_message.
    """
    executed_trades = []
    failed_trades = []
    
    for order in orders:
        summary_str = f"{order['action']} {order['quantity']} shares of {order['ticker']}"
        if order["status"] == "EXECUTED":
            executed_trades.append(f"✓ {summary_str} (ID: {order['broker_order_id']})")
        else:
            err = order.get("error_message") or "Unknown error"
            failed_trades.append(f"✗ {summary_str} - Reason: {err}")
            
    status_emoji = "✅ SUCCESS" if len(failed_trades) == 0 else "⚠️ COMPLETED WITH ERRORS"
    if len(failed_trades) == total_orders:
        status_emoji = "❌ FAILED"
        
    border = "=" * 80
    notification_msg = (
        f"\n{border}\n"
        f"🚨 PORTFOLIO TRADE EXECUTION REPORT 🚨\n"
        f"Execution Job ID : {execution_id}\n"
        f"Portfolio ID     : {portfolio_id}\n"
        f"Time Completed   : {datetime.utcnow().isoformat()} UTC\n"
        f"Status           : {status_emoji}\n"
        f"Summary          : {len(executed_trades)}/{total_orders} Orders Executed Successfully\n"
        f"{border}\n"
    )
    
    if executed_trades:
        notification_msg += "SUCCESSFUL TRADES:\n" + "\n".join(executed_trades) + "\n"
        
    if failed_trades:
        if executed_trades:
            notification_msg += "\n"
        notification_msg += "FAILED/REJECTED TRADES:\n" + "\n".join(failed_trades) + "\n"
        
    notification_msg += border
    
    # Print the report clearly
    notification_logger.info(notification_msg)
    # Output to stdout standard logger as well
    logger.info(f"Notification triggered for portfolio execution {execution_id}. Status: {status_emoji}.")
