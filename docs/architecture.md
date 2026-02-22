# Architecture Document

## System Overview

Production-grade telemedicine backend handling 100,000 daily consultations with 99.95% availability.

**Tech Stack:**
- FastAPI (async I/O, auto-docs)
- PostgreSQL 16 (ACID, row locks)
- Redis 7 (cache, sessions)
- Docker (containerization)
- Prometheus + Grafana (monitoring)

## High-Level Architecture
```
Client → Load Balancer → FastAPI → Business Logic → Database/Cache
```

**Components:**
- **API Layer:** FastAPI with Uvicorn workers
- **Auth:** JWT + refresh tokens + MFA (TOTP)
- **RBAC:** Patient/Doctor/Admin roles
- **Database:** PostgreSQL with connection pooling (20+40)
- **Cache:** Redis for sessions and rate limiting
- **Queue:** Celery for background tasks
- **Monitoring:** Prometheus metrics + Grafana dashboards

## Database Schema

**Core Tables:**
- `users` → `user_profiles` (1:1)
- `users` → `doctors` (1:1)
- `doctors` → `availability_slots` (1:N)
- `availability_slots` → `consultations` (1:1)
- `consultations` → `prescriptions` (1:1)
- `consultations` → `payments` (1:1)

**Key Features:**
- UUID primary keys (security)
- Unique constraints on `idempotency_key` (retry safety)
- JSONB columns (flexible medical data)
- Indexes on foreign keys and filters

## Critical Flow: Booking

**Prevents Double-Booking:**

1. Client sends booking with `idempotency_key`
2. Check if key exists → return existing if yes
3. Lock slot row: `SELECT FOR UPDATE`
4. Verify slot is available
5. In single transaction:
   - Mark slot as booked
   - Create consultation
   - Create payment record
6. Commit transaction

**Race Condition Handled:** Row lock ensures only one request succeeds. Others wait in queue and get 409 Conflict when they see slot is booked.

## Scalability

**Current:** 1.2 req/sec average, 6 req/sec peak → Single instance sufficient

**Future Scaling:**
- Horizontal: N instances behind load balancer
- Database: Read replicas + table partitioning
- Cache: Redis for hot data (60% DB load reduction)
- Async: Celery workers for emails/reports

## Reliability (99.95% Uptime)

- Health checks every 10s
- Auto-restart on failure
- Graceful shutdown (wait 30s for in-flight requests)
- Backups: Daily full, 6-hour incremental, continuous WAL

## Security

- OWASP Top 10 compliant
- bcrypt password hashing (cost 12)
- JWT with 30-min expiry + rotation
- MFA via TOTP
- Account lockout after 5 failed attempts
- All writes logged to audit_logs

## Observability

- Prometheus: Request rate, latency, errors
- Grafana: System health + business metrics dashboards
- Structured JSON logging
- Audit trail for compliance