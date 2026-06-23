# Kalpi Portfolio Trade Execution Engine

An end-to-end, high-performance, asynchronous Portfolio Trade Execution Engine built using **FastAPI**, **Postgres (Raw SQL)**, and **RabbitMQ** with a containerized **multiprocessing worker architecture**.

---

## 🚀 Key Features

* **Single-Click Execution**: Input desired portfolios (or rebalance steps) and trigger multi-order broker submission instantly.
* **5 Broker Adapters**: Unified Adapter Factory structure supporting Zerodha, Fyers, AngelOne, Groww, Upstox, and an active simulated **Mock Broker**.
* **Decoupled Architecture**: Fast API layer handles validation and Risk Management System (RMS) checks, handshaking execution to RabbitMQ queues.
* **Multiprocessing Order Manager Daemon**: Spawns three persistent, isolated subprocesses for execution ingestion, broker API interactions (with simulated latency & errors), and asynchronous DB updates/notifications.
* **Raw SQL Execution**: Stays clear of ORMs, utilizing direct Postgres parameters, and avoids `SELECT *` commands for strict security and performance.
* **Visual Dashboard (Bonus)**: Beautiful glassmorphic dashboard to track executions in real-time, view order statuses, and review execution histories.

---

## 🛠 System Architecture

```
                                  [ Frontend Dashboard ]
                                             |
                                  (1) Submit Trades (REST API)
                                             v
                                  [  FastAPI API Server ] <------> [ Postgres DB ]
                                             |
                             (2) Enqueue Ingest Job (RabbitMQ)
                                             v
      ┌───────────────────────────── [ Order Manager Daemon ] ─────────────────────────────┐
      │                                                                                   │
      │   [ Subprocess 1: Ingest Worker ]                                                 │
      │     - Consumes from portfolio_execution_requests queue                            │
      │     - Inserts PENDING execution job & child orders into DB                        │
      │     - Enqueues individual orders to broker_trades queue                           │
      │                                                                                   │
      │                                       |                                           │
      │                                       v (Message Queue)                           │
      │                                                                                   │
      │   [ Subprocess 2: Broker Worker ]                                                 │
      │     - Consumes from broker_trades queue                                           │
      │     - Selects adapter (Zerodha, Fyers, Mock, etc.) and authenticates              │
      │     - Places trade order with broker API (simulates latency & failures)           │
      │     - Enqueues status update to order_updates queue                               │
      │                                                                                   │
      │                                       |                                           │
      │                                       v (Message Queue)                           │
      │                                                                                   │
      │   [ Subprocess 3: DB & Notification Worker ]                                      │
      │     - Consumes from order_updates queue                                           │
      │     - Updates order & job completion counts in Postgres (Raw SQL)                 │
      │     - Triggers log summary report when all orders for a job complete              │
      │                                                                                   │
      └───────────────────────────────────────────────────────────────────────────────────┘
```

### Decoupling & Queue Strategy
* **`portfolio_execution_requests`**: Decouples API client responses from database inserts. Returning a `202 Accepted` keeps ingestion times under **15ms**.
* **`broker_trades`**: Decouples DB operations from network-bound broker APIs. The Broker Worker executes orders independently, preventing rate limit errors from choking queue operations.
* **`order_updates`**: Decouples broker execution completion from DB state operations. This protects against locks or slowdowns on Postgres.

---

## 📊 Database Schema

We define three key tables using raw SQL:
1. **`portfolios`**: Holds client portfolio accounts and their target broker tags.
2. **`portfolio_executions`**: Tracks the status of execution jobs (e.g. `PROCESSING`, `COMPLETED`, `FAILED`, `PARTIALLY_COMPLETED`).
3. **`orders`**: Individual trades (e.g. `BUY`, `SELL`) tied to a parent execution job.

---

## ⚡ How the Rebalancing Logic Works

1. **API Ingest & Conversion**:
   * The single API endpoint `/api/portfolio/execute` accepts requests in the following format:
     * **First-Time**: Creates `BUY` orders for all stocks in the target portfolio.
     * **Rebalancing**: Supports `BUY`, `SELL`, and `REBALANCE` actions. If a trade action is set to `REBALANCE`, the quantity field supports signed integers (e.g., `+15` or `-5`).
   * The **RMS Validator** translates:
     * `REBALANCE` with `quantity: 15` -> `BUY` order of `15`.
     * `REBALANCE` with `quantity: -5` -> `SELL` order of `5`.
2. **RMS / Validation Engine**:
   * **Holdings Delta Check (No-Trade Recognition)**:
     * Derives the current portfolio holdings by aggregating all successfully executed (`EXECUTED`) orders in the database for the given portfolio UUID (`BUY` increases holdings, `SELL` decreases holdings).
     * Calculates the delta between the desired target portfolio state and these current holdings.
     * If the current holdings already match the desired state exactly (meaning zero trade delta is resolved), the engine skips placing any orders to RabbitMQ, immediately saves a completed execution record in Postgres with `total_orders = 0`, and returns a `200 OK` response with status `COMPLETED` and message `"Portfolio is already in the desired state. No trades executed."`
   * **Duplicate execution guard**: Checks if a portfolio has a job in status `PENDING` or `PROCESSING` in the database. If so, it blocks the request.
   * **Limit constraints**: Rejects orders exceeding `100,000` shares.
   * **Restricted list**: Blocks orders for tickers in blacklisted lists (`RESTRICTED_TICKERS`).
3. **Worker Lifecycle**:
   * If a trade delta is resolved, the Ingest subprocess pushes the orders to the Broker queue. The Broker worker runs them against the designated adapter. Once all sub-orders reach a terminal status (`EXECUTED` or `FAILED`), the DB consumer marks the parent execution job as finished and triggers a console log summary containing successful and failed trades.

---

## 🔧 Installation & Run Instructions

Ensure you have **Docker** and **Docker Compose** installed.

### 1. Spin up the containers
From the project root directory, run:
```bash
docker-compose up --build
```
This builds and starts the following services:
* **`db`** (Postgres 15) on port `5432`
* **`rabbitmq`** (RabbitMQ with Management plugin) on port `5672` (Console: `http://localhost:15672` - guest/guest)
* **`api-service`** (FastAPI) on port `8000`
* **`order-manager`** (Multiprocessing Daemon) running in the background.

### 2. Access the Visual Dashboard
Open your web browser and navigate to:
```
http://localhost:8000/
```
From here you can:
1. Load a sample first-time portfolio or rebalance basket (with signed quantities).
2. Connect simulated mock or Indian brokers.
3. Click **Execute** and watch the live progress bar, trade badges, and log updates as they execute asynchronously.

---

## 📚 Justification for Libraries Used

1. **FastAPI**: Extremely fast asynchronous ASGI framework, standard for high-performance Python microservices. Auto-generates Swagger/OpenAPI documentation.
2. **Pika**: Standard, reliable AMQP 0-9-1 client library for Python to connect and stream messages with RabbitMQ.
3. **Psycopg2-Binary**: The most robust PostgreSQL database adapter for Python, essential for executing raw SQL queries securely.
4. **Pydantic & Pydantic-Settings**: For parsing and validating inputs, and loading configurations dynamically from `.env` variables.
