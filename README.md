# GateForge 🛡️

> High-Throughput API Key Lifecycle Manager, Sub-Millisecond Gateway Auth & Distributed Sliding-Window Rate Limiter.

GateForge is a production-engineered backend system built to solve the key lifecycle, sub-millisecond edge authentication, and distributed rate limiting requirements of modern developer APIs (modeled after architecture patterns from Stripe, Cloudflare, and AWS API Gateway).

---

## ⚡ Core Architecture & Engineering Highlights

- **Cryptographic Key Lifecycle:** Prefixed (`gfg_live_...`), SHA-256 deterministically hashed tokens with masked prefix/suffix storage and zero plaintext secret exposure.
- **Sub-Millisecond Edge Authentication:** Read-through Redis caching with stampede prevention and event-driven cache invalidation on key revocation.
- **Atomic Sliding-Window Rate Limiter:** Zero-race-condition rate limiting powered by atomic Redis Lua scripts evaluating rolling sliding-window logs with full RFC 6585 compliance (`X-RateLimit-*`, `Retry-After`).
- **Asynchronous Telemetry & Analytics:** Non-blocking fire-and-forget usage logging with periodic rollups for developer dashboards.
- **Engineered for Concurrency:** Strict async SQLAlchemy 2.0 connection pooling, Redis connection multiplexing, and robust error handling.

---

## 🛠️ Technology Stack

- **Core Framework:** Python 3.12, FastAPI, Pydantic v2, Pydantic-Settings
- **Database & ORM:** PostgreSQL 15, SQLAlchemy 2.0 (AsyncIO), Asyncpg, Alembic
- **Caching & Rate Limiting:** Redis 7 (Alpine), Redis Lua scripts, Hiredis parser
- **Telemetry & Logging:** Structlog (structured JSON with Correlation IDs)
- **Quality Assurance & Testing:** Pytest, Pytest-Asyncio, Ruff, Mypy (strict), Locust (load testing)

---

## 📁 Repository Structure

```text
├── AGENTS.md                 # Agent governance & CLI protocol
├── DESIGN.md                 # Technical RFC & architectural specification
├── docker-compose.yml        # PostgreSQL 15 & Redis 7 services
├── pyproject.toml            # Dependencies and tool configurations
├── .env.example              # Environment variables template
├── src/
│   └── gateforge/
│       ├── core/             # Config, logging, security, database session
│       ├── models/           # SQLAlchemy 2.0 declarative models
│       ├── schemas/          # Pydantic validation & transfer schemas
│       ├── services/         # Key lifecycle, cache, and limiter services
│       ├── api/              # FastAPI routers, middleware, and dependencies
│       └── main.py           # Application factory and lifespan handler
├── tests/                    # Pytest test suite (unit, integration, concurrency)
└── docs/                     # Interview defense briefs and architecture guides
```

---

## 🚀 Quickstart (Development)

```bash
# 1. Clone & create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows PowerShell: .venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Spin up PostgreSQL & Redis
docker compose up -d

# 4. Run tests & static analysis
pytest
ruff check .
mypy src
```
