import time
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from commons.config import settings

logger = logging.getLogger(__name__)

def get_db_connection():
    """
    Establishes and returns a new raw connection to the Postgres database.
    Each process must call this individually to avoid connection sharing issues.
    """
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        cursor_factory=RealDictCursor
    )

def wait_for_db(retries=10, delay=2):
    """
    Attempts to connect to the database, waiting and retrying if it's not ready.
    """
    for i in range(retries):
        try:
            conn = get_db_connection()
            conn.close()
            logger.info("Successfully connected to the database.")
            return True
        except psycopg2.OperationalError as e:
            logger.warning(f"Database not ready yet (attempt {i+1}/{retries}): {e}")
            time.sleep(delay)
    raise RuntimeError("Could not connect to the database after several retries.")

def init_db():
    """
    Initializes the database schema using raw SQL.
    Ensures that all tables exist.
    """
    wait_for_db()
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Create portfolios table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    id UUID PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    broker VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                );
            """)
            
            # Create portfolio_executions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_executions (
                    id UUID PRIMARY KEY,
                    portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                    status VARCHAR(50) NOT NULL,
                    total_orders INTEGER NOT NULL,
                    completed_orders INTEGER DEFAULT 0,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                );
            """)
            
            # Create orders table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id UUID PRIMARY KEY,
                    portfolio_execution_id UUID NOT NULL REFERENCES portfolio_executions(id) ON DELETE CASCADE,
                    ticker VARCHAR(50) NOT NULL,
                    action VARCHAR(10) NOT NULL,
                    quantity INTEGER NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    error_message TEXT,
                    broker_order_id VARCHAR(255),
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                );
            """)
            conn.commit()
            logger.info("Database schema initialized successfully.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to initialize database: {e}")
        raise e
    finally:
        conn.close()
