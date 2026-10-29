# GateForge: High-Throughput API Key Gateway & Sliding-Window Rate Limiter

[![CI/CD Pipeline](https://github.com/AmanYdv77/GateForge/actions/workflows/ci.yml/badge.svg)](https://github.com/AmanYdv77/GateForge/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Redis](https://img.shields.io/badge/Redis-7.0+-DC382D.svg)](https://redis.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg)](https://www.postgresql.org)
[![Prometheus](https://img.shields.io/badge/Prometheus-Metrics-E6522C.svg)](https://prometheus.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

GateForge is a distributed, production-grade API key lifecycle manager, edge authentication gateway, sliding-window rate limiter, and async telemetry engine designed for low-latency, mission-critical infrastructure.

---

## Key Highlights

- **Sub-Millisecond Edge Authentication:** Two-tier architecture with Redis edge cache (<1ms lookup) backed by PostgreSQL async read-through fallback.
- **Zero Plaintext Secret Storage:** API keys are generated with high-entropy cryptographic randomness (`gfg_live_...`), hashed via SHA-256 for storage, and never persisted in plaintext.
- **Atomic Sliding-Window Rate Limiting:** Enforces quotas with millisecond precision via an atomic Redis Lua script, eliminating burst-at-boundary vulnerabilities. Returns RFC 6585 headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`).
- **Enterprise IP & CIDR Allowlisting:** Restrict API keys to specific corporate CIDRs (`192.168.1.0/24`) or static IP addresses with proxy chain extraction.
- **Asynchronous Telemetry Engine:** Non-blocking in-memory queue drains request metrics into PostgreSQL batches without impacting request latency.
- **Full Observability:** Live `/metrics` endpoint with Prometheus collectors for request throughput, sub-millisecond duration histograms, and cache hit/miss rates.
- **Resilience & Failover:** Circuit breaker pattern preventing cascading outages on Redis or Database degradation.

---

## Architecture Overview

```
Client Request ---> [ GateForge Gateway ]
                           |
            +--------------+--------------+
            |                             |
      (Tier 1 Cache)                (Tier 2 DB)
     Redis Edge RAM            PostgreSQL Storage
      [ < 1ms Latency ]         [ SHA-256 Hash ]
            |                             |
            +--------------+--------------+
                           |
               [ IP & CIDR Filter ]
                           |
            [ Redis Lua Rate Limiter ]
                           |
             [ Non-Blocking Telemetry ]
                           |
                     Downstream API
```

---

## Quickstart with Docker Compose

Spin up the entire GateForge stack (Gateway, PostgreSQL 15, Redis 7, Prometheus) with a single command:

```bash
# Clone the repository
git clone https://github.com/AmanYdv77/GateForge.git
cd GateForge

# Copy environment configuration
cp .env.example .env

# Launch services
docker compose up -d --build
```

Verify service health:
```bash
curl -i http://localhost:8000/health/live
# HTTP/1.1 200 OK
# {"status":"alive","version":"0.1.0"}
```

Access Prometheus metrics:
```bash
curl -i http://localhost:8000/metrics
```

---

## Administrative CLI Utility

GateForge includes a built-in CLI for administrative operations:

```bash
# Create a new key with IP allowlisting and custom rate limits
python -m gateforge.cli create-key \
  --name "Analytics Production Client" \
  --user-id "00000000-0000-0000-0000-000000000001" \
  --scopes "read:analytics,read:reports" \
  --allowed-ips "192.168.1.0/24,10.0.0.1" \
  --rate-limit 120

# Revoke a key instantly and purge edge cache
python -m gateforge.cli revoke-key --key-id "<KEY_UUID>"

# Check database and Redis cache connectivity
python -m gateforge.cli status
```

---

## Running Tests & Static Analysis

```bash
# Run complete test suite (130+ unit & integration tests)
pytest -v

# Run static type checking with strict Mypy
mypy src

# Run fast code formatting & linting with Ruff
ruff check .
```

---

## Benchmark & Load Testing

Run Locust load tests simulating thousands of concurrent requests:

```bash
locust -f benchmarks/locustfile.py --headless -u 100 -r 10 --run-time 1m --host http://localhost:8000
```

---

## Documentation

- [System Architecture & Sequence Diagrams](docs/architecture.md)
- [Security Threat Model & Cryptographic Guarantees](docs/security.md)
