import os
import sys
import json
import time
import signal
import logging
import multiprocessing
from datetime import datetime
from commons.config import settings
from commons.db import get_db_connection, wait_for_db
from commons.queue import get_rabbitmq_connection, publish_message
from app.brokers.factory import get_broker_adapter
from app.notifications.notifier import trigger_execution_notification

# Configure logging for workers
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(processName)s): %(message)s"
)
logger = logging.getLogger("order_manager")

# Set multiprocessing start method to 'spawn' for cross-platform consistency
if sys.platform != 'win32':
    try:
        multiprocessing.set_start_method('spawn')
    except RuntimeError:
        pass


def run_execution_ingest_worker():
    """
    Subprocess 1: Ingest Worker
    - Consumes from 'portfolio_execution_requests'
    - Creates database records for the execution job and individual orders (raw SQL)
    - Publishes individual orders to the 'broker_trades' queue
    """
    logger.info("Starting Ingest Worker subprocess...")
    
    # Establish local process connections
    try:
        db_conn = get_db_connection()
        mq_conn = get_rabbitmq_connection()
    except Exception as e:
        logger.critical(f"Ingest Worker failed to connect to resources: {e}")
        time.sleep(5)
        sys.exit(1)

    channel = mq_conn.channel()
    
    # Declare queues to ensure durability
    channel.queue_declare(queue=settings.QUEUE_EXECUTION_REQUESTS, durable=True)
    channel.queue_declare(queue=settings.QUEUE_BROKER_TRADES, durable=True)
    
    def callback(ch, method, properties, body):
        try:
            payload = json.loads(body)
            exec_id = payload["portfolio_execution_id"]
            portfolio_id = payload["portfolio_id"]
            broker = payload["broker"]
            trades = payload["trades"]
            
            logger.info(f"Received portfolio execution request {exec_id} with {len(trades)} trades.")
            
            now = datetime.utcnow()
            
            # Start Database transaction using raw SQL
            with db_conn.cursor() as cursor:
                # 1. Insert portfolio_executions record
                cursor.execute(
                    """
                    INSERT INTO portfolio_executions (id, portfolio_id, status, total_orders, completed_orders, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """,
                    (exec_id, portfolio_id, "PROCESSING", len(trades), 0, now, now)
                )
                
                # 2. Insert order records and prepare MQ messages
                broker_messages = []
                for trade in trades:
                    order_id = str(uuid_generator())
                    cursor.execute(
                        """
                        INSERT INTO orders (id, portfolio_execution_id, ticker, action, quantity, status, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (order_id, exec_id, trade["ticker"], trade["action"], trade["quantity"], "PENDING", now, now)
                    )
                    
                    broker_messages.append({
                        "order_id": order_id,
                        "portfolio_execution_id": exec_id,
                        "broker": broker,
                        "ticker": trade["ticker"],
                        "action": trade["action"],
                        "quantity": trade["quantity"]
                    })
                
                db_conn.commit()
                logger.info(f"Saved job {exec_id} and {len(trades)} orders to DB.")
                
            # 3. Publish to broker_trades queue (outside of DB transaction lock)
            for msg in broker_messages:
                publish_message(settings.QUEUE_BROKER_TRADES, msg)
                logger.debug(f"Pushed order {msg['order_id']} for {msg['ticker']} to broker trades.")
                
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as err:
            logger.error(f"Error processing execution request: {err}")
            db_conn.rollback()
            # Re-enqueue on DB lock or resource failure, or ack to prevent poison pills
            # For assignment stability, we acknowledge to avoid infinite loops, but log error
            ch.basic_ack(delivery_tag=method.delivery_tag)

    # Set prefetch count to distribute load fairly
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=settings.QUEUE_EXECUTION_REQUESTS, on_message_callback=callback)
    
    logger.info("Ingest Worker waiting for requests...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        db_conn.close()
        mq_conn.close()


def run_broker_worker():
    """
    Subprocess 2: Broker Interaction Layer Worker
    - Consumes from 'broker_trades'
    - Executes order using corresponding BrokerAdapter
    - Publishes execution status updates to 'order_updates' queue
    """
    logger.info("Starting Broker Worker subprocess...")
    
    try:
        mq_conn = get_rabbitmq_connection()
    except Exception as e:
        logger.critical(f"Broker Worker failed to connect to RabbitMQ: {e}")
        time.sleep(5)
        sys.exit(1)

    channel = mq_conn.channel()
    channel.queue_declare(queue=settings.QUEUE_BROKER_TRADES, durable=True)
    channel.queue_declare(queue=settings.QUEUE_ORDER_UPDATES, durable=True)
    
    def callback(ch, method, properties, body):
        try:
            payload = json.loads(body)
            order_id = payload["order_id"]
            exec_id = payload["portfolio_execution_id"]
            broker_name = payload["broker"]
            ticker = payload["ticker"]
            action = payload["action"]
            qty = payload["quantity"]
            
            logger.info(f"Processing trade order {order_id} ({action} {qty} {ticker}) with {broker_name}...")
            
            # Fetch adapter
            adapter = get_broker_adapter(broker_name)
            
            # In production, fetch specific broker credentials from DB/Secret store.
            # Here we pass a mock dict.
            credentials = {"api_key": "mock_api_key", "access_token": "mock_access_token"}
            adapter.authenticate(credentials)
            
            # Execute trade
            result = adapter.place_order(ticker, action, qty)
            
            # Formulate update payload
            update_payload = {
                "order_id": order_id,
                "portfolio_execution_id": exec_id,
                "status": "EXECUTED",
                "broker_order_id": result["broker_order_id"],
                "error_message": None
            }
            logger.info(f"Order {order_id} successfully executed. Broker ID: {result['broker_order_id']}")
            
        except Exception as err:
            logger.error(f"Order {order_id} execution failed: {err}")
            update_payload = {
                "order_id": order_id,
                "portfolio_execution_id": exec_id,
                "status": "FAILED",
                "broker_order_id": None,
                "error_message": str(err)
            }
            
        try:
            # Publish result to updates queue
            publish_message(settings.QUEUE_ORDER_UPDATES, update_payload)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as mq_err:
            logger.error(f"Failed to publish order status update: {mq_err}")
            # Re-enqueue message on broker failure
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=settings.QUEUE_BROKER_TRADES, on_message_callback=callback)
    
    logger.info("Broker Worker waiting for trades...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        mq_conn.close()


def run_db_consumer_worker():
    """
    Subprocess 3: DB & Notification Worker
    - Consumes from 'order_updates'
    - Updates order status in DB (raw SQL)
    - Checks if execution job is completed
    - Triggers log summary notification once execution is fully done
    """
    logger.info("Starting DB Consumer Worker subprocess...")
    
    try:
        db_conn = get_db_connection()
        mq_conn = get_rabbitmq_connection()
    except Exception as e:
        logger.critical(f"DB Consumer Worker failed to connect to resources: {e}")
        time.sleep(5)
        sys.exit(1)

    channel = mq_conn.channel()
    channel.queue_declare(queue=settings.QUEUE_ORDER_UPDATES, durable=True)
    
    def callback(ch, method, properties, body):
        try:
            payload = json.loads(body)
            order_id = payload["order_id"]
            exec_id = payload["portfolio_execution_id"]
            status = payload["status"]
            broker_order_id = payload["broker_order_id"]
            error_message = payload["error_message"]
            
            logger.info(f"Received update for order {order_id}: {status}")
            
            now = datetime.utcnow()
            
            # Start Database transaction
            with db_conn.cursor() as cursor:
                # 1. Update orders table
                cursor.execute(
                    """
                    UPDATE orders 
                    SET status = %s, broker_order_id = %s, error_message = %s, updated_at = %s 
                    WHERE id = %s;
                    """,
                    (status, broker_order_id, error_message, now, order_id)
                )
                
                # 2. Increment completed count in portfolio_executions table
                cursor.execute(
                    """
                    UPDATE portfolio_executions 
                    SET completed_orders = completed_orders + 1, updated_at = %s 
                    WHERE id = %s;
                    """,
                    (now, exec_id)
                )
                
                # 3. Check if all trades for this execution job are complete
                cursor.execute(
                    """
                    SELECT count(id) 
                    FROM orders 
                    WHERE portfolio_execution_id = %s AND status NOT IN ('EXECUTED', 'FAILED', 'REJECTED');
                    """,
                    (exec_id,)
                )
                remaining_count_row = cursor.fetchone()
                remaining_count = remaining_count_row["count"] if remaining_count_row else 0
                
                # 4. If remaining_count is 0, the job is completed
                if remaining_count == 0:
                    logger.info(f"All orders for execution {exec_id} completed. Compiling final status report...")
                    
                    # Fetch execution record using raw SQL (explicit columns)
                    cursor.execute(
                        """
                        SELECT id, portfolio_id, total_orders, completed_orders, status, created_at, updated_at 
                        FROM portfolio_executions 
                        WHERE id = %s;
                        """,
                        (exec_id,)
                    )
                    job = cursor.fetchone()
                    
                    # Fetch all child orders for detailed logging (explicit columns)
                    cursor.execute(
                        """
                        SELECT id, ticker, action, quantity, status, error_message, broker_order_id, created_at, updated_at 
                        FROM orders 
                        WHERE portfolio_execution_id = %s;
                        """,
                        (exec_id,)
                    )
                    job_orders = cursor.fetchall()
                    
                    # Evaluate overall execution status
                    success_orders = [o for o in job_orders if o["status"] == "EXECUTED"]
                    
                    if len(success_orders) == len(job_orders):
                        final_status = "COMPLETED"
                    elif len(success_orders) > 0:
                        final_status = "PARTIALLY_COMPLETED"
                    else:
                        final_status = "FAILED"
                        
                    # Update portfolio execution status
                    cursor.execute(
                        """
                        UPDATE portfolio_executions 
                        SET status = %s, updated_at = %s 
                        WHERE id = %s;
                        """,
                        (final_status, now, exec_id)
                    )
                    
                    # Commit transaction before triggering notification
                    db_conn.commit()
                    
                    # Trigger notification (console log block)
                    trigger_execution_notification(
                        execution_id=exec_id,
                        portfolio_id=job["portfolio_id"],
                        total_orders=job["total_orders"],
                        orders=job_orders
                    )
                else:
                    db_conn.commit()
                    logger.info(f"Job {exec_id} execution in progress. Remaining orders: {remaining_count}")
                    
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as err:
            logger.error(f"Error processing order status update: {err}")
            db_conn.rollback()
            ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=settings.QUEUE_ORDER_UPDATES, on_message_callback=callback)
    
    logger.info("DB Consumer Worker waiting for order updates...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        db_conn.close()
        mq_conn.close()


def uuid_generator():
    """Helper to generate string UUIDs."""
    import uuid
    return str(uuid.uuid4())


def main():
    """
    Main manager orchestration.
    Spawns and monitors the three subprocesses.
    """
    logger.info("Initializing Order Manager Multiprocessing Daemon...")
    
    # Wait for Database schema to be initialized by API container
    try:
        wait_for_db(retries=15, delay=3)
    except Exception as e:
        logger.critical(f"Could not connect to database on startup: {e}")
        sys.exit(1)
        
    processes = []
    
    # Subprocess specifications
    worker_specs = [
        ("Ingest-Worker-Proc", run_execution_ingest_worker),
        ("Broker-Worker-Proc", run_broker_worker),
        ("DBConsumer-Worker-Proc", run_db_consumer_worker)
    ]
    
    # Spawn processes
    for name, target_fn in worker_specs:
        proc = multiprocessing.Process(name=name, target=target_fn)
        proc.daemon = True
        processes.append(proc)
        proc.start()
        logger.info(f"Spawned subprocess '{name}' with PID {proc.pid}")
        
    def graceful_shutdown(signum, frame):
        logger.info("Received termination signal. Shutting down subprocesses...")
        for p in processes:
            if p.is_alive():
                logger.info(f"Terminating subprocess '{p.name}' (PID: {p.pid})...")
                os.kill(p.pid, signal.SIGTERM)
        sys.exit(0)

    # Register shutdown signals
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    
    # Monitor subprocesses
    try:
        while True:
            time.sleep(5)
            for p in processes:
                if not p.is_alive():
                    logger.warning(f"Subprocess '{p.name}' (PID: {p.pid}) died! Restarting...")
                    # Re-instantiate and restart
                    target_fn = next(fn for name, fn in worker_specs if name == p.name)
                    new_proc = multiprocessing.Process(name=p.name, target=target_fn)
                    new_proc.daemon = True
                    processes.remove(p)
                    processes.append(new_proc)
                    new_proc.start()
                    logger.info(f"Restarted subprocess '{new_proc.name}' with new PID {new_proc.pid}")
    except KeyboardInterrupt:
        graceful_shutdown(None, None)


if __name__ == "__main__":
    main()
