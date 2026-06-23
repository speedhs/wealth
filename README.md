# Wealth - Trade Execution Platform

A distributed, microservices-based platform for executing portfolio trades across multiple brokers in real-time. Built with **FastAPI**, **PostgreSQL**, **RabbitMQ**, and containerized **multiprocessing workers**.

## Key Features

- **Unified Portfolio Execution**: Submit trade requests via REST API with automatic multi-order sequencing
- **Multi-Broker Support**: Zerodha, Fyers, Angel One, Groww, Upstox (extensible factory pattern)
- **Decoupled Architecture**: RabbitMQ-based event streaming with three-tier worker topology
- **Real-Time Dashboard**: SPA frontend with live execution tracking and order management
- **Production-Ready**: Raw SQL (no ORM), parameterized queries, comprehensive error handling

## Directory Structure

```
wealth/
├── api-service/              # REST API & Portfolio Management
│   ├── app/
│   │   ├── api/             # Routes and schemas
│   │   └── rms/             # Risk Management System
│   ├── Dockerfile
│   └── requirements.txt
├── order-manager/            # Async Order Processing
│   ├── app/
│   │   ├── brokers/         # Broker adapters (Zerodha, Fyers, etc.)
│   │   ├── notifications/
│   │   └── workers/         # Ingest, Broker, DB Consumer
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                # Web UI (Kalpi Dashboard)
│   ├── index.html
│   ├── app.js
│   └── style.css
├── commons/                 # Shared configuration & utilities
│   ├── config.py
│   ├── db.py
│   └── queue.py
├── db/                      # Database schemas
├── rabbitmq/               # Message broker config
├── .dockerignore
├── .env.example
├── docker-compose.yml
└── README.md
```

## System Architecture

```
┌─────────────────────────────┐
│  Frontend Dashboard (SPA)   │
└──────────────┬──────────────┘
               │ REST API
               ↓
      ┌────────────────────┐
      │   API Service      │ ←→ PostgreSQL
      │   (FastAPI)        │
      │   + RMS Validator  │
      └────────┬───────────┘
               │ RabbitMQ
               ↓
┌──────────────────────────────────────────────┐
│   Order Manager (Multiprocessing Daemon)     │
├──────────────────────────────────────────────┤
│ Worker 1: Ingest                             │
│  • Consume execution requests                │
│  • Create DB records for orders              │
│  • Publish to broker queue                   │
├──────────────────────────────────────────────┤
│ Worker 2: Broker                             │
│  • Select & authenticate broker adapter      │
│  • Execute trade via broker API              │
│  • Publish execution result                  │
├──────────────────────────────────────────────┤
│ Worker 3: Persist & Notify                   │
│  • Update order status in DB                 │
│  • Track execution completion                │
│  • Trigger notifications                     │
└──────────────────────────────────────────────┘
```

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Python 3.9+ (for local development)
- PostgreSQL & RabbitMQ (handled by docker-compose)

### Production Setup

1. **Clone & Configure**:
   ```bash
   git clone <repo>
   cd wealth
   cp .env.example .env
   # Edit .env with production credentials
   ```

2. **Start Services**:
   ```bash
   docker-compose up -d
   ```

3. **Access Dashboard**:
   Open `http://localhost:8000/` in your browser

### Environment Variables

See `.env.example` for all available settings:
- **Database**: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- **RabbitMQ**: `RABBITMQ_HOST`, `RABBITMQ_PORT`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`
- **API**: `API_SERVICE_PORT`, `API_SERVICE_DEBUG`
- **Broker Credentials**: Per-broker API keys and access tokens

## API Endpoints

### Portfolio Execution

- `POST /api/portfolio/execute` - Submit execution request
  ```json
  {
    "portfolio_id": "uuid",
    "broker": "zerodha",
    "action_type": "FIRST_TIME",
    "trades": [
      {"ticker": "RELIANCE", "quantity": 15}
    ]
  }
  ```

- `GET /api/portfolio/execution/{id}` - Fetch execution status
- `GET /api/portfolio/executions` - List execution history
- `GET /api/portfolio/{id}/holdings` - Get current holdings

## Broker Support

Extensible adapter pattern in `order-manager/app/brokers/`:

- **Zerodha**: Full integration with OAuth & order placement
- **Fyers**: REST API adapter with session management
- **Angel One**: Proprietary API wrapper
- **Groww**: Broker API adapter
- **Upstox**: OAuth-based order execution
- **Mock**: Simulated broker for testing

To add a new broker: extend `BaseAdapter` in `base.py` and register in `factory.py`.

## Database

PostgreSQL schema with three core tables:

- **`portfolios`**: Client portfolio accounts & broker mappings
- **`portfolio_executions`**: Execution job tracking (status, completion counts)
- **`orders`**: Individual trades linked to execution jobs

Raw SQL queries ensure strict parameterization and explicit column selection for security & performance.

## Development

### Local Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies (per service)
cd api-service && pip install -r requirements.txt
cd ../order-manager && pip install -r requirements.txt

# Start supporting services only
docker-compose up db rabbitmq

# Run services locally
# In separate terminals:
python -m api-service.app.api.main
python -m order-manager.app.workers.order_manager
```

### Project Conventions

- Each service folder contains only its relevant code
- `commons/` for shared utilities (config, DB, queue connections)
- Dockerfiles at service root enable independent deployments
- `.dockerignore` excludes dev files from images

## Monitoring

- **API Logs**: FastAPI/Uvicorn → stdout
- **Worker Logs**: Multiprocessing with process names → stdout
- **RabbitMQ UI**: `http://localhost:15672` (default: guest/guest)
- **Frontend Console**: Browser DevTools for client-side errors

## Production Checklist

- [ ] Configure `.env` with prod credentials
- [ ] Set `API_SERVICE_DEBUG=false`
- [ ] Update broker API keys & secrets
- [ ] Configure database backups
- [ ] Set up log aggregation (ELK, Datadog, etc.)
- [ ] Enable SSL/TLS for API endpoints
- [ ] Configure monitoring & alerting
- [ ] Test failover & disaster recovery
- [ ] Load test with production data volumes

## License

Proprietary — Internal use only.
